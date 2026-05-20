"""Per-user, per-build profiles. A profile *is* a complete Factorio
write-data dir — its directory gets symlinked in as ~/.factorio before
launch so saves, config, mods, player-data.json, achievements.dat, and
everything else Factorio writes are scoped to the chosen profile.

Authenticated users get per-build profile trees:
    users/<u>/profiles/<build>/<name>/

The guest/demo flow is flat (no build dimension):
    users/_guest/profiles/<name>/
"""

from __future__ import annotations

import configparser
import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import paths, versions
from .auth import Session

DEFAULT_PROFILE = "default"

# Schema version Factorio expects at the top of config.ini as `; version=N`.
# Without it Factorio considers the file invalid and prompts to reset.
# Observed value in Factorio 2.0 is 13; bump if a future Factorio
# release writes a higher number to its own freshly-generated config.
CONFIG_INI_VERSION = 13


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
    use_mimalloc: bool = True,
) -> subprocess.Popen:
    """Spawn Factorio. Returns the Popen so the caller can wait().

    Profile separation is full — the profile directory IS the Factorio
    write-data dir. Before launch we symlink ~/.factorio at it, so
    saves, config, mods, player-data.json, achievements.dat, and
    everything else Factorio writes lands inside the profile. Switching
    profiles re-points the symlink; no CLI flags are needed beyond
    --config.

    If `session` has cached factorio.com credentials we seed them into
    ~/.factorio/player-data.json so the in-game mod portal works without
    a second login. (These aren't CLI flags — only fields in the JSON.)
    """
    ensure(username, profile, build=build)
    # Point ~/.factorio at the chosen profile so each profile gets its
    # own saves/config/mods/player-data — the appliance runs as a single
    # Unix user, so without this every profile would share state.
    _link_home_factorio(username, profile, build)
    # If Factorio's in-game updater bumped the install since we last
    # touched it, the on-disk directory name is stale. Reconcile before
    # exec — versions.reconcile renames the dir to match `factorio
    # --version` output and returns the (possibly new) id.
    if build is not None:
        version_id = versions.reconcile(version_id, build)
    # Retrofit older installs: the standalone Factorio tarball ships in
    # portable mode (data inside the install dir), which silently bypasses
    # our ~/.factorio symlink and credential seeding. Flip it to system
    # mode every launch — idempotent, costs one tiny file write.
    versions.ensure_system_data_mode(version_id)
    if session:
        _seed_service_credentials(session)
    _seed_config_ini()
    _evict_stale_achievements(username, profile, build, version_id)
    binary = paths.factorio_binary(version_id)
    # --config is honored even when it points at an absolute path
    # (config-path.cfg's `config-path` key silently ignores absolutes;
    # only --config does). Our seeded config.ini has [path] read-data
    # pointing back into the install tree and write-data resolving to
    # __PATH__system-write-data__ (= ~/.factorio, then symlinked at the
    # current profile). Mods land at the default ~/.factorio/mods so no
    # --mod-directory flag is needed.
    config_ini = Path.home() / ".factorio" / "config" / "config.ini"
    return subprocess.Popen(
        [str(binary), "--config", str(config_ini)],
        env=_factorio_env(use_mimalloc=use_mimalloc),
    )


