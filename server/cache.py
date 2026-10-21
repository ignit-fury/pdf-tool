"""Evictable memory-only source cache. No filenames, passwords, sessions or undo log."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Callable


class SourceCache:
    def __init__(self, max_bytes: int = 128 * 1024 * 1024, ttl: float = 600,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.max_bytes = max_bytes
        self.ttl = ttl
        self.clock = clock
        self.total_bytes = 0
        self._key = secrets.token_bytes(32)
        self._items: OrderedDict[str, tuple[float, bytes]] = OrderedDict()
        self._lock = threading.Lock()

    def _expire(self) -> None:
        now = self.clock()
        for key, (deadline, data) in list(self._items.items()):
            if deadline <= now:
                self.total_bytes -= len(data)
                del self._items[key]

    def put(self, data: bytes) -> str:
        if len(data) > self.max_bytes:
            raise ValueError('source_exceeds_cache_budget')
        digest = hashlib.sha256(data).digest()
        token = hmac.new(self._key, digest, hashlib.sha256).hexdigest()
        with self._lock:
            self._expire()
            if token in self._items:
                self.total_bytes -= len(self._items.pop(token)[1])
            while self._items and self.total_bytes + len(data) > self.max_bytes:
                self.total_bytes -= len(self._items.popitem(last=False)[1][1])
            self._items[token] = (self.clock() + self.ttl, data)
            self.total_bytes += len(data)
        return token

    def get(self, token: str) -> bytes | None:
        with self._lock:
            self._expire()
            value = self._items.get(token)
            if value is None:
                return None
            self._items.move_to_end(token)
            return value[1]

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self.total_bytes = 0

    def expire(self) -> None:
        """Called periodically even when no user makes another request."""
        with self._lock:
            self._expire()
