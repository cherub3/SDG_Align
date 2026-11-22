import pytest
import copy
from typing import Dict, Any, Optional

from scripts.stage19_conversation_memory import (
    start_conversation,
    append_turn,
    get_conversation,
    close_conversation,
    select_memory,
    serialize_memory_window,
    ConversationStore,
    ConversationMemoryInputError,
    ConversationMemoryInternalError,
    _generate_conversation_id,
    _generate_package_id,
    USER_PREFIX,
    ASSISTANT_PREFIX,
    TURN_SEPARATOR
)

class MockStore(ConversationStore):
    def __init__(self):
        self.store = {}
        self.fail_on_put = False
        self.fail_on_get = False
        
    def get(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        if self.fail_on_get:
            raise Exception("Mock get failure")
        return copy.deepcopy(self.store.get(conversation_id))
        
    def put(self, conversation_state: Dict[str, Any]) -> None:
        if self.fail_on_put:
            raise Exception("Mock put failure")
        self.store[conversation_state["conversation_id"]] = copy.deepcopy(conversation_state)
        
    def delete(self, conversation_id: str) -> None:
        self.store.pop(conversation_id, None)

@pytest.fixture
def store():
    return MockStore()

def test_start_conversation_success(store):
    config = {"session_seed": "test_seed", "metadata": {"title": "Test Conv", "tags": ["test"]}}
    state = start_conversation(config, store)
    assert state["status"] == "ACTIVE"
    assert state["turn_count"] == 0
    assert state["entries"] == []
    assert state["metadata"]["title"] == "Test Conv"
    assert state["conversation_id"] == _generate_conversation_id("test_seed")
    assert store.get(state["conversation_id"]) == state

def test_start_conversation_missing_seed(store):
    with pytest.raises(ConversationMemoryInputError, match="SESSION_SEED_MISSING"):
        start_conversation({}, store)
        
def test_append_turn_success(store):
    config = {"session_seed": "test_seed"}
    state = start_conversation(config, store)
    
    turn = {
        "user_content": "hello",
        "assistant_content": "hi",
        "provenance": {"request_id": "req-1"}
    }
    
    new_state = append_turn(state["conversation_id"], turn, store)
    assert new_state["turn_count"] == 1
    assert len(new_state["entries"]) == 2
    assert new_state["entries"][0]["speaker"] == "user"
    assert new_state["entries"][0]["content"] == "hello"
    assert new_state["entries"][0]["turn_index"] == 0
    assert new_state["entries"][1]["speaker"] == "assistant"
    assert new_state["entries"][1]["content"] == "hi"
    assert new_state["entries"][1]["turn_index"] == 0
    
def test_append_turn_closed_conversation(store):
    config = {"session_seed": "test_seed"}
    state = start_conversation(config, store)
    close_conversation(state["conversation_id"], store)
    
    turn = {
        "user_content": "hello",
        "assistant_content": "hi",
        "provenance": {"request_id": "req-1"}
    }
    with pytest.raises(ConversationMemoryInputError, match="CONVERSATION_CLOSED"):
        append_turn(state["conversation_id"], turn, store)

def test_append_turn_malformed(store):
    config = {"session_seed": "test_seed"}
    state = start_conversation(config, store)
    
    with pytest.raises(ConversationMemoryInputError, match="TURN_CONTENT_MISSING_OR_INVALID"):
        append_turn(state["conversation_id"], {"user_content": "", "assistant_content": "hi", "provenance": {"request_id": "1"}}, store)
    
    with pytest.raises(ConversationMemoryInputError, match="TURN_PROVENANCE_MISSING"):
        append_turn(state["conversation_id"], {"user_content": "h", "assistant_content": "hi"}, store)
        
def test_close_conversation(store):
    config = {"session_seed": "test_seed"}
    state = start_conversation(config, store)
    
    new_state = close_conversation(state["conversation_id"], store)
    assert new_state["status"] == "CLOSED"
    assert new_state["closed_at"] is not None
    
    # idempotent
    new_state2 = close_conversation(state["conversation_id"], store)
    assert new_state2["closed_at"] == new_state["closed_at"]
    
def test_get_conversation_missing(store):
    with pytest.raises(ConversationMemoryInputError, match="CONVERSATION_NOT_FOUND"):
        get_conversation("nonexistent", store)

def test_select_memory_empty(store):
    config = {"session_seed": "test_seed"}
    state = start_conversation(config, store)
    
    pkg = select_memory(state["conversation_id"], {}, store)
    assert pkg["selected_turn_count"] == 0
    assert pkg["serialized_memory"] == ""
    assert pkg["status"] == "WARNING"
    assert any(f["code"] == "EMPTY_CONVERSATION" for f in pkg["findings"])

def test_select_memory_windowing(store):
    config = {"session_seed": "test_seed"}
    state = start_conversation(config, store)
    
    for i in range(15):
        append_turn(state["conversation_id"], {
            "user_content": f"u{i}",
            "assistant_content": f"a{i}",
            "provenance": {"request_id": f"req-{i}"}
        }, store)
        
    pkg = select_memory(state["conversation_id"], {}, store)
    assert pkg["selected_turn_count"] == 10
    assert pkg["window_start_turn_index"] == 4
    assert pkg["window_end_turn_index"] == 13
    assert any(f["code"] == "WINDOW_TRUNCATED_BY_MAX_TURNS" for f in pkg["findings"])

def test_select_memory_character_budget(store):
    config = {"session_seed": "test_seed"}
    state = start_conversation(config, store)
    
    for i in range(4):
        append_turn(state["conversation_id"], {
            "user_content": "1234567890",
            "assistant_content": "1234567890",
            "provenance": {"request_id": f"req-{i}"}
        }, store)
        
    pkg = select_memory(state["conversation_id"], {"max_characters": 45, "exclude_current_turn": True}, store)
    assert pkg["selected_turn_count"] == 2
    assert pkg["window_start_turn_index"] == 1
    assert pkg["window_end_turn_index"] == 2
    assert any(f["code"] == "WINDOW_TRUNCATED_BY_BUDGET" for f in pkg["findings"])
    
def test_select_memory_closed_conversation(store):
    config = {"session_seed": "test_seed"}
    state = start_conversation(config, store)
    close_conversation(state["conversation_id"], store)
    
    pkg = select_memory(state["conversation_id"], {}, store)
    assert any(f["code"] == "CONVERSATION_CLOSED_AT_SELECTION" for f in pkg["findings"])

def test_store_failure(store):
    config = {"session_seed": "test_seed"}
    state = start_conversation(config, store)
    
    store.fail_on_get = True
    with pytest.raises(ConversationMemoryInternalError, match="Store get failed"):
        get_conversation(state["conversation_id"], store)
        
    store.fail_on_get = False
    store.fail_on_put = True
    with pytest.raises(ConversationMemoryInternalError, match="Store put failed"):
        append_turn(state["conversation_id"], {
            "user_content": "hello",
            "assistant_content": "hi",
            "provenance": {"request_id": "req-1"}
        }, store)

def test_serialize_memory_window():
    entries = [
        {"content": "hello", "speaker": "user"},
        {"content": "hi there", "speaker": "assistant"},
        {"content": "how are you?", "speaker": "user"},
        {"content": "good", "speaker": "assistant"}
    ]
    
    out = serialize_memory_window(entries)
    expected = f"{USER_PREFIX}hello{TURN_SEPARATOR}{ASSISTANT_PREFIX}hi there{TURN_SEPARATOR}{USER_PREFIX}how are you?{TURN_SEPARATOR}{ASSISTANT_PREFIX}good{TURN_SEPARATOR}"
    assert out == expected

def test_memory_package_determinism(store):
    config = {"session_seed": "test_seed"}
    state = start_conversation(config, store)
    
    for i in range(3):
        append_turn(state["conversation_id"], {
            "user_content": f"u{i}",
            "assistant_content": f"a{i}",
            "provenance": {"request_id": f"req-{i}"}
        }, store)
        
    pkg1 = select_memory(state["conversation_id"], {"exclude_current_turn": False}, store)
    pkg2 = select_memory(state["conversation_id"], {"exclude_current_turn": False}, store)
    
    # Pop selected_at to compare the rest
    pkg1.pop("selected_at")
    pkg2.pop("selected_at")
    
    assert pkg1 == pkg2
    
def test_internal_invariant_failures():
    # Provide an invalid state to validate_conversation to see if it catches it
    from scripts.stage19_conversation_memory import validate_conversation, validate_memory_package
    with pytest.raises(ConversationMemoryInternalError, match="SELECTED_TURN_COUNT_MISMATCH"):
        validate_conversation({"entries": [1, 2, 3], "turn_count": 2})

    # Test package validation failure
    invalid_pkg = {
        "entries": [],
        "window_start_turn_index": 0, # Should be -1 for empty
        "window_end_turn_index": 0,
        "serialized_memory": "",
        "total_selected_characters": 0,
        "conversation_memory_package_id": "bad",
        "selected_turn_count": 0,
        "conversation_id": "conv_1"
    }
    with pytest.raises(ConversationMemoryInternalError, match="WINDOW_RANGE_INCONSISTENT"):
        validate_memory_package(invalid_pkg)

def test_get_conversation_success(store):
    config = {"session_seed": "test_seed"}
    state = start_conversation(config, store)
    fetched = get_conversation(state["conversation_id"], store)
    assert fetched == state

def test_append_turn_multi_turn_progression(store):
    config = {"session_seed": "test_seed"}
    state = start_conversation(config, store)
    for i in range(5):
        state = append_turn(state["conversation_id"], {
            "user_content": f"u{i}",
            "assistant_content": f"a{i}",
            "provenance": {"request_id": f"req-{i}"}
        }, store)
        assert state["turn_count"] == i + 1
        assert state["entries"][-2]["turn_index"] == i
        assert state["entries"][-1]["turn_index"] == i

def test_select_memory_single_turn(store):
    config = {"session_seed": "test_seed"}
    state = start_conversation(config, store)
    append_turn(state["conversation_id"], {
        "user_content": "u0",
        "assistant_content": "a0",
        "provenance": {"request_id": "req-0"}
    }, store)
    
    pkg = select_memory(state["conversation_id"], {"exclude_current_turn": False}, store)
    assert pkg["selected_turn_count"] == 1
    assert pkg["window_start_turn_index"] == 0
    assert pkg["window_end_turn_index"] == 0

def test_unicode_content(store):
    config = {"session_seed": "test_seed"}
    state = start_conversation(config, store)
    
    append_turn(state["conversation_id"], {
        "user_content": "こんにちは",
        "assistant_content": "世界",
        "provenance": {"request_id": "req-0"}
    }, store)
    
    pkg = select_memory(state["conversation_id"], {"exclude_current_turn": False}, store)
    assert "こんにちは" in pkg["serialized_memory"]
    assert "世界" in pkg["serialized_memory"]

def test_character_budget_boundaries(store):
    config = {"session_seed": "test_seed"}
    state = start_conversation(config, store)
    
    for i in range(3):
        append_turn(state["conversation_id"], {
            "user_content": "12345",
            "assistant_content": "12345",
            "provenance": {"request_id": f"req-{i}"}
        }, store)
        
    pkg = select_memory(state["conversation_id"], {"max_characters": 15, "exclude_current_turn": False}, store)
    assert pkg["selected_turn_count"] == 1
    
    pkg = select_memory(state["conversation_id"], {"max_characters": 20, "exclude_current_turn": False}, store)
    assert pkg["selected_turn_count"] == 2

def test_internal_invariant_failures_extended():
    from scripts.stage19_conversation_memory import validate_conversation, validate_memory_package
    
    with pytest.raises(ConversationMemoryInternalError, match="ENTRY_ORDER_VIOLATED"):
        validate_conversation({"entries": [], "turn_count": 0, "status": "INVALID"})
        
    with pytest.raises(ConversationMemoryInternalError, match="ENTRY_ORDER_VIOLATED"):
        validate_conversation({
            "entries": [{"speaker": "assistant", "turn_index": 0}, {"speaker": "user", "turn_index": 0}],
            "turn_count": 1,
            "status": "ACTIVE"
        })
        
    valid_pkg = {
        "entries": [{"content": "u", "turn_index": 0}, {"content": "a", "turn_index": 0}],
        "window_start_turn_index": 0,
        "window_end_turn_index": 0,
        "serialized_memory": f"{USER_PREFIX}u{TURN_SEPARATOR}{ASSISTANT_PREFIX}a{TURN_SEPARATOR}",
        "total_selected_characters": 2,
        "conversation_memory_package_id": "",
        "selected_turn_count": 1,
        "conversation_id": "c"
    }
    valid_pkg["conversation_memory_package_id"] = _generate_package_id("c", 0, 0, valid_pkg["serialized_memory"])
    
    validate_memory_package(valid_pkg) 
    
    pkg_bad_ser = copy.deepcopy(valid_pkg)
    pkg_bad_ser["serialized_memory"] = "bad"
    pkg_bad_ser["conversation_memory_package_id"] = _generate_package_id("c", 0, 0, "bad")
    with pytest.raises(ConversationMemoryInternalError, match="SERIALIZED_MEMORY_MISMATCH"):
        validate_memory_package(pkg_bad_ser)
        
    pkg_bad_char = copy.deepcopy(valid_pkg)
    pkg_bad_char["total_selected_characters"] = 99
    with pytest.raises(ConversationMemoryInternalError, match="CHARACTER_COUNT_MISMATCH"):
        validate_memory_package(pkg_bad_char)
        
    pkg_bad_id = copy.deepcopy(valid_pkg)
    pkg_bad_id["conversation_memory_package_id"] = "bad"
    with pytest.raises(ConversationMemoryInternalError, match="PACKAGE_ID_MISMATCH"):
        validate_memory_package(pkg_bad_id)

def test_store_malformed_response(store):
    config = {"session_seed": "test_seed"}
    state = start_conversation(config, store)
    
    store.store[state["conversation_id"]] = "not a dict"
    with pytest.raises(ConversationMemoryInternalError, match="Malformed conversation state.*"):
        append_turn(state["conversation_id"], {
            "user_content": "hello",
            "assistant_content": "hi",
            "provenance": {"request_id": "req-1"}
        }, store)

def test_conversation_immutability(store):
    config = {"session_seed": "test_seed"}
    state = start_conversation(config, store)
    state["metadata"]["title"] = "Hacked!"
    
    clean_state = get_conversation(state["conversation_id"], store)
    assert clean_state["metadata"]["title"] != "Hacked!"
    
def test_package_immutability(store):
    config = {"session_seed": "test_seed"}
    state = start_conversation(config, store)
    append_turn(state["conversation_id"], {
        "user_content": "hello",
        "assistant_content": "hi",
        "provenance": {"request_id": "req-1"}
    }, store)
    
    pkg = select_memory(state["conversation_id"], {"exclude_current_turn": False}, store)
    pkg["entries"].pop()
    
    clean_state = get_conversation(state["conversation_id"], store)
    assert len(clean_state["entries"]) == 2
