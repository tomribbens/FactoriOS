#!/bin/bash
# FactoriOS installer. Runs in the archiso live environment.
#
# UEFI-only. Wipes the chosen disk. Installs minimal Arch + factorios-* pkgs,
# enables factorios.service so the greeter comes up on next boot.
set -euo pipefail

die() { echo "error: $*" >&2; exit 1; }
log() { echo "==> $*"; }

[[ $EUID -eq 0 ]] || die "must run as root"
[[ -d /sys/firmware/efi ]] || die "UEFI boot required"

# --- 1. Disk picker -----------------------------------------------------
mapfile -t disks < <(lsblk -dn -o NAME,SIZE,MODEL -e 7,11 | awk '{print "/dev/"$0}')
[[ ${#disks[@]} -gt 0 ]] || die "no installable disks found"

menu_args=()
for i in "${!disks[@]}"; do
    menu_args+=("$i" "${disks[$i]}")
done
choice=$(whiptail --title "FactoriOS installer" \
    --menu "Select the target disk. EVERYTHING ON IT WILL BE ERASED." \
    20 70 10 "${menu_args[@]}" 3>&1 1>&2 2>&3)
DISK=$(echo "${disks[$choice]}" | awk '{print $1}')

whiptail --title "Confirm" --yesno \
    "Wipe $DISK and install FactoriOS?\n\nThis cannot be undone." 10 60 \
    || die "aborted"

# --- 2. Optional pre-seed factorio.com creds ----------------------------
SEED_USER=""
SEED_PASS=""
if whiptail --title "factorio.com" \
        --yesno "Pre-seed factorio.com credentials so the first boot skips the login screen?" \
        10 60; then
    SEED_USER=$(whiptail --title "factorio.com" --inputbox "Username or email" 10 60 3>&1 1>&2 2>&3) || true
    SEED_PASS=$(whiptail --title "factorio.com" --passwordbox "Password" 10 60 3>&1 1>&2 2>&3) || true
fi

# --- 3. Hostname / timezone --------------------------------------------
HOSTNAME=$(whiptail --title "Hostname" --inputbox "" 10 60 "factorios" 3>&1 1>&2 2>&3)
TIMEZONE=$(whiptail --title "Timezone" --inputbox "" 10 60 "UTC" 3>&1 1>&2 2>&3)

# --- 4. Partition -------------------------------------------------------
log "partitioning $DISK"
wipefs -a "$DISK"
parted -s "$DISK" \
    mklabel gpt \
    mkpart ESP fat32 1MiB 513MiB \
    set 1 esp on \
    mkpart root ext4 513MiB 100%

# Handle nvme-style partition naming (nvme0n1p1) vs sda1.
if [[ "$DISK" == *"nvme"* || "$DISK" == *"mmcblk"* ]]; then
    PART_PREFIX="${DISK}p"
else
    PART_PREFIX="$DISK"
fi
ESP="${PART_PREFIX}1"
ROOT="${PART_PREFIX}2"

log "formatting"
mkfs.fat -F32 "$ESP"
mkfs.ext4 -F "$ROOT"

log "mounting"
mount "$ROOT" /mnt
mkdir -p /mnt/boot
mount "$ESP" /mnt/boot

# --- 5. Pacstrap --------------------------------------------------------
log "pacstrap"
pacstrap -K /mnt \
    base linux linux-firmware \
    networkmanager \
    labwc seatd \
    mesa vulkan-icd-loader \
    python python-requests python-gobject gtk4 \
    factorios-launcher factorios-greeter factorios-base

genfstab -U /mnt >> /mnt/etc/fstab

# --- 6. In-chroot config ------------------------------------------------
log "configuring system"
arch-chroot /mnt /bin/bash -e <<EOF
ln -sf /usr/share/zoneinfo/$TIMEZONE /etc/localtime
hwclock --systohc
echo "en_US.UTF-8 UTF-8" > /etc/locale.gen
locale-gen
echo "LANG=en_US.UTF-8" > /etc/locale.conf
echo "$HOSTNAME" > /etc/hostname

# factorios system user, fixed UID so XDG_RUNTIME_DIR is predictable.
id factorios &>/dev/null || useradd -r -m -u 1000 -s /usr/bin/nologin -G seat,video,input factorios

# Bootloader.
bootctl install
cat > /boot/loader/loader.conf <<LOADER
default factorios
timeout 0
console-mode max
LOADER
cat > /boot/loader/entries/factorios.conf <<ENTRY
title   FactoriOS
linux   /vmlinuz-linux
initrd  /initramfs-linux.img
options root=PARTUUID=$(blkid -s PARTUUID -o value "$ROOT") rw quiet
ENTRY

systemctl enable NetworkManager.service
systemctl enable seatd.service
systemctl enable factorios.service
systemctl set-default graphical.target
EOF

# --- 7. Optional credential seeding ------------------------------------
if [[ -n "$SEED_USER" && -n "$SEED_PASS" ]]; then
    log "pre-seeding factorio.com session"
    arch-chroot /mnt /bin/bash -e <<EOF
install -d -o factorios -g factorios -m 700 /var/lib/factorios/users/$SEED_USER
runuser -u factorios -- python -c "
from factorios_launcher.auth import Session
from factorios_launcher import paths
s = Session().login('$SEED_USER', '''$SEED_PASS''')
s.save(paths.user_session('$SEED_USER'))
"
echo "$SEED_USER" > /var/lib/factorios/last-user
chown factorios:factorios /var/lib/factorios/last-user
EOF
fi

log "done. you can now reboot."
