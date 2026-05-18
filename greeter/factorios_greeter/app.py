"""FactoriOS greeter Gtk.Application — top-level wiring."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from factorios_launcher import paths
from factorios_launcher.auth import Session

from . import worker
from .chooser import ChooserScreen
from .demo import DemoScreen
from .login import LoginScreen


class GreeterWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application) -> None:
        super().__init__(application=application, title="FactoriOS")
        self.set_default_size(720, 520)
        # Don't call self.fullscreen() — under labwc on VirtualBox's vmwgfx,
        # the fullscreen mode-set triggers a DRM hot-unplug of the virtual
        # connector (~13s after start), which kills the compositor and
        # restart-loops the session. Kiosk-style fullscreening should come
        # from the compositor config, not the app.
        self._try_remembered_login()

    # --- Remember-Me bootstrap ------------------------------------------

    def _try_remembered_login(self) -> None:
        if not paths.LAST_USER.exists():
            self._show_login()
            return
        username = paths.LAST_USER.read_text().strip()
        sess_path = paths.user_session(username)
        if not sess_path.exists():
            self._show_login()
            return

        # Validate the cached session off the main thread.
        session = Session.load(sess_path)

        def check():
            return session.validate()

        def done(valid):
            if valid:
                self._show_chooser(session)
            else:
                self._show_login()

        def failed(_exc):
            self._show_login()

        worker.run(check, on_done=done, on_error=failed)

    # --- screen swaps ----------------------------------------------------

    def _show_login(self) -> None:
        self.set_child(LoginScreen(
            on_success=self._on_login_success,
            on_guest=self._show_demo,
        ))

    def _show_chooser(self, session: Session) -> None:
        self.set_child(ChooserScreen(session, on_switch_user=self._on_switch_user))

    def _show_demo(self) -> None:
        # Guest mode is one-off: deliberately do *not* touch LAST_USER, so a
        # remembered account stays remembered for the next boot.
        self.set_child(DemoScreen(on_back=self._show_login))

    # --- callbacks -------------------------------------------------------

    def _on_login_success(self, session: Session, remember: bool) -> None:
        try:
            session.save(paths.user_session(session.username))
            if remember:
                paths.LAST_USER.parent.mkdir(parents=True, exist_ok=True)
                paths.LAST_USER.write_text(session.username)
            elif paths.LAST_USER.exists():
                paths.LAST_USER.unlink()
        except PermissionError:
            # Running outside the kiosk (no /var/lib/factorios). That's fine for dev.
            pass
        self._show_chooser(session)

    def _on_switch_user(self) -> None:
        if paths.LAST_USER.exists():
            try:
                paths.LAST_USER.unlink()
            except PermissionError:
                pass
        self._show_login()


class GreeterApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="com.factorios.Greeter")

    def do_activate(self) -> None:
        window = GreeterWindow(self)
        window.present()


def main() -> int:
    return GreeterApp().run(None)
