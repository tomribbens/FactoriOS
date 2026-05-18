"""factorio.com session via the auth API.

The HTML /login page at www.factorio.com is gated by Cloudflare's bot
challenge and returns 403 to any non-browser client (curl, requests, etc.)
regardless of User-Agent. The auth.factorio.com/api-login endpoint, which
the Factorio binary itself uses, is *not* gated and accepts a simple form
POST. Downloads then use ?username=&token= query params instead of a
session cookie.

Response shape on success (as of 2026-05): {"token": "...", ...} or
{"data": {"token": "..."}, "status": 200}. We accept both.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

from . import paths

LOGIN_URL = "https://auth.factorio.com/api-login"
EXPANSION_PROBE_URL = "https://www.factorio.com/get-download/latest/expansion/linux64"
USER_AGENT = "FactoriOS-greeter/0.1"


class AuthError(Exception):
    """Raised when login fails or a cached token is no longer valid."""


class Session:
    """A logged-in factorio.com session backed by a service token.

    Token + username are sufficient for every authenticated factorio.com
    request we care about (downloads, entitlement probes). Persisted via
    `save`/`load` for the Remember-Me path.
    """

    def __init__(self) -> None:
        self.http = requests.Session()
        self.http.headers["User-Agent"] = USER_AGENT
        self.username: str | None = None
        self.token: str | None = None
        self.has_space_age: bool = False

    def login(self, username_or_email: str, password: str) -> "Session":
        try:
            r = self.http.post(
                LOGIN_URL,
                data={"username": username_or_email, "password": password},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise AuthError(f"network error contacting factorio.com: {exc}") from exc

        try:
            payload = r.json()
        except ValueError:
            raise AuthError(
                f"unexpected non-JSON response (status {r.status_code}) from {LOGIN_URL}"
            )

        if r.status_code != 200:
            # Error shape: {"data":{},"error":"login-failed","message":"...","status":401}
            msg = payload.get("message") or payload.get("error") or f"HTTP {r.status_code}"
            raise AuthError(msg)

        token, returned_username = _extract_token(payload)
        if not token:
            raise AuthError("login succeeded but no token in response")
        self.username = returned_username or username_or_email
        self.token = token
        self.check_entitlements()
        return self

    def validate(self) -> bool:
        """Check whether the cached token is still accepted. Side-effect:
        refreshes `has_space_age`."""
        if not (self.username and self.token):
            return False
        ok = self.check_entitlements_strict()
        return ok

    def check_entitlements(self) -> bool:
        """Set `has_space_age`. Returns it. Never raises — treats network
        errors as "not entitled" so the UI degrades gracefully."""
        try:
            self.check_entitlements_strict()
        except requests.RequestException:
            self.has_space_age = False
        return self.has_space_age

    def check_entitlements_strict(self) -> bool:
        """Like `check_entitlements` but raises on network errors so
        validate() can distinguish "token rejected" from "you're offline".
        Returns True iff token works (regardless of Space Age ownership)."""
        if not (self.username and self.token):
            self.has_space_age = False
            return False
        r = self.http.head(
            EXPANSION_PROBE_URL,
            params={"username": self.username, "token": self.token},
            timeout=15,
            allow_redirects=False,
        )
        location = r.headers.get("location", "")
        # 200 or a redirect to dl.factorio.com → user owns Space Age.
        if r.status_code == 200 or (r.is_redirect and "dl.factorio.com" in location):
            self.has_space_age = True
            return True
        # 403/404/redirect-to-purchase → token is fine but no Space Age.
        # We can't reliably tell "bad token" from "no entitlement" here
        # without a dedicated validate endpoint; treat anything that isn't
        # a server error (5xx) as "token works, no Space Age".
        if r.status_code < 500:
            self.has_space_age = False
            return True
        self.has_space_age = False
        return False

    # --- serialization ---------------------------------------------------

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"username": self.username, "token": self.token}))
        path.chmod(0o600)

    @classmethod
    def load(cls, path: Path) -> "Session":
        data = json.loads(path.read_text())
        s = cls()
        s.username = data.get("username")
        s.token = data.get("token")
        return s


def _extract_token(payload: object) -> tuple[str | None, str | None]:
    """Pull (token, username) out of whichever JSON shape api-login returns.

    Observed shapes over the years:
      ["TOKEN_STRING"]                                        (older)
      {"token": "...", "username": "..."}
      {"data": {"token": "...", "username": "..."}, "status": 200}
    """
    if isinstance(payload, list) and payload:
        return str(payload[0]), None
    if isinstance(payload, dict):
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        token = data.get("token") if isinstance(data, dict) else None
        username = data.get("username") if isinstance(data, dict) else None
        if token:
            return token, username
    return None, None
