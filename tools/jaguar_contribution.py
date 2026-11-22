"""How much of the 'after' result comes from the 6th document (ecuador_jaguar_landscape_connectivity), which did not exist
in the 'before' index? Writes reports/evidence/judging/jaguar_contribution.json.
Uses the key and the final labels, so run it only after unblinding.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chunk_metrics as cm  # noqa: E402
import compute_phase1_results as cpr  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(REPO, "reports", "evidence")
J = os.path.join(EV, "judging")
JAG = "ecuador_jaguar_landscape_connectivity"


def main():
    key = json.load(open(os.path.join(EV, "blind_key.json"), encoding="utf-8"))
    final = {i: v["label"] for i, v in json.load(open(os.path.join(J, "labels_final.json")))["labels"].items()}
    slots = []
    for iid, v in key["items"].items():
        for s in v["sources"]:
            if s["version"] == "after" and v["question_no"] <= 13:
                slots.append((v["question_no"], s["rank"], s["doc"], final[iid]))
    jag = [s for s in slots if s[2] == JAG]
    out = {
        "after_top5_slots_answerable": len(slots),
        "from_jaguar": len(jag),
        "jaguar_labels_UPN": [sum(1 for s in jag if s[3] == 2), sum(1 for s in jag if s[3] == 1), sum(1 for s in jag if s[3] == 0)],
        "questions_with_a_jaguar_result_in_top5": sorted({s[0] for s in jag}),
        "jaguar_rank1_questions": sorted(s[0] for s in jag if s[1] == 0),
    }
    # chunk metrics of the jaguar document alone vs the other five
    manifest = json.load(open(os.path.join(REPO, "data", "proposals", "manifest.json"), encoding="utf-8"))
    recs = manifest if isinstance(manifest, dict) else {r["doc_id"]: r for r in manifest}
    jag_doc = [d for d, r in recs.items() if os.path.basename(r.get("source_path") or "").replace(".pdf", "") == JAG]
    jag_texts, other_texts = [], []
    for f in glob.glob(os.path.join(REPO, "data", "proposals", "chunks", "*", "chunks.json")):
        doc = os.path.basename(os.path.dirname(f))
        texts = [c["text"] for c in json.load(open(f, encoding="utf-8"))["chunks"]]
        (jag_texts if doc in jag_doc else other_texts).extend(texts)
    out["chunk_metrics_jaguar_only"] = cm.chunk_metrics(jag_texts)
    out["chunk_metrics_other_five"] = cm.chunk_metrics(other_texts)
    json.dump(out, open(os.path.join(J, "jaguar_contribution.json"), "w", encoding="utf-8"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if not k.startswith("chunk_metrics")}, indent=1))
    for k in ("chunk_metrics_jaguar_only", "chunk_metrics_other_five"):
        m = out[k]
        print(k, {x: m[x] for x in ("chunk_count", "fragments", "duplicate_chunks", "mid_sentence_ending_rate")})


if __name__ == "__main__":
    main()
