"""Manage installed Factorio versions under /var/lib/factorios/versions/.

Authenticated installs live at `versions/<version>-<build>/`. The demo lives
at `versions/_demo/` (no build dimension — demo is its own build).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from . import paths
from .auth import Session
from .download import download, ProgressCb

# `factorio --version` output starts with e.g. "Version: 1.1.110 (build 60394, linux64, alpha)"
_VERSION_RE = re.compile(r"^Version:\s+(\S+)\s")


def list_installed() -> list[tuple[str, str]]:
    """Return (version, build) for every authenticated install. Demo is
    excluded — guests don't pick from this list."""
    if not paths.VERSIONS.exists():
        return []
    out: list[tuple[str, str]] = []
    for p in paths.VERSIONS.iterdir():
        if not p.is_dir() or p.name == paths.DEMO_VERSION:
            continue
        for build in paths.ALL_BUILDS:
            suffix = f"-{build}"
            if p.name.endswith(suffix) and len(p.name) > len(suffix):
                out.append((p.name[: -len(suffix)], build))
                break
    return sorted(out)


def list_installed_for_build(build: str) -> list[str]:
    return sorted(v for v, b in list_installed() if b == build)


def is_installed(version: str, build: str) -> bool:
    return paths.factorio_binary(paths.version_id(version, build)).is_file()


def install(
    session: Session,
    version: str,
    build: str = paths.DEFAULT_BUILD,
    progress: ProgressCb | None = None,
) -> Path:
    """Download and extract a Factorio version of the given build. No-op if
    already installed."""
    vid = paths.version_id(version, build)
    target = paths.version_dir(vid)
    if is_installed(version, build):
        return target

    paths.VERSIONS.mkdir(parents=True, exist_ok=True)
    # Stage the tarball alongside its eventual extraction target rather
    # than in /tmp (tmpfs, sized at ~½ RAM). Multi-GB Factorio downloads
    # blow out tmpfs and surface as errno 122 (EDQUOT/ENOSPC).
    with tempfile.NamedTemporaryFile(suffix=".tar.xz", delete=False, dir=str(paths.VERSIONS)) as tmp:
        tarball = Path(tmp.name)
    try:
        download(
            session,
            tarball,
            version=version,
            build=paths.BUILD_API[build],
            progress=progress,
        )
        with tarfile.open(tarball, "r:xz") as tf:
            tf.extractall(paths.VERSIONS)
        # Tarball extracts to "factorio/"; rename to the build-tagged dir.
        extracted = paths.VERSIONS / "factorio"
        if extracted.exists():
            if target.exists():
                shutil.rmtree(target)
            extracted.rename(target)
    finally:
        tarball.unlink(missing_ok=True)
    ensure_system_data_mode(vid)
    return target


def ensure_system_data_mode(version_id: str) -> None:
    """Flip a Factorio install from "portable" mode (data lives next to
    the binary) to "system" mode (data lives in ~/.factorio).

    The standalone Linux tarball ships without config-path.cfg, which
    makes Factorio default to portable mode — it then reads and writes
    player-data.json, config/config.ini, saves/, and mods/ INSIDE the
    install dir, ignoring ~/.factorio entirely. That breaks our per-user
    data isolation (the ~/.factorio symlink we set up at launch points
    to /var/lib/factorios/users/<u>/factorio, but Factorio never looks
    there) and means our credential/config seeding has no effect.

    Writing this one-line config-path.cfg in the install root tells
    Factorio to use the platform default (~/.factorio on Linux), which
    is exactly what our architecture assumes everywhere else.

    Idempotent: safe to re-call on every launch to retrofit installs
    that predate this fix.

    Both keys are required: Factorio parses the file as a property tree
    and refuses to start if `config-path` is missing (Util.cpp asserts
    "value must be a string in the property tree at ROOT.config-path").
    The use-system flag overrides the actual path resolution, but the
    key still has to be present.
    """
    cfg = paths.version_dir(version_id) / "config-path.cfg"
    cfg.write_text(
        "config-path=__PATH__system-write-data__/config/config.ini\n"
        "use-system-read-write-data-directories=true\n"
    )


def remove(version: str, build: str) -> None:
    d = paths.version_dir(paths.version_id(version, build))
    if d.exists():
        shutil.rmtree(d)


def detect_version(version_id: str) -> str | None:
    """Run `factorio --version` on an installed version and parse the
    actual version string. Returns None on any failure (binary missing,
    timeout, unexpected output)."""
    binary = paths.factorio_binary(version_id)
    if not binary.is_file():
        return None
    try:
        out = subprocess.run(
            [str(binary), "--version"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    for line in out.splitlines():
        m = _VERSION_RE.match(line)
        if m:
            return m.group(1)
    return None


def reconcile(version_id: str, build: str) -> str:
    """Bring the on-disk directory name in line with the actual Factorio
    version inside it. Returns the (possibly renamed) version_id.

    Factorio's in-game updater can upgrade an install in place; without
    this, our chooser keeps showing the old version label until the user
    reinstalls. No-op for the demo (its dir is name-stable).
    """
    if version_id == paths.DEMO_VERSION:
        return version_id
    actual = detect_version(version_id)
    if not actual:
        return version_id
    expected = paths.version_id(actual, build)
    if expected == version_id:
        return version_id
    src = paths.version_dir(version_id)
    dst = paths.version_dir(expected)
    if dst.exists():
        # Both src and dst now claim the same version — typically because
        # the in-game updater bumped src to a release that was already
        # installed separately at dst. Verify dst really is what its name
        # says, then drop the now-redundant src. Version dirs hold no
        # per-user state (that lives under users/<u>/), so this is
        # lossless. If dst's name lies about its content, bail rather
        # than compound the mess.
        if detect_version(expected) == actual:
            shutil.rmtree(src)
            return expected
        return version_id
    src.rename(dst)
    return expected


def reconcile_all(build: str) -> None:
    """Reconcile every installed version for a build. Used post-launch
    to catch in-game updates without having to track which specific
    version_id was just played (the dir may have been renamed during
    the session, so the pre-launch id is unreliable)."""
    for version in list_installed_for_build(build):
        reconcile(paths.version_id(version, build), build)


def install_demo(session: Session | None = None, progress: ProgressCb | None = None) -> Path:
    """Download and extract the Factorio demo. No-op if already installed.

    The demo download endpoint is public, so `session` can be a fresh
    `Session()` with no login cookies.
    """
    target = paths.version_dir(paths.DEMO_VERSION)
    if paths.factorio_binary(paths.DEMO_VERSION).is_file():
        return target

    if session is None:
        session = Session()

    paths.VERSIONS.mkdir(parents=True, exist_ok=True)
    # Stage the tarball alongside its eventual extraction target rather
    # than in /tmp (tmpfs, sized at ~½ RAM). Multi-GB Factorio downloads
    # blow out tmpfs and surface as errno 122 (EDQUOT/ENOSPC).
    with tempfile.NamedTemporaryFile(suffix=".tar.xz", delete=False, dir=str(paths.VERSIONS)) as tmp:
        tarball = Path(tmp.name)
    try:
        download(session, tarball, version="latest", build="demo", progress=progress)
        with tarfile.open(tarball, "r:xz") as tf:
            tf.extractall(paths.VERSIONS)
        extracted = paths.VERSIONS / "factorio"
        if extracted.exists():
            if target.exists():
                shutil.rmtree(target)
            extracted.rename(target)
    finally:
        tarball.unlink(missing_ok=True)
    return target
