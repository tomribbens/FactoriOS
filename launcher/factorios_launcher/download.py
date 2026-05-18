"""Factorio binary download via the authenticated session."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .auth import Session

GET_DOWNLOAD = "https://www.factorio.com/get-download/{version}/{build}/{distro}"
LATEST_RELEASES = "https://factorio.com/api/latest-releases"

ProgressCb = Callable[[int, int], None]  # (bytes_done, bytes_total)


def latest_releases(session: Session) -> dict:
    """Public endpoint — works even without login."""
    r = session.http.get(LATEST_RELEASES, timeout=15)
    r.raise_for_status()
    return r.json()


def download(
    session: Session,
    dest: Path,
    version: str = "latest",
    build: str = "alpha",
    distro: str = "linux64",
    progress: ProgressCb | None = None,
) -> Path:
    url = GET_DOWNLOAD.format(version=version, build=build, distro=distro)
    # Authenticated builds (alpha, expansion) need ?username=&token=.
    # The public demo build accepts requests with no params.
    params: dict[str, str] = {}
    if session.username and session.token:
        params = {"username": session.username, "token": session.token}
    with session.http.get(url, params=params, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(64 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    return dest
