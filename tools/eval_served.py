"""Served-path retrieval check (Phase 3 step 7): run the gold retrieval eval against the DEPLOYED service using retrieval_only (0 LLM calls),
scored with the same code as the offline eval (tools/eval_retrieval.score_item / summarize). Token from gcloud, never printed or saved.
  python tools/eval_served.py <service_url> <gcloud.cmd> <out.json>
Chunk -> character span mapping uses the local chunks.json (same derived corpus that was copied into the image); each served chunk's text
is compared with the local chunk's text so a corpus mismatch is detected, not assumed away."""
import json, os, subprocess, sys, time
import numpy as np
import requests

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, "tools"))
import eval_retrieval as er  # noqa: E402
import gold_common as gc  # noqa: E402
import freeze_gold as fg  # noqa: E402


def local_chunks():
    out = {}
    for d in os.listdir(gc.CHUNKS):
        p = os.path.join(gc.CHUNKS, d, "chunks.json")
        if os.path.exists(p):
            for c in json.load(open(p, encoding="utf-8"))["chunks"]:
                out[c["chunk_id"]] = c
    return out


def served_to_ranked(chunks, local):
    """Served chunks (rank order) -> [(doc_id, char_start, char_end)], and the number of chunks whose text differs from the local copy."""
    ranked, text_mismatch = [], 0
    for c in chunks:
        lc = local[c["chunk_id"]]
        ranked.append((lc["doc_id"], lc["char_start"], lc["char_end"]))
        if (c.get("text") or "") != (lc.get("text") or ""):
            text_mismatch += 1
    return ranked, text_mismatch


if __name__ == "__main__":
    url, gcloud, out = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]
    bad = fg.check_frozen()
    if bad:
        raise SystemExit("frozen inputs differ: " + "; ".join(bad))
    tok = subprocess.run([gcloud, "auth", "print-identity-token"], capture_output=True, text=True, check=True).stdout.strip()
    S = requests.Session(); S.headers["Authorization"] = "Bearer " + tok
    local = local_chunks()
    result = {"url": url, "llm_calls_total": 0, "splits": {}}
    for split in ("dev", "test"):
        rows, lat, mism, ncalls = [], [], 0, 0
        for it in er.load_items(split):
            t = time.perf_counter()
            r = S.post(url + "/run-query", json={"query": it["question"], "retrieval_only": True}, timeout=130)
            lat.append((time.perf_counter() - t) * 1000)
            r.raise_for_status()
            j = r.json()
            assert j["retrieval_only"] is True and j["llm_calls"] == 0
            ncalls += j["llm_calls"]
            ranked, m = served_to_ranked(j["chunks"], local)
            mism += m
            base = {"qid": it["qid"], "type": it["type"], "paraphrased": bool(it.get("paraphrased")), "kind": it.get("kind"),
                    "top1_score": round(float(j["chunks"][0]["score"]), 4) if j["chunks"] else None, "n_returned": len(ranked)}
            if it["type"] != "unanswerable":
                base.update(er.score_item(it, ranked))
            rows.append(base)
        result["splits"][split] = {"n_items": len(rows), "served_chunks_with_text_differing_from_local": mism, "llm_calls": ncalls,
                                   "latency_ms_per_query": {"p50": round(float(np.percentile(lat, 50)), 1), "p95": round(float(np.percentile(lat, 95)), 1)},
                                   "summary": er.summarize(rows), "items": rows}
        result["llm_calls_total"] += ncalls
        print(split, len(rows), "items", mism, "text mismatches")
    json.dump(result, open(out, "w", encoding="utf-8", newline="\n"), indent=1)
