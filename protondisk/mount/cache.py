"""A small TTL cache of directory listings (fuse-free)."""
from __future__ import annotations

import time


class ListingCache:
    def __init__(self, ttl: float = 5.0, clock=time.monotonic) -> None:
        self._ttl = ttl
        self._clock = clock
        self._data: dict[str, tuple] = {}

    def get(self, path: str):
        hit = self._data.get(path)
        if hit is None:
            return None
        entries, expires = hit
        if self._clock() >= expires:
            self._data.pop(path, None)
            return None
        return entries

    def put(self, path: str, entries) -> None:
        self._data[path] = (entries, self._clock() + self._ttl)

    def invalidate(self, path: str | None = None) -> None:
        if path is None:
            self._data.clear()
        else:
            self._data.pop(path, None)