def _link_home_factorio(username: str, profile: str, build: str | None) -> None:
    """Make ~/.factorio resolve to the chosen profile's directory.

    On a multi-user, multi-profile appliance with one shared Unix
    account, Factorio would otherwise smash everyone's saves/config/
    player-data together. Symlinking the profile dir as ~/.factorio
    before launch is the cleanest fix that doesn't depend on Factorio
    CLI flags.

    Two migrations are handled here, both one-shot:

    1. ~/.factorio is a real directory (extremely old single-user
       layout): refuse and ask the user to move it aside — too
       ambiguous to claim it for any specific user/profile.
    2. users/<u>/factorio/ exists (older per-user but not per-profile
       layout): fold its contents into the profile being launched.
       The first profile a user launches after the refactor wins the
       legacy data; subsequent profiles start empty. Acceptable for a
       joke kiosk where realistic users have one profile.
    """
    target = paths.profile_dir(username, profile, build=build)
    home_fac = Path.home() / ".factorio"

    # --- legacy users/<u>/factorio/ migration --------------------------
    legacy_factorio = paths.user_factorio_dir(username)
    legacy_sidecar = paths.user_dir(username) / "achievements-version.txt"
    if legacy_factorio.is_dir() and not legacy_factorio.is_symlink():
        target.mkdir(parents=True, exist_ok=True)
        for item in legacy_factorio.iterdir():
            dst = target / item.name
            if not dst.exists():
                item.rename(dst)
        try:
            legacy_factorio.rmdir()
        except OSError:
            pass  # Non-empty: leftovers were already in the new profile.
    if legacy_sidecar.exists():
        new_sidecar = target / "achievements-version.txt"
        if not new_sidecar.exists():
            target.mkdir(parents=True, exist_ok=True)
            legacy_sidecar.rename(new_sidecar)

    # --- ~/.factorio symlink ------------------------------------------
    if home_fac.is_symlink():
        # Already managed — repoint to whichever profile is launching now.
        home_fac.unlink()
    elif home_fac.is_dir():
        raise RuntimeError(
            f"~/.factorio is a real directory; move it aside manually so "
            f"profile {profile} can claim the symlink"
        )
    elif home_fac.exists():
        raise RuntimeError(f"{home_fac} exists and is neither symlink nor directory")

    target.mkdir(parents=True, exist_ok=True)
    home_fac.symlink_to(target, target_is_directory=True)


def _evict_stale_achievements(
    username: str, profile: str, build: str | None, version_id: str,
) -> None:
    """Delete the profile's achievements.dat if it was written by a
    different Factorio version than the one we're about to launch.

    Factorio stores a Map-version header inside achievements.dat. If we
    launch a binary that doesn't recognise that header (different game
    version) the player sees "Failed to load local achievement data.
    Local achievements might be lost." — a benign one-time warning per
    version, but annoying when testing across versions.

    Tracked via a sidecar inside the profile dir. Same-version relaunches
    are no-ops; cross-profile launches don't interfere with each other.

    Demo (no build dimension) is skipped — guest data isn't worth the
    extra plumbing.
    """
    if build is None or version_id == paths.DEMO_VERSION:
        return
    # Derive the user-visible version string ("1.1.110") from the
    # version_id ("1.1.110-vanilla"). If the suffix doesn't match,
    # something is off and we'd rather do nothing than guess.
    suffix = f"-{build}"
    if not version_id.endswith(suffix):
        return
    current = version_id[: -len(suffix)]
    profile_root = paths.profile_dir(username, profile, build=build)
    sidecar = profile_root / "achievements-version.txt"
    last = None
    try:
        last = sidecar.read_text().strip()
    except OSError:
        pass
    if last == current:
        return
    ach = profile_root / "achievements.dat"
    if ach.exists():
        ach.unlink()
        print(
            f"evict: dropped achievements.dat for profile {profile!r} "
            f"(was {last or 'untracked'}, launching {current})",
            file=sys.stderr,
        )
    profile_root.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(current)


def _seed_service_credentials(session: Session) -> None:
    """Write service-username + service-token into ~/.factorio/player-data.json
    so the in-game mod portal skips its own login. Preserves any other
    fields already in the file (Factorio writes lots of state in there).

    Prints a one-line summary to stderr (captured in the session log) so
    you can confirm the seed actually ran without digging into the JSON.
    """
    if not (session.username and session.token):
        print(
            f"seed: skipping player-data.json — session missing "
            f"username={bool(session.username)} token={bool(session.token)}",
            file=sys.stderr,
        )
        return
    fac_dir = Path.home() / ".factorio"
    fac_dir.mkdir(parents=True, exist_ok=True)
    pd = fac_dir / "player-data.json"
    pre_existing = pd.exists()
    data: dict = {}
    if pre_existing:
        try:
            data = json.loads(pd.read_text())
        except (json.JSONDecodeError, OSError):
            data = {}
    data["service-username"] = session.username
    data["service-token"] = session.token
    pd.write_text(json.dumps(data, indent=2))
    print(
        f"seed: player-data.json written ({'patched' if pre_existing else 'created'}) "
        f"at {pd} for {session.username}",
        file=sys.stderr,
    )


