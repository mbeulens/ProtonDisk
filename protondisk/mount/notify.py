"""Best-effort desktop notifications via libnotify.

Degrades to a silent no-op if libnotify / the notification D-Bus service is not
available, so the mount never breaks (headless, cron, minimal desktops).
"""
from __future__ import annotations

SUMMARY = "ProtonDisk"
_ICON = "folder-remote"


class Notifier:
    def __init__(self, app_name: str = "ProtonDisk", enabled: bool = True) -> None:
        self._enabled = False
        self._Notify = None
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

    def begin(self, body: str = ""):
        if not self._enabled:
            return None
        try:
            note = self._Notify.Notification.new(SUMMARY, body, _ICON)
            note.show()
            return note
        except Exception:
            return None

    def update(self, handle, body: str) -> None:
        if handle is None:
            return
        try:
            handle.update(SUMMARY, body, _ICON)
            handle.show()
        except Exception:
            pass

    def finish(self, handle, body: str, timeout_ms: int = 3000) -> None:
        if handle is None:
            return
        try:
            handle.update(SUMMARY, body, _ICON)
            handle.set_timeout(timeout_ms)
            handle.show()
        except Exception:
            pass
