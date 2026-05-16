# archiso profile

Produces the FactoriOS installer ISO. Boot it, it autologs root on tty1, and (if the network is up) launches `factorios-install`.

## Build

You almost never want to run this directly — use the top-level `./build.sh` instead, which builds the PKGBUILDs and stages them into the airootfs as a local repo before invoking this script.

If the packages are already staged, this script alone builds the ISO:

```
iso/build.sh
```

Run it as a regular user with sudo access — `mkchiso` needs root, so the script re-execs itself under `sudo` when not already root, and `chown`s the resulting `work/` and `out/` back to the calling user afterwards. It stages `installer/install.sh` into `airootfs/usr/local/bin/factorios-install` and then runs `mkarchiso -v -w iso/work -o iso/out iso/`. Output lands in `iso/out/`.

## Two pacman.conf files, on purpose

- `iso/pacman.conf` — used by `mkarchiso` on the **build host** to populate the live env's airootfs. No `[factorios]` entry: nothing factorios-* is installed into the live env itself.
- `iso/airootfs/etc/pacman.conf` — the **live env's** pacman config, which the installer's `pacstrap` reuses. Has a `[factorios]` entry pointing at `file:///var/cache/factorios-repo`, populated by `build.sh`.

## Boot config

UEFI-only via grub (`bootmodes=('uefi.grub')`). No BIOS, no syslinux — the installer is UEFI-only anyway, and this keeps the profile minimal.

- `grub/grub.cfg` — live ISO grub menu.
- `grub/loopback.cfg` — variant used when the ISO is chainloaded from another bootloader (e.g. ventoy).

Building requires the `grub` package on the build host (for `grub-install`/`grub-mkrescue`); the CI workflow installs it.

## airootfs layout (what we add on top of archiso defaults)

- `airootfs/etc/pacman.conf` — adds `[factorios]` file:// repo for the installer's pacstrap.
- `airootfs/etc/systemd/system/getty@tty1.service.d/autologin.conf` — autologin root on tty1.
- `airootfs/root/.automated_script.sh` — runs on autologin; greets the user and execs the installer if the network is up.
- `airootfs/var/cache/factorios-repo/` — staged at build time by `build.sh`; gitignored.
