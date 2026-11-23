"""Accuracy with Wilson 95% CI from eval/test_v21_correctness_labels.json (two blind Claude labelling runs plus one owner adjudication). Writes eval/results/test_v21_correctness_summary.json. No model call."""
import json, math, os, collections
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def wilson(k, n, z=1.96):
    if n == 0:
        return [None, None]
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 3), round(c + h, 3)]

def main():
    d = json.load(open(os.path.join(REPO, "eval/test_v21_correctness_final.json"), encoding="utf-8"))
    n = collections.Counter(v["label"] for v in d["labels"].values()); N = sum(n.values()); A = N - n["refused"]
    rate = lambda k, m: {"k": k, "n": m, "rate": round(k / m, 3), "wilson95": wilson(k, m)}
    out = {"labeller": "two blind AI (Claude) runs + owner adjudication of Q036", "AI_made_not_human": True, "adjudicated_by_owner": ["Q036"], "labeller_agreement": {"agree": 43, "of": 44, "cohens_kappa": 0.95}, "counts": dict(n),
           "correct_of_all_44_answerable": rate(n["correct"], N),
           "correct_or_partial_of_44": rate(n["correct"] + n["partial"], N),
           "correct_of_answered_38": rate(n["correct"], A),
           "wrong_of_answered_38": rate(n["wrong"], A),
           "refused_of_44": rate(n["refused"], N)}
    by = collections.defaultdict(collections.Counter)
    gold = {json.loads(l)["qid"]: json.loads(l)["type"] for l in open(os.path.join(REPO, "eval/gold_set.jsonl"), encoding="utf-8")}
    for q, v in d["labels"].items():
        by[gold[q]][v["label"]] += 1
    out["by_type"] = {t: dict(c) for t, c in by.items()}
    json.dump(out, open(os.path.join(REPO, "eval/results/test_v21_correctness_summary.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps(out, indent=1))

if __name__ == "__main__":
    main()
