"""Check for and install Arch + factorios-* package updates.

Relies on a sudoers.d rule shipped by factorios-base that lets the
factorios user run two exact pacman invocations without password:

    sudo /usr/bin/pacman -Sy
    sudo /usr/bin/pacman --noconfirm -Syu

Anything else still prompts for a password and will fail in this kiosk
environment — which is the point.
"""

from __future__ import annotations

import subprocess

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from . import worker

PACMAN_REFRESH = ["sudo", "/usr/bin/pacman", "-Sy"]
PACMAN_UPGRADE = ["sudo", "/usr/bin/pacman", "--noconfirm", "-Syu"]


def show_dialog(parent: Gtk.Widget) -> None:
    dialog = Gtk.Window(
        title="Updates", transient_for=parent.get_root(), modal=True,
    )
    dialog.set_default_size(600, 420)

    box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=10,
        margin_top=16, margin_bottom=16, margin_start=16, margin_end=16,
    )

    status = Gtk.Label(label="Checking for updates…", xalign=0)
    box.append(status)

    spinner = Gtk.Spinner()
    spinner.start()
    spinner.set_halign(Gtk.Align.START)
    box.append(spinner)

    scroller = Gtk.ScrolledWindow()
    scroller.set_vexpand(True)
    scroller.set_visible(False)
    text_view = Gtk.TextView()
    text_view.set_editable(False)
    text_view.set_monospace(True)
    scroller.set_child(text_view)
    box.append(scroller)

    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    actions.set_halign(Gtk.Align.END)
    close_btn = Gtk.Button(label="Close")
    close_btn.connect("clicked", lambda *_: dialog.close())
    actions.append(close_btn)
    install_btn = Gtk.Button(label="Install updates")
    install_btn.add_css_class("suggested-action")
    install_btn.set_sensitive(False)
    actions.append(install_btn)
    box.append(actions)

    dialog.set_child(box)
    dialog.present()

    def check() -> str:
        # -Sy doesn't fetch packages, just refreshes the DB. -Qu lists
        # what would be upgraded; doesn't need root.
        r = subprocess.run(PACMAN_REFRESH, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or f"pacman -Sy exit {r.returncode}")
        r = subprocess.run(["pacman", "-Qu"], capture_output=True, text=True)
        # -Qu exits 1 when nothing is upgradable; treat that as empty.
        return r.stdout

    def show_results(out: str) -> None:
        spinner.stop()
        spinner.set_visible(False)
        if out.strip():
            count = sum(1 for ln in out.splitlines() if ln.strip())
            status.set_label(f"{count} package(s) available:")
            text_view.get_buffer().set_text(out)
            scroller.set_visible(True)
            install_btn.set_sensitive(True)
        else:
            status.set_label("Up to date — no packages to upgrade.")

    def check_failed(exc: BaseException) -> None:
        spinner.stop()
        spinner.set_visible(False)
        status.set_label(f"Update check failed: {exc}")

    def do_install() -> int:
        proc = subprocess.Popen(
            PACMAN_UPGRADE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            GLib.idle_add(_append_line, text_view, line)
        return proc.wait()

    def install_done(rc: int) -> None:
        spinner.stop()
        spinner.set_visible(False)
        close_btn.set_sensitive(True)
        close_btn.set_label("Close")
        if rc == 0:
            status.set_label("Updates installed. Reboot to apply kernel/library changes.")
        else:
            status.set_label(f"Upgrade failed (exit {rc}). See output above.")

    def install_failed(exc: BaseException) -> None:
        spinner.stop()
        spinner.set_visible(False)
        close_btn.set_sensitive(True)
        status.set_label(f"Upgrade failed: {exc}")

    def on_install(*_args) -> None:
        install_btn.set_sensitive(False)
        close_btn.set_sensitive(False)
        status.set_label("Installing updates… (do not power off)")
        text_view.get_buffer().set_text("")
        scroller.set_visible(True)
        spinner.set_visible(True)
        spinner.start()
        worker.run(do_install, on_done=install_done, on_error=install_failed)

    install_btn.connect("clicked", on_install)
    worker.run(check, on_done=show_results, on_error=check_failed)


def _append_line(text_view: Gtk.TextView, line: str) -> bool:
    buf = text_view.get_buffer()
    buf.insert(buf.get_end_iter(), line)
    text_view.scroll_to_iter(buf.get_end_iter(), 0.0, False, 0.0, 0.0)
    return False  # one-shot
