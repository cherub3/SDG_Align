"""
In-memory ConversationStore for Stage 19.

Demo-grade: data is not persisted across process restarts and is not
synchronized for concurrent access beyond what CPython's GIL provides
for simple dict operations.
"""

from typing import Optional, Dict, Any
from scripts.stage19_conversation_memory import ConversationStore


class InMemoryConversationStore(ConversationStore):
    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}

    def get(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        return self._store.get(conversation_id)

    def put(self, conversation_state: Dict[str, Any]) -> None:
        self._store[conversation_state["conversation_id"]] = conversation_state

    def delete(self, conversation_id: str) -> None:
        self._store.pop(conversation_id, None)
