"""
Unit and Stage 17 integration tests for InMemoryCacheAdapter.
"""

import pytest
from unittest.mock import MagicMock
from scripts.cache_adapter import InMemoryCacheAdapter
from scripts.stage17_response_caching import (
    lookup_cache,
    store_cache_entry,
    compute_cache_key,
)


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _make_llm_response(prompt_package_id: str = "pkg_001", status: str = "PASS") -> dict:
    cache_key = compute_cache_key(
        prompt_package_id,
        "gemini-test",
        {"model_name": "gemini-test", "max_output_tokens": 2000},
    )
    return {
        "llm_response_id": cache_key,
        "status": status,
        "prompt_package_id": prompt_package_id,
        "response_text": "hello",
    }


def _make_entry(cache_key: str, prompt_package_id: str = "pkg_001") -> dict:
    return {
        "cache_key": cache_key,
        "llm_response": _make_llm_response(prompt_package_id),
        "prompt_package_id": prompt_package_id,
        "model_name": "gemini-test",
        "cached_at": "2099-01-01T00:00:00Z",  # far future — never expired in tests
    }


# ── InMemoryCacheAdapter CRUD ──────────────────────────────────────────────────

class TestInMemoryCacheAdapter:
    def test_cache_miss_returns_none(self):
        adapter = InMemoryCacheAdapter()
        assert adapter.get("nonexistent_key") is None

    def test_put_and_get(self):
        adapter = InMemoryCacheAdapter()
        adapter.put("key1", {"data": "value"})
        assert adapter.get("key1") == {"data": "value"}

    def test_overwrite_existing(self):
        adapter = InMemoryCacheAdapter()
        adapter.put("key1", {"v": 1})
        adapter.put("key1", {"v": 2})
        assert adapter.get("key1") == {"v": 2}

    def test_multiple_entries_independent(self):
        adapter = InMemoryCacheAdapter()
        adapter.put("a", {"x": 1})
        adapter.put("b", {"x": 2})
        assert adapter.get("a") == {"x": 1}
        assert adapter.get("b") == {"x": 2}

    def test_missing_key_after_put_returns_none(self):
        adapter = InMemoryCacheAdapter()
        adapter.put("key1", {"data": "value"})
        assert adapter.get("key2") is None

    def test_backend_name(self):
        assert InMemoryCacheAdapter().backend_name == "in_memory"

    def test_get_statistics_includes_entry_count(self):
        adapter = InMemoryCacheAdapter()
        adapter.put("k1", {})
        adapter.put("k2", {})
        stats = adapter.get_statistics()
        assert stats["entry_count"] == 2
        assert stats["backend_name"] == "in_memory"


# ── Stage 17 helper integration ────────────────────────────────────────────────

class TestStage17Integration:
    def _cache_key(self, pkg_id: str = "pkg_001") -> str:
        return compute_cache_key(
            pkg_id, "gemini-test", {"model_name": "gemini-test", "max_output_tokens": 2000}
        )

    def test_lookup_miss_on_empty_store(self):
        adapter = InMemoryCacheAdapter()
        hit, entry, findings = lookup_cache(adapter, self._cache_key(), None)
        assert hit is False
        assert entry is None
        assert findings == []

    def test_lookup_hit_after_store(self):
        adapter = InMemoryCacheAdapter()
        key = self._cache_key()
        adapter.put(key, _make_entry(key))
        hit, entry, findings = lookup_cache(adapter, key, None)
        assert hit is True
        assert entry is not None
        assert entry["cache_key"] == key

    def test_store_cacheable_status_writes_entry(self):
        adapter = InMemoryCacheAdapter()
        key = self._cache_key()
        llm_resp = _make_llm_response(status="PASS")
        stored, findings = store_cache_entry(adapter, key, llm_resp, "pkg_001", "gemini-test")
        assert stored is True
        assert adapter.get(key) is not None

    def test_store_non_cacheable_status_skips_write(self):
        adapter = InMemoryCacheAdapter()
        key = self._cache_key()
        llm_resp = _make_llm_response(status="FAIL")
        stored, findings = store_cache_entry(adapter, key, llm_resp, "pkg_001", "gemini-test")
        assert stored is False
        assert adapter.get(key) is None
        assert any(f["code"] == "CACHE_WRITE_SKIPPED_NON_CACHEABLE_STATUS" for f in findings)

    def test_lookup_expired_entry_treated_as_miss(self):
        adapter = InMemoryCacheAdapter()
        key = self._cache_key()
        expired_entry = {
            "cache_key": key,
            "llm_response": _make_llm_response(),
            "prompt_package_id": "pkg_001",
            "model_name": "gemini-test",
            "cached_at": "2000-01-01T00:00:00Z",  # ancient — always expired
        }
        adapter.put(key, expired_entry)
        hit, entry, findings = lookup_cache(adapter, key, cache_ttl_seconds=1)
        assert hit is False
        assert any(f["code"] == "CACHE_ENTRY_EXPIRED" for f in findings)
