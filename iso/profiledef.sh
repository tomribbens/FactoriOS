#!/usr/bin/env bash
# shellcheck disable=SC2034

# iso_name is variant-tagged via FACTORIOS_VARIANT so the slim and full
# release ISOs end up with distinct filenames in iso/out/. The variant is
# set by iso/build.sh from its $1 argument.
iso_name="factorios${FACTORIOS_VARIANT:+-${FACTORIOS_VARIANT}}"
iso_label="FACTORIOS_$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y%m)"
iso_publisher="FactoriOS <https://github.com/tomribbens/FactoriOS>"
iso_application="FactoriOS Installer"
iso_version="$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y.%m.%d)"
install_dir="factorios"
buildmodes=('iso')
# BIOS + UEFI so VirtualBox's default (BIOS) VMs Just Work without the user
# having to flip the firmware setting. The installer itself is still
# UEFI-only — these bootmodes are about getting the live ISO booted.
bootmodes=('bios.syslinux' 'uefi.grub')
arch="x86_64"
pacman_conf="pacman.conf"
# Squashfs+xz: previous attempt at erofs+lzma produced an unbootable ISO
# (initrd couldn't mount the airootfs — likely missing erofs kernel
# module in the initrd despite mkinitcpio-archiso). Squashfs is safe and
# the trims we already did (no linux-firmware/dhcpcd/openssh/htop) are
# where the real size win came from anyway.
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'xz' '-Xbcj' 'x86' '-b' '1M' '-Xdict-size' '1M')
file_permissions=(
    ["/etc/shadow"]="0:0:400"
    ["/root"]="0:0:750"
    ["/root/.bash_profile"]="0:0:644"
    ["/usr/local/bin/factorios-install"]="0:0:755"
)
