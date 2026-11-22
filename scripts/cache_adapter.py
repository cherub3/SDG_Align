"""
In-memory CacheAdapter for Stage 17.

Demo-grade: not persisted across process restarts and not synchronized for
concurrent access beyond what CPython's GIL provides for simple dict operations.
"""

from typing import Any, Dict, Optional

from scripts.stage17_response_caching import CacheAdapter


class InMemoryCacheAdapter(CacheAdapter):
    """Dict-backed CacheAdapter.

    put() with an existing key silently replaces the previous entry.
    get_statistics() returns the minimal dict required by the ABC — no extra
    counters, no eviction tracking.
    """

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}

    @property
    def backend_name(self) -> str:
        return "in_memory"

    def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        return self._store.get(cache_key)

    def put(self, cache_key: str, entry: Dict[str, Any]) -> None:
        self._store[cache_key] = entry

    def get_statistics(self) -> Dict[str, Any]:
        return {"backend_name": self.backend_name, "entry_count": len(self._store)}
