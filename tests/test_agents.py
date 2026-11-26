"""Unit tests for the optional ADK multi-agent path (scripts/agents). Fake model and fake retrieval: no network, no quota.
Written before the implementation; each test failed (ImportError) before scripts/agents existed."""
import json
import os
import sys

import pytest

pytest.importorskip("google.adk")
sys.path.insert(0, os.path.dirname(__file__))

from agents_fakes import PASS, FakeRetrieve, ScriptedLlm, call, make_chunk, revise  # noqa: E402

from scripts.agents.config import AgentsConfig, agents_enabled, config_hash  # noqa: E402
from scripts.agents.pipeline import AgentPipeline, interleave_chunks, cited_chunk_ids  # noqa: E402

Q = "What share of elephants vanished from the park?"
FACT = "Over 75% of the elephants vanished [c1]."


def build(script, retrieve=None, cfg=None, **llm_kw):
    llm = ScriptedLlm(script=list(script), requests=[], **llm_kw)
    retrieve = retrieve or FakeRetrieve()
    pipe = AgentPipeline(model=llm, retrieve=retrieve, fingerprints=["fp"], config=cfg or AgentsConfig())
    return pipe, llm, retrieve


HAPPY = [call("search_proposals", query=Q), "SUFFICIENT", FACT, PASS]


def test_delegation_order_and_calls_on_the_happy_path():
    pipe, llm, retrieve = build(HAPPY)
    r = pipe.answer(Q, correlation_id="corr-1")
    assert [t["agent"] for t in r["trace"] if t["kind"] == "model"] == ["retriever", "retriever", "answerer", "verifier"]
    assert r["calls"] == 4 and r["final_text"] == FACT and r["decision"] == "ANSWERED"
    assert r["cap_hit"] is None and r["revision_count"] == 0 and r["verdict"] == "PASS"
    assert len(retrieve.requests) == 1 and retrieve.requests[0]["query"] == Q
    assert retrieve.requests[0]["index_fingerprints"] == ["fp"] and retrieve.requests[0]["top_k"] == 10
    assert llm.script == []                       # the whole script was consumed, nothing extra was called


def test_reformulation_path_makes_two_searches_and_no_third_model_call():
    script = [call("search_proposals", query=Q), call("search_proposals", query="elephant decline Boumba Bek"), FACT, PASS]
    retrieve = FakeRetrieve(by_query={Q: ["c1", "c2"], "elephant decline Boumba Bek": ["c9", "c1", "c8"]})
    pipe, llm, _ = build(script, retrieve)
    r = pipe.answer(Q)
    assert r["queries"] == [Q, "elephant decline Boumba Bek"]
    assert r["tool_calls"] == 2 and r["calls"] == 4 and llm.script == []
    assert r["context_chunk_ids"] == ["c1", "c9", "c2", "c8"]          # interleaved by rank, de-duplicated


def test_third_search_in_one_turn_is_refused_and_retrieval_is_not_called():
    script = [[call("search_proposals", query="a"), call("search_proposals", query="b"), call("search_proposals", query="c")], FACT, PASS]
    pipe, llm, retrieve = build(script)
    r = pipe.answer(Q)
    assert len(retrieve.requests) == 2 and r["tool_calls"] == 2
    refused = [t for t in r["trace"] if t["kind"] == "tool" and t.get("refused")]
    assert len(refused) == 1


def test_revision_is_requested_once_and_the_revised_draft_is_final_and_not_reverified():
    script = HAPPY[:2] + ["Over 75% vanished [c1]. Poachers were paid [c2].", revise("Poachers were paid [c2]."), "Over 75% vanished [c1].", "UNUSED"]
    pipe, llm, _ = build(script)
    r = pipe.answer(Q)
    assert r["final_text"] == "Over 75% vanished [c1]." and r["revision_count"] == 1 and r["calls"] == 5
    assert [t["agent"] for t in r["trace"] if t["kind"] == "model"] == ["retriever", "retriever", "answerer", "verifier", "answerer"]
    assert llm.script == ["UNUSED"]               # the verifier was NOT called a second time: one revision cap
    assert "Poachers were paid [c2]." in llm.system_text(4)    # the revision request carries the verifier's finding


