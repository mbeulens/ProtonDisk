import types

from protondisk.mount.notify import Notifier


def test_disabled_notifier_is_silent_noop():
    n = Notifier(enabled=False)              # deterministic: never touches gi/D-Bus
    assert n.enabled is False
    assert n.begin("hi") is None             # returns None when disabled
    n.update(None, "x")                      # no raise
    n.finish(None, "done")                   # no raise
    n.fail(None, "boom")                     # no raise


def test_methods_tolerate_none_handle():
    n = Notifier(enabled=False)
    # even if a caller passes None (e.g. begin failed), update/finish must not raise
    n.update(None, "phase")
    n.finish(None, "done", timeout_ms=1000)


def test_enabled_flag_exposed():
    assert hasattr(Notifier(enabled=False), "enabled")


# ---- popup policy (libnotify stubbed out; no D-Bus involved) ----
class _FakeBubble:
    def __init__(self, body):
        self.bodies = [body]
        self.shows = 0
        self.closes = 0

    def update(self, summary, body, icon):
        self.bodies.append(body)

    def show(self):
        self.shows += 1

    def close(self):
        self.closes += 1

    def set_timeout(self, ms):
        pass


def _notifier(times=None):
    """A Notifier wired to a fake libnotify and a scripted clock."""
    created = []

    class Notification:
        @staticmethod
        def new(summary, body, icon):
            bubble = _FakeBubble(body)
            created.append(bubble)
            return bubble

    ticks = list(times or [0.0])
    clock = lambda: ticks.pop(0) if len(ticks) > 1 else ticks[0]
    n = Notifier(enabled=False, delay=2.0, clock=clock)
    n._Notify = types.SimpleNamespace(Notification=Notification)
    n._enabled = True
    return n, created


def test_quick_background_read_never_pops_up():
    n, created = _notifier([0.0, 0.1, 0.2])
    note = n.begin("Opening a.txt…", quiet=True)
    n.update(note, "Downloading… a.txt")
    n.finish(note, "Ready: a.txt")
    assert created == []          # the whole point: browsing a folder stays silent


def test_a_folder_full_of_quick_reads_stays_silent():
    n, created = _notifier([0.0])
    for name in ("a.jpg", "b.jpg", "c.jpg", "d.jpg", "e.jpg"):
        note = n.begin(f"Opening {name}…", quiet=True)
        n.update(note, f"Downloading… {name}")
        n.finish(note, f"Ready: {name}")
    assert created == []


def test_slow_background_read_shows_one_bubble_and_clears_it():
    n, created = _notifier([0.0, 3.0, 3.5])
    note = n.begin("Opening big.iso…", quiet=True)
    n.update(note, "Downloading… big.iso")     # now overdue → worth showing
    assert len(created) == 1
    n.finish(note, "Ready: big.iso")
    assert created[0].closes == 1              # and it goes away when done


def test_saves_are_announced_immediately():
    n, created = _notifier([0.0])
    note = n.begin("Saving doc.txt…")          # not quiet: user-initiated
    n.finish(note, "Saved doc.txt to Proton Drive")
    assert len(created) == 1
    assert created[0].bodies[-1] == "Saved doc.txt to Proton Drive"


def test_transfers_share_a_single_bubble():
    n, created = _notifier([0.0])
    for name in ("one.txt", "two.txt", "three.txt"):
        note = n.begin(f"Saving {name}…")
        n.finish(note, f"Saved {name} to Proton Drive")
    assert len(created) == 1                   # never a stack of popups
    assert created[0].shows == 6               # each begin/finish updates it in place


def test_failure_is_visible_even_for_a_quiet_transfer():
    n, created = _notifier([0.0, 0.1])
    note = n.begin("Opening a.txt…", quiet=True)
    n.fail(note, "Failed: a.txt")
    assert len(created) == 1
    assert created[0].bodies[-1] == "Failed: a.txt"


def test_notifications_survive_a_broken_notification_service():
    class Exploding:
        @staticmethod
        def new(*args):
            raise RuntimeError("no D-Bus")

    n, _ = _notifier([0.0])
    n._Notify = types.SimpleNamespace(Notification=Exploding)
    note = n.begin("Saving x.txt…")            # must not take the mount down
    n.update(note, "Uploading… x.txt")
    n.finish(note, "Saved x.txt to Proton Drive")
