"""Answer-level evaluation on the frozen gold set (Phase 3 step 4). One real pipeline call per gold item:
retrieve (served hybrid config) -> context -> prompt template -> Gemini -> citations -> groundedness -> API response.

  python tools/eval_answers.py --split dev  --template 2.0.0 --label dev_pass1 --max-calls 14          (LIVE, uses quota)
  python tools/eval_answers.py --split test --template 2.0.0 --label test_noplanner --max-calls 52 --expect-prompt-sha256 <sha>
  python tools/eval_answers.py --split dev --template 2.0.0 --label offline --fake                      (no network, scripted model)

Safety: the daily guard cap is 450 (this runner only), pace 12 RPM, max_retry_attempts=1 (a call is never silently repeated),
the run STOPS on the first 429, guard refusal or any other LLM failure and keeps everything done so far (results are appended
to eval/results/<label>.jsonl as each item finishes; re-running the same label resumes). --max-calls hard-limits the run.
The frozen gold hashes are checked first. A summary is written to eval/results/<label>_summary.json.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import answer_checks as ac  # noqa: E402
import freeze_gold as fg  # noqa: E402
import gold_common as gc  # noqa: E402

RESULTS = os.path.join(REPO, "eval", "results")
GUARD_CAP, PACE_RPM, MAX_OUTPUT_TOKENS = 450, 12, 512
TEMPLATES = os.path.join(REPO, "config", "prompt_templates")
_CHUNK_ID = re.compile(r"^Chunk ID: (\S+)$", re.MULTILINE)


class StopRun(Exception):
    """Raised by an item runner to stop the whole run; the reason is recorded in the summary."""


def prompt_sha256(version):
    h = hashlib.sha256()
    for name in ("system_prompt.txt", "user_prompt.txt", "template_metadata.json"):
        h.update(open(os.path.join(TEMPLATES, version, name), "rb").read())
    return h.hexdigest()


def load_items(split):
    sp = json.load(open(fg.SPLIT, encoding="utf-8"))["split"]
    items = [json.loads(x) for x in open(fg.GOLD, encoding="utf-8") if x.strip()]
    return [i for i in items if sp[i["qid"]] == split]


def read_rows(path):
    if not os.path.exists(path):
        return []
    return [json.loads(x) for x in open(path, encoding="utf-8") if x.strip()]


def run_items(items, ask, out_path, max_calls):
    """ask(item) -> row dict (must contain 'response_text'); may raise StopRun. Appends each finished row to out_path."""
    done = {r["qid"] for r in read_rows(out_path)}
    stop, calls = None, 0
    for it in items:
        if it["qid"] in done:
            continue
        if calls >= max_calls:
            stop = f"MAX_CALLS_REACHED ({max_calls})"
            break
        try:
            calls += 1
            row = ask(it)
        except StopRun as e:
            stop = str(e)
            break
        with open(out_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
    return {"calls_this_run": calls, "stopped": stop}


def summarize_rows(rows, items_by_qid):
    checks = [ac.check_item(items_by_qid[r["qid"]], r["response_text"]) for r in rows]
    s = ac.summarize(checks)
    ans_rows = [(r, c) for r, c in zip(rows, checks) if c["type"] != "unanswerable"]
    s["false_refusals_with_gold_in_context"] = sum(1 for r, c in ans_rows if c["decision"] == "NOT_IN_CONTEXT" and r.get("gold_in_context"))
    s["false_refusals_gold_not_in_context"] = sum(1 for r, c in ans_rows if c["decision"] == "NOT_IN_CONTEXT" and not r.get("gold_in_context"))
    s["answerable_with_gold_in_context"] = sum(1 for r, _ in ans_rows if r.get("gold_in_context"))
    answered = [r for r, c in zip(rows, checks) if c["decision"] == "ANSWERED"]
    gs = [r["groundedness_score"] for r in answered if r.get("groundedness_score") is not None]
    s["mean_groundedness_of_answered"] = round(sum(gs) / len(gs), 3) if gs else None
    s["tokens"] = {k: sum(r.get(k) or 0 for r in rows) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    s["latency_ms_per_call"] = ({"p50": sorted(r["latency_ms"] for r in rows)[len(rows) // 2], "max": max(r["latency_ms"] for r in rows)} if rows else None)
    return s, checks


def build_live_runner(template, fake):
    """Real retrieval + pipeline. fake=True swaps only the model for a scripted offline stand-in. Returns ask(item)."""
    os.chdir(REPO)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    from scripts.cache_adapter import InMemoryCacheAdapter
    from scripts.embedding_provider_local import LocalEmbeddingAdapter
    from scripts.model_config import default_gemini_model
    from scripts.pipeline_deps_factory import build_pipeline_deps
    from scripts.quota_guard import GuardedLLMAdapter, QuotaGuard
    from scripts.stage13_llm_execution import LLMAdapter, LLMQuotaExhaustedError, RawLLMResult
    from scripts.stage18_api_response_serving import handle_request

    model = default_gemini_model()
    emb = LocalEmbeddingAdapter()
    ident = (emb.provider_name, "BAAI/bge-small-en-v1.5", "v1.5")
    fps = [m["index_fingerprint"] for m in (json.load(open(p, encoding="utf-8")) for p in sorted(glob.glob("data/proposals/vector_index/*/index_metadata.json")))
           if (m.get("provider"), m.get("model_name"), m.get("model_version")) == ident]
    if len(fps) != 1:
        raise SystemExit(f"expected exactly one matching index, found {fps}")
    spans = {}
    for doc in os.listdir(gc.CHUNKS):
        p = os.path.join(gc.CHUNKS, doc, "chunks.json")
        if os.path.exists(p):
            for c in json.load(open(p, encoding="utf-8"))["chunks"]:
                spans[c["chunk_id"]] = (c["doc_id"], c["char_start"], c["char_end"])

    class Recorder(LLMAdapter):
        provider_name = "recorder"

        def __init__(self, inner):
            self.inner, self.last, self.error, self.prompt, self.latency_ms = inner, None, None, "", 0

        @property
        def model_version_reported(self):
            return getattr(self.inner, "model_version_reported", None)

        def reset(self):
            self.last, self.error, self.prompt = None, None, ""

        def invoke(self, system_prompt, user_prompt, config):
            self.prompt = user_prompt
            t = time.time()
            try:
                self.last = self.inner.invoke(system_prompt, user_prompt, config)
                self.latency_ms = int((time.time() - t) * 1000)
                return self.last
            except Exception as e:                    # noqa: BLE001  (recorded, then re-raised for the pipeline's own handling)
                self.error = e
                raise

    if fake:
        class Scripted(LLMAdapter):
            provider_name, model_version_reported = "scripted-offline", "none"

            def invoke(self, system_prompt, user_prompt, config):
                # offline stand-in: abstain when the question's capitalised words are absent from the context, else echo the first block
                q = re.search(r"Question:\n(.*?)\n\n<context>", user_prompt, re.S).group(1)
                ctx = user_prompt.split("<context>", 1)[1]
                caps = [w for w in re.findall(r"\b[A-Z][a-z]{3,}\b", q) if w not in ("What", "Which", "How", "Where", "Under", "Rank", "According")]
                if caps and not any(w.lower() in ctx.lower() for w in caps):
                    text = "NOT_IN_CONTEXT"
                else:
                    text = ctx.split("Chunk ID:")[1].split("\n\n", 1)[1][:240].strip() if "Chunk ID:" in ctx else "NOT_IN_CONTEXT"
                return RawLLMResult(text, "complete", len(user_prompt) // 4, len(text) // 4, len(user_prompt) // 4 + len(text) // 4, "fake")
        inner = Scripted()
        guard = QuotaGuard(cap=10_000, pace=0)
    else:
        from scripts.llm_provider_gemini import gemini_llm_factory
        from tools_env import gemini_key
        key = gemini_key()
        if not key:
            raise SystemExit("GEMINI_API_KEY not set in the environment or .env; no call made.")
        inner = gemini_llm_factory({"seam": "LLM_PROVIDER", "provider_name": "gemini", "credential_ref": "", "extra": {}}, key)
        guard = QuotaGuard(cap=GUARD_CAP, pace=PACE_RPM)
    rec = Recorder(inner)
    deps = build_pipeline_deps(GuardedLLMAdapter(rec, guard), emb, InMemoryCacheAdapter(), model)

    def ask(it):
        rec.reset()
        req = {"query": it["question"], "index_fingerprints": fps,
               "pipeline_options": {"template_version": template, "temperature": 0.0, "max_output_tokens": MAX_OUTPUT_TOKENS,
                                    "max_retry_attempts": 1, "timeout_seconds": 90}}
        t0 = time.time()
        resp = handle_request(req, deps)
        if rec.error is not None:
            raise StopRun(f"LLM_ERROR at {it['qid']}: {type(rec.error).__name__}" + (" (429 / quota)" if isinstance(rec.error, LLMQuotaExhaustedError) else ""))
        if rec.last is None:
            raise StopRun(f"NO_LLM_CALL_MADE at {it['qid']} (guard refused: used {guard.used}/{guard.cap}, breaker_open={guard.tripped})")
        ctx_ids = _CHUNK_ID.findall(rec.prompt)
        row = {"qid": it["qid"], "type": it["type"], "kind": it.get("kind"), "question": it["question"],
               "response_text": rec.last.response_text, "finish_reason": rec.last.finish_reason, "api_status": resp["status"],
               "api_abstained": resp["answer"]["abstained"], "api_decision": resp["answer"]["decision"],
               "prompt_tokens": rec.last.prompt_tokens, "completion_tokens": rec.last.completion_tokens, "total_tokens": rec.last.total_tokens,
               "latency_ms": rec.latency_ms, "wall_ms": int((time.time() - t0) * 1000), "model_version_reported": rec.model_version_reported,
               "context_chunk_ids": ctx_ids, "groundedness_score": resp["groundedness"]["groundedness_score"],
               "answer_quality_score": resp["quality"]["answer_quality_score"], "citation_presence_ratio": resp["quality"]["citation_presence_ratio"],
               "guard_used": guard.used}
        if it["type"] != "unanswerable":
            gold = [(e["doc_id"], e["clean_start"], e["clean_end"]) for e in it["evidence"]]
            row["gold_in_context"] = any(c in spans and any(spans[c][0] == d and gc.is_hit(spans[c][1], spans[c][2], s, e) for d, s, e in gold) for c in ctx_ids)
        return row
    return ask


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--max-calls", type=int, required=True)
    ap.add_argument("--expect-prompt-sha256")
    ap.add_argument("--fake", action="store_true", help="scripted offline model; makes no network call")
    a = ap.parse_args()
    bad = fg.check_frozen()
    if bad:
        raise SystemExit("REFUSING TO RUN, frozen inputs differ: " + "; ".join(bad))
    sha = prompt_sha256(a.template)
    if a.expect_prompt_sha256 and a.expect_prompt_sha256 != sha:
        raise SystemExit(f"REFUSING TO RUN: prompt template {a.template} hash {sha} != expected {a.expect_prompt_sha256}")
    if a.split == "test" and not a.expect_prompt_sha256 and not a.fake:
        raise SystemExit("REFUSING TO RUN on TEST without --expect-prompt-sha256 (the frozen prompt hash).")
    items = load_items(a.split)
    by_qid = {i["qid"]: i for i in items}
    os.makedirs(RESULTS, exist_ok=True)
    out = os.path.join(RESULTS, f"{a.label}.jsonl")
    ask = build_live_runner(a.template, a.fake)
    info = run_items(items, ask, out, a.max_calls)
    rows = read_rows(out)
    summ, _ = summarize_rows(rows, by_qid)
    from scripts.model_config import default_gemini_model
    summary = {"label": a.label, "split": a.split, "template_version": a.template, "prompt_sha256": sha, "fake_model": a.fake,
               "items_in_split": len(items), "items_done": len(rows), **info, "frozen_file_sha256": fg.sha_file(fg.FROZEN),
               "model": None if a.fake else default_gemini_model(),
               "settings": {"temperature": 0.0, "max_output_tokens": MAX_OUTPUT_TOKENS, "max_retry_attempts": 1, "retrieval": "hybrid rrf_k=10 w_bm25=2.0 depth=50",
                            "top_k": 10, "context_budget_tokens": 4000, "guard_cap": GUARD_CAP, "pace_rpm": PACE_RPM},
               "summary": summ, "keep_rule": ac.keep_rule(summ) if len(rows) == len(items) else "not evaluated (run incomplete)"}
    json.dump(summary, open(os.path.join(RESULTS, f"{a.label}_summary.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({k: summary[k] for k in ("label", "items_done", "calls_this_run", "stopped", "keep_rule")}, indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
