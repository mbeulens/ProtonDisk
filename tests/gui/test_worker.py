import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib

from protondisk.gui.worker import run_async


def _drain(predicate, timeout_ms=2000):
    """Run a GLib main loop until predicate() is true or timeout."""
    loop = GLib.MainLoop()
    state = {"done": False}

    def check():
        if predicate():
            state["done"] = True
            loop.quit()
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    GLib.timeout_add(10, check)
    GLib.timeout_add(timeout_ms, loop.quit)
    loop.run()
    return state["done"]


def test_success_callback_receives_result():
    got = {}
    run_async(lambda: 6 * 7, lambda r: got.setdefault("v", r))
    assert _drain(lambda: "v" in got)
    assert got["v"] == 42


def test_error_callback_receives_exception():
    err = {}

    def boom():
        raise ValueError("nope")

    run_async(boom, lambda r: None, lambda e: err.setdefault("e", e))
    assert _drain(lambda: "e" in err)
    assert isinstance(err["e"], ValueError)
