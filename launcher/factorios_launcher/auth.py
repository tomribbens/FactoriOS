"""factorio.com session login + Space Age entitlement detection.

The factorio.com login flow is form-based with a CSRF token embedded in the
login page. We GET the page, scrape the token, POST credentials, and keep the
resulting session cookie for downloads and the profile page.

After successful login (and after re-validating a cached session) we also
HEAD the expansion download endpoint to detect whether the account owns the
Space Age DLC. A successful redirect to dl.factorio.com means yes; anything
else (redirect to login/buy, 4xx) means no.
"""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path

import requests

from . import paths

LOGIN_URL = "https://www.factorio.com/login"
PROFILE_URL = "https://www.factorio.com/profile"
EXPANSION_PROBE_URL = "https://www.factorio.com/get-download/latest/expansion/linux64"
USER_AGENT = "FactoriOS-greeter/0.1"


class AuthError(Exception):
    """Raised when login fails or a cached session is no longer valid."""


class _CSRFParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.token: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag != "input":
            return
        a = dict(attrs)
        if a.get("name") == "csrf_token":
            self.token = a.get("value")


class Session:
    """A logged-in factorio.com session.

    Owns a `requests.Session` so cookies persist across calls. Serializable to
    JSON for the Remember-Me path. Tracks Space Age entitlement on
    `has_space_age`; re-checked on every login or successful validate, never
    persisted.
    """

    def __init__(self) -> None:
        self.http = requests.Session()
        self.http.headers["User-Agent"] = USER_AGENT
        self.username: str | None = None
        self.has_space_age: bool = False

    def login(self, username_or_email: str, password: str) -> "Session":
        r = self.http.get(LOGIN_URL, timeout=30)
        r.raise_for_status()
        parser = _CSRFParser()
        parser.feed(r.text)
        if not parser.token:
            raise AuthError("could not find csrf_token on the login page")

        r = self.http.post(
            LOGIN_URL,
            data={
                "csrf_token": parser.token,
                "username_or_email": username_or_email,
                "password": password,
            },
            timeout=30,
            allow_redirects=True,
        )
        r.raise_for_status()
        # If the POST left us back on /login, the server rejected the credentials.
        if r.url.rstrip("/").endswith("/login"):
            raise AuthError("invalid factorio.com credentials")
        self.username = username_or_email
        self.check_entitlements()
        return self

    def validate(self) -> bool:
        """Cheap check that the cached session still works. Refreshes
        `has_space_age` as a side effect when the session is valid."""
        r = self.http.get(PROFILE_URL, timeout=15, allow_redirects=False)
        if r.status_code != 200:
            return False
        self.check_entitlements()
        return True

    def check_entitlements(self) -> bool:
        """HEAD the expansion download endpoint and set `has_space_age`.

        Owns Space Age: server issues the redirect to dl.factorio.com (or
        in theory serves 200 directly). Doesn't own it: bounced to /login or
        a purchase page, or 4xx.
        """
        try:
            r = self.http.head(EXPANSION_PROBE_URL, timeout=15, allow_redirects=False)
        except requests.RequestException:
            self.has_space_age = False
            return False
        location = r.headers.get("location", "")
        if r.status_code == 200:
            self.has_space_age = True
        elif r.is_redirect and "dl.factorio.com" in location:
            self.has_space_age = True
        else:
            self.has_space_age = False
        return self.has_space_age

    # --- serialization ---------------------------------------------------

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "username": self.username,
            "cookies": [
                {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
                for c in self.http.cookies
            ],
        }
        # Root-owned, mode 600. We're a single-purpose appliance — cookies on
        # disk are effectively plaintext-equivalent either way.
        path.write_text(json.dumps(data))
        path.chmod(0o600)

    @classmethod
    def load(cls, path: Path) -> "Session":
        data = json.loads(path.read_text())
        s = cls()
        s.username = data.get("username")
        for c in data.get("cookies", []):
            s.http.cookies.set(c["name"], c["value"], domain=c["domain"], path=c["path"])
        return s
