"""Reboot / shutdown buttons shared between the login and chooser screens.

systemctl reboot/poweroff is reachable without privilege for the active
session user — polkit's default rules allow it — so the factorios user
can fire these directly. Each action gets a confirmation dialog to avoid
accidental clicks on a kiosk.
"""

from __future__ import annotations

import subprocess
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402


def make_row() -> Gtk.Box:
    """A small right-aligned row with Reboot + Shutdown buttons."""
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    row.set_halign(Gtk.Align.END)
    reboot = Gtk.Button(label="Reboot")
    reboot.add_css_class("flat")
    reboot.connect("clicked", lambda *_: _confirm(
        reboot, "Reboot now?", lambda: _run("reboot")))
    row.append(reboot)
    shutdown = Gtk.Button(label="Shutdown")
    shutdown.add_css_class("flat")
    shutdown.connect("clicked", lambda *_: _confirm(
        shutdown, "Shut down now?", lambda: _run("poweroff")))
    row.append(shutdown)
    return row


def _run(verb: str) -> None:
    # Don't wait — once systemd accepts the request the session is going
    # away anyway. Errors will surface in the journal.
    subprocess.Popen(["systemctl", verb])


def _confirm(parent: Gtk.Widget, prompt: str, action: Callable[[], None]) -> None:
    dialog = Gtk.Window(
        title="Confirm", transient_for=parent.get_root(), modal=True,
    )
    box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=12,
        margin_top=16, margin_bottom=16, margin_start=16, margin_end=16,
    )
    box.append(Gtk.Label(label=prompt, xalign=0))

    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    actions.set_halign(Gtk.Align.END)
    cancel = Gtk.Button(label="Cancel")
    cancel.connect("clicked", lambda *_: dialog.close())
    actions.append(cancel)
    ok = Gtk.Button(label="OK")
    ok.add_css_class("destructive-action")

    def go(*_):
        dialog.close()
        action()

    ok.connect("clicked", go)
    actions.append(ok)
    box.append(actions)
    dialog.set_child(box)
    dialog.present()
