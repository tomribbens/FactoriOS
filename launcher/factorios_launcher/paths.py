"""Single source of truth for FactoriOS on-disk layout."""

from pathlib import Path

ROOT = Path("/var/lib/factorios")
VERSIONS = ROOT / "versions"
USERS = ROOT / "users"
LAST_USER = ROOT / "last-user"

# Reserved names for the guest/demo flow. factorio.com usernames are
# alphanumeric, so a leading underscore can never collide with a real one.
GUEST_USER = "_guest"
DEMO_VERSION = "_demo"


def user_dir(username: str) -> Path:
    return USERS / username


def user_session(username: str) -> Path:
    return user_dir(username) / "session.json"


def user_profiles(username: str) -> Path:
    return user_dir(username) / "profiles"


def profile_dir(username: str, profile: str) -> Path:
    return user_profiles(username) / profile


def version_dir(version: str) -> Path:
    return VERSIONS / version


def factorio_binary(version: str) -> Path:
    # Layout inside the official linux64 tarball.
    return version_dir(version) / "bin" / "x64" / "factorio"
