"""Cleaning-only comparison: before (429 chunks, 5 docs) vs after restricted to the same 5 documents vs after with 6 documents.

'after_5doc' = retrieval_after_5doc.json: the after pipeline's chunks and vectors, retrieved over an index that holds only the
original 5 documents, so the jaguar document cannot contribute (the correct way to remove the confound: the top-5 is re-filled
from the 5-document index, not filtered from the 6-document result).
Labels: adjudicated final labels where the passage was already judged; the few new passages carry Judge 4's label
(judging/labels_judge4_cleaning_only_new.json) in every label set. Writes judging/results_cleaning_only.json and .md.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compute_phase1_results as cpr  # noqa: E402
import judge_agreement as ja  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(REPO, "reports", "evidence")
J = os.path.join(EV, "judging")
ANS = cpr.ANSWERABLE


def norm(t):
    return " ".join(t.split())


def levels_by_text(retr, text_label, new_label):
    out = {}
    for r in retr["results"]:
        lv = []
        for t in r["top5"]:
            k = (r["n"], norm(t["text"]))
            lv.append(text_label[k] if k in text_label else new_label[k])
        out[r["n"]] = lv
    return out


def metrics(levels):
    ans = [levels[q] for q in ANS]
    n = len(ans)
    return {"useful_at_5": round(sum(sum(1 for x in lv if x == 2) / 5 for lv in ans) / n, 4),
            "useful_or_partial_at_5": round(sum(sum(1 for x in lv if x >= 1) / 5 for lv in ans) / n, 4),
            "mean_score_0_to_2": round(sum(sum(lv) / 5 for lv in ans) / n, 4),
            "questions_served": sum(1 for lv in ans if 2 in lv),
            "counts_UPN_of_65": [sum(lv.count(2) for lv in ans), sum(lv.count(1) for lv in ans), sum(lv.count(0) for lv in ans)],
            "per_question_mean": {q: round(sum(levels[q]) / 5, 3) for q in ANS}}


def compare(a, b):
    diffs = [b["per_question_mean"][q] - a["per_question_mean"][q] for q in ANS]
    p_w, _ = cpr.wilcoxon_exact_two_sided(diffs)
    return {"wins": sum(d > 1e-12 for d in diffs), "losses": sum(d < -1e-12 for d in diffs),
            "ties": sum(abs(d) <= 1e-12 for d in diffs), "mean_diff": round(sum(diffs) / len(diffs), 4),
            "sign_test_p_two_sided": round(cpr.sign_test_two_sided(diffs), 4),
            "wilcoxon_exact_p_two_sided": round(p_w, 4),
            "per_question_diff": {q: round(d, 3) for q, d in zip(ANS, diffs)}}


def main():
    key = json.load(open(os.path.join(EV, "blind_key.json"), encoding="utf-8"))
    sm = cpr.slots(key)
    qmap = ja.question_map(os.path.join(J, "packet.jsonl"))
    texts = {}
    for line in open(os.path.join(J, "packet.jsonl"), encoding="utf-8"):
        p = json.loads(line)
        texts[p["id"]] = (p["question_no"], norm(p["text"]))
    new_packet = {json.loads(l)["id"]: json.loads(l) for l in open(os.path.join(J, "packet_cleaning_only_new.jsonl"), encoding="utf-8")}
    j4 = ja.load_labels(os.path.join(J, "labels_judge4_cleaning_only_new.json"))
    new_label = {(p["question_no"], norm(p["text"])): j4[i] for i, p in new_packet.items()}
    before = json.load(open(os.path.join(EV, "retrieval_before.json"), encoding="utf-8"))
    after6 = json.load(open(os.path.join(EV, "retrieval_after.json"), encoding="utf-8"))
    after5 = json.load(open(os.path.join(EV, "retrieval_after_5doc.json"), encoding="utf-8"))
    final = json.load(open(os.path.join(J, "labels_final.json"), encoding="utf-8"))["labels"]
    sets = {"final (headline)": {i: v["label"] for i, v in final.items()},
            "judge1_frozen": ja.load_labels(os.path.join(J, "labels_judge1_frozen.json")),
            "judge2": ja.load_labels(os.path.join(J, "labels_judge2.json"))}
    res = {"label_sets": {}, "automatic": {}}
    for name, lab in sets.items():
        text_label = {texts[i]: (0 if qmap[i] in (14, 15) else v) for i, v in lab.items()}
        lv = {"before": levels_by_text(before, text_label, new_label),
              "after_5doc": levels_by_text(after5, text_label, new_label),
              "after_6doc": levels_by_text(after6, text_label, new_label)}
        m = {k: metrics(v) for k, v in lv.items()}
        res["label_sets"][name] = {**m, "cleaning_only_before_vs_after_5doc": compare(m["before"], m["after_5doc"]),
                                   "before_vs_after_6doc": compare(m["before"], m["after_6doc"])}
    for name, d in (("before", before), ("after_5doc", after5), ("after_6doc", after6)):
        res["automatic"][name] = d["retrieval_metrics"]
        res["automatic"][name]["chunk_count"] = d["chunk_metrics"]["chunk_count"]
    json.dump(res, open(os.path.join(J, "results_cleaning_only.json"), "w", encoding="utf-8"), indent=1)

    out = ["# Cleaning-only comparison (tools/compute_cleaning_only.py)", "",
           "after_5doc = after pipeline, index of the original 5 documents only (jaguar excluded). after_6doc = the full 6-document result.", ""]
    for name, r in res["label_sets"].items():
        out += [f"## Labels: {name}", "", "| metric (13 answerable questions) | before | after_5doc (cleaning only) | after_6doc |", "|---|---|---|---|"]
        for k in ("useful_at_5", "useful_or_partial_at_5", "mean_score_0_to_2", "questions_served", "counts_UPN_of_65"):
            out.append(f"| {k} | {r['before'][k]} | {r['after_5doc'][k]} | {r['after_6doc'][k]} |")
        for lab, c in (("before vs after_5doc (headline)", r["cleaning_only_before_vs_after_5doc"]), ("before vs after_6doc", r["before_vs_after_6doc"])):
            out += ["", f"{lab}: wins / losses / ties {c['wins']} / {c['losses']} / {c['ties']}; mean diff {c['mean_diff']}; "
                    f"sign test p = {c['sign_test_p_two_sided']}; exact Wilcoxon p = {c['wilcoxon_exact_p_two_sided']}"]
        out += ["", "| Q | before | after_5doc | diff |", "|---|---|---|---|"]
        for q in ANS:
            out.append(f"| {q} | {r['before']['per_question_mean'][q]} | {r['after_5doc']['per_question_mean'][q]} | "
                       f"{r['cleaning_only_before_vs_after_5doc']['per_question_diff'][q]} |")
        out.append("")
    out += ["## Automatic metrics (frozen rules)", "", "| metric | before | after_5doc | after_6doc |", "|---|---|---|---|"]
    for k in ("boilerplate_share_top5_all15", "fragments_in_top5", "duplicates_in_top5", "expected_doc_rank1"):
        out.append(f"| {k} | " + " | ".join(str(res["automatic"][v][k]) for v in ("before", "after_5doc", "after_6doc")) + " |")
    open(os.path.join(J, "results_cleaning_only.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
    print("\n".join(out[:24]))


if __name__ == "__main__":
    main()
