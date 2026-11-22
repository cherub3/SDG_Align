"""Gold-set retrieval evaluation (Phase 2). Refuses to run if the frozen hashes do not match.

Usage:  python tools/eval_retrieval.py --split test --label baseline --out eval/results/baseline.json
        python tools/eval_retrieval.py --compare eval/results/a.json eval/results/b.json   (paired tests, same split)
Tune only with --split dev. Reported numbers come from --split test.

Hit rule (frozen, tools/gold_common.is_hit): same doc_id and the chunk's [char_start, char_end) in the stage-4 clean text
overlaps a gold span by >= min(50 chars, 50% of the span). An item is a hit at rank r if ANY of its spans is hit.
Metrics (answerable items): Recall@1/5/10 (any span), MRR@10 (first hit), nDCG@10 (gain 1 for a chunk that newly covers
a gold span; ideal = min(#spans,10) hits at the top), all-spans@10 (every span covered by the top 10; multi/cross only).
CIs: percentile bootstrap over items, 10000 resamples, seed 1. Unanswerable items: top-1 score recorded (no abstention yet).
"""
import argparse
import glob
import json
import math
import os
import subprocess
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import gold_common as gc  # noqa: E402
import freeze_gold as fg  # noqa: E402

TOP_K = 10
BOOT = 10000
METRICS = ("recall@1", "recall@5", "recall@10", "mrr@10", "ndcg@10")


def load_items(split):
    sp = json.load(open(fg.SPLIT, encoding="utf-8"))["split"]
    items = [json.loads(line) for line in open(fg.GOLD, encoding="utf-8") if line.strip()]
    return [it for it in items if sp[it["qid"]] == split]


def score_item(it, ranked):
    """ranked: list of (doc_id, start, end) in rank order. Returns metric dict for an answerable item."""
    spans = [(e["doc_id"], e["clean_start"], e["clean_end"]) for e in it["evidence"]]
    covered, first, dcg = set(), None, 0.0
    for r, (d, s, e) in enumerate(ranked[:TOP_K], 1):
        new = [i for i, (gd, gs, ge) in enumerate(spans) if i not in covered and gd == d and gc.is_hit(s, e, gs, ge)]
        if new:
            first = first or r
            dcg += 1.0 / math.log2(r + 1)
            covered.update(new)
    ideal = sum(1.0 / math.log2(r + 1) for r in range(1, min(len(spans), TOP_K) + 1))
    row = {"recall@1": float(first == 1), "recall@5": float(first is not None and first <= 5),
           "recall@10": float(first is not None), "mrr@10": 1.0 / first if first else 0.0, "ndcg@10": dcg / ideal,
           "first_hit_rank": first, "spans": len(spans), "spans_covered@10": len(covered)}
    if it["type"] in ("multi_passage", "cross_document"):
        row["all_spans@10"] = float(len(covered) == len(spans))
    return row


def boot_ci(x, rng):
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return [None, None, None]
    idx = rng.integers(0, len(x), (BOOT, len(x)))
    m = x[idx].mean(axis=1)
    return [round(float(x.mean()), 4), round(float(np.percentile(m, 2.5)), 4), round(float(np.percentile(m, 97.5)), 4)]


def summarize(rows):
    rng = np.random.default_rng(1)
    ans = [r for r in rows if r["type"] != "unanswerable"]
    groups = {"ALL answerable": ans}
    for t in ("single_fact", "numbers_tables", "multi_passage", "cross_document"):
        groups[f"type={t}"] = [r for r in ans if r["type"] == t]
    groups["paraphrased"] = [r for r in ans if r["paraphrased"]]
    groups["not paraphrased"] = [r for r in ans if not r["paraphrased"]]
    out = {}
    for g, rs in groups.items():
        d = {"n": len(rs)}
        for m in METRICS:
            d[m] = boot_ci([r[m] for r in rs], rng)
        multi = [r for r in rs if "all_spans@10" in r]
        if multi:
            d["all_spans@10"] = boot_ci([r["all_spans@10"] for r in multi], rng) + [len(multi)]
        out[g] = d
    multi = [r for r in ans if "all_spans@10" in r]
    out["multi+cross pooled"] = {"n": len(multi), "all_spans@10": boot_ci([r["all_spans@10"] for r in multi], rng),
                                 "recall@5": boot_ci([r["recall@5"] for r in multi], rng)}
    un = [r for r in rows if r["type"] == "unanswerable"]
    out["unanswerable"] = {k: {"n": len([r for r in un if r["kind"] == k]),
                               "top1_scores": [r["top1_score"] for r in un if r["kind"] == k]} for k in ("near_miss", "off_corpus")}
    out["answerable_top1_scores"] = sorted(r["top1_score"] for r in ans)
    return out


