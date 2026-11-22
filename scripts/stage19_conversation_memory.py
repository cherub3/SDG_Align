"""
Stage 19 — Conversation Memory

Manages multi-turn conversation state.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import datetime
import hashlib
import json
import copy

# Constants
CONVERSATION_MEMORY_VERSION = "1.0.0"
DEFAULT_SELECTION_MAX_TURNS = 10
DEFAULT_SELECTION_MAX_CHARACTERS = 50_000
MAX_SELECTION_TURNS_CEILING = 50
MAX_SELECTION_CHARACTERS_CEILING = 200_000
TURN_SEPARATOR = "\n"
USER_PREFIX = "User: "
ASSISTANT_PREFIX = "Assistant: "

class ConversationMemoryInputError(Exception):
    """Raised for malformed inputs or lifecycle violations."""
    pass

class ConversationMemoryInternalError(Exception):
    """Raised for internal invariant violations or store failures."""
    pass

class ConversationStore(ABC):
    @abstractmethod
    def get(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Returns the ConversationState for the given id, or None if not found."""
        pass

    @abstractmethod
    def put(self, conversation_state: Dict[str, Any]) -> None:
        """Stores (creates or replaces) a ConversationState."""
        pass

    @abstractmethod
    def delete(self, conversation_id: str) -> None:
        """Removes a conversation from the store. Idempotent.
        Stage 19 itself never calls this method — it exists for
        administrative tooling outside Stage 19's scope."""
        pass

def _utc_now_iso() -> str:
    # Deterministic output string format for ISO 8601 UTC
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _generate_conversation_id(session_seed: str) -> str:
    seed_bytes = session_seed.encode("utf-8")
    hash_hex = hashlib.sha256(seed_bytes).hexdigest()[:16]
    return f"conv_{hash_hex}"

def _generate_package_id(conversation_id: str, start: int, end: int, memory: str) -> str:
    canonical_dict = {
        "conversation_id": conversation_id,
        "serialized_memory": memory,
        "window_end_turn_index": end,
        "window_start_turn_index": start
    }
    canonical_json = json.dumps(canonical_dict, separators=(',', ':'), sort_keys=True)
    hash_hex = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:16]
    return f"cmp_{hash_hex}"

def validate_conversation(conversation_state: Dict[str, Any]) -> None:
    try:
        entries = conversation_state["entries"]
        turn_count = conversation_state["turn_count"]
        
        if len(entries) != turn_count * 2:
            raise ConversationMemoryInternalError("SELECTED_TURN_COUNT_MISMATCH")
            
        expected_index = 0
        for i in range(0, len(entries), 2):
            user_entry = entries[i]
            asst_entry = entries[i+1]
            if user_entry["turn_index"] != expected_index or asst_entry["turn_index"] != expected_index:
                raise ConversationMemoryInternalError("ENTRY_ORDER_VIOLATED")
            if user_entry["speaker"] != "user" or asst_entry["speaker"] != "assistant":
                raise ConversationMemoryInternalError("ENTRY_ORDER_VIOLATED")
            expected_index += 1
            
        status = conversation_state["status"]
        if status not in ("ACTIVE", "CLOSED"):
            raise ConversationMemoryInternalError("ENTRY_ORDER_VIOLATED")
            
    except KeyError as e:
        raise ConversationMemoryInternalError(f"Malformed conversation state missing key: {e}")

def validate_memory_package(package: Dict[str, Any]) -> None:
    entries = package["entries"]
    start = package["window_start_turn_index"]
    end = package["window_end_turn_index"]
    memory = package["serialized_memory"]
    chars = package["total_selected_characters"]
    pkg_id = package["conversation_memory_package_id"]
    
    # Verify selected_turn_count
    actual_turn_count = len(entries) // 2
    if package["selected_turn_count"] != actual_turn_count:
        raise ConversationMemoryInternalError("SELECTED_TURN_COUNT_MISMATCH")
        
    # Verify ordering and gapless indices
    if entries:
        if start > end:
            raise ConversationMemoryInternalError("WINDOW_RANGE_INCONSISTENT")
        if start != entries[0]["turn_index"] or end != entries[-1]["turn_index"]:
            raise ConversationMemoryInternalError("WINDOW_RANGE_INCONSISTENT")
        last_index = -1
        for e in entries:
            if e["turn_index"] < last_index:
                raise ConversationMemoryInternalError("ENTRY_ORDER_VIOLATED")
            last_index = e["turn_index"]
    else:
        if start != -1 or end != -1:
            raise ConversationMemoryInternalError("WINDOW_RANGE_INCONSISTENT")

    # Re-serialize
    if serialize_memory_window(entries) != memory:
        raise ConversationMemoryInternalError("SERIALIZED_MEMORY_MISMATCH")
        
    # Character count
    if sum(len(e["content"]) for e in entries) != chars:
        raise ConversationMemoryInternalError("CHARACTER_COUNT_MISMATCH")
        
    # Hash
    if _generate_package_id(package["conversation_id"], start, end, memory) != pkg_id:
        raise ConversationMemoryInternalError("PACKAGE_ID_MISMATCH")

