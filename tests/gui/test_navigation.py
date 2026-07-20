from protondisk.gui.navigation import NavigationState
from protondisk.core.models import Entry


def _entry(name, parent, is_dir=True):
    return Entry(name=name, path=f"{parent.rstrip('/')}/{name}", is_dir=is_dir,
                 size=None, mtime=None, uid=name)


class FakeDisk:
    def __init__(self):
        self.list_calls = []
        self.responses = {
            "/my-files": [_entry("Reports", "/my-files"), _entry("a.txt", "/my-files", is_dir=False)],
            "/my-files/Reports": [_entry("q3.pdf", "/my-files/Reports", is_dir=False)],
        }

    def list(self, path):
        self.list_calls.append(path)
        return self.responses.get(path, [])


def test_starts_at_root():
    nav = NavigationState(FakeDisk())
    assert nav.current == "/my-files"
    assert nav.can_go_back() is False


def test_entries_are_cached():
    disk = FakeDisk()
    nav = NavigationState(disk)
    first = nav.entries()
    second = nav.entries()
    assert [e.name for e in first] == ["Reports", "a.txt"]
    assert first == second
    assert disk.list_calls == ["/my-files"]  # only one real call


def test_navigate_pushes_history_and_forward_clears():
    disk = FakeDisk()
    nav = NavigationState(disk)
    nav.navigate_to("/my-files/Reports")
    assert nav.current == "/my-files/Reports"
    assert nav.can_go_back() is True
    assert nav.can_go_forward() is False
    assert [e.name for e in nav.entries()] == ["q3.pdf"]


def test_back_and_forward():
    nav = NavigationState(FakeDisk())
    nav.navigate_to("/my-files/Reports")
    nav.go_back()
    assert nav.current == "/my-files"
    assert nav.can_go_forward() is True
    nav.go_forward()
    assert nav.current == "/my-files/Reports"


def test_navigating_after_back_clears_forward():
    nav = NavigationState(FakeDisk())
    nav.navigate_to("/my-files/Reports")
    nav.go_back()
    nav.navigate_to("/my-files/a.txt")
    assert nav.can_go_forward() is False


def test_breadcrumbs():
    nav = NavigationState(FakeDisk())
    nav.navigate_to("/my-files/Reports")
    assert nav.breadcrumbs() == [("my-files", "/my-files"), ("Reports", "/my-files/Reports")]


def test_refresh_relists():
    disk = FakeDisk()
    nav = NavigationState(disk)
    nav.entries()
    nav.refresh()
    assert disk.list_calls == ["/my-files", "/my-files"]  # cache dropped then re-listed
