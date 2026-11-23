"""Why is groundedness 0 on sensible answers? Offline, 0 LLM calls.
Per answered row of an eval arm: for each sentence span, best char-5-gram overlap (stage 14 citation score) and best longest-common-substring
ratio (stage 15 groundedness score) against the chunks that were in the context. Writes eval/results/groundedness_diagnosis.json."""
import json, os, sys, statistics
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, "tools"))
from scripts import stage14_citation_extraction as s14, stage15_groundedness_validation as s15
from tools.eval_served import local_chunks

def main(arm="eval/results/test_noplanner_v21.jsonl", out="eval/results/groundedness_diagnosis.json"):
    local = local_chunks()
    rows = [json.loads(x) for x in open(os.path.join(REPO, arm), encoding="utf-8") if x.strip()]
    res, spans_all = [], []
    for r in rows:
        if r["api_decision"] != "ANSWERED":
            continue
        texts = [local[c]["text"] if isinstance(local.get(c), dict) else local.get(c) for c in r["context_chunk_ids"] if c in local]
        for s in s14.segment_response_text(r["response_text"]):
            ng = max((s14.compute_ngram_overlap(s["text"], t) for t in texts), default=0.0)
            lc = max((s15.compute_groundedness_overlap(s["text"], t) for t in texts), default=0.0)
            spans_all.append((ng, lc))
        res.append({"qid": r["qid"], "groundedness_score": r["groundedness_score"], "citation_presence_ratio": r["citation_presence_ratio"]})
    ng = [a for a, _ in spans_all]; lc = [b for _, b in spans_all]
    out_d = {"arm": arm, "answered_rows": len(res), "spans": len(spans_all),
             "spans_ngram_overlap_ge_0.6 (cited)": sum(x >= 0.6 for x in ng),
             "spans_lcs_ratio_ge_0.8 (GROUNDED)": sum(x >= 0.8 for x in lc),
             "median_ngram_overlap": round(statistics.median(ng), 3), "median_lcs_ratio": round(statistics.median(lc), 3),
             "rows_groundedness_0": sum(x["groundedness_score"] == 0 for x in res), "rows": res}
    json.dump(out_d, open(os.path.join(REPO, out), "w", encoding="utf-8", newline="\n"), indent=1)
    print({k: v for k, v in out_d.items() if k != "rows"})

if __name__ == "__main__":
    main()
