# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

FactoriOS is a joke Linux distribution whose sole purpose is to boot into Factorio. Treat the joke premise as a real design constraint: the system should do nothing else of note. Don't add general-purpose desktop features or "useful" extras — if it isn't in service of launching and running Factorio, it doesn't belong.

## Architecture

Three runtime layers, each in its own top-level directory:

- **`launcher/`** — pure Python library. All factorio.com interaction (api-login token auth, version download, archive extraction), and all on-disk layout knowledge (versions, profiles, the `last-user` pointer). No UI. Both the greeter and any future CLI tooling depend on it.
- **`greeter/`** — GTK4 Python app. The *only* user-facing surface on an installed system. Login screen → version/profile chooser → spawns Factorio as a child → returns to chooser on game exit. All HTTP runs on a worker thread; results posted back via `GLib.idle_add`.
- **`iso/` + `installer/`** — the install-time path. archiso profile boots a live env that autoruns the shell installer; the installer partitions, pacstraps Arch base + the `factorios-*` packages, and enables `factorios.service`.

Glue: `systemd/factorios.service` runs `/usr/bin/factorios-session` on tty1 as the `factorios` user (UID 1000). The wrapper logs the full session transcript to `/tmp/factorios-session.log` (env, `/dev/dri/` state, labwc `-d` debug, greeter stderr, Factorio stderr) and then exec's `labwc -d -s /usr/bin/factorios-greeter`. There is no display manager and no Unix-level login — factorio.com identity is the only identity.

## Identity model (load-bearing)

No local Linux user accounts are ever created. One shared system user runs sessions; per-user state is segregated by directory under `/var/lib/factorios/users/<factorio-username>/`. Authentication is purely against factorio.com. If you find yourself reaching for `useradd`, PAM, or per-user homes, stop — that's the wrong layer.

## Filesystem layout (installed system)

```
/var/lib/factorios/
  versions/
    <version>-<build>/             # build ∈ {vanilla, space-age}; shared
    _demo/                         # demo install; no build dimension
  users/<factorio-username>/
    profiles/<build>/<name>/mods/  # per-build, per-profile MOD directory
    factorio/                      # per-user ~/.factorio (saves, config,
                                   # player-data.json, achievements …)
    session.json                   # {"username": ..., "token": ...}
  users/_guest/
    profiles/<n>/mods/             # guest/demo profiles (flat — no build dim)
    factorio/                      # demo's ~/.factorio
  last-user                        # present iff Remember Me
```

`launcher/factorios_launcher/paths.py` is the single source of truth — don't hard-code these elsewhere. Build identifiers are `vanilla` / `space-age` user-facing; the factorio.com download API uses `alpha` / `expansion` — the mapping lives in `paths.BUILD_API` and the rest of the codebase never deals in alpha/expansion. Profiles are per-build because mod compatibility differs across the two; the guest/demo flow is flat (no build dim) because the demo is its own build.

**Two granularity levels:** per-user (everything in `~/.factorio`: saves, config, achievements, `player-data.json` with the service token) is segregated by symlinking `~/.factorio` at `users/<u>/factorio/` before launch. Per-profile (mods only) is segregated by passing `--mod-directory <profile>/mods` on the Factorio command line. `~/.factorio` is the only CLI flag we use (we tried `--write-data` and it isn't recognized by all Factorio builds; service-credential flags don't exist — `service-username`/`service-token` are JSON fields, not CLI args). `profiles._link_home_factorio()` migrates a pre-existing real `~/.factorio` into the current user's dir on first run; refuses if both exist.

Space Age ownership lives on `Session.has_space_age` (refreshed on every `login()` / `validate()` via a HEAD probe against the expansion download endpoint, never persisted). The chooser hides the Build selector when `has_space_age == False`.

User + dir ownership are declarative: `/usr/lib/sysusers.d/factorios.conf` creates the `factorios` user (UID 1000) with seat/video/input/render group memberships; `/usr/lib/tmpfiles.d/factorios.conf` enforces ownership of `/var/lib/factorios/{,versions,users}` on every boot. Don't put `useradd` or `chown` in `.install` hooks — it's the wrong layer and `useradd --groups` fails the whole user creation if any one group is missing.

## factorio.com auth flow

