"""Single source of truth for FactoriOS on-disk layout and build identifiers."""

from pathlib import Path

ROOT = Path("/var/lib/factorios")
VERSIONS = ROOT / "versions"
USERS = ROOT / "users"
LAST_USER = ROOT / "last-user"

# Reserved names for the guest/demo flow. factorio.com usernames are
# alphanumeric, so a leading underscore can never collide with a real one.
GUEST_USER = "_guest"
DEMO_VERSION = "_demo"

# Build identifiers. The user-facing names (vanilla, space-age) map to
# factorio.com's internal build names (alpha, expansion). These map both
# directions here so the rest of the codebase never deals in alpha/expansion.
BUILD_VANILLA = "vanilla"
BUILD_SPACE_AGE = "space-age"
ALL_BUILDS = (BUILD_VANILLA, BUILD_SPACE_AGE)
BUILD_DISPLAY = {
    BUILD_VANILLA: "Vanilla",
    BUILD_SPACE_AGE: "Space Age",
}
BUILD_API = {
    BUILD_VANILLA: "alpha",
    BUILD_SPACE_AGE: "expansion",
}
DEFAULT_BUILD = BUILD_SPACE_AGE  # used when the user owns both


# --- users / sessions / profiles --------------------------------------

def user_dir(username: str) -> Path:
    return USERS / username


def user_session(username: str) -> Path:
    return user_dir(username) / "session.json"


def user_profiles(username: str, build: str | None = None) -> Path:
    """Profiles root for a user. Build-segregated for real accounts, flat
    for the guest/demo flow."""
    base = user_dir(username) / "profiles"
    return base / build if build is not None else base


def profile_dir(username: str, profile: str, build: str | None = None) -> Path:
    return user_profiles(username, build) / profile


# --- versions ---------------------------------------------------------

def version_id(version: str, build: str) -> str:
    """The on-disk identifier for an authenticated install. Demo passes
    DEMO_VERSION directly and skips this."""
    return f"{version}-{build}"


def version_dir(version_id: str) -> Path:
    return VERSIONS / version_id


def factorio_binary(version_id: str) -> Path:
    # Layout inside the official linux64 tarball.
    return version_dir(version_id) / "bin" / "x64" / "factorio"