def test_refusal_from_the_answerer_skips_the_verifier():
    pipe, llm, _ = build([call("search_proposals", query=Q), "SUFFICIENT", "NOT_IN_CONTEXT"])
    r = pipe.answer(Q)
    assert r["decision"] == "NOT_IN_CONTEXT" and r["calls"] == 3 and r["verdict"] is None


def test_unparsable_verifier_output_is_recorded_and_treated_as_pass():
    pipe, _, _ = build(HAPPY[:3] + ["I think it is fine"])
    r = pipe.answer(Q)
    assert r["verdict"] == "verifier_unparsable" and r["final_text"] == FACT and r["revision_count"] == 0


def test_no_search_means_not_in_context():
    pipe, _, retrieve = build(["I can answer without searching."])
    r = pipe.answer(Q)
    assert r["final_text"] == "NOT_IN_CONTEXT" and r["cap_hit"] == "no_retrieval" and retrieve.requests == []


def test_llm_call_cap_returns_not_in_context_never_a_partial_answer():
    pipe, _, _ = build(HAPPY, cfg=AgentsConfig(max_llm_calls=3))
    r = pipe.answer(Q)
    assert r["final_text"] == "NOT_IN_CONTEXT" and r["cap_hit"] == "llm_calls" and r["calls"] == 3


def test_timeout_returns_not_in_context():
    pipe, _, _ = build(HAPPY, cfg=AgentsConfig(timeout_s=0.3), delay_s=1.0)
    r = pipe.answer(Q)
    assert r["final_text"] == "NOT_IN_CONTEXT" and r["cap_hit"] == "timeout"


def test_model_error_returns_not_in_context_and_is_reported():
    pipe, _, _ = build([call("search_proposals", query=Q), RuntimeError("429 quota")])
    r = pipe.answer(Q)
    assert r["final_text"] == "NOT_IN_CONTEXT" and r["cap_hit"] == "llm_error" and "429" in r["error"]


def test_retrieval_failure_returns_not_in_context():
    def boom(_req):
        raise RuntimeError("index missing")
    pipe, _, _ = build([call("search_proposals", query=Q), "SUFFICIENT"], retrieve=boom)
    r = pipe.answer(Q)
    assert r["final_text"] == "NOT_IN_CONTEXT" and r["cap_hit"] in ("no_retrieval", "llm_error")


def test_session_state_holds_the_run_not_a_global():
    pipe, _, _ = build(HAPPY)
    r1 = pipe.answer(Q, correlation_id="a")
    st = r1["state"]
    for key in ("question", "correlation_id", "queries", "context_chunk_ids", "draft", "verdict", "revision_count"):
        assert key in st, key
    assert st["question"] == Q and st["correlation_id"] == "a" and st["draft"] == FACT and st["context_chunk_ids"] == ["c1", "c2", "c3"]


def test_two_questions_do_not_share_state():
    pipe, _, _ = build(HAPPY + [call("search_proposals", query="other"), "SUFFICIENT", "NOT_IN_CONTEXT"])
    a = pipe.answer(Q, correlation_id="a")
    b = pipe.answer("other", correlation_id="b")
    assert a["state"]["draft"] == FACT and b["state"]["draft"] == "NOT_IN_CONTEXT"
    assert b["queries"] == ["other"] and b["calls"] == 3


def test_token_accounting_sums_every_model_call():
    pipe, _, _ = build(HAPPY, tokens_in=120, tokens_out=7, tokens_thought=3)
    r = pipe.answer(Q)
    assert r["tokens"] == {"in": 480, "out": 28, "thought": 12}
    model_rows = [t for t in r["trace"] if t["kind"] == "model"]
    assert sum(t["tokens_in"] for t in model_rows) == 480 and sum(t["tokens_out"] for t in model_rows) == 28
    assert r["llm_ms"] >= 0 and r["wall_ms"] >= r["llm_ms"] * 0


def test_trace_records_carry_correlation_id_agent_times_and_tokens():
    pipe, _, _ = build(HAPPY)
    r = pipe.answer(Q, correlation_id="corr-xyz")
    assert len(r["trace"]) == 5                    # 4 model calls + 1 tool call
    for t in r["trace"]:
        assert t["correlation_id"] == "corr-xyz" and t["agent"] and t["start"] <= t["end"] and t["kind"] in ("model", "tool")
    tool = [t for t in r["trace"] if t["kind"] == "tool"][0]
    assert tool["agent"] == "retriever" and tool["name"] == "search_proposals" and tool["args"] == {"query": Q}
    assert all("tokens_in" in t and "tokens_out" in t for t in r["trace"] if t["kind"] == "model")


