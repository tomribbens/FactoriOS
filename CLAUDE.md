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
  versions/<version>/         # shared, system-wide
  users/<factorio-username>/
    profiles/<profile-name>/  # one Factorio --write-data target per profile
    session.json
  last-user                   # present iff Remember Me
```

`launcher/factorios_launcher/paths.py` is the single source of truth for these paths — don't hard-code them elsewhere.

## factorio.com auth flow

GET `https://www.factorio.com/login` → scrape `input[name=csrf_token]` → POST `csrf_token` + `username_or_email` + `password` → reuse the resulting session cookie for `https://www.factorio.com/get-download/{version}/{build}/{distro}`. Implemented in `launcher/factorios_launcher/auth.py`.

## Build

`./build.sh` is the only entry point. It (1) runs `makepkg` for the three PKGBUILDs in dependency order, (2) `repo-add`s the results into `iso/airootfs/var/cache/factorios-repo/`, and (3) execs `iso/build.sh`, which stages the installer script and runs `mkarchiso`. The repo dir is gitignored and recreated every run.

PKGBUILDs pull their source out of the monorepo via `$startdir/../../<dir>` in `prepare()` — no manual file shuffling, no tarballs. Don't add `source=()` URLs; keep the monorepo-relative pattern.

Two pacman.conf files exist on purpose: `iso/pacman.conf` is for the build host (no `[factorios]` repo — nothing factorios-* gets installed into the live env); `iso/airootfs/etc/pacman.conf` is the live env's config and *does* have the `[factorios]` `file:///var/cache/factorios-repo` entry that the installer's `pacstrap` inherits.

Python packages are flat and importable without install during dev: `PYTHONPATH=launcher python -m factorios_launcher releases`.
