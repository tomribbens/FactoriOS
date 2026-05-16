"""Run blocking work off the GTK main thread and post the result back.

GTK is single-threaded; HTTP calls must not block the main loop. This helper
runs a callable on a worker thread and dispatches `on_done(result)` /
`on_error(exc)` back on the main thread via `GLib.idle_add`.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from gi.repository import GLib


def run(
    fn: Callable[..., Any],
    *args,
    on_done: Callable[[Any], None] | None = None,
    on_error: Callable[[BaseException], None] | None = None,
    **kwargs,
) -> threading.Thread:
    def _target():
        try:
            result = fn(*args, **kwargs)
        except BaseException as exc:
            if on_error is not None:
                GLib.idle_add(on_error, exc)
            return
        if on_done is not None:
            GLib.idle_add(on_done, result)

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    return t
