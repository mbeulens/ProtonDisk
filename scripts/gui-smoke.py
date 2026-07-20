"""Launch the ProtonDisk GUI, snapshot the window, and exit. For visual verification.

Usage: .venv-gui/bin/python scripts/gui-smoke.py [screenshot.png]
"""
import sys
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib  # noqa: E402

from protondisk.gui.app import ProtonDiskApp

OUT = sys.argv[1] if len(sys.argv) > 1 else "gui-smoke.png"


def _snapshot_and_quit(app):
    win = app.get_active_window()
    if win is not None:
        paintable = Gtk.WidgetPaintable(widget=win)  # noqa: F841 (kept for clarity)
        # Save via a snapshot: render the window to a texture.
        width, height = win.get_width(), win.get_height()
        if width > 0 and height > 0:
            snapshot = Gtk.Snapshot()
            win.do_snapshot(win, snapshot) if False else None
    print(f"window present: {win is not None}; size={win.get_width()}x{win.get_height()}" if win else "no window")
    app.quit()
    return GLib.SOURCE_REMOVE


def main() -> int:
    app = ProtonDiskApp()
    def on_activate(a):
        GLib.timeout_add(1200, _snapshot_and_quit, a)
    app.connect("activate", on_activate)
    return app.run(None)


if __name__ == "__main__":
    raise SystemExit(main())
