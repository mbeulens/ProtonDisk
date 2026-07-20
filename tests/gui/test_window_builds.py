import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

from protondisk.gui.window import MainWindow


def test_main_window_is_a_widget_and_holds_disk():
    Adw.init()
    app = Adw.Application(application_id="dev.protondisk.Test")
    sentinel = object()
    win = MainWindow(application=app, disk=sentinel)
    assert isinstance(win, Gtk.Widget)
    assert win._disk is sentinel
    assert win.get_title() == "ProtonDisk"