def build_retriever(top_k=TOP_K, hybrid=None):
    """Real stage-10 retrieve() over the local index (same as tools/retrieval_eval.py): fn(query) -> [(doc_id,start,end,score)]."""
    os.chdir(REPO)
    from scripts.embedding_provider_local import LocalEmbeddingAdapter
    from scripts.stage0_register import load_manifest
    from scripts.stage9_vector_indexing import FAISSAdapter
    from scripts.stage10_retrieval import retrieve
    ad = LocalEmbeddingAdapter()
    ident = (ad.provider_name, "BAAI/bge-small-en-v1.5", "v1.5")
    manifest = load_manifest()
    fps = []
    for mp in sorted(glob.glob("data/proposals/vector_index/*/index_metadata.json")):
        meta = json.load(open(mp, encoding="utf-8"))
        if (meta.get("provider"), meta.get("model_name"), meta.get("model_version")) == ident:
            fps.append(meta["index_fingerprint"])
    if len(fps) != 1:
        raise SystemExit(f"expected exactly one matching index, found {fps}")
    spans = {}
    for doc in manifest:
        p = os.path.join(gc.CHUNKS, doc, "chunks.json")
        if os.path.exists(p):
            for c in json.load(open(p, encoding="utf-8"))["chunks"]:
                spans[c["chunk_id"]] = (c["doc_id"], c["char_start"], c["char_end"])

    def run(q):
        r = retrieve({"query": q, "index_fingerprints": fps, "top_k": top_k, "hybrid": hybrid}, manifest,
                     lambda p, m, v: ad, lambda m: FAISSAdapter(m))
        return [(*spans[x["chunk_id"]], x["score"]) for x in r["results"]]
    return run


def evaluate(split, retriever, label):
    bad = fg.check_frozen()
    if bad:
        raise SystemExit("REFUSING TO RUN, frozen inputs differ: " + "; ".join(bad))
    rows, lat = [], []
    for it in load_items(split):
        t = time.perf_counter()
        ranked = retriever(it["question"])
        lat.append((time.perf_counter() - t) * 1000)
        base = {"qid": it["qid"], "type": it["type"], "paraphrased": bool(it.get("paraphrased")), "kind": it.get("kind"),
                "top1_score": round(float(ranked[0][3]), 4) if ranked else None}
        if it["type"] != "unanswerable":
            base.update(score_item(it, [(d, s, e) for d, s, e, _ in ranked]))
        rows.append(base)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=REPO).stdout.strip()
    return {"label": label, "split": split, "git_commit": commit, "top_k": TOP_K, "bootstrap": {"resamples": BOOT, "seed": 1},
            "frozen_file_sha256": fg.sha_file(fg.FROZEN),
            "latency_ms_per_query": {"mean": round(float(np.mean(lat)), 1), "p50": round(float(np.percentile(lat, 50)), 1),
                                     "p95": round(float(np.percentile(lat, 95)), 1)},
            "summary": summarize(rows), "items": rows}


def _paired(d, rng, binary):
    from scipy.stats import wilcoxon, binomtest
    d = np.asarray(d, dtype=float)
    idx = rng.integers(0, len(d), (BOOT, len(d)))
    bm = d[idx].mean(axis=1)
    e = {"n": len(d), "delta": round(float(d.mean()), 4),
         "ci95": [round(float(np.percentile(bm, 2.5)), 4), round(float(np.percentile(bm, 97.5)), 4)]}
    nz = d[d != 0]
    e["wilcoxon_p"] = round(float(wilcoxon(nz).pvalue), 4) if len(nz) else 1.0
    if binary:
        up, down = int((d > 0).sum()), int((d < 0).sum())
        e.update(improved=up, worsened=down, mcnemar_exact_p=round(float(binomtest(up, up + down, 0.5).pvalue), 4) if up + down else 1.0)
    return e


