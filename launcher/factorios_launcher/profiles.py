"""Per-user profiles. A profile is one Factorio --write-data target."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from . import paths

DEFAULT_PROFILE = "default"


def list_profiles(username: str) -> list[str]:
    d = paths.user_profiles(username)
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir())


def ensure(username: str, name: str = DEFAULT_PROFILE) -> Path:
    """Create a profile directory tree if missing, return its path."""
    p = paths.profile_dir(username, name)
    (p / "mods").mkdir(parents=True, exist_ok=True)
    (p / "saves").mkdir(parents=True, exist_ok=True)
    (p / "config").mkdir(parents=True, exist_ok=True)
    return p


def clone(username: str, src: str, dst: str) -> Path:
    src_dir = paths.profile_dir(username, src)
    dst_dir = paths.profile_dir(username, dst)
    if dst_dir.exists():
        raise FileExistsError(dst_dir)
    shutil.copytree(src_dir, dst_dir)
    return dst_dir


def remove(username: str, name: str) -> None:
    d = paths.profile_dir(username, name)
    if d.exists():
        shutil.rmtree(d)


def launch(version: str, username: str, profile: str = DEFAULT_PROFILE) -> subprocess.Popen:
    """Spawn Factorio. Returns the Popen so the caller can wait()."""
    ensure(username, profile)
    binary = paths.factorio_binary(version)
    profile_path = paths.profile_dir(username, profile)
    env = os.environ.copy()
    return subprocess.Popen(
        [str(binary), "--write-data", str(profile_path)],
        env=env,
    )
