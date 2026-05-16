# Installer

`install.sh` runs inside the archiso live environment. UEFI-only, wipes the target disk, installs a minimal Arch system plus the `factorios-*` packages, and enables `factorios.service` so the greeter comes up on first boot.

## Flow

1. `whiptail` picks a target disk and confirms wipe.
2. Optionally pre-seeds factorio.com credentials so the first boot skips the login screen.
3. Hostname + timezone.
4. GPT layout: 512 MiB FAT32 ESP + ext4 root using the rest.
5. `pacstrap` base + factorios packages, `genfstab`, in-chroot bootloader (systemd-boot), user creation (`factorios`, UID 1000), `systemctl enable factorios.service NetworkManager.service seatd.service`.
6. If creds were given: run the launcher's `Session().login(...).save(...)` inside the chroot to drop a `session.json` and `last-user` pointer.

## How it finds factorios-* packages

The live env's `/etc/pacman.conf` (provided by `iso/airootfs/etc/pacman.conf`) has a `[factorios]` repo entry pointing at `file:///var/cache/factorios-repo`. The top-level `build.sh` populates that directory before the ISO is built. `pacstrap` inherits the live env's pacman config, so it resolves the factorios-* names from there.

## Requirements in the live env

`whiptail`, `parted`, `dosfstools`, `e2fsprogs`, `arch-install-scripts` — see `iso/packages.x86_64`.
