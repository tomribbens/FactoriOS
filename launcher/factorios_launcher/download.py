"""Factorio binary download via the authenticated session."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .auth import Session

GET_DOWNLOAD = "https://www.factorio.com/get-download/{version}/{build}/{distro}"
LATEST_RELEASES = "https://factorio.com/api/latest-releases"

ProgressCb = Callable[[int, int], None]  # (bytes_done, bytes_total)


@dataclass
class ProgressStats:
    """Tracks a download's progress + derived rate/ETA for display.

    Cheap to update — meant to be called from a streaming progress
    callback on every chunk. UI reads `fraction` and `label` to refresh
    a progress bar.
    """

    done: int = 0
    total: int = 0
    start: float = field(default_factory=time.monotonic)

    def update(self, done: int, total: int) -> None:
        self.done = done
        # Some servers don't send Content-Length until later; accept any
        # non-zero `total` we see and keep it.
        if total:
            self.total = total

    @property
    def elapsed(self) -> float:
        return max(time.monotonic() - self.start, 1e-6)

    @property
    def fraction(self) -> float:
        return (self.done / self.total) if self.total else 0.0

    @property
    def rate_bps(self) -> float:
        return self.done / self.elapsed

    @property
    def eta_seconds(self) -> float | None:
        if not self.total or self.done >= self.total:
            return None
        rate = self.rate_bps
        if rate <= 0:
            return None
        return (self.total - self.done) / rate

    def label(self) -> str:
        """One-line summary suitable for a Gtk.ProgressBar text."""
        done_mb = self.done / 1_000_000
        if self.total:
            total_mb = self.total / 1_000_000
            pct = self.fraction * 100
            size = f"{done_mb:.1f} / {total_mb:.1f} MB ({pct:.0f}%)"
        else:
            size = f"{done_mb:.1f} MB"
        rate = self.rate_bps / 1_000_000
        eta = self.eta_seconds
        if eta is None:
            return f"{size} · {rate:.1f} MB/s"
        return f"{size} · {rate:.1f} MB/s · {_format_eta(eta)} left"


def _format_eta(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60:02d}s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m:02d}m"


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
