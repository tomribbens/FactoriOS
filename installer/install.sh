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

# --- 2. Keyboard layout -------------------------------------------------
# Two layers to set: the kbd console keymap (loadkeys / /etc/vconsole.conf)
# and the XKB layout libxkbcommon uses for Wayland/X11
# (/etc/X11/xorg.conf.d/00-keyboard.conf). The menu is keyed by XKB layout
# (the more expressive namespace); the console keymap is derived via the
# XKB_TO_KEYMAP table below.
KEYBOARD_LAYOUTS=(
    us  "US English (QWERTY)"
    gb  "British English"
    ie  "Irish"
    de  "German"
    fr  "French (AZERTY)"
    be  "Belgian (AZERTY)"
    es  "Spanish"
    it  "Italian"
    pt  "Portuguese"
    br  "Brazilian"
    nl  "Dutch"
    no  "Norwegian"
    se  "Swedish"
    dk  "Danish"
    fi  "Finnish"
    ch  "Swiss German"
    "ch(fr)" "Swiss French"
    pl  "Polish"
    cz  "Czech"
    hu  "Hungarian"
    ru  "Russian"
    jp  "Japanese"
    other "(type a custom layout name)"
)
declare -A XKB_TO_KEYMAP=(
    [us]=us
    [gb]=uk
    [ie]=ie
    [de]=de-latin1
    [fr]=fr-latin1
    [be]=be-latin1
    [es]=es
    [it]=it
    [pt]=pt-latin1
    [br]=br-abnt2
    [nl]=nl
    [no]=no-latin1
    [se]=sv-latin1
    [dk]=dk-latin1
    [fi]=fi-latin1
    [ch]=de_CH-latin1
    ["ch(fr)"]=fr_CH-latin1
    [pl]=pl
    [cz]=cz-lat2
    [hu]=hu
    [ru]=ru
    [jp]=jp106
)
XKB_LAYOUT=$(whiptail --title "Keyboard layout" \
    --menu "Select your keyboard layout" 22 70 14 \
    "${KEYBOARD_LAYOUTS[@]}" 3>&1 1>&2 2>&3)
if [[ "$XKB_LAYOUT" == "other" ]]; then
    XKB_LAYOUT=$(whiptail --title "Keyboard layout" \
        --inputbox "XKB layout name (e.g. us, gb, de, dvorak)" \
        10 60 us 3>&1 1>&2 2>&3)
fi
# Strip an optional XKB variant in parens — we currently only special-case
# Swiss French ("ch(fr)") and don't expose other variants.
XKB_VARIANT=""
if [[ "$XKB_LAYOUT" == *"("*")"* ]]; then
    XKB_VARIANT="${XKB_LAYOUT##*\(}"
    XKB_VARIANT="${XKB_VARIANT%\)}"
    XKB_LAYOUT="${XKB_LAYOUT%%\(*}"
fi
KEYBOARD="${XKB_TO_KEYMAP[${XKB_LAYOUT}${XKB_VARIANT:+(${XKB_VARIANT})}]:-${XKB_TO_KEYMAP[$XKB_LAYOUT]:-$XKB_LAYOUT}}"
loadkeys "$KEYBOARD" || log "loadkeys $KEYBOARD failed (continuing — installed system will still try)"

# --- 3. Optional pre-seed factorio.com creds ----------------------------
SEED_USER=""
SEED_PASS=""
if whiptail --title "factorio.com" \
        --yesno "Pre-seed factorio.com credentials so the first boot skips the login screen?" \
        10 60; then
    SEED_USER=$(whiptail --title "factorio.com" --inputbox "Username or email" 10 60 3>&1 1>&2 2>&3) || true
    SEED_PASS=$(whiptail --title "factorio.com" --passwordbox "Password" 10 60 3>&1 1>&2 2>&3) || true
fi

# --- 4. Hostname / timezone --------------------------------------------
HOSTNAME=$(whiptail --title "Hostname" --inputbox "" 10 60 "factorios" 3>&1 1>&2 2>&3)