def _seed_config_ini() -> None:
    """Write the [path] section of Factorio's config.ini.

    Factorio's startup defaults send both read-data and write-data into
    /usr/share/factorio (the Linux distro convention), where our `core/`
    game package isn't. Override:
      * read-data = install_dir/data (where core/ actually lives)
      * write-data = ~/.factorio (per-user via symlink)
    The __PATH__…__ tokens DO expand inside config.ini (unlike
    config-path.cfg), so this is the right place to set them.

    Earlier versions of this function also wrote [other] check-updates=false
    — but `check-updates` isn't a real config key. Factorio's parser
    rejects unknown keys with a "Configuration file has invalid contents.
    Do you want to reset it?" dialog. There's no per-config disable for
    the update check in current Factorio; the relevant valid key is
    `force-enable-factorio-version-check` and it doesn't do what its
    name suggests for our purposes.

    Preserves any other config.ini keys/sections already set.
    """
    cfg_path = Path.home() / ".factorio" / "config" / "config.ini"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg = configparser.ConfigParser()
    # Factorio's keys are case-sensitive; default ConfigParser lowercases.
    cfg.optionxform = str
    if cfg_path.exists():
        try:
            cfg.read(cfg_path)
        except configparser.Error:
            cfg = configparser.ConfigParser()
            cfg.optionxform = str
    if not cfg.has_section("path"):
        cfg.add_section("path")
    cfg.set("path", "read-data", "__PATH__executable__/../../data")
    cfg.set("path", "write-data", "__PATH__system-write-data__")
    # Drop a stale [other] check-updates=false from previous seeds —
    # if left behind, Factorio rejects the file as invalid. Also drop
    # the [other] section itself if it'd be empty after that.
    if cfg.has_section("other") and cfg.has_option("other", "check-updates"):
        cfg.remove_option("other", "check-updates")
    if cfg.has_section("other") and not cfg.options("other"):
        cfg.remove_section("other")
    with cfg_path.open("w") as f:
        cfg.write(f, space_around_delimiters=False)
    # Prepend the schema version marker. Factorio uses `; version=N` at
    # the top of config.ini as a validity check — without it the file
    # is "invalid contents" and the user is prompted to reset. As of
    # Factorio 2.0 the value is 13. configparser strips all comments
    # on read, so every seed would nuke the marker if we didn't re-add
    # it here.
    contents = cfg_path.read_text()
    if not contents.lstrip().startswith("; version="):
        cfg_path.write_text(f"; version={CONFIG_INI_VERSION}\n" + contents)
    print(f"seed: config.ini [path] at {cfg_path}", file=sys.stderr)


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


def _factorio_env(use_mimalloc: bool = True) -> dict[str, str]:
    """Inherit the greeter's env but strip the keys that would force
    Factorio onto software rendering or otherwise confuse its renderer.

    When `use_mimalloc` is True (the default), preload libmimalloc via
    LD_PRELOAD if a versioned copy is installed under /usr/lib. Scoped
    to the Factorio child only — the greeter/labwc must not inherit it.
    """
    env = os.environ.copy()
    for k in _GREETER_ONLY_ENV:
        env.pop(k, None)
    if use_mimalloc:
        lib = _mimalloc_path()
        if lib:
            existing = env.get("LD_PRELOAD", "")
            env["LD_PRELOAD"] = f"{lib}:{existing}" if existing else lib
        else:
            print(
                "factorios: mimalloc not found under /usr/lib; "
                "launching without LD_PRELOAD",
                file=sys.stderr,
            )
    return env


def _mimalloc_path() -> str | None:
    """Resolve the highest-versioned libmimalloc.so.* in /usr/lib.

    Skip the bare .so symlink so we never depend on a -devel package.
    Returns None if no versioned library is installed.
    """
    cands = [
        p for p in glob.glob("/usr/lib/libmimalloc.so.*")
        if not p.endswith(".so")
    ]
    if not cands:
        return None

    def _ver(p: str) -> tuple[int, ...]:
        return tuple(
            int(x) for x in p.rsplit(".so.", 1)[1].split(".") if x.isdigit()
        )

    return max(cands, key=_ver)