def serialize_memory_window(entries: List[Dict[str, Any]]) -> str:
    if not entries:
        return ""
    
    parts = []
    for i in range(0, len(entries), 2):
        if i + 1 < len(entries):
            u_content = entries[i]["content"]
            a_content = entries[i+1]["content"]
            parts.append(f"{USER_PREFIX}{u_content}{TURN_SEPARATOR}{ASSISTANT_PREFIX}{a_content}{TURN_SEPARATOR}")
    
    return "".join(parts)

def start_conversation(config: Dict[str, Any], store: ConversationStore) -> Dict[str, Any]:
    seed = config.get("session_seed") if isinstance(config, dict) else None
    
    if not seed or not isinstance(seed, str):
        raise ConversationMemoryInputError("SESSION_SEED_MISSING")
        
    conv_id = _generate_conversation_id(seed)
    
    state = {
        "conversation_id": conv_id,
        "conversation_memory_version": CONVERSATION_MEMORY_VERSION,
        "status": "ACTIVE",
        "created_at": _utc_now_iso(),
        "closed_at": None,
        "turn_count": 0,
        "entries": [],
        "metadata": {
            "title": config.get("metadata", {}).get("title"),
            "tags": config.get("metadata", {}).get("tags", [])
        },
        "findings": []
    }
    
    validate_conversation(state)
    
    try:
        store.put(copy.deepcopy(state))
    except Exception as e:
        raise ConversationMemoryInternalError(f"Store put failed: {e}")
        
    return state

def get_conversation(conversation_id: str, store: ConversationStore) -> Dict[str, Any]:
    try:
        state = store.get(conversation_id)
    except Exception as e:
        raise ConversationMemoryInternalError(f"Store get failed: {e}")
        
    if state is None:
        raise ConversationMemoryInputError("CONVERSATION_NOT_FOUND")
        
    if not isinstance(state, dict):
        raise ConversationMemoryInternalError("Malformed conversation state: not a dict")
        
    return copy.deepcopy(state)

def close_conversation(conversation_id: str, store: ConversationStore) -> Dict[str, Any]:
    state = get_conversation(conversation_id, store)
    if state["status"] == "CLOSED":
        return state
        
    state["status"] = "CLOSED"
    state["closed_at"] = _utc_now_iso()
    
    try:
        store.put(copy.deepcopy(state))
    except Exception as e:
        raise ConversationMemoryInternalError(f"Store put failed: {e}")
        
    return state

def _validate_turn_input(turn: Dict[str, Any]) -> None:
    if not isinstance(turn, dict):
        raise ConversationMemoryInputError("TURN_CONTENT_MISSING_OR_INVALID")
        
    u_content = turn.get("user_content")
    a_content = turn.get("assistant_content")
    
    if not isinstance(u_content, str) or not u_content:
        raise ConversationMemoryInputError("TURN_CONTENT_MISSING_OR_INVALID")
    if not isinstance(a_content, str) or not a_content:
        raise ConversationMemoryInputError("TURN_CONTENT_MISSING_OR_INVALID")
        
    prov = turn.get("provenance")
    if not isinstance(prov, dict):
        raise ConversationMemoryInputError("TURN_PROVENANCE_MISSING")
        
    if not prov.get("request_id"):
        raise ConversationMemoryInputError("TURN_PROVENANCE_MISSING")

def append_turn(conversation_id: str, turn: Dict[str, Any], store: ConversationStore) -> Dict[str, Any]:
    _validate_turn_input(turn)
    
    state = get_conversation(conversation_id, store)
    
    if state["status"] == "CLOSED":
        raise ConversationMemoryInputError("CONVERSATION_CLOSED")
        
    t_idx = state["turn_count"]
    now = _utc_now_iso()
    
    user_entry = {
        "conversation_id": conversation_id,
        "turn_index": t_idx,
        "speaker": "user",
        "content": turn["user_content"],
        "created_at": now,
        "provenance": copy.deepcopy(turn["provenance"])
    }
    
    asst_entry = {
        "conversation_id": conversation_id,
        "turn_index": t_idx,
        "speaker": "assistant",
        "content": turn["assistant_content"],
        "created_at": now,
        "provenance": copy.deepcopy(turn["provenance"])
    }
    
    state["entries"].append(user_entry)
    state["entries"].append(asst_entry)
    state["turn_count"] += 1
    
    validate_conversation(state)
    
    try:
        store.put(copy.deepcopy(state))
    except Exception as e:
        raise ConversationMemoryInternalError(f"Store put failed: {e}")
        
    return state

