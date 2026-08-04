"""Best-effort desktop notifications via libnotify.

Deliberately quiet. A file manager touches many files in a row, and one popup per
file (let alone one per transfer phase) is noise, so:

* every message shares a **single** notification bubble, updated in place — the
  mount can never stack popups on top of each other;
* transfers marked ``quiet`` (background reads) raise no bubble at all unless they
  run longer than ``delay`` seconds, and clear it again when they finish;
* saves and failures stay visible — those are worth interrupting for.

Degrades to a silent no-op if libnotify / the notification D-Bus service is not
available, so the mount never breaks (headless, cron, minimal desktops).
"""
from __future__ import annotations

import time

SUMMARY = "ProtonDisk"
_ICON = "folder-remote"
# A background transfer has to run at least this long before it earns a popup.
_QUIET_DELAY = 2.0  # seconds


class _Note:
    __slots__ = ("body", "quiet", "started", "shown")

    def __init__(self, body: str, quiet: bool, started: float) -> None:
        self.body = body
        self.quiet = quiet
        self.started = started
        self.shown = False


class Notifier:
    def __init__(self, app_name: str = "ProtonDisk", enabled: bool = True, *,
                 delay: float = _QUIET_DELAY, clock=time.monotonic) -> None:
        self._enabled = False
        self._Notify = None
        self._delay = delay
        self._clock = clock
        self._bubble = None          # the one notification object we ever create
        if not enabled:
            return
        try:
            import gi
            gi.require_version("Notify", "0.7")
            from gi.repository import Notify
            Notify.init(app_name)
            self._Notify = Notify
            self._enabled = True
        except Exception:
            self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def begin(self, body: str = "", *, quiet: bool = False):
        if not self._enabled:
            return None
        note = _Note(body, quiet, self._clock())
        if not quiet:
            self._show(note, body)
        return note

    def update(self, handle, body: str) -> None:
        if handle is None:
            return
        handle.body = body
        if handle.quiet and not self._overdue(handle):
            return               # still quick — say nothing yet
        self._show(handle, body)

    def finish(self, handle, body: str, timeout_ms: int = 3000) -> None:
        if handle is None:
            return
        if handle.quiet:
            self._close(handle)  # a background read leaves no trace behind
            return
        self._show(handle, body, timeout_ms)

    def fail(self, handle, body: str, timeout_ms: int = 5000) -> None:
        """Report an error — always visible, however quiet the transfer was."""
        if handle is None:
            return
        handle.quiet = False
        self._show(handle, body, timeout_ms)

    # ---- internals ----
    def _overdue(self, handle) -> bool:
        return self._clock() - handle.started >= self._delay

    def _show(self, handle, body: str, timeout_ms: int | None = None) -> None:
        try:
            if self._bubble is None:
                self._bubble = self._Notify.Notification.new(SUMMARY, body, _ICON)
            else:
                self._bubble.update(SUMMARY, body, _ICON)
            if timeout_ms is not None:
                self._bubble.set_timeout(timeout_ms)
            self._bubble.show()
            handle.shown = True
        except Exception:
            pass

    def _close(self, handle) -> None:
        if not handle.shown:
            return
        try:
            if self._bubble is not None:
                self._bubble.close()
        except Exception:
            pass
        handle.shown = False