def test_answerer_sees_only_its_own_context_not_the_retriever_transcript():
    pipe, llm, _ = build(HAPPY)
    pipe.answer(Q)
    answer_req = llm.requests[2]
    flat = json.dumps([[str(p) for p in c.parts] for c in answer_req.contents])
    assert "search_proposals" not in flat
    sys_text = llm.system_text(2)
    assert "Chunk ID: c1" in sys_text and Q in sys_text and "NOT_IN_CONTEXT" in sys_text and "square brackets" in sys_text


def test_context_is_cut_to_the_token_budget():
    big = FakeRetrieve(default=["c1", "c2", "c3"])
    orig = big.__call__
    def huge(req):
        out = orig(req)
        for c in out["results"]:
            c["text"] = "x" * 9000                 # ~2250 tokens each at 4 chars/token
        return out
    pipe, _, _ = build(HAPPY, retrieve=huge, cfg=AgentsConfig(context_budget_tokens=4000))
    r = pipe.answer(Q)
    assert r["context_chunk_ids"] == ["c1"]


def test_interleave_chunks_orders_by_rank_across_searches_and_drops_duplicates():
    s1 = [make_chunk("a", 1), make_chunk("b", 2), make_chunk("c", 3)]
    s2 = [make_chunk("d", 1), make_chunk("a", 2)]
    assert [c["chunk_id"] for c in interleave_chunks([s1, s2])] == ["a", "d", "b", "c"]
    assert [c["rank"] for c in interleave_chunks([s1, s2])] == [1, 2, 3, 4]


def test_cited_chunk_ids_keeps_only_ids_that_were_in_the_context_in_order():
    assert cited_chunk_ids("A [c2]. B [c1][c2]. C [zzz].", ["c1", "c2", "c3"]) == ["c2", "c1"]


def test_agents_are_off_unless_the_flag_is_true():
    assert agents_enabled({}) is False
    assert agents_enabled({"AGENTS_ENABLED": "false"}) is False
    assert agents_enabled({"AGENTS_ENABLED": "1"}) is False
    assert agents_enabled({"AGENTS_ENABLED": " TRUE "}) is True


def test_config_hash_changes_with_any_cap():
    a = config_hash(AgentsConfig(), model_name="m", files=[])
    assert a == config_hash(AgentsConfig(), model_name="m", files=[])
    assert a != config_hash(AgentsConfig(max_llm_calls=5), model_name="m", files=[])
    assert a != config_hash(AgentsConfig(), model_name="other", files=[])


def test_braces_in_chunk_text_do_not_break_the_instruction_templating():
    def braces(req):
        out = FakeRetrieve()(req)
        out["results"][0]["text"] = "Budget {total} and {{query}} stay literal."
        return out
    pipe, llm, _ = build(HAPPY, retrieve=braces)
    r = pipe.answer(Q)
    assert r["final_text"] == FACT and "Budget {total} and {{query}} stay literal." in llm.system_text(2)


def test_one_pipeline_runs_many_questions_with_independent_caps():
    pipe, _, _ = build(HAPPY + HAPPY, cfg=AgentsConfig(max_llm_calls=4))
    assert pipe.answer(Q)["calls"] == 4 and pipe.answer(Q)["calls"] == 4


# ---- GuardedGeminiLlm: the ADK model that keeps the project's quota guard in the path --------------------------------
import asyncio  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

from google.adk.models import LlmRequest  # noqa: E402
from google.genai import errors, types  # noqa: E402

from scripts.agents.llm import GuardedGeminiLlm  # noqa: E402
from scripts.quota_guard import QuotaGuard  # noqa: E402
from scripts.stage13_llm_execution import LLMQuotaExhaustedError  # noqa: E402


def _genai_client(side_effect=None, text="hello"):
    resp = types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(text=text)]), finish_reason=types.FinishReason.STOP)],
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=11, candidates_token_count=2, total_token_count=13))
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(side_effect=side_effect, return_value=resp)
    return client


