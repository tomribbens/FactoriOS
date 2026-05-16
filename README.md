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
./build.sh    # builds all three PKGBUILDs, stages them into a local repo
              # inside the airootfs, then runs mkarchiso. Output: iso/out/*.iso
```

Requires `archiso`, `pacman`, `base-devel` on the build host. Run as a regular user with sudo access — `makepkg` runs as you, `mkarchiso` self-elevates.

CI also builds the ISO: see `.github/workflows/build-iso.yml`. Every push to `main` produces a downloadable artifact on the workflow run; tag pushes (`v*`) attach the ISO to a GitHub Release.

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
      vanilla/<profile-name>/    # per-build profile (mods, saves, config)
      space-age/<profile-name>/
    session.json                 # cached factorio.com session cookies
  users/_guest/profiles/<name>/  # guest/demo profiles (flat — no build dim)
  last-user                      # only present when Remember Me was checked
```

Profiles are per-build because mod compatibility differs across Vanilla and Space Age. Space Age ownership is detected at login time via a HEAD probe against the expansion download endpoint; if you only own Vanilla, the greeter hides the Build selector entirely.

## Build

See per-component READMEs:

- `iso/README.md` — building the ISO with `mkarchiso`
- `launcher/README.md` and `greeter/README.md` — Python packages
- `packages/*/PKGBUILD` — Arch packages