# Timezone: pick a region first, then a city in that region. Mirrors the
# layout of /usr/share/zoneinfo (which tzdata ships) — we don't hardcode
# city lists. Plus a top-level "UTC" shortcut for people who don't care.
mapfile -t TZ_REGIONS < <(
    find /usr/share/zoneinfo -maxdepth 1 -mindepth 1 -type d -printf '%f\n' \
        | grep -vE '^(posix|right|SystemV)$' \
        | sort
)
tz_menu=("UTC" "(no region — use UTC)")
for r in "${TZ_REGIONS[@]}"; do
    tz_menu+=("$r" "")
done
TZ_REGION=$(whiptail --title "Timezone region" \
    --menu "Select your region" 22 60 14 \
    "${tz_menu[@]}" 3>&1 1>&2 2>&3)
if [[ "$TZ_REGION" == "UTC" ]]; then
    TIMEZONE="UTC"
else
    mapfile -t TZ_CITIES < <(
        find "/usr/share/zoneinfo/$TZ_REGION" -type f -printf '%P\n' | sort
    )
    city_menu=()
    for c in "${TZ_CITIES[@]}"; do
        city_menu+=("$c" "")
    done
    TZ_CITY=$(whiptail --title "Timezone — $TZ_REGION" \
        --menu "Select your city" 22 70 14 \
        "${city_menu[@]}" 3>&1 1>&2 2>&3)
    TIMEZONE="$TZ_REGION/$TZ_CITY"
fi

# --- 5. Partition -------------------------------------------------------
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

# --- 6. Pacstrap --------------------------------------------------------
log "pacstrap"
pacstrap -K /mnt \
    base linux linux-firmware \
    networkmanager \
    labwc seatd \
    mesa vulkan-icd-loader \
    python python-requests python-gobject gtk4 \
    factorios-launcher factorios-greeter factorios-base

genfstab -U /mnt >> /mnt/etc/fstab

# --- 7. In-chroot config ------------------------------------------------
log "configuring system"
arch-chroot /mnt /bin/bash -e <<EOF
ln -sf /usr/share/zoneinfo/$TIMEZONE /etc/localtime
hwclock --systohc
echo "en_US.UTF-8 UTF-8" > /etc/locale.gen
locale-gen
echo "LANG=en_US.UTF-8" > /etc/locale.conf
echo "KEYMAP=$KEYBOARD" > /etc/vconsole.conf
# XKB layout for Wayland/X11 (labwc + the greeter read this via
# libxkbcommon). vconsole.conf alone doesn't carry into Wayland.
mkdir -p /etc/X11/xorg.conf.d
cat > /etc/X11/xorg.conf.d/00-keyboard.conf <<KB
Section "InputClass"
    Identifier "system-keyboard"
    MatchIsKeyboard "on"
    Option "XkbLayout" "$XKB_LAYOUT"
$( [[ -n "$XKB_VARIANT" ]] && echo "    Option \"XkbVariant\" \"$XKB_VARIANT\"" )
EndSection
KB
echo "$HOSTNAME" > /etc/hostname

# factorios user creation is declarative via factorios-base's sysusers.d
# entry, which pacman triggers after each transaction. This is just a
# safety net for the unlikely case that systemd-sysusers didn't run.
id factorios &>/dev/null || useradd -m -u 1000 -s /usr/bin/nologin -G seat,video,input,render factorios

# Passwordless root for tty/console recovery. Appliance-OS pattern:
# factorio.com is the real auth surface, root only exists so anyone with
# physical access can debug when labwc/the greeter falls over. The kiosk
# session doesn't expose a shell, so this isn't a remote-access risk.
passwd -d root

# Bootloader.
bootctl install
# Verbose-by-default boot: show the systemd-boot menu for a few seconds
# and let the kernel log to the console. The compositor still owns tty1
# once factorios.service starts, so this only affects very early boot.
cat > /boot/loader/loader.conf <<LOADER
default factorios
timeout 3
console-mode max
LOADER
cat > /boot/loader/entries/factorios.conf <<ENTRY
title   FactoriOS
linux   /vmlinuz-linux
initrd  /initramfs-linux.img
options root=PARTUUID=$(blkid -s PARTUUID -o value "$ROOT") rw
ENTRY

systemctl enable NetworkManager.service
systemctl enable seatd.service
systemctl enable factorios.service
systemctl set-default graphical.target
EOF

# --- 8. Optional credential seeding ------------------------------------
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
