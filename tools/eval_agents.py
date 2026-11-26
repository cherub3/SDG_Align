"""Phase 4: evaluate the optional ADK multi-agent path (arm B) against the single-call pipeline (arm A) on the frozen gold set.

  python tools/eval_agents.py run --split dev  --label dev_agents_v1 --limit 3 --max-calls 18        (LIVE, uses quota)
  python tools/eval_agents.py run --split dev  --label dev_agents_v1 --max-calls 80
  python tools/eval_agents.py freeze --label dev_agents_v1                                           (writes the frozen config hash)
  python tools/eval_agents.py run --split test --label test_agents_v1 --expect-config-hash <sha> --max-calls 312
  python tools/eval_agents.py compare --label test_agents_v1                                         (offline: A vs B table + keep rule)
  python tools/eval_agents.py run --split dev --label dev_fake --fake                                (scripted model, no network)

Safety: the pre-registered budget is 400 model calls per Pacific day. `run` adds today's calls from eval/results/quota_ledger.json
to the planned maximum (items still to run x max_llm_calls, capped by --max-calls) and REFUSES to start if that exceeds 400. Pace is
12 calls/minute (the Gemini limit observed is 15). The run stops on the first 429, guard refusal or model error and keeps the rows done
so far; re-running the same label resumes. A TEST run needs the frozen config hash and a complete DEV run. No row is ever re-run.
"""
import argparse
import glob
import hashlib
import json
import os
import sys
import time
import uuid

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import answer_checks as ac  # noqa: E402
import eval_answers as ea  # noqa: E402
import freeze_gold as fg  # noqa: E402
import gold_common as gc  # noqa: E402

RESULTS = os.path.join(REPO, "eval", "results")
LEDGER = os.path.join(RESULTS, "quota_ledger.json")
DAILY_LIMIT = 400           # pre-registered (PHASE_4_REPORT.md section 3)
PACE_RPM = 12
ARM_A_ROWS, ARM_A_SUMMARY = "test_noplanner_v21.jsonl", "test_noplanner_v21_summary.json"
FROZEN = os.path.join(RESULTS, "agents_frozen_config.json")
PRICE_IN_PER_M, PRICE_OUT_PER_M = 0.30, 2.50     # USD per 1M tokens, gemini-3.5-flash-lite paid tier, read 2026-11-23 (estimate only)
SENTINEL = "NOT_IN_CONTEXT"


class StopRun(Exception):
    pass


# ---- ledger and daily budget ------------------------------------------------------------------------------------------
def pacific_today():
    from scripts.quota_guard import pacific_day
    return pacific_day()


def ledger_used_today(path=LEDGER, today=None):
    today = today or pacific_today()
    data = json.load(open(path, encoding="utf-8"))
    entries = [e for e in data["entries"] if e["day_pacific"] == today]
    # A "key_change" entry (reset=true) starts a new count: the daily quota belongs to the API key's account.
    for i in range(len(entries) - 1, -1, -1):
        if entries[i].get("reset"):
            entries = entries[i + 1:]
            break
    return sum(e["calls"] for e in entries)


def check_budget(used_today, remaining_items, max_llm_calls, max_calls, limit=DAILY_LIMIT):
    """Returns (planned_max, ok). planned_max = remaining items x per-question cap, never more than --max-calls."""
    planned = min(remaining_items * max_llm_calls, max_calls)
    return planned, used_today + planned <= limit


