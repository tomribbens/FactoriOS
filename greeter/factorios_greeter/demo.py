"""Guest/demo screen — no auth, no version picker, no profile picker.

Downloads the Factorio demo if needed, launches it, then offers to go back
to the login screen when the game exits.
"""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from factorios_launcher import paths, profiles, versions
from factorios_launcher.auth import Session

from . import worker


class DemoScreen(Gtk.Box):
    """Self-driving demo screen. Auto-starts download + launch on construction."""

    def __init__(self, on_back: Callable[[], None]) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(120)
        self.set_margin_bottom(120)
        self.set_margin_start(120)
        self.set_margin_end(120)
        self._on_back = on_back

        title = Gtk.Label(label="Factorio Demo")
        title.add_css_class("title-1")
        self.append(title)

        self.status = Gtk.Label(label="Preparing…")
        self.status.add_css_class("dim-label")
        self.append(self.status)

        self.progress = Gtk.ProgressBar()
        self.progress.set_visible(False)
        self.append(self.progress)

        self.back_button = Gtk.Button(label="Back to sign-in")
        self.back_button.set_halign(Gtk.Align.CENTER)
        self.back_button.connect("clicked", lambda *_: self._on_back())
        self.append(self.back_button)

        self._start()

    def _start(self) -> None:
        # If the demo isn't installed yet, download then launch. Otherwise
        # jump straight to launch.
        if paths.factorio_binary(paths.DEMO_VERSION).is_file():
            self._launch()
        else:
            self._download_then_launch()

    def _download_then_launch(self) -> None:
        self.status.set_label("Downloading demo…")
        self.progress.set_visible(True)
        self.progress.set_fraction(0.0)
        self.back_button.set_sensitive(False)

        def cb(done, total):
            if total:
                GLib.idle_add(self.progress.set_fraction, done / total)

        def do_download():
            versions.install_demo(Session(), progress=cb)

        def done(_):
            self.progress.set_visible(False)
            self.back_button.set_sensitive(True)
            self._launch()

        def failed(exc):
            self.progress.set_visible(False)
            self.back_button.set_sensitive(True)
            self.status.set_label(f"Download failed: {exc}")

        worker.run(do_download, on_done=done, on_error=failed)

    def _launch(self) -> None:
        self.status.set_label("Launching Factorio demo…")
        self.back_button.set_sensitive(False)

        def do_launch():
            p = profiles.launch(paths.DEMO_VERSION, paths.GUEST_USER, profiles.DEFAULT_PROFILE)
            return p.wait()

        def done(rc):
            self.back_button.set_sensitive(True)
            self.status.set_label(f"Demo exited (status {rc}).")

        def failed(exc):
            self.back_button.set_sensitive(True)
            self.status.set_label(f"Launch failed: {exc}")

        worker.run(do_launch, on_done=done, on_error=failed)
