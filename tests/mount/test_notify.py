from protondisk.mount.notify import Notifier


def test_disabled_notifier_is_silent_noop():
    n = Notifier(enabled=False)              # deterministic: never touches gi/D-Bus
    assert n.enabled is False
    assert n.begin("hi") is None             # returns None when disabled
    n.update(None, "x")                      # no raise
    n.finish(None, "done")                   # no raise


def test_methods_tolerate_none_handle():
    n = Notifier(enabled=False)
    # even if a caller passes None (e.g. begin failed), update/finish must not raise
    n.update(None, "phase")
    n.finish(None, "done", timeout_ms=1000)


def test_enabled_flag_exposed():
    assert hasattr(Notifier(enabled=False), "enabled")