def add_ledger_entry(label, calls, note, path=LEDGER):
    data = json.load(open(path, encoding="utf-8"))
    data["entries"].append({"day_pacific": pacific_today(), "label": label, "calls": calls, "note": note})
    json.dump(data, open(path, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)


# ---- configuration freeze -------------------------------------------------------------------------------------------
def agent_files():
    return sorted(glob.glob(os.path.join(REPO, "scripts", "agents", "*.py")))


def current_config_hash():
    from scripts.agents.config import AgentsConfig, config_hash
    from scripts.model_config import default_gemini_model
    return config_hash(AgentsConfig(), model_name=default_gemini_model(), files=agent_files(),
                       extra={"retrieval": "hybrid rrf_k=10 w_bm25=2.0 depth=50", "pace_rpm": PACE_RPM, "daily_limit": DAILY_LIMIT})


# ---- environment (real retrieval, real or fake model) ------------------------------------------------------------------
def build_env(fake):
    os.chdir(REPO)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    from scripts.agents.config import AgentsConfig
    from scripts.agents.llm import GuardedGeminiLlm
    from scripts.agents.pipeline import AgentPipeline
    from scripts.cache_adapter import InMemoryCacheAdapter
    from scripts.embedding_provider_local import LocalEmbeddingAdapter
    from scripts.model_config import default_gemini_model
    from scripts.pipeline_deps_factory import build_pipeline_deps
    from scripts.quota_guard import QuotaGuard

    model = default_gemini_model()
    emb = LocalEmbeddingAdapter()
    ident = (emb.provider_name, "BAAI/bge-small-en-v1.5", "v1.5")
    fps = [m["index_fingerprint"] for m in (json.load(open(p, encoding="utf-8")) for p in sorted(glob.glob("data/proposals/vector_index/*/index_metadata.json")))
           if (m.get("provider"), m.get("model_name"), m.get("model_version")) == ident]
    if len(fps) != 1:
        raise SystemExit(f"expected exactly one matching index, found {fps}")
    retrieve = build_pipeline_deps(None, emb, InMemoryCacheAdapter(), model)["retrieve"]
    if fake:
        sys.path.insert(0, os.path.join(REPO, "tests"))
        from agents_fakes import PASS, ScriptedLlm, call

        class Auto(ScriptedLlm):
            """Offline stand-in that follows the protocol (search, SUFFICIENT, cite, PASS). Not a measurement of anything."""
            async def generate_content_async(self, llm_request, stream=False):
                si = str(llm_request.config.system_instruction)
                last = llm_request.contents[-1].parts[0] if llm_request.contents else None
                if "You find the passages" in si:
                    q = llm_request.contents[0].parts[0].text
                    self.script = [call("search_proposals", query=q) if not any(p.function_response for c in llm_request.contents for p in c.parts) else "SUFFICIENT"]
                elif "You check an answer" in si:
                    self.script = [PASS]
                else:
                    ids = [l.split("Chunk ID: ")[1] for l in si.splitlines() if l.startswith("Chunk ID: ")]
                    self.script = [f"See the excerpt [{ids[0]}]." if ids else SENTINEL]
                async for r in super().generate_content_async(llm_request, stream):
                    yield r
        llm, guard = Auto(script=[], requests=[]), None
    else:
        from scripts.llm_provider_gemini import gemini_llm_factory
        from tools_env import gemini_key
        key = gemini_key()
        if not key:
            raise SystemExit("GEMINI_API_KEY not set in the environment or .env; no call made.")
        inner = gemini_llm_factory({"seam": "LLM_PROVIDER", "provider_name": "gemini", "credential_ref": "", "extra": {}}, key)
        guard = QuotaGuard(cap=DAILY_LIMIT, pace=PACE_RPM)
        llm = GuardedGeminiLlm(model=model, client=inner._client, guard=guard)
    cfg = AgentsConfig()
    return AgentPipeline(model=llm, retrieve=retrieve, fingerprints=fps, config=cfg), guard, cfg


def chunk_index():
    spans, texts = {}, {}
    for doc in os.listdir(gc.CHUNKS):
        p = os.path.join(gc.CHUNKS, doc, "chunks.json")
        if os.path.exists(p):
            for c in json.load(open(p, encoding="utf-8"))["chunks"]:
                spans[c["chunk_id"]] = (c["doc_id"], c["char_start"], c["char_end"])
                texts[c["chunk_id"]] = c["text"]
    return spans, texts


def make_row(it, r, spans, guard_used):
    from scripts.agents.pipeline import strip_citation_markers
    ids = r["context_chunk_ids"]
    row = {"qid": it["qid"], "type": it["type"], "kind": it.get("kind"), "question": it["question"], "correlation_id": r["correlation_id"],
           "response_text": r["final_text"], "response_text_plain": strip_citation_markers(r["final_text"], ids), "decision": r["decision"],
           "cap_hit": r["cap_hit"], "error": r["error"], "calls": r["calls"], "retries": r["retries"], "tool_calls": r["tool_calls"], "queries": r["queries"],
           "revision_count": r["revision_count"], "verdict": r["verdict"], "draft_initial": r["draft_initial"],
           "context_chunk_ids": ids, "cited_chunk_ids": r["cited_chunk_ids"], "tokens": r["tokens"], "llm_ms": r["llm_ms"],
           "wall_ms": r["wall_ms"], "agents_used": r["agents_used"], "trace": r["trace"], "guard_used": guard_used}
    if it["type"] != "unanswerable":
        gold = [(e["doc_id"], e["clean_start"], e["clean_end"]) for e in it["evidence"]]
        row["gold_in_context"] = any(c in spans and any(spans[c][0] == d and gc.is_hit(spans[c][1], spans[c][2], s, e) for d, s, e in gold) for c in ids)
    return row


def cmd_run(a):
    bad = fg.check_frozen()
    if bad:
        raise SystemExit("REFUSING TO RUN, frozen inputs differ: " + "; ".join(bad))
    items = ea.load_items(a.split)
    out = os.path.join(RESULTS, f"{a.label}.jsonl")
    done = {r["qid"] for r in ea.read_rows(out)}
    todo = [i for i in items if i["qid"] not in done]
    if a.limit:
        todo = todo[:a.limit]
    if a.split == "test" and not a.fake:
        if not a.expect_config_hash:
            raise SystemExit("REFUSING TO RUN on TEST without --expect-config-hash (the frozen configuration hash).")
        now = current_config_hash()
        if now != a.expect_config_hash:
            raise SystemExit(f"REFUSING TO RUN: configuration hash {now} != expected {a.expect_config_hash}")
        dev_rows = ea.read_rows(os.path.join(RESULTS, "dev_agents_v1.jsonl"))
        if len(dev_rows) < len(ea.load_items("dev")):
            raise SystemExit("REFUSING TO RUN on TEST: the DEV smoke run is not complete.")
    pipe, guard, cfg = build_env(a.fake)
    if not a.fake:
        planned, ok = check_budget(ledger_used_today(), len(todo), cfg.max_llm_calls, a.max_calls)
        print(f"planned LLM calls (maximum): {planned}; already used today (Pacific {pacific_today()}): {ledger_used_today()}; limit {DAILY_LIMIT}")
        if not ok:
            raise SystemExit("REFUSING TO RUN: used today + planned maximum exceeds the daily limit of 400 calls.")
    spans, _ = chunk_index()
    stop, calls0, used = None, 0, 0
    try:
        for it in todo:
            if guard is not None and guard.used >= a.max_calls:
                stop = f"MAX_CALLS_REACHED ({a.max_calls})"
                break
            r = pipe.answer(it["question"], correlation_id=f"{a.label}-{it['qid']}-{uuid.uuid4().hex[:8]}")
            if r["cap_hit"] in ("llm_error", "timeout") and not a.fake:
                # A provider failure or a provider-side stall (429, 503, hung call, guard refusal) says nothing about the question: no row is
                # written, the attempt is logged, the run stops, and a resume tries this item again (same policy as tools/eval_answers.py).
                # Its calls still count in the ledger. The attempts log is part of the evidence.
                stop = f"{r['cap_hit'].upper()} at {it['qid']}: {r['error']}"
                with open(os.path.join(RESULTS, f"{a.label}_attempts_not_recorded.jsonl"), "a", encoding="utf-8", newline="\n") as f:
                    f.write(json.dumps({"qid": it["qid"], "cap_hit": r["cap_hit"], "error": r["error"], "calls": r["calls"], "retries": r["retries"],
                                        "wall_ms": r["wall_ms"], "when_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + chr(10))
                print(it["qid"], "NOT RECORDED:", r["cap_hit"], r["error"], flush=True)
                break
            row = make_row(it, r, spans, guard.used if guard else None)
            with open(out, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(it["qid"], r["decision"], f"calls={r['calls']}", f"cap={r['cap_hit']}", f"wall={r['wall_ms']:.0f}ms", flush=True)
    finally:
        used = guard.used if guard else 0
        if used and not a.fake:
            add_ledger_entry(a.label, used, f"ADK multi-agent arm, run of {time.strftime('%Y-%m-%d')}; counted by QuotaGuard (every attempted call)")
    rows = ea.read_rows(out)
    print(json.dumps({"label": a.label, "rows": len(rows), "items_in_split": len(items), "calls_this_run": used, "stopped": stop}))


def cmd_freeze(a):
    rows = ea.read_rows(os.path.join(RESULTS, f"{a.label}.jsonl"))
    if len(rows) < len(ea.load_items("dev")):
        raise SystemExit("freeze needs a complete DEV run")
    from scripts.agents.config import AgentsConfig
    import dataclasses
    from scripts.model_config import default_gemini_model
    doc = {"frozen_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "config_hash": current_config_hash(), "model": default_gemini_model(),
           "caps": dataclasses.asdict(AgentsConfig()), "template_sha256": ea.prompt_sha256("2.1.0"), "dev_label": a.label,
           "files": {os.path.basename(f): hashlib.sha256(open(f, "rb").read()).hexdigest() for f in agent_files()}}
    json.dump(doc, open(FROZEN, "w", encoding="utf-8", newline="\n"), indent=1)
    print(doc["config_hash"])


# ---- offline comparison -------------------------------------------------------------------------------------------
def _pct(sorted_vals, p):
    return sorted_vals[min(len(sorted_vals) - 1, int(round(p * (len(sorted_vals) - 1))))] if sorted_vals else None


def arm_metrics(rows, items_by_qid, texts, spans, arm):
    """Same definitions for both arms (PHASE_4_REPORT.md section 3). arm 'A' rows come from eval_answers, 'B' rows from this tool."""
    from scripts.abstention import decision
    from scripts.stage14_citation_extraction import match_span_to_blocks, segment_response_text
    out_rows = []
    for r in rows:
        it = items_by_qid[r["qid"]]
        text = r["response_text_plain"] if arm == "B" else r["response_text"]
        chk = ac.check_item(it, text)
        ids = r["context_chunk_ids"]
        blocks = [{"context_block_id": c, "chunk_id": c, "doc_id": spans[c][0], "text": texts[c]} for c in ids if c in texts]
        cited = []
        if chk["decision"] in ("ANSWERED", "MIXED"):
            for sp in segment_response_text(text):
                for c in match_span_to_blocks(sp, blocks, 0.6):
                    if c["chunk_id"] not in cited:
                        cited.append(c["chunk_id"])
        hit = None
        if it["type"] != "unanswerable":
            gold = [(e["doc_id"], e["clean_start"], e["clean_end"]) for e in it["evidence"]]
            hit = any(c in spans and any(spans[c][0] == d and gc.is_hit(spans[c][1], spans[c][2], s, e) for d, s, e in gold) for c in cited[:5])
        explicit = r.get("cited_chunk_ids") if arm == "B" else None
        ehit = None
        if explicit is not None and it["type"] != "unanswerable":
            gold = [(e["doc_id"], e["clean_start"], e["clean_end"]) for e in it["evidence"]]
            ehit = any(c in spans and any(spans[c][0] == d and gc.is_hit(spans[c][1], spans[c][2], s, e) for d, s, e in gold) for c in explicit[:5])
        wrong = (chk["decision"] in ("ANSWERED", "MIXED") and not chk["implicit_refusal"]
                 and ((it["type"] != "unanswerable" and not chk["correct_proxy"]) or it["type"] == "unanswerable"))
        if arm == "A":
            t_in, t_out, t_th, calls, llm_ms, wall = r["prompt_tokens"], r["completion_tokens"], 0, 1, r["latency_ms"], r["wall_ms"]
        else:
            t_in, t_out, t_th, calls, llm_ms, wall = r["tokens"]["in"], r["tokens"]["out"], r["tokens"]["thought"], r["calls"], r["llm_ms"], r["wall_ms"]
        out_rows.append({"qid": r["qid"], "type": it["type"], "decision": chk["decision"], "wrong": wrong, "implicit_refusal": chk["implicit_refusal"],
                         "cited_hit": hit, "cited_hit_explicit": ehit, "t_in": t_in, "t_out": t_out, "t_th": t_th, "calls": calls,
                         "llm_ms": llm_ms, "wall_ms": wall, "cap_hit": r.get("cap_hit")})
    ans = [x for x in out_rows if x["type"] != "unanswerable"]
    un = [x for x in out_rows if x["type"] == "unanswerable"]
    answered = [x for x in ans if x["decision"] in ("ANSWERED", "MIXED") and not x["implicit_refusal"]]
    walls = sorted(x["wall_ms"] for x in out_rows)
    t_in, t_out, t_th = (sum(x[k] for x in out_rows) for k in ("t_in", "t_out", "t_th"))
    n = len(out_rows)
    llm_s = sum(x["llm_ms"] for x in out_rows) / 1000.0
    return {"n_items": n, "n_answerable": len(ans), "n_unanswerable": len(un),
            "false_refusals_answerable": sum(x["decision"] == "NOT_IN_CONTEXT" for x in ans),
            "refusals_unanswerable": sum(x["decision"] == "NOT_IN_CONTEXT" for x in un),
            "wrong_answers_automatic": sum(x["wrong"] for x in out_rows),
            "wrong_answerable": sum(x["wrong"] for x in ans), "wrong_unanswerable": sum(x["wrong"] for x in un),
            "answered_answerable": len(answered),
            "cited_hit_at5_among_answered": sum(bool(x["cited_hit"]) for x in answered),
            "cited_hit_at5_over_all_answerable": sum(bool(x["cited_hit"]) for x in ans),
            "cited_hit_at5_explicit_markers_among_answered": (sum(bool(x["cited_hit_explicit"]) for x in answered) if arm == "B" else None),
            "llm_calls_per_question": {"mean": round(sum(x["calls"] for x in out_rows) / n, 3), "max": max(x["calls"] for x in out_rows), "total": sum(x["calls"] for x in out_rows)},
            "tokens": {"input_total": t_in, "output_total": t_out, "thinking_total": t_th, "input_per_question": round(t_in / n, 1),
                       "output_incl_thinking_per_question": round((t_out + t_th) / n, 1)},
            "tokens_per_second_output": round((t_out + t_th) / llm_s, 2) if llm_s else None,
            "estimated_cost_usd": {"total": round((t_in * PRICE_IN_PER_M + (t_out + t_th) * PRICE_OUT_PER_M) / 1e6, 5),
                                   "per_request": round((t_in * PRICE_IN_PER_M + (t_out + t_th) * PRICE_OUT_PER_M) / 1e6 / n, 6),
                                   "basis": "list price, gemini-3.5-flash-lite paid tier, 0.30 USD/1M input, 2.50 USD/1M output incl. thinking; an estimate, the project runs on the free tier"},
            "latency_ms_per_question": {"n": n, "p50": round(_pct(walls, 0.5), 1), "max": round(walls[-1], 1)},
            "cap_hits": sum(1 for x in out_rows if x["cap_hit"]), "implicit_refusals": sum(x["implicit_refusal"] for x in out_rows)}


def keep_rule(a, b):
    f_a, f_b = a["false_refusals_answerable"], b["false_refusals_answerable"]
    w_a, w_b = a["wrong_answers_automatic"], b["wrong_answers_automatic"]
    mean_calls = b["llm_calls_per_question"]["mean"]
    cond = {"false_refusals_drop_by_2_or_more": f_a - f_b >= 2, "wrong_answers_do_not_increase": w_b <= w_a, "mean_calls_le_4": mean_calls <= 4}
    return {"conditions": cond, "values": {"false_refusals_A": f_a, "false_refusals_B": f_b, "wrong_A": w_a, "wrong_B": w_b, "mean_calls_B": mean_calls},
            "verdict": "ELIGIBLE_AS_DEFAULT (default not changed in this phase)" if all(cond.values()) else "STAYS_OPTIONAL_AND_OFF"}


def cmd_compare(a):
    items = {i["qid"]: i for i in ea.load_items("test")}
    spans, texts = chunk_index()
    a_rows = ea.read_rows(os.path.join(RESULTS, ARM_A_ROWS))
    b_rows = ea.read_rows(os.path.join(RESULTS, f"{a.label}.jsonl"))
    if len(b_rows) != len(items) or {r["qid"] for r in b_rows} != set(items):
        raise SystemExit(f"arm B is incomplete: {len(b_rows)} of {len(items)} TEST rows")
    am, bm = arm_metrics(a_rows, items, texts, spans, "A"), arm_metrics(b_rows, items, texts, spans, "B")
    a_sum = json.load(open(os.path.join(RESULTS, ARM_A_SUMMARY), encoding="utf-8"))
    frozen = json.load(open(FROZEN, encoding="utf-8"))
    from scripts.model_config import default_gemini_model
    reuse = {"arm_a_rows": ARM_A_ROWS, "arm_a_prompt_sha256_in_summary": a_sum["prompt_sha256"], "template_2_1_0_sha256_now": ea.prompt_sha256("2.1.0"),
             "prompt_unchanged": a_sum["prompt_sha256"] == ea.prompt_sha256("2.1.0"), "arm_a_model": a_sum["model"], "model_now": default_gemini_model(),
             "model_unchanged": a_sum["model"] == default_gemini_model()}
    summary = {"label": a.label, "frozen_config_hash": frozen["config_hash"], "arm_a_reuse_check": reuse, "A": am, "B": bm, "keep_rule": keep_rule(am, bm),
               "label_note": "correctness labels were not produced for arm B; the wrong-answer count is the automatic proxy defined in PHASE_4_REPORT.md section 3"}
    json.dump(summary, open(os.path.join(RESULTS, f"{a.label}_summary.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({"keep_rule": summary["keep_rule"], "reuse_ok": reuse["prompt_unchanged"] and reuse["model_unchanged"]}, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--split", choices=["dev", "test"], required=True)
    r.add_argument("--label", required=True)
    r.add_argument("--max-calls", type=int, default=DAILY_LIMIT)
    r.add_argument("--limit", type=int)
    r.add_argument("--expect-config-hash")
    r.add_argument("--fake", action="store_true")
    f = sub.add_parser("freeze")
    f.add_argument("--label", required=True)
    c = sub.add_parser("compare")
    c.add_argument("--label", required=True)
    a = ap.parse_args()
    {"run": cmd_run, "freeze": cmd_freeze, "compare": cmd_compare}[a.cmd](a)


if __name__ == "__main__":
    main()
