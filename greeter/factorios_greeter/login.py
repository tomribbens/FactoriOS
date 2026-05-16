"""Login screen: factorio.com username + password + Remember Me."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from factorios_launcher.auth import AuthError, Session

from . import worker


class LoginScreen(Gtk.Box):
    """Emits `on_success(session, remember)` when login succeeds, or
    `on_guest()` when the user picks the demo path.
    """

    def __init__(
        self,
        on_success: Callable[[Session, bool], None],
        on_guest: Callable[[], None],
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(80)
        self.set_margin_bottom(80)
        self.set_margin_start(120)
        self.set_margin_end(120)
        self._on_success = on_success
        self._on_guest = on_guest

        title = Gtk.Label(label="FactoriOS")
        title.add_css_class("title-1")
        self.append(title)

        subtitle = Gtk.Label(label="Sign in with your factorio.com account")
        subtitle.add_css_class("dim-label")
        self.append(subtitle)

        self.user_entry = Gtk.Entry(placeholder_text="Username or email")
        self.append(self.user_entry)

        self.pass_entry = Gtk.PasswordEntry(show_peek_icon=True)
        self.append(self.pass_entry)

        self.remember = Gtk.CheckButton(label="Remember me on this machine")
        self.append(self.remember)

        self.status = Gtk.Label(label="")
        self.status.add_css_class("error")
        self.append(self.status)

        self.button = Gtk.Button(label="Sign in")
        self.button.add_css_class("suggested-action")
        self.button.connect("clicked", self._on_clicked)
        self.append(self.button)

        # Guest path — downloads and plays the demo, no account needed.
        guest = Gtk.Button(label="Play demo (no account needed)")
        guest.add_css_class("flat")
        guest.set_halign(Gtk.Align.CENTER)
        guest.connect("clicked", lambda *_: self._on_guest())
        self.append(guest)

        # Submit on Enter from either entry.
        self.user_entry.connect("activate", lambda *_: self.pass_entry.grab_focus())
        self.pass_entry.connect("activate", self._on_clicked)

    def _set_busy(self, busy: bool) -> None:
        self.button.set_sensitive(not busy)
        self.user_entry.set_sensitive(not busy)
        self.pass_entry.set_sensitive(not busy)
        self.button.set_label("Signing in…" if busy else "Sign in")

    def _on_clicked(self, *_args) -> None:
        username = self.user_entry.get_text().strip()
        password = self.pass_entry.get_text()
        if not username or not password:
            self.status.set_label("Username and password are required.")
            return
        self.status.set_label("")
        self._set_busy(True)

        def do_login():
            return Session().login(username, password)

        def done(session):
            self._set_busy(False)
            self._on_success(session, self.remember.get_active())

        def failed(exc):
            self._set_busy(False)
            if isinstance(exc, AuthError):
                self.status.set_label(str(exc))
            else:
                self.status.set_label(f"Network error: {exc}")

        worker.run(do_login, on_done=done, on_error=failed)
