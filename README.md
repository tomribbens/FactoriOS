# FactoriOS

A joke Linux distribution whose only purpose is playing Factorio.

Boot → GUI login with your factorio.com credentials → pick a Factorio version and a profile → play. There is nothing else.

## Status

Early scaffolding. Working pieces:

- Launcher library — factorio.com auth (CSRF + session), version download/install, profile management.
- GTK4 greeter — login + version/profile chooser, opt-in Remember Me.
- archiso profile — boots into the installer.
- Shell installer — partitions disk and installs the system.

## Layout

```
build.sh     top-level orchestrator: builds packages, stages the local repo, builds the ISO
iso/         archiso profile that produces the installer ISO
installer/   shell script that runs in the live env to install onto disk
launcher/    Python library: factorio.com auth, downloads, version/profile management
greeter/     GTK4 Python app: login screen + version/profile chooser
packages/    PKGBUILDs for launcher, greeter, and a factorios-base meta-package
systemd/     factorios.service + supporting config
```

## Build

```
./build.sh           # slim ISO (~150 MB). Default. Works in VMs and on
                     # bare metal with ethernet + Intel/AMD GPUs.
./build.sh full      # full ISO (~800 MB) — same plus linux-firmware for
                     # WiFi and modern AMD/NVidia firmware needs.
```

Both write to `iso/out/`. Requires `archiso`, `pacman`, `base-devel`, `erofs-utils` on the build host. Run as a regular user with sudo access — `makepkg` runs as you, `mkarchiso` runs under sudo from inside the scripts.

CI also builds the ISO(s): see `.github/workflows/build-iso.yml`. Every push to `main` produces a slim ISO as a downloadable artifact and publishes the `[factorios]` pacman repo to GitHub Pages. Tag pushes (`v*`) additionally build the full ISO and attach **both** to the GitHub Release.

## Updates

Installed FactoriOS systems can `pacman -Syu` to upgrade Arch + our packages together. The `[factorios]` repo at <https://tomribbens.github.io/FactoriOS/x86_64/> is wired into `/etc/pacman.conf` by the installer; the greeter has an *Updates…* button (footer of the chooser) that calls `pacman -Sy` + lists upgrades + runs `pacman --noconfirm -Syu`, all via a narrow `sudoers.d` rule that allows the kiosk user *only* those two exact invocations.

**One-time setup** (repo owner only): the first CI run after enabling Pages distribution needs `Settings → Pages → Source: GitHub Actions` ticked. Without it the `pages` job fails — fix is the same one click.

## Identity model

There are no local Linux user accounts. A single system user (`factorios`) runs all sessions. Per-user data lives under `/var/lib/factorios/users/<factorio-username>/`, segregated by directory only. Authentication is against factorio.com.

## Filesystem layout on an installed system

```
/var/lib/factorios/
  versions/
    <version>-vanilla/           # base game install
    <version>-space-age/         # Space Age DLC install
    _demo/                       # demo install (no build dimension)
  users/<factorio-username>/
    profiles/
      vanilla/<profile-name>/    # full Factorio write-data dir per
      space-age/<profile-name>/  # profile — saves, mods, config, achievements,
                                 # player-data, scenarios …
    session.json                 # cached factorio.com session cookies
    last-launch.json             # remembered (build, version, profile)
  users/_guest/profiles/<name>/  # guest/demo profiles (flat — no build dim)
  last-user                      # only present when Remember Me was checked
```

A profile is a complete Factorio write-data dir — switching profiles re-symlinks `~/.factorio` at the chosen one, so each profile gets its own saves, mods, config, achievements, and player-data. Profiles are per-build because mod compatibility differs across Vanilla and Space Age. Space Age ownership is detected at login time via a HEAD probe against the expansion download endpoint; if you only own Vanilla, the greeter hides the Build selector entirely.

## Build

See per-component READMEs:

- `iso/README.md` — building the ISO with `mkarchiso`
- `launcher/README.md` and `greeter/README.md` — Python packages
- `packages/*/PKGBUILD` — Arch packages
