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
        self.delete_version_button = Gtk.Button(label="Delete")
        self.delete_version_button.connect("clicked", self._on_delete_version)
        version_row.append(self.delete_version_button)
        self.append(version_row)

        # Per-build cache of (stable, experimental) from latest-releases,
        # populated lazily by _refresh_update_hint. {} = not fetched yet.
        self._releases: dict[str, tuple[str | None, str | None]] = {}
        self.update_hint = Gtk.Label(label="", xalign=0)
        self.update_hint.add_css_class("dim-label")
        self.update_hint.set_visible(False)
        self.append(self.update_hint)

        # --- Profile row -------------------------------------------------
        self.append(Gtk.Label(label="Profile", xalign=0))
        profile_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.profile_combo = Gtk.DropDown.new_from_strings([])
        self.profile_combo.set_hexpand(True)
        profile_row.append(self.profile_combo)
        self.new_profile_button = Gtk.Button(label="New profile…")
        self.new_profile_button.connect("clicked", self._on_new_profile)
        profile_row.append(self.new_profile_button)
        self.delete_profile_button = Gtk.Button(label="Delete")
        self.delete_profile_button.connect("clicked", self._on_delete_profile)
        profile_row.append(self.delete_profile_button)
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
        self._refresh_update_hint()

    # --- helpers ---------------------------------------------------------

    def _on_build_changed(self, *_args) -> None:
        idx = self.build_combo.get_selected()
        if 0 <= idx < len(self._build_order):
            self._build = self._build_order[idx]
            self._refresh_versions()
            self._refresh_profiles()
            self._refresh_update_hint()

    def _refresh_versions(self) -> None:
        installed = versions.list_installed_for_build(self._build)
        model = Gtk.StringList.new(installed or ["(none installed)"])
        self.version_combo.set_model(model)
        self.launch_button.set_sensitive(bool(installed))
        self.delete_version_button.set_sensitive(bool(installed))

    def _refresh_update_hint(self) -> None:
        """Compare latest stable for the current build against the newest
        installed version and show a hint when there's an upgrade
        available. Lazy-fetches latest-releases on first request per build
        and caches per-session (no automatic invalidation — re-login to
        refresh)."""
        build = self._build
        cached = self._releases.get(build)

        def render(stable: str | None, experimental: str | None) -> None:
            installed = versions.list_installed_for_build(build)
            newest = max(installed, key=lambda v: tuple(int(x) for x in v.split(".") if x.isdigit()), default=None) if installed else None
            parts: list[str] = []
            if stable and (newest is None or is_newer(stable, newest)):
                if newest is None:
                    parts.append(f"Latest stable: {stable}")
                else:
                    parts.append(f"Update available: {stable} (you have {newest})")
            if experimental and is_newer(experimental, stable or "") and (newest is None or is_newer(experimental, newest)):
                parts.append(f"experimental: {experimental}")
            text = " · ".join(parts)
            self.update_hint.set_label(text)
            self.update_hint.set_visible(bool(text))

        if cached is not None:
            render(*cached)
            return

        # Not fetched yet — hide hint and fetch in the background.
        self.update_hint.set_visible(False)

        def fetch():
            releases = latest_releases(self.session)
            api = paths.BUILD_API[build]
            return (
                releases.get("stable", {}).get(api),
                releases.get("experimental", {}).get(api),
            )

        def done(result):
            self._releases[build] = result
            # User may have switched build between fetch start and now; only
            # render if the current build still matches the fetched one.
            if self._build == build:
                render(*result)

        def failed(_exc):
            # Silently swallow — an update hint isn't important enough to
            # surface a network error in the status line.
            pass

        worker.run(fetch, on_done=done, on_error=failed)

    def _refresh_profiles(self) -> None:
        on_disk = profiles.list_profiles(self.session.username, build=self._build)
        profs = on_disk or [profiles.DEFAULT_PROFILE]
        self.profile_combo.set_model(Gtk.StringList.new(profs))
        # Only allow delete when a profile actually exists on disk —
        # the DEFAULT_PROFILE fallback in the dropdown is a placeholder.
        self.delete_profile_button.set_sensitive(bool(on_disk))

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

    def _on_delete_profile(self, *_args) -> None:
        profile = self._selected(self.profile_combo)
        if not profile:
            return
        build = self._build
        build_label = paths.BUILD_DISPLAY[build]

        dialog = Gtk.Window(
            title="Delete profile",
            transient_for=self.get_root(),
            modal=True,
        )
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12,
            margin_top=16, margin_bottom=16, margin_start=16, margin_end=16,
        )
        msg = Gtk.Label(
            label=f"Delete the “{profile}” {build_label} profile?\n\n"
                  "This removes the profile's mods directory. Saves and "
                  "config live at ~/.factorio and are not affected."
        )
        msg.set_wrap(True)
        msg.set_xalign(0)
        box.append(msg)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: dialog.close())
        actions.append(cancel)
        confirm = Gtk.Button(label="Delete")
        confirm.add_css_class("destructive-action")

        def on_confirm(*_):
            dialog.close()
            try:
                profiles.remove(self.session.username, profile, build=build)
                self.status.set_label(f"Deleted profile “{profile}”.")
            except OSError as e:
                self.status.set_label(f"Delete failed: {e}")
            self._refresh_profiles()

        confirm.connect("clicked", on_confirm)
        actions.append(confirm)
        box.append(actions)
        dialog.set_child(box)
        dialog.present()

    def _on_delete_version(self, *_args) -> None:
        version = self._selected(self.version_combo)
        if not version or version == "(none installed)":
            return
        build = self._build
        build_label = paths.BUILD_DISPLAY[build]

        dialog = Gtk.Window(
            title="Delete version",
            transient_for=self.get_root(),
            modal=True,
        )
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12,
            margin_top=16, margin_bottom=16, margin_start=16, margin_end=16,
        )
        msg = Gtk.Label(label=f"Remove {build_label} {version}?\n\nSaves and mods are kept; only the game files are deleted.")
        msg.set_wrap(True)
        msg.set_xalign(0)
        box.append(msg)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: dialog.close())
        actions.append(cancel)
        confirm = Gtk.Button(label="Delete")
        confirm.add_css_class("destructive-action")

        def on_confirm(*_):
            dialog.close()
            try:
                versions.remove(version, build)
                self.status.set_label(f"Removed {build_label} {version}.")
            except OSError as e:
                self.status.set_label(f"Delete failed: {e}")
            self._refresh_versions()

        confirm.connect("clicked", on_confirm)
        actions.append(confirm)
        box.append(actions)
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
            self._refresh_update_hint()

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
