"""
Unit tests for InMemoryConversationStore and its integration with Stage 19 helpers.
"""

import pytest
from scripts.conversation_store import InMemoryConversationStore
from scripts.stage19_conversation_memory import (
    ConversationMemoryInputError,
    start_conversation,
    get_conversation,
    append_turn,
    select_memory,
)


def _make_store() -> InMemoryConversationStore:
    return InMemoryConversationStore()


def _make_turn(user: str = "hello", assistant: str = "hi") -> dict:
    return {
        "user_content": user,
        "assistant_content": assistant,
        "provenance": {"request_id": "req-test-1"},
    }


# ── ConversationStore CRUD ────────────────────────────────────────────────────

class TestPut:
    def test_stores_and_retrieves(self):
        store = _make_store()
        record = {"conversation_id": "conv_abc", "status": "ACTIVE"}
        store.put(record)
        assert store.get("conv_abc") is record

    def test_overwrites_existing(self):
        store = _make_store()
        store.put({"conversation_id": "conv_abc", "v": 1})
        store.put({"conversation_id": "conv_abc", "v": 2})
        assert store.get("conv_abc")["v"] == 2


class TestGet:
    def test_missing_returns_none(self):
        store = _make_store()
        assert store.get("conv_nonexistent") is None

    def test_present_returns_value(self):
        store = _make_store()
        record = {"conversation_id": "conv_xyz", "status": "ACTIVE"}
        store.put(record)
        assert store.get("conv_xyz") is record


class TestDelete:
    def test_removes_existing(self):
        store = _make_store()
        store.put({"conversation_id": "conv_del", "status": "ACTIVE"})
        store.delete("conv_del")
        assert store.get("conv_del") is None

    def test_idempotent_on_missing(self):
        store = _make_store()
        store.delete("conv_never_existed")  # must not raise


# ── Stage 19 integration ──────────────────────────────────────────────────────

class TestStage19Integration:
    def test_start_conversation_stores_state(self):
        store = _make_store()
        state = start_conversation({"session_seed": "seed-1"}, store)
        conv_id = state["conversation_id"]
        assert store.get(conv_id) is not None
        assert store.get(conv_id)["status"] == "ACTIVE"

    def test_get_conversation_retrieves_stored(self):
        store = _make_store()
        state = start_conversation({"session_seed": "seed-2"}, store)
        retrieved = get_conversation(state["conversation_id"], store)
        assert retrieved["conversation_id"] == state["conversation_id"]

    def test_get_conversation_missing_raises(self):
        store = _make_store()
        with pytest.raises(ConversationMemoryInputError, match="CONVERSATION_NOT_FOUND"):
            get_conversation("conv_never_existed", store)

    def test_append_turn_increments_count(self):
        store = _make_store()
        state = start_conversation({"session_seed": "seed-3"}, store)
        conv_id = state["conversation_id"]
        updated = append_turn(conv_id, _make_turn(), store)
        assert updated["turn_count"] == 1

    def test_append_turn_persists_to_store(self):
        store = _make_store()
        state = start_conversation({"session_seed": "seed-4"}, store)
        conv_id = state["conversation_id"]
        append_turn(conv_id, _make_turn(), store)
        stored = store.get(conv_id)
        assert stored["turn_count"] == 1

    def test_select_memory_on_new_conversation(self):
        store = _make_store()
        state = start_conversation({"session_seed": "seed-5"}, store)
        pkg = select_memory(state["conversation_id"], {}, store)
        assert pkg["selected_turn_count"] == 0
        assert pkg["serialized_memory"] == ""

    def test_select_memory_after_turn(self):
        store = _make_store()
        state = start_conversation({"session_seed": "seed-6"}, store)
        conv_id = state["conversation_id"]
        append_turn(conv_id, _make_turn("question", "answer"), store)
        # select_memory by default excludes the current (most-recent) turn
        pkg = select_memory(conv_id, {"exclude_current_turn": False}, store)
        assert pkg["selected_turn_count"] == 1
        assert "question" in pkg["serialized_memory"]
