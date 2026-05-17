#!/bin/bash
# Build a FactoriOS installer ISO.
#
# Usage:  iso/build.sh [slim|full]   (default: slim)
#
#   slim  — default. No linux-firmware; ~150–200 MB ISO. Works in VMs and
#           on bare metal with ethernet + Intel/AMD GPUs that don't need
#           firmware blobs.
#   full  — adds linux-firmware (~600 MB). For the release ISO that should
#           boot on bare metal with WiFi or modern AMD/NVidia GPUs.
#
# Caller must be a regular user with sudo (mkarchiso needs root). We
# explicitly do NOT `exec sudo` ourselves — that would skip the cleanup
# trap that restores packages.x86_64 after a full build mutates it.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"

VARIANT="${1:-slim}"
case "$VARIANT" in
    slim|full) ;;
    *) echo "error: unknown variant '$VARIANT' (use slim or full)" >&2; exit 2 ;;
esac

# Stage the installer into the airootfs.
install -Dm755 "$REPO/installer/install.sh" "$HERE/airootfs/usr/local/bin/factorios-install"

mkdir -p "$HERE/out"
rm -rf "$HERE/work"

# The full variant temporarily appends linux-firmware to packages.x86_64
# (mkarchiso has no "extra-packages" flag). The trap restores the file no
# matter how we exit so the source tree stays pristine.
PKGS_FILE="$HERE/packages.x86_64"
cleanup() {
    if [[ -f "$PKGS_FILE.bak" ]]; then
        mv -f "$PKGS_FILE.bak" "$PKGS_FILE"
    fi
}
trap cleanup EXIT

if [[ "$VARIANT" == "full" ]]; then
    cp "$PKGS_FILE" "$PKGS_FILE.bak"
    cat <<'EOF' >> "$PKGS_FILE"

# --- Added by iso/build.sh full ---
linux-firmware
EOF
    export FACTORIOS_VARIANT=full
fi

# Run mkarchiso as root (sudo if we're not already).
if [[ $EUID -eq 0 ]]; then
    mkarchiso -v -w "$HERE/work" -o "$HERE/out" "$HERE"
else
    sudo --preserve-env=FACTORIOS_VARIANT \
        mkarchiso -v -w "$HERE/work" -o "$HERE/out" "$HERE"
    # mkarchiso left the work/out trees root-owned; hand them back.
    sudo chown -R "$(id -u):$(id -g)" "$HERE/work" "$HERE/out"
fi
