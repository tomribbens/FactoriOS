"""factorio.com session login.

The factorio.com login flow is form-based with a CSRF token embedded in the
login page. We GET the page, scrape the token, POST credentials, and keep the
resulting session cookie for downloads and the profile page.
"""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path

import requests

LOGIN_URL = "https://www.factorio.com/login"
PROFILE_URL = "https://www.factorio.com/profile"
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
    JSON for the Remember-Me path.
    """

    def __init__(self) -> None:
        self.http = requests.Session()
        self.http.headers["User-Agent"] = USER_AGENT
        self.username: str | None = None

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
        return self

    def validate(self) -> bool:
        """Cheap check that the cached session still works."""
        r = self.http.get(PROFILE_URL, timeout=15, allow_redirects=False)
        return r.status_code == 200

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