def select_memory(conversation_id: str, selection_config: Dict[str, Any], store: ConversationStore) -> Dict[str, Any]:
    if not isinstance(selection_config, dict):
        raise ConversationMemoryInputError("SELECTION_CONFIG_MALFORMED")
        
    state = get_conversation(conversation_id, store)
    
    findings = []
    if state["status"] == "CLOSED":
        findings.append({
            "severity": "INFO",
            "code": "CONVERSATION_CLOSED_AT_SELECTION",
            "message": "Memory was selected from a CLOSED conversation"
        })
        
    req_max_turns = selection_config.get("max_turns", DEFAULT_SELECTION_MAX_TURNS)
    req_max_chars = selection_config.get("max_characters", DEFAULT_SELECTION_MAX_CHARACTERS)
    
    if not isinstance(req_max_turns, int) or not isinstance(req_max_chars, int) or req_max_turns < 0 or req_max_chars < 0:
        raise ConversationMemoryInputError("SELECTION_CONFIG_MALFORMED")
        
    effective_max_turns = min(req_max_turns, MAX_SELECTION_TURNS_CEILING)
    effective_max_chars = min(req_max_chars, MAX_SELECTION_CHARACTERS_CEILING)
    
    entries = state["entries"]
    
    if selection_config.get("exclude_current_turn", True):
        candidate_entries = entries[:-2] if len(entries) >= 2 else []
    else:
        candidate_entries = entries
        
    turns = []
    for i in range(0, len(candidate_entries), 2):
        turns.append((candidate_entries[i], candidate_entries[i+1]))
        
    turns.reverse()
    
    selected_turns = []
    accumulated_chars = 0
    
    truncated_by_turns = False
    truncated_by_budget = False
    
    for idx, turn in enumerate(turns):
        if len(selected_turns) >= effective_max_turns:
            truncated_by_turns = True
            break
            
        turn_cost = len(turn[0]["content"]) + len(turn[1]["content"])
        if accumulated_chars + turn_cost > effective_max_chars:
            truncated_by_budget = True
            break
            
        selected_turns.append(turn)
        accumulated_chars += turn_cost
        
    if truncated_by_turns:
        findings.append({
            "severity": "INFO",
            "code": "WINDOW_TRUNCATED_BY_MAX_TURNS",
            "message": "max_turns limit caused older turns to be excluded"
        })
        
    if truncated_by_budget:
        findings.append({
            "severity": "INFO",
            "code": "WINDOW_TRUNCATED_BY_BUDGET",
            "message": "Character budget caused fewer turns to be selected than max_turns would have allowed"
        })
        
    selected_turns.reverse()
    
    selected_entries = []
    for t in selected_turns:
        selected_entries.extend(t)
        
    if not selected_entries:
        findings.append({
            "severity": "WARNING",
            "code": "EMPTY_CONVERSATION",
            "message": "Conversation has zero turns; serialized_memory = ''"
        })
        
    serialized_memory = serialize_memory_window(selected_entries)
    
    start_idx = selected_entries[0]["turn_index"] if selected_entries else -1
    end_idx = selected_entries[-1]["turn_index"] if selected_entries else -1
    
    pkg_id = _generate_package_id(conversation_id, start_idx, end_idx, serialized_memory)
    
    package = {
        "conversation_memory_package_id": pkg_id,
        "conversation_id": conversation_id,
        "conversation_memory_version": CONVERSATION_MEMORY_VERSION,
        "selected_turn_count": len(selected_turns),
        "total_turn_count": state["turn_count"],
        "window_start_turn_index": start_idx,
        "window_end_turn_index": end_idx,
        "total_selected_characters": accumulated_chars,
        "serialized_memory": serialized_memory,
        "status": "WARNING" if any(f["severity"] == "WARNING" for f in findings) else "PASS",
        "entries": selected_entries,
        "findings": findings,
        "selected_at": _utc_now_iso()
    }
    
    validate_memory_package(package)
    
    return package
