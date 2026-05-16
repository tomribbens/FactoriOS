#!/bin/bash
# Build the FactoriOS installer ISO.
#
# Stages the installer script into the archiso airootfs, then invokes
# mkarchiso. Run from the repo root.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"

# Stage the installer.
install -Dm755 "$REPO/installer/install.sh" "$HERE/airootfs/usr/local/bin/factorios-install"

# Out / work dirs are in .gitignore.
mkdir -p "$HERE/out" "$HERE/work"

exec mkarchiso -v -w "$HERE/work" -o "$HERE/out" "$HERE"
