"""Authenticated smoke test of the deployed Cloud Run service (Phase 3 step 6). Token comes from gcloud, is never printed or saved.
  python tools/cloud_smoke.py <service_url> <gcloud.cmd> <out.json>
Uses DEV items only. 2 LLM questions (2 of the DAILY_LLM_CALL_CAP=10 calls), 3 retrieval-only, health, then warm repeats (no LLM)."""
import json, statistics, subprocess, sys, time
import requests

REPO = __file__.rsplit("tools", 1)[0] or "."
url, gcloud, out = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]
split = json.load(open(REPO + "eval/gold_split.json"))["split"]
gold = [json.loads(x) for x in open(REPO + "eval/gold_set.jsonl", encoding="utf-8") if x.strip()]
dev = [g for g in gold if split.get(g.get("qid") or g.get("id")) == "dev" and g.get("type") != "unanswerable"]
assert len(dev) >= 5 and all(split.get(g.get("qid") or g.get("id")) == "dev" for g in dev)
tok = subprocess.run([gcloud, "auth", "print-identity-token"], capture_output=True, text=True, check=True, shell=False).stdout.strip()
H = {"Authorization": "Bearer " + tok, "Content-Type": "application/json"}
WARM_ONLY = len(sys.argv) > 4 and sys.argv[4] == "warm_only"   # re-run only the warm repeats; first-phase records come from the file named in argv[5]
res = json.load(open(sys.argv[5])) if WARM_ONLY else {"url": url, "calls": []}
S = requests.Session() if WARM_ONLY else requests   # warm repeats reuse one connection


def call(label, method, path, body=None):
    t = time.perf_counter()
    try:
        r = S.request(method, url + path, headers=H, json=body, timeout=130)
        ms = round((time.perf_counter() - t) * 1000)
        rec = {"label": label, "status": r.status_code, "ms": ms}
        try:
            j = r.json()
        except Exception:
            j = {}
        if label.startswith("llm"):
            fr = j.get("final_response") or {}
            ans = (fr.get("answer") or fr.get("response") or {})
            rec.update(agent_status=j.get("status"), steps=(j.get("plan") or {}).get("total_step_count"),
                       answer_chars=len(json.dumps(fr)), findings=[f.get("code") for f in j.get("findings", [])][:5])
        elif label.startswith("retr"):
            rec.update(llm_calls=j.get("llm_calls"), n_chunks=len(j.get("chunks", [])))
        else:
            rec.update(body=j if r.status_code == 200 else None)
    except Exception as e:
        rec = {"label": label, "status": None, "ms": round((time.perf_counter() - t) * 1000), "error": type(e).__name__}
    res["calls"].append(rec)
    print(rec)
    return rec


q = lambda g: g["question"]
if not WARM_ONLY:
  call("health_first", "GET", "/health")
for i, g in enumerate([] if WARM_ONLY else dev[:2]):
    call(f"llm_{i}_{g.get('qid') or g.get('id')}", "POST", "/run-query", {"query": q(g)})
for i, g in enumerate([] if WARM_ONLY else dev[2:5]):
    call(f"retrieval_{i}_{g.get('qid') or g.get('id')}", "POST", "/run-query", {"query": q(g), "retrieval_only": True})
for i in range(10):
    call(f"warm_health_{i}", "GET", "/health")
for i in range(10):
    call(f"warm_retrieval_{i}", "POST", "/run-query", {"query": q(dev[2 + i % 3]), "retrieval_only": True})
def stats(prefix):
    v = sorted(c["ms"] for c in res["calls"] if c["label"].startswith(prefix) and c["status"] == 200)
    return {"n": len(v), "p50": v[len(v)//2] if v else None, "p95": v[min(len(v)-1, int(.95*len(v)))] if v else None, "max": v[-1] if v else None}
res["summary"] = {"warm_health": stats("warm_health"), "warm_retrieval_only": stats("warm_retrieval"), "llm": stats("llm")}
json.dump(res, open(out, "w", encoding="utf-8", newline="\n"), indent=1)
print(json.dumps(res["summary"]))
