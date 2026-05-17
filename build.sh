#!/bin/bash
# Top-level FactoriOS build.
#
# 1. Builds the three PKGBUILDs (in dependency order).
# 2. Stages the resulting packages into a local Arch repo at
#    iso/airootfs/var/cache/factorios-repo/ — this directory shows up at
#    /var/cache/factorios-repo inside the live ISO, and the live env's
#    pacman.conf has a [factorios] entry pointing at it via file://.
# 3. Hands off to iso/build.sh, which runs mkarchiso.
#
# Run from anywhere; uses absolute paths internally.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

REPO_DIR="$HERE/iso/airootfs/var/cache/factorios-repo"

log() { echo "==> $*"; }
die() { echo "error: $*" >&2; exit 1; }

command -v makepkg >/dev/null || die "makepkg not found (install pacman/base-devel)"
command -v repo-add >/dev/null || die "repo-add not found (install pacman)"

# Clear out stale build artifacts and prior repo state.
log "preparing $REPO_DIR"
rm -rf "$REPO_DIR"
mkdir -p "$REPO_DIR"

build_pkg() {
    local name="$1"
    local pkg_src="$HERE/packages/$name"

    log "building $name"
    [[ -d "$pkg_src" ]] || die "missing $pkg_src"
    # Wipe makepkg state from any previous run.
    rm -rf "$pkg_src/src" "$pkg_src/pkg" "$pkg_src"/*.pkg.tar.zst
    (
        cd "$pkg_src"
        # --nodeps: factorios-greeter depends on factorios-launcher, but we
        # build them in order and stage them locally; we don't need pacman to
        # resolve the dep tree just to *build* them.
        makepkg --force --noconfirm --nodeps --skippgpcheck
    )
    cp "$pkg_src"/*.pkg.tar.zst "$REPO_DIR/"
}

build_pkg factorios-launcher
build_pkg factorios-greeter
build_pkg factorios-base

log "creating repo database"
repo-add --new --remove \
    "$REPO_DIR/factorios.db.tar.zst" \
    "$REPO_DIR"/*.pkg.tar.zst

log "packages staged:"
ls -1 "$REPO_DIR"

log "handing off to iso/build.sh"
exec "$HERE/iso/build.sh" "$@"
