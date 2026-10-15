"""Thread-safe counters for server-confirmed abandoned response deliveries."""
from __future__ import annotations

import threading


class AbandonedResponseCounter:
    def __init__(self) -> None:
        self._count = 0
        self._lock = threading.Lock()

    @property
    def count(self) -> int:
        with self._lock:
            return self._count

    def record_abandoned(self) -> None:
        with self._lock:
            self._count += 1
