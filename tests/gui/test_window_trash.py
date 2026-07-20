from protondisk.gui.window import MainWindow


def test_trash_confirm_text():
    assert MainWindow._trash_confirm_text("a.txt") == "Move “a.txt” to trash?"
