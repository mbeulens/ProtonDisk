from protondisk.gui.window import MainWindow
from protondisk.core.models import ShareInfo


def test_valid_email():
    assert MainWindow._valid_email("a@pm.me") is True
    assert MainWindow._valid_email("nope") is False
    assert MainWindow._valid_email("@pm.me") is False
    assert MainWindow._valid_email("a@b") is False


def test_share_summary():
    assert MainWindow._share_summary(ShareInfo("/p", False, [])) == "Not shared"
    assert MainWindow._share_summary(ShareInfo("/p", True, ["a@pm.me"])) == "Shared with 1 person"
    assert MainWindow._share_summary(ShareInfo("/p", True, ["a@pm.me", "b@pm.me"])) == "Shared with 2 people"
