"""Per-question-type comparison of evaluation arms (Phase 3 step 5). No model is called.

  python tools/compare_arms.py --out eval/results/step5_arms.json  label=path.jsonl [label=path.jsonl ...]  --base <label>

For every arm: refusals on unanswerable items, false refusals on answerable items (overall and per type), Gemini calls per request and
latency per request. For every non-base arm: a PAIRED comparison with the base arm on the same items (exact McNemar test on
refused / not refused, per type and overall; 95% bootstrap CI of the difference in refusal rate, 10 000 resamples, seed 1).
Refusal = the bare NOT_IN_CONTEXT sentinel (scripts/abstention.py). Rows with no final response count as NOT refused.
"""
import argparse
import json
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from scripts.abstention import decision  # noqa: E402

TYPES = ("single_fact", "numbers_tables", "multi_passage", "cross_document")


def load(path):
    return {r["qid"]: r for r in (json.loads(x) for x in open(path, encoding="utf-8") if x.strip())}


def refused(r):
    return decision(r["response_text"]) == "NOT_IN_CONTEXT"


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))] if v else None


def arm_stats(rows):
    ans = [r for r in rows.values() if r["type"] != "unanswerable"]
    un = [r for r in rows.values() if r["type"] == "unanswerable"]
    s = {"n": len(rows), "unanswerable_refused": f"{sum(map(refused, un))}/{len(un)}", "false_refusal_all": f"{sum(map(refused, ans))}/{len(ans)}"}
    for t in TYPES:
        g = [r for r in ans if r["type"] == t]
        s[f"false_refusal_{t}"] = f"{sum(map(refused, g))}/{len(g)}"
    s["empty_or_no_final"] = sum(decision(r["response_text"]) == "EMPTY" for r in rows.values())
    s["partial_or_implicit_refusal_text"] = sum(1 for r in rows.values() if decision(r["response_text"]) == "ANSWERED" and
                                                any(p in r["response_text"].lower() for p in ("do not state", "does not state", "not stated", "do not mention", "does not mention")))
    calls = [r.get("total_calls", 1) for r in rows.values()]
    lat = [r["latency_ms"] for r in rows.values()]
    s["gemini_calls_per_request"] = {"mean": round(float(np.mean(calls)), 2), "max": max(calls), "total": int(sum(calls))}
    s["latency_ms_per_request"] = {"p50": pct(lat, .5), "p95": pct(lat, .95), "max": max(lat)}
    s["prompt_tokens_total"] = int(sum(r.get("prompt_tokens") or 0 for r in rows.values()))
    return s


def paired(base, other, which):
    from scipy.stats import binomtest
    qs = [q for q in base if q in other and (which(base[q]))]
    b = np.array([refused(base[q]) for q in qs], float)
    o = np.array([refused(other[q]) for q in qs], float)
    up, down = int(((o == 1) & (b == 0)).sum()), int(((o == 0) & (b == 1)).sum())      # newly refused / no longer refused
    d = o - b
    rng = np.random.default_rng(1)
    bm = d[rng.integers(0, len(d), (10000, len(d)))].mean(axis=1) if len(d) else np.array([0.0])
    return {"n": len(qs), "refused_base": int(b.sum()), "refused_other": int(o.sum()), "no_longer_refused": down, "newly_refused": up,
            "delta_rate": round(float(d.mean()), 3) if len(d) else None, "ci95": [round(float(np.percentile(bm, 2.5)), 3), round(float(np.percentile(bm, 97.5)), 3)],
            "mcnemar_exact_p": round(float(binomtest(up, up + down, 0.5).pvalue), 4) if up + down else 1.0}


def compare(arms, base_label):
    out = {"arms": {k: arm_stats(v) for k, v in arms.items()}, "paired_vs_base": {}}
    base = arms[base_label]
    for k, v in arms.items():
        if k == base_label:
            continue
        c = {"answerable_all": paired(base, v, lambda r: r["type"] != "unanswerable"), "unanswerable": paired(base, v, lambda r: r["type"] == "unanswerable")}
        for t in TYPES:
            c[t] = paired(base, v, lambda r, t=t: r["type"] == t)
        out["paired_vs_base"][f"{k} vs {base_label}"] = c
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("arms", nargs="+", help="label=path.jsonl")
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    arms = {x.split("=", 1)[0]: load(x.split("=", 1)[1]) for x in a.arms}
    res = compare(arms, a.base)
    json.dump(res, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps(res["arms"], indent=1))
    for k, c in res["paired_vs_base"].items():
        print("==", k)
        for t, v in c.items():
            print(f"  {t:16s} n={v['n']:2d} refused {v['refused_base']}->{v['refused_other']}  no-longer {v['no_longer_refused']} newly {v['newly_refused']}  delta {v['delta_rate']} CI {v['ci95']} p={v['mcnemar_exact_p']}")
