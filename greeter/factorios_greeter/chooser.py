"""Build + version + profile chooser. Launches Factorio and waits for exit.

Layout: if the signed-in user owns Space Age, a Build dropdown is shown
above the version/profile selectors and controls what they list. If they
own only Vanilla, the Build row is hidden and the build is fixed to vanilla.
"""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from factorios_launcher import paths, profiles, versions
from factorios_launcher.auth import Session
from factorios_launcher.download import ProgressStats, is_newer, latest_releases

from . import worker


class ChooserScreen(Gtk.Box):
    """Pick a build + version + profile and launch Factorio.

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

        # Default build = Space Age if owned, else Vanilla.
        self._build = paths.DEFAULT_BUILD if session.has_space_age else paths.BUILD_VANILLA

        header = Gtk.Label(label=f"Signed in as {session.username}")
        header.add_css_class("title-2")
        self.append(header)

        # --- Build row (hidden if user only owns Vanilla) ----------------
        self.build_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.build_row.append(Gtk.Label(label="Build", xalign=0))
        # Always include both labels in display order Space Age, Vanilla so
        # the default selection (Space Age) is index 0 when shown.
        build_labels = [paths.BUILD_DISPLAY[b] for b in (paths.BUILD_SPACE_AGE, paths.BUILD_VANILLA)]
        self._build_order = (paths.BUILD_SPACE_AGE, paths.BUILD_VANILLA)
        self.build_combo = Gtk.DropDown.new_from_strings(build_labels)
        self.build_combo.connect("notify::selected", self._on_build_changed)
        self.build_row.append(self.build_combo)
        self.append(self.build_row)
        self.build_row.set_visible(session.has_space_age)

        # --- Version row -------------------------------------------------
        self.append(Gtk.Label(label="Version", xalign=0))
        version_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.version_combo = Gtk.DropDown.new_from_strings([])
        self.version_combo.set_hexpand(True)
        version_row.append(self.version_combo)
        self.install_button = Gtk.Button(label="Install…")
        self.install_button.connect("clicked", self._on_install_clicked)
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
        self.progress.set_show_text(True)
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

    def _on_build_changed(self, *_args) -> None:
        idx = self.build_combo.get_selected()
        if 0 <= idx < len(self._build_order):
            self._build = self._build_order[idx]
            self._refresh_versions()
            self._refresh_profiles()

    def _refresh_versions(self) -> None:
        installed = versions.list_installed_for_build(self._build)
        model = Gtk.StringList.new(installed or ["(none installed)"])
        self.version_combo.set_model(model)
        self.launch_button.set_sensitive(bool(installed))

    def _refresh_profiles(self) -> None:
        profs = profiles.list_profiles(self.session.username, build=self._build) or [profiles.DEFAULT_PROFILE]
        self.profile_combo.set_model(Gtk.StringList.new(profs))

    def _selected(self, combo: Gtk.DropDown) -> str | None:
        model = combo.get_model()
        idx = combo.get_selected()
        if model is None or idx == Gtk.INVALID_LIST_POSITION:
            return None
        item = model.get_item(idx)
        return item.get_string() if item else None

    # --- actions ---------------------------------------------------------

    def _on_install_clicked(self, *_args) -> None:
        """Look up available releases, then show a dialog letting the
        user pick latest stable, latest experimental (if newer), or any
        specific version."""
        build = self._build
        build_label = paths.BUILD_DISPLAY[build]
        self.install_button.set_sensitive(False)
        self.status.set_label(f"Looking up {build_label} releases…")

        def fetch():
            releases = latest_releases(self.session)
            api = paths.BUILD_API[build]
            stable = releases.get("stable", {}).get(api)
            experimental = releases.get("experimental", {}).get(api)
            return stable, experimental

        def show(result):
            stable, experimental = result
            self.install_button.set_sensitive(True)
            self.status.set_label("")
            self._show_install_dialog(stable, experimental)

        def failed(exc):
            self.install_button.set_sensitive(True)
            self.status.set_label(f"Lookup failed: {exc}")

        worker.run(fetch, on_done=show, on_error=failed)

    def _show_install_dialog(self, stable: str | None, experimental: str | None) -> None:
        dialog = Gtk.Window(
            title=f"Install {paths.BUILD_DISPLAY[self._build]}",
            transient_for=self.get_root(),
            modal=True,
        )
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8,
            margin_top=16, margin_bottom=16, margin_start=16, margin_end=16,
        )

        stable_btn: Gtk.CheckButton | None = None
        exp_btn: Gtk.CheckButton | None = None

        if stable:
            stable_btn = Gtk.CheckButton.new_with_label(f"Latest stable ({stable})")
            stable_btn.set_active(True)
            box.append(stable_btn)

        # Only show experimental if it's actually newer than stable —
        # otherwise it's the same thing under another name.
        if experimental and (not stable or is_newer(experimental, stable)):
            exp_btn = Gtk.CheckButton.new_with_label(f"Latest experimental ({experimental})")
            if stable_btn is not None:
                exp_btn.set_group(stable_btn)
            else:
                exp_btn.set_active(True)
            box.append(exp_btn)

        custom_btn = Gtk.CheckButton.new_with_label("Specific version:")
        if stable_btn is not None:
            custom_btn.set_group(stable_btn)
        elif exp_btn is not None:
            custom_btn.set_group(exp_btn)
        else:
            custom_btn.set_active(True)
        box.append(custom_btn)

        version_entry = Gtk.Entry(placeholder_text="e.g. 1.1.110")
        version_entry.set_margin_start(24)
        # Auto-select the radio when the user types into the entry.
        version_entry.connect("changed", lambda *_: custom_btn.set_active(True))
        box.append(version_entry)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        actions.set_margin_top(8)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: dialog.close())
        actions.append(cancel)
        install = Gtk.Button(label="Install")
        install.add_css_class("suggested-action")
        actions.append(install)
        box.append(actions)

        def on_install(*_):
            if stable_btn is not None and stable_btn.get_active():
                version = stable
            elif exp_btn is not None and exp_btn.get_active():
                version = experimental
            else:
                version = version_entry.get_text().strip()
            if not version:
                return
            dialog.close()
            self._do_install(version)

        install.connect("clicked", on_install)
        version_entry.connect("activate", on_install)
        dialog.set_child(box)
        dialog.present()

    def _do_install(self, version: str) -> None:
        build = self._build
        build_label = paths.BUILD_DISPLAY[build]
        self.install_button.set_sensitive(False)
        self.status.set_label(f"Installing {build_label} {version}…")
        self.progress.set_visible(True)
        self.progress.set_fraction(0.0)
        self.progress.set_text("")

        stats = ProgressStats()

        def push():
            self.progress.set_fraction(stats.fraction)
            self.progress.set_text(stats.label())
            return False

        def cb(done, total):
            stats.update(done, total)
            GLib.idle_add(push)

        def do_install():
            versions.install(self.session, version, build=build, progress=cb)
            return version

        def done(_version):
            self.install_button.set_sensitive(True)
            self.progress.set_visible(False)
            self.status.set_label(f"Installed {build_label} {version}.")
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
                profiles.ensure(self.session.username, name, build=self._build)
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
        build = self._build
        if not version or version == "(none installed)":
            self.status.set_label(f"No {paths.BUILD_DISPLAY[build]} version installed. Click 'Install latest' first.")
            return
        self.status.set_label(f"Launching Factorio {version} ({paths.BUILD_DISPLAY[build]})…")
        self.launch_button.set_sensitive(False)

        def do_launch():
            vid = paths.version_id(version, build)
            p = profiles.launch(vid, self.session.username, profile, build=build)
            return p.wait()

        def done(rc):
            self.launch_button.set_sensitive(True)
            self.status.set_label(f"Factorio exited (status {rc}).")

        def failed(exc):
            self.launch_button.set_sensitive(True)
            self.status.set_label(f"Launch failed: {exc}")

        worker.run(do_launch, on_done=done, on_error=failed)
