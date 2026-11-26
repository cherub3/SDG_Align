"""Hierarchical ADK pipeline: coordinator -> retriever (ReAct, search tool) -> answerer -> verifier (-> one revision).

Retrieval is the existing hybrid retrieve function, injected as `retrieve`; nothing is reimplemented here. The model is any
ADK BaseLlm (GuardedGeminiLlm live, a scripted fake in tests). Every cap hit ends in NOT_IN_CONTEXT, never a partial answer.
"""
import asyncio
import json
import re
import threading
import time
import uuid
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Sequence

from google.adk.agents import BaseAgent, Context, LlmAgent
from google.adk.events import Event
from google.adk.events.event_actions import EventActions
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool
from google.genai import types
from pydantic import ConfigDict

from scripts.abstention import SENTINEL, decision
from scripts.agents import prompts
from scripts.agents.config import AgentsConfig
from scripts.agents.runtime import CapExceeded, RunContext, current_run, now_iso
from scripts.stage11_context_assembly import build_context_blocks, enforce_budget
from scripts.stage12_prompt_construction import render_context_text

APP_NAME = "agents"       # ADK expects the runner app name to match the package the agent is defined in
_CITE = re.compile(r"\[([^\[\]]+)\]")


def interleave_chunks(result_lists: Sequence[Sequence[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Merge the results of several searches by rank (rank 1 of each search, then rank 2, ...), dropping repeated chunk ids, re-ranked 1..n."""
    seen, merged = set(), []
    for i in range(max((len(r) for r in result_lists), default=0)):
        for results in result_lists:
            if i < len(results) and results[i]["chunk_id"] not in seen:
                seen.add(results[i]["chunk_id"])
                merged.append(dict(results[i]))
    for n, c in enumerate(merged, 1):
        c["rank"] = n
    return merged


def cited_chunk_ids(text: str, valid_ids: Sequence[str]) -> List[str]:
    """Chunk ids written in square brackets, in order of first appearance, keeping only ids that were in the context."""
    valid, out = set(valid_ids), []
    for m in _CITE.finditer(text or ""):
        for part in re.split(r"[,;\s]+", m.group(1).strip()):
            if part in valid and part not in out:
                out.append(part)
    return out


def strip_citation_markers(text: str, valid_ids: Sequence[str]) -> str:
    valid = set(valid_ids)

    def repl(m):
        parts = [p for p in re.split(r"[,;\s]+", m.group(1).strip()) if p]
        return "" if parts and all(p in valid for p in parts) else m.group(0)
    return re.sub(r"\s*\[([^\[\]]+)\]", repl, text or "").strip()


def parse_verdict(raw: str) -> Dict[str, Any]:
    """{'verdict': 'PASS'|'REVISE'|'verifier_unparsable', 'unsupported': [...]}. Unparsable output is reported, never guessed."""
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    m = re.search(r"\{.*\}", text, re.S)
    try:
        obj = json.loads(m.group(0)) if m else None
    except ValueError:
        obj = None
    if not isinstance(obj, dict) or str(obj.get("verdict", "")).upper() not in ("PASS", "REVISE"):
        return {"verdict": "verifier_unparsable", "unsupported": []}
    uns = obj.get("unsupported") if isinstance(obj.get("unsupported"), list) else []
    return {"verdict": str(obj["verdict"]).upper(), "unsupported": uns}


def _output_of(llm_response) -> List[Dict[str, Any]]:
    """What the model returned, as plain data: [{'text': ...}] or [{'function_call': name, 'args': {...}}]. Kept in the trace (and used to record real responses)."""
    out = []
    for p in (getattr(getattr(llm_response, "content", None), "parts", None) or []):
        if getattr(p, "function_call", None) is not None:
            out.append({"function_call": p.function_call.name, "args": dict(p.function_call.args or {})})
        elif getattr(p, "text", None) is not None and not getattr(p, "thought", False):
            out.append({"text": p.text[:2000]})
    return out


def _run_sync_loop():
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, name="agents-loop", daemon=True).start()
    return loop


class Coordinator(BaseAgent):
    """Deterministic orchestration: no model call of its own. Delegates to the three LLM agents and enforces the revision cap."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    retriever: Any
    answerer: Any
    verifier: Any
    cfg: Any

    def _event(self, ctx, delta: Dict[str, Any], text: Optional[str] = None) -> Event:
        content = types.Content(role="model", parts=[types.Part(text=text)]) if text is not None else None
        return Event(author=self.name, invocation_id=ctx.invocation_id, branch=ctx.branch, content=content, actions=EventActions(state_delta=delta))

    def _fail(self, ctx, cap_hit: str, error: Optional[str] = None) -> Event:
        d = {"final": SENTINEL, "cap_hit": cap_hit}
        if error:
            d["error"] = error
        return self._event(ctx, d, SENTINEL)

    async def _run_async_impl(self, ctx) -> AsyncGenerator[Event, None]:
        run = current_run.get()
        cfg = self.cfg
        state = ctx.session.state
        try:
            async for ev in self.retriever.run_async(ctx):
                yield ev
            if not run.search_results:
                yield self._fail(ctx, "no_retrieval")
                return
            blocks, _ = enforce_budget(build_context_blocks(interleave_chunks(run.search_results)), cfg.context_budget_tokens)
            ids = [b["chunk_id"] for b in blocks]
            run.context_blocks = blocks
            yield self._event(ctx, {"queries": list(run.queries), "context_chunk_ids": ids, "context_text": render_context_text(blocks),
                                    "revision_count": 0})

            async for ev in self.answerer.run_async(ctx):
                yield ev
            draft = ctx.session.state.get("draft") or ""
            if decision(draft) == "EMPTY":
                yield self._fail(ctx, "empty_answer")
                return
            if decision(draft) == "NOT_IN_CONTEXT":
                yield self._event(ctx, {"final": SENTINEL}, SENTINEL)
                return

            cited = cited_chunk_ids(draft, ids)
            shown = [b for b in blocks if b["chunk_id"] in cited] or blocks
            yield self._event(ctx, {"verifier_prompt": prompts.verifier_instruction(draft, shown)})
            async for ev in self.verifier.run_async(ctx):
                yield ev
            verdict = parse_verdict(ctx.session.state.get("verdict_raw") or "")
            yield self._event(ctx, {"verdict": verdict["verdict"]})

            if verdict["verdict"] == "REVISE" and ctx.session.state.get("revision_count", 0) < cfg.max_revisions:
                findings = "\n".join(f"- {u.get('sentence', u) if isinstance(u, dict) else u}" for u in verdict["unsupported"]) or "- (not itemised)"
                yield self._event(ctx, {"revision_count": 1, "revision_findings": findings, "draft_initial": draft})
                async for ev in self.answerer.run_async(ctx):
                    yield ev
                draft = ctx.session.state.get("draft") or ""
                if decision(draft) == "EMPTY":
                    yield self._fail(ctx, "empty_answer")
                    return
            yield self._event(ctx, {"final": draft}, draft)
        except CapExceeded as e:
            yield self._fail(ctx, e.kind)
        except Exception as e:  # noqa: BLE001  (a model or ADK failure ends the question as a refusal and is reported)
            yield self._fail(ctx, "llm_error", f"{type(e).__name__}: {e}"[:300])


class AgentPipeline:
    def __init__(self, model: Any, retrieve: Callable[[Dict[str, Any]], Dict[str, Any]], fingerprints: Sequence[str],
                 config: Optional[AgentsConfig] = None):
        self.cfg = config or AgentsConfig()
        self._retrieve, self._fps = retrieve, list(fingerprints)
        self.model = model
        self._loop = _run_sync_loop()
        self.coordinator = self._build()

    # ---- tool -------------------------------------------------------------------------------------------------------
    def _make_search_tool(self) -> FunctionTool:
        cfg = self.cfg

        def search_proposals(query: str, tool_context: Context) -> dict:
            """Search the project proposals with the hybrid (keyword + semantic) retriever. Returns the best passages as short snippets."""
            run = current_run.get()
            slot = run.take_search()
            if slot is None:
                return {"refused": True, "error": f"search limit of {cfg.max_searches} reached; do not search again"}
            try:
                result = self._retrieve({"query": query, "index_fingerprints": self._fps, "top_k": cfg.top_k})
            except Exception as e:  # noqa: BLE001
                run.tool_calls -= 1
                return {"error": f"retrieval failed: {type(e).__name__}"}
            chunks = result.get("results", []) if isinstance(result, dict) else []
            run.queries.append(query)
            run.search_results.append(chunks)
            tool_context.state["queries"] = list(run.queries)
            return {"search_number": slot, "query": query,
                    "hits": [{"chunk_id": c["chunk_id"], "document": c.get("title", ""), "snippet": c["text"][:cfg.snippet_chars]} for c in chunks]}
        return FunctionTool(search_proposals)

    # ---- callbacks (cap, tokens, trace) -----------------------------------------------------------------------------
    def _before_model(self, ctx, llm_request):
        run = current_run.get()
        run.take_call()
        run.start(("model", run.calls))
        return None

    def _after_model(self, ctx, llm_response):
        run = current_run.get()
        start, end, ms = run.finish(("model", run.calls))
        u = getattr(llm_response, "usage_metadata", None)
        t_in = int(getattr(u, "prompt_token_count", None) or 0)
        t_out = int(getattr(u, "candidates_token_count", None) or 0)
        t_th = int(getattr(u, "thoughts_token_count", None) or 0)
        run.tokens_in += t_in
        run.tokens_out += t_out
        run.tokens_thought += t_th
        run.llm_ms += ms
        run.trace.append({"correlation_id": run.correlation_id, "agent": ctx.agent_name, "kind": "model", "call": run.calls, "start": start,
                          "end": end, "ms": round(ms, 1), "tokens_in": t_in, "tokens_out": t_out, "tokens_thought": t_th,
                          "output": _output_of(llm_response)})
        return None

    def _before_tool(self, tool, args, ctx):
        current_run.get().start(("tool", ctx.function_call_id))
        return None

    def _after_tool(self, tool, args, ctx, result):
        run = current_run.get()
        start, end, ms = run.finish(("tool", ctx.function_call_id))
        rec = {"correlation_id": run.correlation_id, "agent": ctx.agent_name, "kind": "tool", "name": tool.name, "args": dict(args),
               "start": start, "end": end, "ms": round(ms, 1)}
        if isinstance(result, dict):
            if result.get("refused"):
                rec["refused"] = True
            if "hits" in result:
                rec["hits"] = len(result["hits"])
            if result.get("error"):
                rec["error"] = result["error"]
            if result.get("search_number") == self.cfg.max_searches:
                ctx.actions.skip_summarization = True          # the second search ends the retriever turn: no further model call
        run.trace.append(rec)
        return None

    # ---- agents -----------------------------------------------------------------------------------------------------
    def _gen(self, max_tokens: int) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(temperature=self.cfg.temperature, max_output_tokens=max_tokens)

    def _build(self) -> Coordinator:
        cfg = self.cfg
        hooks = dict(before_model_callback=self._before_model, after_model_callback=self._after_model,
                     before_tool_callback=self._before_tool, after_tool_callback=self._after_tool)
        retriever = LlmAgent(name="retriever", model=self.model, instruction=prompts.RETRIEVER_INSTRUCTION, tools=[self._make_search_tool()],
                             generate_content_config=self._gen(cfg.retriever_max_tokens), **hooks)

        def answer_instruction(ctx):
            s = ctx.state
            return prompts.answer_instruction(cfg.template_version, s.get("question", ""), s.get("context_text", ""),
                                              s.get("revision_findings", "") if s.get("revision_count", 0) else "")

        answerer = LlmAgent(name="answerer", model=self.model, instruction=answer_instruction, include_contents="none", output_key="draft",
                            generate_content_config=self._gen(cfg.answer_max_tokens), **hooks)
        verifier = LlmAgent(name="verifier", model=self.model, instruction=lambda ctx: ctx.state.get("verifier_prompt", ""),
                            include_contents="none", output_key="verdict_raw", generate_content_config=self._gen(cfg.verifier_max_tokens), **hooks)
        return Coordinator(name="coordinator", sub_agents=[retriever, answerer, verifier], retriever=retriever, answerer=answerer,
                           verifier=verifier, cfg=cfg)

    # ---- public -----------------------------------------------------------------------------------------------------
    def answer(self, question: str, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """Blocking. Safe to call from sync code and from a running event loop's thread (the run happens on a private loop)."""
        fut = asyncio.run_coroutine_threadsafe(self._answer_async(question, correlation_id or uuid.uuid4().hex), self._loop)
        return fut.result()

    async def _answer_async(self, question: str, correlation_id: str) -> Dict[str, Any]:
        cfg = self.cfg
        run = RunContext(correlation_id=correlation_id, max_llm_calls=cfg.max_llm_calls, max_searches=cfg.max_searches)
        token = current_run.set(run)
        t0 = time.monotonic()
        started = now_iso()
        svc = InMemorySessionService()
        sid = uuid.uuid4().hex
        await svc.create_session(app_name=APP_NAME, user_id="agents", session_id=sid, state={"question": question, "correlation_id": correlation_id})
        runner = Runner(agent=self.coordinator, app_name=APP_NAME, session_service=svc)
        outer_cap, outer_error = None, None

        async def drive():
            msg = types.Content(role="user", parts=[types.Part(text=question)])
            async for _ in runner.run_async(user_id="agents", session_id=sid, new_message=msg):
                pass
        try:
            await asyncio.wait_for(drive(), timeout=cfg.timeout_s)
        except asyncio.TimeoutError:
            outer_cap = "timeout"
        except Exception as e:  # noqa: BLE001
            outer_cap, outer_error = "llm_error", f"{type(e).__name__}: {e}"[:300]
        finally:
            current_run.reset(token)
        session = await svc.get_session(app_name=APP_NAME, user_id="agents", session_id=sid)
        state = dict(session.state) if session else {}
        cap_hit = outer_cap or state.get("cap_hit")
        final = SENTINEL if outer_cap else (state.get("final") or SENTINEL)
        if outer_cap:
            state["final"], state["cap_hit"] = final, outer_cap
        ids = state.get("context_chunk_ids") or []
        agents_used = ["coordinator"] + [a for a in ("retriever", "answerer", "verifier") if any(t["agent"] == a for t in run.trace)]
        return {"correlation_id": correlation_id, "started": started, "question": question, "final_text": final, "decision": decision(final),
                "cap_hit": cap_hit, "error": outer_error or state.get("error"), "calls": run.calls, "retries": run.retries, "tool_calls": run.tool_calls,
                "queries": list(run.queries), "context_chunk_ids": ids, "cited_chunk_ids": cited_chunk_ids(final, ids),
                "draft_initial": state.get("draft_initial"), "revision_count": state.get("revision_count", 0), "verdict": state.get("verdict"),
                "tokens": {"in": run.tokens_in, "out": run.tokens_out, "thought": run.tokens_thought}, "llm_ms": round(run.llm_ms, 1),
                "wall_ms": round((time.monotonic() - t0) * 1000.0, 1), "agents_used": agents_used, "trace": run.trace, "state": state, "context_blocks": run.context_blocks}
