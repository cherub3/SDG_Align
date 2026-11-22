"""Baseline diagnostics (no tuning): recall ceilings at deeper cut-offs, and a type x paraphrased cross-tab.

Usage: python tools/diag_baseline.py --split test --out eval/results/baseline_diagnostics.json [--baseline eval/results/baseline.json]
Recall@20/50 = share of answerable items with ANY gold span hit in the top 20/50 (the ceiling for a reranker over top-20/50).
Also all-spans@20/50 for multi_passage and cross_document. The cross-tab is read from the saved baseline file.
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval_retrieval as ev  # noqa: E402
import freeze_gold as fg  # noqa: E402
import gold_common as gc  # noqa: E402

KS = (1, 5, 10, 20, 50)


def depth_scores(it, ranked):
    spans = [(e["doc_id"], e["clean_start"], e["clean_end"]) for e in it["evidence"]]
    rank_of = [None] * len(spans)
    for r, (d, s, e, _) in enumerate(ranked, 1):
        for i, (gd, gs, ge) in enumerate(spans):
            if rank_of[i] is None and gd == d and gc.is_hit(s, e, gs, ge):
                rank_of[i] = r
    hits = [r for r in rank_of if r]
    first = min(hits) if hits else None
    out = {"first_hit_rank": first, "type": it["type"], "paraphrased": bool(it.get("paraphrased"))}
    for k in KS:
        out[f"recall@{k}"] = float(first is not None and first <= k)
        if it["type"] in ("multi_passage", "cross_document"):
            out[f"all_spans@{k}"] = float(all(r is not None and r <= k for r in rank_of))
    return out


def cross_tab(items):
    ans = [r for r in items if r["type"] != "unanswerable"]
    tab = {}
    for t in ("single_fact", "numbers_tables", "multi_passage", "cross_document"):
        for p in (True, False):
            rs = [r for r in ans if r["type"] == t and r["paraphrased"] == p]
            tab[f"{t}|{'paraphrased' if p else 'not_paraphrased'}"] = {
                "n": len(rs), "recall@5": round(float(np.mean([r["recall@5"] for r in rs])), 3) if rs else None}
    # type-adjusted gap: mean of within-type (paraphrased - not) R@5, weighted by cell size of the smaller side
    num = den = 0.0
    for t in ("single_fact", "numbers_tables", "multi_passage", "cross_document"):
        a, b = tab[f"{t}|paraphrased"], tab[f"{t}|not_paraphrased"]
        if a["n"] and b["n"]:
            w = a["n"] * b["n"] / (a["n"] + b["n"])
            num += w * (a["recall@5"] - b["recall@5"])
            den += w
    tab["type_adjusted_gap_R@5 (paraphrased - not)"] = round(num / den, 3)
    from scipy.stats import fisher_exact
    p = [r for r in ans if r["paraphrased"]]
    n = [r for r in ans if not r["paraphrased"]]
    t2 = [[int(sum(r["recall@5"] for r in p)), len(p) - int(sum(r["recall@5"] for r in p))],
          [int(sum(r["recall@5"] for r in n)), len(n) - int(sum(r["recall@5"] for r in n))]]
    tab["crude_gap_R@5"] = round(float(np.mean([r["recall@5"] for r in p]) - np.mean([r["recall@5"] for r in n])), 3)
    tab["fisher_exact_p_crude"] = round(float(fisher_exact(t2)[1]), 3)
    tab["composition"] = {"paraphrased": {t: sum(r["type"] == t for r in p) for t in ("single_fact", "numbers_tables", "multi_passage", "cross_document")},
                          "not_paraphrased": {t: sum(r["type"] == t for r in n) for t in ("single_fact", "numbers_tables", "multi_passage", "cross_document")}}
    return tab


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test")
    ap.add_argument("--out", required=True)
    ap.add_argument("--hybrid", help="JSON dict of hybrid fusion params; omit for dense only")
    ap.add_argument("--baseline", default=os.path.join(fg.gc.REPO, "eval", "results", "baseline.json"))
    a = ap.parse_args()
    bad = fg.check_frozen()
    if bad:
        raise SystemExit("REFUSING TO RUN, frozen inputs differ: " + "; ".join(bad))
    retr = ev.build_retriever(top_k=max(KS), hybrid=json.loads(a.hybrid) if a.hybrid else None)
    rows = [depth_scores(it, retr(it["question"])) for it in ev.load_items(a.split) if it["type"] != "unanswerable"]
    rng = np.random.default_rng(1)
    summ = {"n": len(rows)}
    for k in KS:
        summ[f"recall@{k}"] = ev.boot_ci([r[f"recall@{k}"] for r in rows], rng)
    for k in (10, 20, 50):
        m = [r[f"all_spans@{k}"] for r in rows if f"all_spans@{k}" in r]
        summ[f"all_spans@{k} (multi+cross, n={len(m)})"] = ev.boot_ci(m, rng)
    never50 = [r for r in rows if r["first_hit_rank"] is None]
    summ["no_hit_in_top50"] = len(never50)
    summ["no_hit_in_top50_by_type"] = {t: sum(r["type"] == t for r in never50) for t in ("single_fact", "numbers_tables", "multi_passage", "cross_document")}
    base = json.load(open(a.baseline, encoding="utf-8"))
    out = {"split": a.split, "git_commit": base["git_commit"], "depth_summary": summ, "cross_tab": cross_tab(base["items"])}
    json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps(out, indent=1))
