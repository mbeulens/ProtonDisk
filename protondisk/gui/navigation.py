"""Navigation state for the browser: current path, history, and a listing cache.

Pure logic — intentionally free of any GTK/gi import so it unit-tests without a display.
"""
from __future__ import annotations

from protondisk.core.models import Entry


class NavigationState:
    def __init__(self, disk, root: str = "/my-files") -> None:
        self._disk = disk
        self._root = root
        self._current = root
        self._back: list[str] = []
        self._forward: list[str] = []
        self._cache: dict[str, list[Entry]] = {}

    @property
    def current(self) -> str:
        return self._current

    def entries(self) -> list[Entry]:
        if self._current not in self._cache:
            self._cache[self._current] = self._disk.list(self._current)
        return self._cache[self._current]

    def navigate_to(self, path: str) -> None:
        if path == self._current:
            return
        self._back.append(self._current)
        self._forward.clear()
        self._current = path

    def go_back(self) -> None:
        if not self._back:
            return
        self._forward.append(self._current)
        self._current = self._back.pop()

    def go_forward(self) -> None:
        if not self._forward:
            return
        self._back.append(self._current)
        self._current = self._forward.pop()

    def can_go_back(self) -> bool:
        return bool(self._back)

    def can_go_forward(self) -> bool:
        return bool(self._forward)

    def breadcrumbs(self) -> list[tuple[str, str]]:
        # Root is like "/my-files"; build cumulative paths from its segments onward.
        root_name = self._root.strip("/")
        crumbs = [(root_name, self._root)]
        remainder = self._current[len(self._root):].strip("/")
        if remainder:
            acc = self._root
            for segment in remainder.split("/"):
                acc = f"{acc}/{segment}"
                crumbs.append((segment, acc))
        return crumbs

    def invalidate(self, path: str | None = None) -> None:
        if path is None:
            self._cache.clear()
        else:
            self._cache.pop(path, None)

    def refresh(self) -> list[Entry]:
        self.invalidate(self._current)
        return self.entries()
