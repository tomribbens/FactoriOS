"""Manage installed Factorio versions under /var/lib/factorios/versions/."""

from __future__ import annotations

import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Callable

from . import paths
from .auth import Session
from .download import download, ProgressCb


def list_installed() -> list[str]:
    if not paths.VERSIONS.exists():
        return []
    return sorted(p.name for p in paths.VERSIONS.iterdir() if p.is_dir())


def is_installed(version: str) -> bool:
    return paths.factorio_binary(version).is_file()


def install(session: Session, version: str, progress: ProgressCb | None = None) -> Path:
    """Download and extract a Factorio version. No-op if already installed."""
    target = paths.version_dir(version)
    if is_installed(version):
        return target

    paths.VERSIONS.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".tar.xz", delete=False) as tmp:
        tarball = Path(tmp.name)
    try:
        download(session, tarball, version=version, progress=progress)
        with tarfile.open(tarball, "r:xz") as tf:
            tf.extractall(paths.VERSIONS)
        # Tarball extracts to "factorio/"; rename to the concrete version dir.
        extracted = paths.VERSIONS / "factorio"
        if extracted.exists():
            extracted.rename(target)
    finally:
        tarball.unlink(missing_ok=True)
    return target


def remove(version: str) -> None:
    d = paths.version_dir(version)
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
