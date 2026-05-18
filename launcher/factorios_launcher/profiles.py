"""Per-user profiles. A profile is one Factorio --write-data target.

Authenticated users get per-build profile trees:
    users/<u>/profiles/<build>/<name>/

The guest/demo flow is flat (no build dimension):
    users/_guest/profiles/<name>/
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from . import paths, versions
from .auth import Session

DEFAULT_PROFILE = "default"


def list_profiles(username: str, build: str | None = None) -> list[str]:
    d = paths.user_profiles(username, build)
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir())


def ensure(username: str, name: str = DEFAULT_PROFILE, build: str | None = None) -> Path:
    """Create a profile directory tree if missing, return its path."""
    p = paths.profile_dir(username, name, build=build)
    (p / "mods").mkdir(parents=True, exist_ok=True)
    (p / "saves").mkdir(parents=True, exist_ok=True)
    (p / "config").mkdir(parents=True, exist_ok=True)
    return p


def clone(username: str, src: str, dst: str, build: str | None = None) -> Path:
    src_dir = paths.profile_dir(username, src, build=build)
    dst_dir = paths.profile_dir(username, dst, build=build)
    if dst_dir.exists():
        raise FileExistsError(dst_dir)
    shutil.copytree(src_dir, dst_dir)
    return dst_dir


def remove(username: str, name: str, build: str | None = None) -> None:
    d = paths.profile_dir(username, name, build=build)
    if d.exists():
        shutil.rmtree(d)


def launch(
    version_id: str,
    username: str,
    profile: str = DEFAULT_PROFILE,
    build: str | None = None,
    session: Session | None = None,
) -> subprocess.Popen:
    """Spawn Factorio. Returns the Popen so the caller can wait().

    Profile separation is by mod directory only — Factorio's
    --mod-directory is universally recognized across builds, while
    --write-data is not (vanilla failed with `Option "write-data" does
    not exist`). Saves and config live at the default location
    (~/.factorio/{saves,config}) and are shared across profiles.

    If `session` has cached factorio.com credentials we seed them into
    ~/.factorio/player-data.json so the in-game mod portal works without
    a second login. (These aren't CLI flags — only fields in the JSON.)
    """
    ensure(username, profile, build=build)
    # Point ~/.factorio at the per-user data dir so each factorio.com
    # account gets its own saves/config/player-data — the appliance runs
    # as a single Unix user, so without this everything would be shared.
    _link_home_factorio(username)
    # If Factorio's in-game updater bumped the install since we last
    # touched it, the on-disk directory name is stale. Reconcile before
    # exec — versions.reconcile renames the dir to match `factorio
    # --version` output and returns the (possibly new) id.
    if build is not None:
        version_id = versions.reconcile(version_id, build)
    if session:
        _seed_service_credentials(session)
    binary = paths.factorio_binary(version_id)
    mod_dir = paths.profile_dir(username, profile, build=build) / "mods"
    return subprocess.Popen(
        [str(binary), "--mod-directory", str(mod_dir)],
        env=_factorio_env(),
    )


def _link_home_factorio(username: str) -> None:
    """Make ~/.factorio resolve to the per-user data dir.

    On a multi-user appliance with one shared Unix account, Factorio
    would otherwise smash everyone's saves/config/player-data together.
    Symlinking before launch is the cleanest fix that doesn't depend on
    Factorio CLI flags.

    Migration: if ~/.factorio already exists as a real directory (from
    an older single-user install where everything lived there), move it
    to the current user's per-user dir on first run. Refuses to do this
    if the per-user dir already has content — that case is ambiguous
    enough to deserve a manual decision.
    """
    user_fac = paths.user_factorio_dir(username)
    home_fac = Path.home() / ".factorio"

    if home_fac.is_symlink():
        # Already managed — repoint to whichever user is launching now.
        home_fac.unlink()
    elif home_fac.is_dir():
        # Pre-existing shared data. Migrate it into the current user's
        # per-user dir if that dir doesn't already exist.
        if user_fac.exists():
            raise RuntimeError(
                f"~/.factorio is a real directory and {user_fac} already "
                f"exists; can't decide which to keep — move one aside manually"
            )
        user_fac.parent.mkdir(parents=True, exist_ok=True)
        home_fac.rename(user_fac)
    elif home_fac.exists():
        raise RuntimeError(f"{home_fac} exists and is neither symlink nor directory")

    user_fac.mkdir(parents=True, exist_ok=True)
    home_fac.symlink_to(user_fac, target_is_directory=True)


def _seed_service_credentials(session: Session) -> None:
    """Write service-username + service-token into ~/.factorio/player-data.json
    so the in-game mod portal skips its own login. Preserves any other
    fields already in the file (Factorio writes lots of state in there)."""
    if not (session.username and session.token):
        return
    fac_dir = Path.home() / ".factorio"
    fac_dir.mkdir(parents=True, exist_ok=True)
    pd = fac_dir / "player-data.json"
    data: dict = {}
    if pd.exists():
        try:
            data = json.loads(pd.read_text())
        except (json.JSONDecodeError, OSError):
            data = {}
    data["service-username"] = session.username
    data["service-token"] = session.token
    pd.write_text(json.dumps(data, indent=2))


# Env vars the greeter session needs (to survive on VirtualBox vmwgfx) but
# Factorio must NOT inherit — software GL via llvmpipe makes Factorio fail
# during renderer init, and the WLR_* hints are for wlroots only.
_GREETER_ONLY_ENV = (
    "LIBGL_ALWAYS_SOFTWARE",
    "WLR_RENDERER",
    "WLR_NO_HARDWARE_CURSORS",
    "WLR_DRM_NO_ATOMIC",
    "WLR_LIBINPUT_NO_DEVICES",
)


def _factorio_env() -> dict[str, str]:
    """Inherit the greeter's env but strip the keys that would force
    Factorio onto software rendering or otherwise confuse its renderer."""
    env = os.environ.copy()
    for k in _GREETER_ONLY_ENV:
        env.pop(k, None)
    return env
