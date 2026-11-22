import functools
from typing import Dict, Any, Sequence, Optional, List

from scripts.phase1_1_configuration_layer import (
    load_raw_settings,
    validate_settings,
    build_provider_registry,
    wire_dependencies,
    validate_wiring_result,
    ProviderRegistration
)
from scripts.stage21_agent_planning import AgentDependencies

from scripts.conversation_store import InMemoryConversationStore
from scripts.stage19_conversation_memory import (
    get_conversation as _stage19_get_conversation,
    select_memory as _stage19_select_memory,
    append_turn as _stage19_append_turn,
)
from scripts.tool_registry import InMemoryToolRegistry, CallableToolAdapter
from scripts.stage20_tool_function_calling import execute_tool as _stage20_execute_tool
from scripts.cache_adapter import InMemoryCacheAdapter
from scripts.pipeline_deps_factory import build_pipeline_deps
from scripts.stage18_api_response_serving import handle_request as _stage18_handle_request


def _discover_index_fingerprints(embedding_adapter: Any) -> List[str]:
    """Fingerprints of on-disk vector indexes built by the wired embedding provider."""
    import json
    from pathlib import Path

    fingerprints: List[str] = []
    if embedding_adapter is None:
        return fingerprints
    index_root = Path("data/proposals/vector_index")
    if not index_root.is_dir():
        return fingerprints
    for meta_path in sorted(index_root.glob("*/index_metadata.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (
            meta.get("provider") == embedding_adapter.provider_name
            and meta.get("model_name") == embedding_adapter.model_name
            and meta.get("model_version") == embedding_adapter.model_version
        ):
            fp = meta.get("index_fingerprint")
            if fp:
                fingerprints.append(fp)
    return fingerprints


def compose_application(
    registrations: Sequence[ProviderRegistration],
    env: Optional[Dict[str, str]] = None,
    dotenv_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Composition root entrypoint.
    Executes the full Phase 1.1 configuration lifecycle, wiring, and object graph mapping.
    """
    # 1. Configuration Lifecycle [2]: load and validate
    raw = load_raw_settings(env=env, dotenv_path=dotenv_path)
    settings = validate_settings(raw)

    # 2. Composition Lifecycle [3]: assemble and build registry
    registry = build_provider_registry(registrations)

    # 3. Composition Lifecycle [4]: dependency wiring and validation
    wiring_result = wire_dependencies(settings, registry)
    validate_wiring_result(wiring_result, settings)

    # 4. Composition Lifecycle [5]: application assembly mapping
    wired = wiring_result["wired"]

    llm_adapter = wired.get("LLM_PROVIDER")
    embedding_adapter = wired.get("EMBEDDING_PROVIDER")
    planner_adapter = wired.get("PLANNER_LLM_PROVIDER")

    # Extract deployment scalars from raw configuration values
    values = raw.get("values", {})
    default_planner_model = values.get("DEFAULT_PLANNER_MODEL_NAME", "gemini-2.0-flash")
    default_llm_model = values.get("LLM_PROVIDER_EXTRA_MODEL", "gemini-2.5-flash")

    # Conversation store and Stage 19 hook closures (store bound via partial)
    conversation_store = InMemoryConversationStore()
    get_conversation_fn = functools.partial(_stage19_get_conversation, store=conversation_store)
    select_memory_fn = functools.partial(_stage19_select_memory, store=conversation_store)
    _append_turn_raw = functools.partial(_stage19_append_turn, store=conversation_store)

    def append_turn_fn(conversation_id, turn):
        # Stage 19's start_conversation() derives its own id from a session seed, so a
        # client-supplied conversation_id can never pre-exist in the store. The transport
        # accepts arbitrary conversation ids (stateless, Decision 3), so the composition
        # root creates the conversation lazily on the first append under that id.
        from scripts.stage19_conversation_memory import (
            CONVERSATION_MEMORY_VERSION,
            ConversationMemoryInputError,
            _utc_now_iso,
            validate_conversation,
        )
        import copy as _copy

        try:
            return _append_turn_raw(conversation_id, turn)
        except ConversationMemoryInputError as exc:
            if str(exc) != "CONVERSATION_NOT_FOUND":
                raise
            state = {
                "conversation_id": conversation_id,
                "conversation_memory_version": CONVERSATION_MEMORY_VERSION,
                "status": "ACTIVE",
                "created_at": _utc_now_iso(),
                "closed_at": None,
                "turn_count": 0,
                "entries": [],
                "metadata": {"title": None, "tags": []},
                "findings": [],
            }
            validate_conversation(state)
            conversation_store.put(_copy.deepcopy(state))
            return _append_turn_raw(conversation_id, turn)

    # Tool registry and adapter — empty, no production ToolDefinitions exist in this repo
    tool_registry = InMemoryToolRegistry()
    tool_adapter = CallableToolAdapter({})

    # Cache adapter and PipelineDependencies (requires both LLM and embedding adapters)
    cache_adapter = InMemoryCacheAdapter()
    pipeline_deps = None
    if llm_adapter and embedding_adapter:
        pipeline_deps = build_pipeline_deps(
            llm_adapter=llm_adapter,
            embedding_adapter=embedding_adapter,
            cache_adapter=cache_adapter,
            default_model_name=default_llm_model,
        )

    # The planner LLM cannot know which index fingerprints are deployed on disk — that is
    # deployment state, so the composition root defaults an empty index_fingerprints to the
    # indexes that match the wired embedding provider (never a stale other-provider index).
    default_fingerprints = _discover_index_fingerprints(embedding_adapter)

    def _handle_request_with_default_indexes(request, deps):
        if not request.get("index_fingerprints") and default_fingerprints:
            request = dict(request)
            request["index_fingerprints"] = list(default_fingerprints)
        return _stage18_handle_request(request, deps)

    # Construct fully-wired AgentDependencies
    agent_deps = AgentDependencies(
        handle_request=_handle_request_with_default_indexes,
        select_memory=select_memory_fn,
        append_turn=append_turn_fn,
        get_conversation=get_conversation_fn,
        execute_tool=_stage20_execute_tool,
        tool_registry=tool_registry,
        tool_adapter=tool_adapter,
        planner_llm_adapter=planner_adapter,
        pipeline_deps=pipeline_deps,
        default_planner_model_name=default_planner_model,
    )

    return {
        "settings": settings,
        "llm_adapter": llm_adapter,
        "embedding_adapter": embedding_adapter,
        "agent_dependencies": agent_deps,
    }
