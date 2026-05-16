"""Manage installed Factorio versions under /var/lib/factorios/versions/.

Authenticated installs live at `versions/<version>-<build>/`. The demo lives
at `versions/_demo/` (no build dimension — demo is its own build).
"""

from __future__ import annotations

import shutil
import tarfile
import tempfile
from pathlib import Path

from . import paths
from .auth import Session
from .download import download, ProgressCb


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
    with tempfile.NamedTemporaryFile(suffix=".tar.xz", delete=False) as tmp:
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
    return target


def remove(version: str, build: str) -> None:
    d = paths.version_dir(paths.version_id(version, build))
    if d.exists():
        shutil.rmtree(d)


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
    with tempfile.NamedTemporaryFile(suffix=".tar.xz", delete=False) as tmp:
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