POST `https://auth.factorio.com/api-login` with form-encoded `username=&password=` → JSON response with `token` + `username` (response shape varies — list, flat, or `{"data": {...}, "status": 200}`; `_extract_token` handles all three). Downloads then go to `https://www.factorio.com/get-download/{version}/{build}/{distro}?username=&token=`. Implemented in `launcher/factorios_launcher/auth.py`.

**Do not** use `www.factorio.com/login` (the HTML form): it's behind Cloudflare's bot challenge (`cf-mitigated: challenge`) and returns 403 to every non-browser client regardless of User-Agent. `auth.factorio.com` is the API the Factorio binary itself uses and is ungated. The download endpoints on `www.factorio.com` are also fine (302 to `dl.factorio.com`).

## Build

`./build.sh [slim|full]` is the entry point. It (1) runs `makepkg` for the three PKGBUILDs in dependency order, (2) `repo-add`s the results into `iso/airootfs/var/cache/factorios-repo/`, and (3) execs `iso/build.sh "$@"`, which stages the installer script and runs `mkarchiso`. The repo dir is gitignored and recreated every run.

Two ISO variants share one profile: **slim** (default — no linux-firmware, ~370 MB) and **full** (adds linux-firmware, ~800 MB). `iso/build.sh` selects the variant via `$1`; for full it temporarily appends `linux-firmware` to `packages.x86_64` (cleanup via trap) and exports `FACTORIOS_VARIANT=full`, which `profiledef.sh` substitutes into `iso_name` so the outputs don't collide. CI builds slim every push and additionally builds full on tag pushes (`v*`), attaching both to the release.

airootfs uses squashfs+xz, not erofs. We tried erofs once for ~30 MB savings; the initrd couldn't mount the result. Squashfs is safe — don't switch back without verifying the mkinitcpio modules list explicitly includes `erofs`.

PKGBUILDs pull their source out of the monorepo via `$startdir/../../<dir>` in `prepare()` — no manual file shuffling, no tarballs. Don't add `source=()` URLs; keep the monorepo-relative pattern.

Two pacman.conf files exist on purpose: `iso/pacman.conf` is for the build host (no `[factorios]` repo — nothing factorios-* gets installed into the live env); `iso/airootfs/etc/pacman.conf` is the live env's config and *does* have the `[factorios]` `file:///var/cache/factorios-repo` entry that the installer's `pacstrap` inherits.

Python packages are flat and importable without install during dev: `PYTHONPATH=launcher python -m factorios_launcher releases`.

## Debugging an installed system

The kiosk session has no shell, so debugging means:

1. **Reach a tty.** `Right Ctrl + F2` in VirtualBox (host key + F2). Log in as `root` (passwordless — set by the installer for recovery).
2. **Read the session transcript.** `/tmp/factorios-session.log` has everything — env, `/dev/dri/` state, labwc `-d` output, greeter stderr, Factorio stderr. Truncated on every restart of `factorios.service`.
3. **Boot to a shell-only target.** At the systemd-boot menu (`timeout 3`), press `e`, append ` systemd.unit=multi-user.target`, Enter. `factorios.service` won't start and tty1 has a normal getty.
4. **Persistent journal.** Not on by default. `mkdir /var/log/journal && systemctl restart systemd-journald` to enable, then `journalctl -b -1 -u factorios.service` reads the previous boot's failure.

## VirtualBox quirks (load-bearing for testing)

The kiosk session runs on labwc/wlroots, which is finicky on VirtualBox's vmwgfx. The combination that actually works:

- VM Display → Graphics Controller: **VMSVGA**, Enable 3D Acceleration: **on**.
- `factorios.service` sets `WLR_NO_HARDWARE_CURSORS=1`, `WLR_DRM_NO_ATOMIC=1`, `WLR_RENDERER=pixman`, `LIBGL_ALWAYS_SOFTWARE=1`. Without these, labwc fails the linux-dmabuf path and dies before the greeter can present.
- Greeter does *not* call `Gtk.Window.fullscreen()` — that triggers a vmwgfx DRM hot-unplug ~13s in.
- `profiles.launch()` **strips** `LIBGL_ALWAYS_SOFTWARE` + `WLR_*` from Factorio's env via `_factorio_env()`. The greeter needs software GL to survive; Factorio needs the real GPU.