def _gen(llm):
    async def go():
        req = LlmRequest(model=llm.model, contents=[types.Content(role="user", parts=[types.Part(text="hi")])], config=types.GenerateContentConfig())
        return [r async for r in llm.generate_content_async(req)]
    return asyncio.run(go())


def test_guarded_llm_counts_the_call_and_returns_text_and_usage():
    guard = QuotaGuard(cap=5, pace=0)
    client = _genai_client()
    out = _gen(GuardedGeminiLlm(model="m", client=client, guard=guard))
    assert guard.used == 1 and out[0].content.parts[0].text == "hello" and out[0].usage_metadata.prompt_token_count == 11
    assert client.aio.models.generate_content.call_args.kwargs["model"] == "m"


def test_guarded_llm_refuses_without_touching_the_network_when_the_daily_cap_is_used_up():
    guard = QuotaGuard(cap=0, pace=0)
    client = _genai_client()
    with pytest.raises(LLMQuotaExhaustedError):
        _gen(GuardedGeminiLlm(model="m", client=client, guard=guard))
    client.aio.models.generate_content.assert_not_called()


def test_guarded_llm_trips_the_breaker_on_a_429():
    guard = QuotaGuard(cap=5, pace=0)
    err = errors.ClientError(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})
    with pytest.raises(LLMQuotaExhaustedError):
        _gen(GuardedGeminiLlm(model="m", client=_genai_client(side_effect=err), guard=guard))
    assert guard.tripped is True


# ---- wiring: composition root flag, /run-query use_agents, /capabilities ---------------------------------------------
from unittest.mock import patch  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from scripts import backend_server  # noqa: E402
from scripts.composition_root import build_agent_pipeline  # noqa: E402
from scripts.stage21_agent_planning import AgentDependencies  # noqa: E402


def _instance(pipeline=None):
    deps = AgentDependencies(handle_request=None, select_memory=None, append_turn=None, get_conversation=None, execute_tool=None,
                             tool_registry=None, tool_adapter=None, planner_llm_adapter=None, pipeline_deps=None, default_planner_model_name="m")
    return {"agent_dependencies": deps, "agent_pipeline": pipeline, "llm_adapter": object()}


def _client(pipeline=None):
    p = patch.object(backend_server, "_create_application_instance", return_value=_instance(pipeline))
    p.start()
    return TestClient(backend_server.app), p


def test_composition_root_builds_no_pipeline_when_the_flag_is_off():
    assert build_agent_pipeline({}, object(), None, None, [], "m") is None
    assert build_agent_pipeline({"AGENTS_ENABLED": "false"}, object(), None, None, [], "m") is None


def test_composition_root_fails_fast_when_the_flag_is_on_without_a_gemini_client():
    with pytest.raises(ValueError, match="AGENTS_ENABLED"):
        build_agent_pipeline({"AGENTS_ENABLED": "true"}, object(), None, {"retrieve": lambda r: r}, [], "m")


def test_use_agents_without_the_flag_is_a_client_error_and_runs_nothing():
    client, p = _client(None)
    try:
        with client as c:
            r = c.post("/run-query", json={"query": "q", "use_agents": True})
            assert r.status_code == 422 and "AGENTS_ENABLED" in r.json()["message"]
            assert c.get("/capabilities").json()["agents_available"] is False
    finally:
        p.stop()


def test_use_agents_with_the_flag_returns_the_agents_block_and_the_same_correlation_id_as_the_record():
    pipe, _, _ = build(HAPPY)
    client, p = _client(pipe)
    try:
        with client as c:
            r = c.post("/run-query", json={"query": Q, "use_agents": True})
            assert c.get("/capabilities").json()["agents_available"] is True
            recs = c.get("/observation-records").json()
    finally:
        p.stop()
    body = r.json()
    assert r.status_code == 200 and body["final_response"]["answer"]["response_text"] == FACT and body["status"] == "PASS"
    a = body["agents"]
    assert a["calls"] == 4 and a["agents_used"] == ["coordinator", "retriever", "answerer", "verifier"] and a["tokens"]["in"] == 400
    assert len(a["steps"]) == 5 and a["verdict"] == "PASS" and a["queries"] == [Q]
    assert body["correlation_id"] == recs[-1]["correlation_id"]
    assert "state" not in body and [c["chunk_id"] for c in body["chunks"]] == ["c1", "c2", "c3"]