def compare(a_path, b_path):
    """Per-question paired comparison of config B vs config A (same split). Headline tests requested for every Step 3 change:
    McNemar (exact) on R@5 hit/miss and Wilcoxon signed-rank on reciprocal rank (mrr@10), each with delta + bootstrap CI."""
    a, b = (json.load(open(p, encoding="utf-8")) for p in (a_path, b_path))
    assert a["split"] == b["split"], "different splits"
    ia = {r["qid"]: r for r in a["items"] if r["type"] != "unanswerable"}
    ib = {r["qid"]: r for r in b["items"] if r["type"] != "unanswerable"}
    assert ia.keys() == ib.keys(), "different items"
    rng, out, q = np.random.default_rng(2), {}, sorted(ia)
    for m in METRICS:
        out[m] = _paired([ib[k][m] - ia[k][m] for k in q], rng, m.startswith("recall"))
    multi = [k for k in q if "all_spans@10" in ia[k]]
    out["all_spans@10 (multi+cross)"] = _paired([ib[k]["all_spans@10"] - ia[k]["all_spans@10"] for k in multi], rng, True)
    out["latency_ms_p50"] = {"A": a["latency_ms_per_query"]["p50"], "B": b["latency_ms_per_query"]["p50"]}
    return out


def compare_table(c, name_a, name_b):
    r5, rr = c["recall@5"], c["mrr@10"]
    return chr(10).join([
        f"{name_b} vs {name_a}  (n={r5['n']} answerable, paired by question)",
        f"  R@5: delta {r5['delta']:+.3f} CI [{r5['ci95'][0]:+.3f},{r5['ci95'][1]:+.3f}]  McNemar exact p={r5['mcnemar_exact_p']} "
        f"(improved {r5['improved']}, worsened {r5['worsened']})",
        f"  reciprocal rank (MRR@10): delta {rr['delta']:+.3f} CI [{rr['ci95'][0]:+.3f},{rr['ci95'][1]:+.3f}]  Wilcoxon p={rr['wilcoxon_p']}",
        f"  nDCG@10: delta {c['ndcg@10']['delta']:+.3f}   R@1: delta {c['recall@1']['delta']:+.3f}   R@10: delta {c['recall@10']['delta']:+.3f}",
        f"  all-spans@10 (multi+cross): delta {c['all_spans@10 (multi+cross)']['delta']:+.3f} (improved {c['all_spans@10 (multi+cross)']['improved']}, worsened {c['all_spans@10 (multi+cross)']['worsened']})",
        f"  latency p50 ms: {c['latency_ms_p50']['A']} -> {c['latency_ms_p50']['B']}"])


def fmt(c):
    return f"{c[0]:.2f} [{c[1]:.2f},{c[2]:.2f}]" if c and c[0] is not None else "-"


def table(res):
    lines = [f"split={res['split']}  commit={res['git_commit']}  latency p50={res['latency_ms_per_query']['p50']}ms",
             "| group | n | R@1 | R@5 | R@10 | MRR@10 | nDCG@10 | all-spans@10 (n) |", "|---|---|---|---|---|---|---|---|"]
    for g, d in res["summary"].items():
        if "recall@1" not in d:
            continue
        a = d.get("all_spans@10")
        lines.append(f"| {g} | {d['n']} | " + " | ".join(fmt(d[m]) for m in METRICS) +
                     (f" | {fmt(a)} ({a[3]}) |" if a else " | - |"))
    p = res["summary"]["multi+cross pooled"]
    lines.append(f"| multi+cross pooled | {p['n']} | | {fmt(p['recall@5'])} | | | | {fmt(p['all_spans@10'])} |")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"])
    ap.add_argument("--label")
    ap.add_argument("--out")
    ap.add_argument("--compare", nargs=2)
    ap.add_argument("--hybrid", help="JSON dict of hybrid params, e.g. '{\"rrf_k\":60,\"w_bm25\":1,\"depth\":50}'; omit for dense only")
    a = ap.parse_args()
    if a.compare:
        c = compare(*a.compare)
        print(json.dumps(c, indent=1))
        print(compare_table(c, *[os.path.basename(p) for p in a.compare]))
    else:
        res = evaluate(a.split, build_retriever(hybrid=json.loads(a.hybrid) if a.hybrid else None), a.label)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        json.dump(res, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
        print(table(res))
