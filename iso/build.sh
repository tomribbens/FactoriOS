#!/bin/bash
# Build the FactoriOS installer ISO.
#
# Stages the installer script into the archiso airootfs, then invokes
# mkarchiso. mkarchiso requires root (chroot/mount/loop); if we're not root
# already, re-exec under sudo so callers don't have to think about it.
#
# The work and out dirs end up root-owned because mkarchiso runs as root.
# We chown them back to SUDO_USER at the end so a regular-user `./build.sh`
# leaves no root-owned artifacts behind.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"

# Stage the installer (cheap, fine to do twice if we re-exec).
install -Dm755 "$REPO/installer/install.sh" "$HERE/airootfs/usr/local/bin/factorios-install"

mkdir -p "$HERE/out" "$HERE/work"

if [[ $EUID -ne 0 ]]; then
    # Pass our UID through so the post-build chown can target the caller.
    exec sudo --preserve-env=SUDO_USER FACTORIOS_CALLER_UID="$(id -u)" FACTORIOS_CALLER_GID="$(id -g)" "$0" "$@"
fi

mkarchiso -v -w "$HERE/work" -o "$HERE/out" "$HERE"

# Hand the build artifacts back to the calling user if we self-elevated.
if [[ -n "${FACTORIOS_CALLER_UID:-}" ]]; then
    chown -R "$FACTORIOS_CALLER_UID:$FACTORIOS_CALLER_GID" "$HERE/work" "$HERE/out"
fi