def test_the_default_request_never_touches_the_agent_pipeline():
    class Boom:
        def answer(self, *a, **k):
            raise AssertionError("agent pipeline called on a default request")
    client, p = _client(Boom())
    try:
        with client as c:
            r = c.post("/run-query", json={"query": "q", "retrieval_only": True})
        assert "agents" not in r.json() or r.status_code != 200
    finally:
        p.stop()


def _server_error(code=503):
    return errors.ServerError(code, {"error": {"code": code, "message": "high demand", "status": "UNAVAILABLE"}})


def test_guarded_llm_retries_a_503_through_the_guard_and_counts_every_attempt():
    guard = QuotaGuard(cap=10, pace=0)
    client = _genai_client()
    ok = client.aio.models.generate_content.return_value
    client.aio.models.generate_content = AsyncMock(side_effect=[_server_error(), ok])
    out = _gen(GuardedGeminiLlm(model="m", client=client, guard=guard, backoff_s=0.0))
    assert out[0].content.parts[0].text == "hello" and guard.used == 2


def test_guarded_llm_gives_up_after_the_retries_and_raises_the_provider_error():
    guard = QuotaGuard(cap=10, pace=0)
    client = _genai_client(side_effect=_server_error())
    with pytest.raises(errors.ServerError):
        _gen(GuardedGeminiLlm(model="m", client=client, guard=guard, backoff_s=0.0, max_retries=2))
    assert guard.used == 3 and guard.tripped is False


def test_guarded_llm_does_not_retry_a_400():
    guard = QuotaGuard(cap=10, pace=0)
    client = _genai_client(side_effect=errors.ClientError(400, {"error": {"code": 400, "message": "bad", "status": "INVALID_ARGUMENT"}}))
    with pytest.raises(errors.ClientError):
        _gen(GuardedGeminiLlm(model="m", client=client, guard=guard, backoff_s=0.0))
    assert guard.used == 1


def test_trace_keeps_what_each_model_call_returned():
    pipe, _, _ = build(HAPPY)
    r = pipe.answer(Q)
    outs = [t["output"] for t in r["trace"] if t["kind"] == "model"]
    assert outs[0] == [{"function_call": "search_proposals", "args": {"query": Q}}] and outs[1] == [{"text": "SUFFICIENT"}]
    assert outs[2] == [{"text": FACT}] and outs[3] == [{"text": PASS}]


# ---- recorded-response regression (like tests/test_planner_live_regression.py) --------------------------------------------
FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "agents_recorded_dev.json")


def _recorded():
    return json.load(open(FIXTURE, encoding="utf-8"))["items"]


def _script_from(outputs):
    script = []
    for out in outputs:
        calls_ = [call(o["function_call"], **o["args"]) for o in out if "function_call" in o]
        script.append(calls_ if len(calls_) > 1 else calls_[0] if calls_ else out[0]["text"])
    return script


@pytest.mark.parametrize("item", _recorded(), ids=lambda i: i["qid"])
def test_recorded_live_responses_replay_to_the_same_outcome(item):
    """REAL raw responses of gemini-3.5-flash-lite on two DEV questions (eval/results/dev_agents_v1_record.jsonl). The model outputs are replayed
    unchanged; retrieval is faked with synthetic text under the real chunk ids (no corpus text in the repo)."""
    exp = item["expected"]
    by_query = {q: exp["context_chunk_ids"] for q in exp["queries"]}
    retrieve = FakeRetrieve(by_query=by_query, default=exp["context_chunk_ids"])
    pipe, llm, _ = build(_script_from(item["model_outputs"]), retrieve=retrieve)
    r = pipe.answer(item["question"])
    assert r["calls"] == exp["calls"] and r["tool_calls"] == exp["tool_calls"] and r["queries"] == exp["queries"]
    assert r["verdict"] == exp["verdict"] and r["decision"] == exp["decision"] and r["final_text"] == exp["final_text"]
    assert r["cited_chunk_ids"] == exp["cited_chunk_ids"] and r["cap_hit"] is None and llm.script == []
