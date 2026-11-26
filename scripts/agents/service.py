"""Turns one AgentPipeline run into the API response of /run-query (use_agents=true). No corpus text leaves except the context chunks."""
from typing import Any, Dict


def run_agents_request(pipeline, agent_request: Dict[str, Any]) -> Dict[str, Any]:
    r = pipeline.answer(agent_request["query"], correlation_id=agent_request.get("correlation_id"))
    steps = [{k: t[k] for k in ("agent", "kind", "start", "end", "ms") if k in t}
             | {k: t[k] for k in ("name", "args", "tokens_in", "tokens_out", "tokens_thought", "hits", "refused", "error") if k in t}
             for t in r["trace"]]
    chunks = [{"chunk_id": b["chunk_id"], "doc_id": b["doc_id"], "title": b.get("title", ""), "text": b["text"], "score": b.get("score"),
               "heading_path": b.get("heading_path", []), "page_start": b.get("page_start"), "page_end": b.get("page_end")}
              for b in r["context_blocks"]]
    return {
        "status": "PASS" if not r["cap_hit"] else "CAP_HIT",
        "query": agent_request["query"],
        "final_response": {"answer": {"response_text": r["final_text"], "decision": r["decision"]}},
        "chunks": chunks,
        "agents": {"agents_used": r["agents_used"], "steps": steps, "calls": r["calls"], "tool_calls": r["tool_calls"],
                   "tokens": r["tokens"], "queries": r["queries"], "revision_count": r["revision_count"], "verdict": r["verdict"],
                   "cap_hit": r["cap_hit"], "cited_chunk_ids": r["cited_chunk_ids"], "llm_ms": r["llm_ms"], "wall_ms": r["wall_ms"]},
    }
