"""Step 5: open the key and compute the Phase 1 before/after results.

Inputs (reports/evidence/): blind_key.json, retrieval_before.json, retrieval_after.json, judging/labels_*.json.
Outputs: judging/results.json and judging/results.md.
Usefulness is computed over the 13 answerable questions (65 results per version). Questions 14 and 15 are scored 0 by the
frozen rule and are reported separately.
"""
import itertools
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import judge_agreement as ja  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(REPO, "reports", "evidence")
J = os.path.join(EV, "judging")
ANSWERABLE = range(1, 14)


def sign_test_two_sided(diffs):
    d = [x for x in diffs if abs(x) > 1e-12]
    n, k = len(d), sum(1 for x in d if x > 0)
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(0, min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def wilcoxon_exact_two_sided(diffs):
    """Exact two-sided Wilcoxon signed-rank test: zero differences dropped, mid-ranks for ties, all 2^n sign
    assignments enumerated (no normal approximation). Returns (p, W+)."""
    d = [x for x in diffs if abs(x) > 1e-12]
    n = len(d)
    if n == 0:
        return 1.0, 0.0
    order = sorted(range(n), key=lambda i: abs(d[i]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(abs(d[order[j + 1]]) - abs(d[order[i]])) < 1e-9:
            j += 1
        for t in range(i, j + 1):
            ranks[order[t]] = (i + j) / 2 + 1
        i = j + 1
    w_plus = sum(r for r, x in zip(ranks, d) if x > 0)
    mean = sum(ranks) / 2
    obs = abs(w_plus - mean)
    cnt = 0
    for signs in itertools.product((0, 1), repeat=n):
        w = sum(r for r, s in zip(ranks, signs) if s)
        if abs(w - mean) >= obs - 1e-9:
            cnt += 1
    return cnt / 2 ** n, w_plus


def slots(key):
    """(version, question_no, rank) -> item id."""
    m = {}
    for iid, v in key["items"].items():
        for s in v["sources"]:
            m[(s["version"], v["question_no"], s["rank"])] = iid
    return m


def per_version(labels, slot_map, version, retr):
    levels = {}
    for q in range(1, 16):
        levels[q] = [labels[slot_map[(version, q, t["rank"])]] for t in retr["results"][q - 1]["top5"]]
    ans = [levels[q] for q in ANSWERABLE]
    n = len(ans)
    first = [next((r + 1 for r, x in enumerate(lv) if x == 2), None) for lv in ans]
    firsts = [f for f in first if f]
    return {
        "useful_at_5": round(sum(sum(1 for x in lv if x == 2) / 5 for lv in ans) / n, 4),
        "useful_or_partial_at_5": round(sum(sum(1 for x in lv if x >= 1) / 5 for lv in ans) / n, 4),
        "mean_score_0_to_2": round(sum(sum(lv) / 5 for lv in ans) / n, 4),
        "weighted_useful_at_5_frozen": round(sum(sum(lv) / 10 for lv in ans) / n, 4),
        "questions_served": sum(1 for lv in ans if 2 in lv),
        "first_useful_rank_mean": round(sum(firsts) / len(firsts), 3) if firsts else None,
        "counts_UPN_of_65": [sum(lv.count(2) for lv in ans), sum(lv.count(1) for lv in ans), sum(lv.count(0) for lv in ans)],
        "per_question_mean": {q: round(sum(levels[q]) / len(levels[q]), 3) for q in ANSWERABLE},
    }


def main():
    key = json.load(open(os.path.join(EV, "blind_key.json"), encoding="utf-8"))
    before = json.load(open(os.path.join(EV, "retrieval_before.json"), encoding="utf-8"))
    after = json.load(open(os.path.join(EV, "retrieval_after.json"), encoding="utf-8"))
    sm = slots(key)
    final = json.load(open(os.path.join(J, "labels_final.json"), encoding="utf-8"))["labels"]
    sets = {
        "final (headline)": {i: v["label"] for i, v in final.items()},
        "judge1_frozen": ja.load_labels(os.path.join(J, "labels_judge1_frozen.json")),
        "judge2": ja.load_labels(os.path.join(J, "labels_judge2.json")),
        "judge1_asis (deviation)": ja.load_labels(os.path.join(J, "labels_judge1_asis.json")),
    }
    qmap = ja.question_map(os.path.join(J, "packet.jsonl"))
    res = {"label_sets": {}, "automatic": {}, "unanswerable": {}}
    for name, lab in sets.items():
        lab = {i: (0 if qmap[i] in (14, 15) else v) for i, v in lab.items()}
        b, a = per_version(lab, sm, "before", before), per_version(lab, sm, "after", after)
        diffs = [a["per_question_mean"][q] - b["per_question_mean"][q] for q in ANSWERABLE]
        p_w, _ = wilcoxon_exact_two_sided(diffs)
        res["label_sets"][name] = {
            "before": b, "after": a,
            "wins": sum(d > 1e-12 for d in diffs), "losses": sum(d < -1e-12 for d in diffs),
            "ties": sum(abs(d) <= 1e-12 for d in diffs),
            "per_question_diff": {q: round(d, 3) for q, d in zip(ANSWERABLE, diffs)},
            "sign_test_p_two_sided": round(sign_test_two_sided(diffs), 4),
            "wilcoxon_exact_p_two_sided": round(p_w, 4), "mean_diff": round(sum(diffs) / len(diffs), 4)}
    for name, d in (("before", before), ("after", after)):
        res["automatic"][name] = {**d["retrieval_metrics"], "chunk_metrics": d["chunk_metrics"]}
        res["unanswerable"][name] = {
            str(r["n"]): {"top1_score": r["top5"][0]["score"], "top1_doc": r["top5"][0]["doc"],
                          "top1_text_start": r["top5"][0]["text"].strip()[:90]}
            for r in d["results"] if r["n"] in (14, 15)}
    res["rank1_by_question"] = {}
    for name, d in (("before", before), ("after", after)):
        res["rank1_by_question"][name] = {
            str(r["n"]): {"expected": r["expected_doc"], "rank1_doc": r["top5"][0]["doc"]}
            for r in d["results"] if r["expected_doc"] not in ("any", "NOT INDEXED")}
    json.dump(res, open(os.path.join(J, "results.json"), "w", encoding="utf-8"), indent=1)

    out = ["# Phase 1 results (computed by tools/compute_phase1_results.py)", ""]
    for name, r in res["label_sets"].items():
        b, a = r["before"], r["after"]
        out += [f"## Labels: {name}", "", "| metric (13 answerable questions) | before | after |", "|---|---|---|"]
        for k in ("useful_at_5", "useful_or_partial_at_5", "mean_score_0_to_2", "weighted_useful_at_5_frozen",
                  "questions_served", "first_useful_rank_mean", "counts_UPN_of_65"):
            out.append(f"| {k} | {b[k]} | {a[k]} |")
        out += ["", f"Per-question wins / losses / ties (after vs before, mean score): {r['wins']} / {r['losses']} / {r['ties']}; "
                f"mean difference {r['mean_diff']}; sign test p = {r['sign_test_p_two_sided']}; "
                f"exact Wilcoxon p = {r['wilcoxon_exact_p_two_sided']}", "",
                "| Q | before | after | diff |", "|---|---|---|---|"]
        for q in ANSWERABLE:
            out.append(f"| {q} | {b['per_question_mean'][q]} | {a['per_question_mean'][q]} | {r['per_question_diff'][q]} |")
        out.append("")
    out += ["## Automatic metrics (frozen rules)", "", "| metric | before | after |", "|---|---|---|"]
    for k in ("boilerplate_share_top5_all15", "boilerplate_share_top5_answerable13", "fragments_in_top5",
              "duplicates_in_top5", "expected_doc_rank1"):
        out.append(f"| {k} | {res['automatic']['before'][k]} | {res['automatic']['after'][k]} |")
    out += ["", "## Unanswerable questions (14, 15): top-1 that came back (no abstention exists)", ""]
    for name in ("before", "after"):
        for q, v in res["unanswerable"][name].items():
            out.append(f"* {name} Q{q}: top-1 score {v['top1_score']} from {v['top1_doc']}: {v['top1_text_start']!r}")
    open(os.path.join(J, "results.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
    print("\n".join(out[:34]))


if __name__ == "__main__":
    main()
