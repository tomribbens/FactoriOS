# archiso profile

Produces the FactoriOS installer ISO. Boot it, it autologs root on tty1, and (if the network is up) launches `factorios-install`.

## Build

You almost never want to run this directly — use the top-level `./build.sh` instead, which builds the PKGBUILDs and stages them into the airootfs as a local repo before invoking this script.

If the packages are already staged (i.e., `./build.sh` ran successfully before), this script builds an ISO without re-running the PKGBUILDs:

```
iso/build.sh           # slim variant (default)
iso/build.sh full      # full variant — adds linux-firmware
```

The full variant temporarily appends `linux-firmware` to `packages.x86_64` and exports `FACTORIOS_VARIANT=full`; `profiledef.sh` uses that env var to tag the output filename, so slim and full ISOs coexist in `iso/out/`. A cleanup trap restores `packages.x86_64` no matter how the script exits.

Run as a regular user with sudo access — `mkarchiso` needs root, so the script invokes it via `sudo` and `chown`s the resulting `work/` and `out/` trees back to the caller afterwards.

## Two pacman.conf files, on purpose

- `iso/pacman.conf` — used by `mkarchiso` on the **build host** to populate the live env's airootfs. No `[factorios]` entry: nothing factorios-* is installed into the live env itself.
- `iso/airootfs/etc/pacman.conf` — the **live env's** pacman config, which the installer's `pacstrap` reuses. Has a `[factorios]` entry pointing at `file:///var/cache/factorios-repo`, populated by `build.sh`.

## Boot config

Hybrid BIOS + UEFI (`bootmodes=('bios.syslinux' 'uefi.grub')`). The installer itself is still UEFI-only — these bootmodes are about getting the live ISO to boot, primarily so VirtualBox VMs (which default to BIOS firmware) work without the user having to enable EFI by hand.

- `grub/grub.cfg` + `grub/loopback.cfg` — UEFI grub menu, plus a loopback variant for when the ISO is chainloaded from another bootloader (e.g. ventoy).
- `syslinux/syslinux.cfg` + `syslinux/syslinux-linux.cfg` — BIOS syslinux menu.

Building requires the `grub` package on the build host (for `grub-install`/`grub-mkrescue`); the CI workflow installs it. The `syslinux` package is in `packages.x86_64` so its boot files are present in the live env for mkarchiso to copy.

## airootfs layout (what we add on top of archiso defaults)

- `airootfs/etc/pacman.conf` — adds `[factorios]` file:// repo for the installer's pacstrap.
- `airootfs/etc/systemd/system/getty@tty1.service.d/autologin.conf` — autologin root on tty1.
- `airootfs/root/.automated_script.sh` — runs on autologin; greets the user and execs the installer if the network is up.
- `airootfs/var/cache/factorios-repo/` — staged at build time by `build.sh`; gitignored.
