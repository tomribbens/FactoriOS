# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

FactoriOS is a joke Linux distribution whose sole purpose is to boot into Factorio. Treat the joke premise as a real design constraint: the system should do nothing else of note. Don't add general-purpose desktop features or "useful" extras — if it isn't in service of launching and running Factorio, it doesn't belong.

## Architecture

Three runtime layers, each in its own top-level directory:

- **`launcher/`** — pure Python library. All factorio.com interaction (CSRF-scraped session login, version download, archive extraction), and all on-disk layout knowledge (versions, profiles, the `last-user` pointer). No UI. Both the greeter and any future CLI tooling depend on it.
- **`greeter/`** — GTK4 Python app. The *only* user-facing surface on an installed system. Login screen → version/profile chooser → spawns Factorio as a child → returns to chooser on game exit. All HTTP runs on a worker thread; results posted back via `GLib.idle_add`.
- **`iso/` + `installer/`** — the install-time path. archiso profile boots a live env that autoruns the shell installer; the installer partitions, pacstraps Arch base + the `factorios-*` packages, and enables `factorios.service`.

Glue: `systemd/factorios.service` runs `labwc` on tty1 as the `factorios` system user, and labwc execs the greeter (`labwc -s /usr/bin/factorios-greeter`). There is no display manager and no Unix-level login — factorio.com identity is the only identity.

## Identity model (load-bearing)

No local Linux user accounts are ever created. One shared system user runs sessions; per-user state is segregated by directory under `/var/lib/factorios/users/<factorio-username>/`. Authentication is purely against factorio.com. If you find yourself reaching for `useradd`, PAM, or per-user homes, stop — that's the wrong layer.

## Filesystem layout (installed system)

```
/var/lib/factorios/
  versions/
    <version>-<build>/        # build ∈ {vanilla, space-age}; shared system-wide
    _demo/                    # demo install; no build dimension
  users/<factorio-username>/
    profiles/<build>/<name>/  # per-build profiles
    session.json
  users/_guest/profiles/<n>/  # guest/demo profiles (flat — no build dim)
  last-user                   # present iff Remember Me
```

`launcher/factorios_launcher/paths.py` is the single source of truth — don't hard-code these elsewhere. Build identifiers are `vanilla` / `space-age` user-facing; the factorio.com download API uses `alpha` / `expansion` — the mapping lives in `paths.BUILD_API` and the rest of the codebase never deals in alpha/expansion. Profiles are per-build because mod compatibility differs across the two; the guest/demo flow is flat (no build dim) because the demo is its own build.

Space Age ownership lives on `Session.has_space_age` (refreshed on every `login()` / `validate()` via a HEAD probe against the expansion download endpoint, never persisted). The chooser hides the Build selector when `has_space_age == False`.

## factorio.com auth flow

GET `https://www.factorio.com/login` → scrape `input[name=csrf_token]` → POST `csrf_token` + `username_or_email` + `password` → reuse the resulting session cookie for `https://www.factorio.com/get-download/{version}/{build}/{distro}`. Implemented in `launcher/factorios_launcher/auth.py`.

## Build

`./build.sh [slim|full]` is the entry point. It (1) runs `makepkg` for the three PKGBUILDs in dependency order, (2) `repo-add`s the results into `iso/airootfs/var/cache/factorios-repo/`, and (3) execs `iso/build.sh "$@"`, which stages the installer script and runs `mkarchiso`. The repo dir is gitignored and recreated every run.

Two ISO variants share one profile: **slim** (default — no linux-firmware, ~150 MB) and **full** (adds linux-firmware, ~800 MB). `iso/build.sh` selects the variant via `$1`; for full it temporarily appends `linux-firmware` to `packages.x86_64` (cleanup via trap) and exports `FACTORIOS_VARIANT=full`, which `profiledef.sh` substitutes into `iso_name` so the outputs don't collide. CI builds slim every push and additionally builds full on tag pushes (`v*`), attaching both to the release.

PKGBUILDs pull their source out of the monorepo via `$startdir/../../<dir>` in `prepare()` — no manual file shuffling, no tarballs. Don't add `source=()` URLs; keep the monorepo-relative pattern.

Two pacman.conf files exist on purpose: `iso/pacman.conf` is for the build host (no `[factorios]` repo — nothing factorios-* gets installed into the live env); `iso/airootfs/etc/pacman.conf` is the live env's config and *does* have the `[factorios]` `file:///var/cache/factorios-repo` entry that the installer's `pacstrap` inherits.

Python packages are flat and importable without install during dev: `PYTHONPATH=launcher python -m factorios_launcher releases`.
