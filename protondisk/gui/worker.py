"""Run blocking core calls off the GTK main loop and marshal results back onto it."""
from __future__ import annotations

import threading
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib  # noqa: E402


def run_async(func: Callable, on_success: Callable, on_error: Callable | None = None) -> None:
    def worker() -> None:
        try:
            result = func()
        except Exception as exc:  # deliver to the main loop, don't crash the thread
            if on_error is not None:
                GLib.idle_add(on_error, exc)
            return
        GLib.idle_add(on_success, result)

    threading.Thread(target=worker, daemon=True).start()
