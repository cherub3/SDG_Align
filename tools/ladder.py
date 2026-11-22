"""Phase 2 headline: the configuration ladder on the TEST split (44 answerable + 8 unanswerable), each step vs the previous one.
Reads result files only. Usage: python tools/ladder.py -> eval/results/phase2_ladder.json and phase2_ladder.md
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval_retrieval as ev  # noqa: E402

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "eval", "results")
LADDER = [("baseline (dense, original text)", "baseline.json"), ("3a: embed text without heading/template prefixes", "3a_test_fast.json"),
          ("3b: + BM25 hybrid, RRF (k=10, w_bm25=2)", "3b_test_fast.json"), ("3c: + MiniLM reranker N=20 (OFF by default)", "3c_test.json"),
          ("3d: advisory flag on 3b (same retrieval as 3b)", "3d_test_hybrid.json")]
PREV = {4: 2}          # 3c is off by default, so 3d is compared with the last KEPT configuration (3b); 3c is also compared with 3b
J = lambda n: json.load(open(os.path.join(R, n), encoding="utf-8"))  # noqa: E731


def main():
    rows, steps = [], []
    for i, (name, f) in enumerate(LADDER):
        d = J(f)
        s = d["summary"]["ALL answerable"]
        rows.append({"config": name, "file": f, "n": s["n"], **{m: s[m] for m in ("recall@1", "recall@5", "recall@10", "mrr@10", "ndcg@10", "all_spans@10")},
                     "latency_ms": d["latency_ms_per_query"]})
        if i:
            j = PREV.get(i, i - 1)
            steps.append({"from": LADDER[j][0], "to": name, "paired": ev.compare(os.path.join(R, LADDER[j][1]), os.path.join(R, f))})
    json.dump({"split": "test", "rows": rows, "paired_vs_previous": steps}, open(os.path.join(R, "phase2_ladder.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    f3 = lambda v: f"{v[0]:.2f} [{v[1]:.2f},{v[2]:.2f}]"  # noqa: E731
    md = ["| config | R@1 | R@5 | R@10 | MRR@10 | latency p50 / p95 ms |", "|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['config']} | {f3(r['recall@1'])} | {f3(r['recall@5'])} | {f3(r['recall@10'])} | {f3(r['mrr@10'])} | {r['latency_ms']['p50']} / {r['latency_ms']['p95']} |")
    md += ["", "| step | metric | delta | 95% CI | better/worse | test p |", "|---|---|---|---|---|---|"]
    for st in steps:
        for m in ("recall@1", "recall@5", "recall@10", "mrr@10"):
            c = st["paired"][m]
            p = c.get("mcnemar_exact_p", c.get("wilcoxon_p"))
            md.append(f"| {st['to'].split(':')[0]} vs {st['from'].split(':')[0][:8]} | {m} | {c['delta']:+.3f} | [{c['ci95'][0]:+.3f},{c['ci95'][1]:+.3f}] | "
                      f"{c.get('improved', '')}/{c.get('worsened', '')} | {p} |")
    open(os.path.join(R, "phase2_ladder.md"), "w", encoding="utf-8", newline="\n").write("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
