"""Version + profile chooser. Launches Factorio and waits for it to exit."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from factorios_launcher import profiles, versions
from factorios_launcher.auth import Session
from factorios_launcher.download import latest_releases

from . import worker


class ChooserScreen(Gtk.Box):
    """Pick a version + profile and launch Factorio.

    `on_switch_user` is called when the user wants to log out.
    """

    def __init__(self, session: Session, on_switch_user: Callable[[], None]) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(40)
        self.set_margin_bottom(40)
        self.set_margin_start(80)
        self.set_margin_end(80)
        self.session = session
        self._on_switch_user = on_switch_user

        header = Gtk.Label(label=f"Signed in as {session.username}")
        header.add_css_class("title-2")
        self.append(header)

        # --- Version row -------------------------------------------------
        self.append(Gtk.Label(label="Factorio version", xalign=0))
        version_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.version_combo = Gtk.DropDown.new_from_strings([])
        self.version_combo.set_hexpand(True)
        version_row.append(self.version_combo)
        self.install_button = Gtk.Button(label="Install latest")
        self.install_button.connect("clicked", self._on_install_latest)
        version_row.append(self.install_button)
        self.append(version_row)

        # --- Profile row -------------------------------------------------
        self.append(Gtk.Label(label="Profile", xalign=0))
        profile_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.profile_combo = Gtk.DropDown.new_from_strings([])
        self.profile_combo.set_hexpand(True)
        profile_row.append(self.profile_combo)
        self.new_profile_button = Gtk.Button(label="New profile…")
        self.new_profile_button.connect("clicked", self._on_new_profile)
        profile_row.append(self.new_profile_button)
        self.append(profile_row)

        # --- Status + progress ------------------------------------------
        self.status = Gtk.Label(label="")
        self.status.add_css_class("dim-label")
        self.append(self.status)

        self.progress = Gtk.ProgressBar()
        self.progress.set_visible(False)
        self.append(self.progress)

        # --- Actions -----------------------------------------------------
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        switch = Gtk.Button(label="Switch user")
        switch.connect("clicked", lambda *_: self._on_switch_user())
        actions.append(switch)
        self.launch_button = Gtk.Button(label="Launch")
        self.launch_button.add_css_class("suggested-action")
        self.launch_button.connect("clicked", self._on_launch)
        actions.append(self.launch_button)
        self.append(actions)

        self._refresh_versions()
        self._refresh_profiles()

    # --- helpers ---------------------------------------------------------

    def _refresh_versions(self) -> None:
        installed = versions.list_installed()
        model = Gtk.StringList.new(installed or ["(none installed)"])
        self.version_combo.set_model(model)
        self.launch_button.set_sensitive(bool(installed))

    def _refresh_profiles(self) -> None:
        profs = profiles.list_profiles(self.session.username) or [profiles.DEFAULT_PROFILE]
        self.profile_combo.set_model(Gtk.StringList.new(profs))

    def _selected(self, combo: Gtk.DropDown) -> str | None:
        model = combo.get_model()
        idx = combo.get_selected()
        if model is None or idx == Gtk.INVALID_LIST_POSITION:
            return None
        item = model.get_item(idx)
        return item.get_string() if item else None

    # --- actions ---------------------------------------------------------

    def _on_install_latest(self, *_args) -> None:
        self.install_button.set_sensitive(False)
        self.status.set_label("Looking up latest release…")
        self.progress.set_visible(True)
        self.progress.set_fraction(0.0)

        def do_install():
            releases = latest_releases(self.session)
            version = releases["stable"]["alpha"]
            def progress(done, total):
                from gi.repository import GLib
                if total:
                    GLib.idle_add(self.progress.set_fraction, done / total)
            versions.install(self.session, version, progress=progress)
            return version

        def done(version):
            self.install_button.set_sensitive(True)
            self.progress.set_visible(False)
            self.status.set_label(f"Installed Factorio {version}.")
            self._refresh_versions()

        def failed(exc):
            self.install_button.set_sensitive(True)
            self.progress.set_visible(False)
            self.status.set_label(f"Install failed: {exc}")

        worker.run(do_install, on_done=done, on_error=failed)

    def _on_new_profile(self, *_args) -> None:
        dialog = Gtk.Window(title="New profile", transient_for=self.get_root(), modal=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        entry = Gtk.Entry(placeholder_text="Profile name")
        box.append(entry)
        confirm = Gtk.Button(label="Create")

        def on_confirm(*_):
            name = entry.get_text().strip()
            if name:
                profiles.ensure(self.session.username, name)
                self._refresh_profiles()
            dialog.close()

        confirm.connect("clicked", on_confirm)
        entry.connect("activate", on_confirm)
        box.append(confirm)
        dialog.set_child(box)
        dialog.present()

    def _on_launch(self, *_args) -> None:
        version = self._selected(self.version_combo)
        profile = self._selected(self.profile_combo) or profiles.DEFAULT_PROFILE
        if not version or version == "(none installed)":
            self.status.set_label("No version installed. Click 'Install latest' first.")
            return
        self.status.set_label(f"Launching Factorio {version}…")
        self.launch_button.set_sensitive(False)

        def do_launch():
            p = profiles.launch(version, self.session.username, profile)
            return p.wait()

        def done(rc):
            self.launch_button.set_sensitive(True)
            self.status.set_label(f"Factorio exited (status {rc}).")

        def failed(exc):
            self.launch_button.set_sensitive(True)
            self.status.set_label(f"Launch failed: {exc}")

        worker.run(do_launch, on_done=done, on_error=failed)
