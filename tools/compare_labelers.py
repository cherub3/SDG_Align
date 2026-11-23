"""
compare_labelers.py - Compare two independent label sets for inter-rater reliability.
Computes raw agreement, Cohen's kappa, confusion matrix, and lists disagreements.
Uses only Python standard library.
"""
import json
import sys
import os

def load_labeler_a(path):
    """Load Labeller A (other AI) labels from nested dict format."""
    with open(path) as f:
        data = json.load(f)
    labels = {}
    for qid, obj in data["labels"].items():
        labels[qid] = {
            "label": obj["label"],
            "note": obj.get("note", "")
        }
    return labels

def load_labeler_b(path):
    """Load Labeller B (independent) labels from list format."""
    with open(path) as f:
        data = json.load(f)
    labels = {}
    for obj in data:
        labels[obj["qid"]] = {
            "label": obj["label"],
            "confidence": obj.get("confidence", "high"),
            "reason": obj.get("reason", ""),
            "type": obj.get("type", "")
        }
    return labels

def cohens_kappa(labels_a, labels_b, categories):
    """Compute Cohen's kappa for two raters over shared items."""
    n = len(labels_a)
    if n == 0:
        return 0.0

    # Build confusion matrix
    matrix = {}
    for c1 in categories:
        matrix[c1] = {}
        for c2 in categories:
            matrix[c1][c2] = 0

    for qid in labels_a:
        la = labels_a[qid]
        lb = labels_b[qid]
        matrix[la][lb] += 1

    # Observed agreement
    agree = sum(matrix[c][c] for c in categories)
    po = agree / n

    # Expected agreement
    pe = 0.0
    for c in categories:
        row_sum = sum(matrix[c][c2] for c2 in categories)
        col_sum = sum(matrix[c1][c] for c1 in categories)
        pe += (row_sum * col_sum) / (n * n)

    if pe == 1.0:
        return 1.0
    kappa = (po - pe) / (1.0 - pe)
    return kappa

def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    path_a = os.path.join(base, "eval", "test_v21_correctness_labels.json")
    path_b = os.path.join(base, "eval", "test_v21_correctness_labels_independent.json")
    out_path = os.path.join(base, "eval", "results", "labeler_agreement.json")

    la = load_labeler_a(path_a)
    lb = load_labeler_b(path_b)

    # Shared QIDs
    shared = sorted(set(la.keys()) & set(lb.keys()))
    print(f"Shared items: {len(shared)}")

    categories = ["correct", "partial", "wrong", "refused"]

    # Extract label strings
    la_labels = {qid: la[qid]["label"] for qid in shared}
    lb_labels = {qid: lb[qid]["label"] for qid in shared}

    # Raw agreement
    agreements = sum(1 for qid in shared if la_labels[qid] == lb_labels[qid])
    raw_agree_pct = round(100 * agreements / len(shared), 2)

    # Cohen's kappa
    kappa = round(cohens_kappa(la_labels, lb_labels, categories), 4)

    # Confusion matrix
    matrix = {}
    for c1 in categories:
        matrix[c1] = {}
        for c2 in categories:
            matrix[c1][c2] = 0
    for qid in shared:
        matrix[la_labels[qid]][lb_labels[qid]] += 1

    # Disagreements
    disagreements = []
    for qid in shared:
        if la_labels[qid] != lb_labels[qid]:
            disagreements.append({
                "qid": qid,
                "type": lb[qid].get("type", ""),
                "labeller_a": la_labels[qid],
                "labeller_a_note": la[qid].get("note", ""),
                "labeller_b": lb_labels[qid],
                "labeller_b_reason": lb[qid].get("reason", ""),
                "labeller_b_confidence": lb[qid].get("confidence", "high")
            })

    result = {
        "shared_items": len(shared),
        "raw_agreement_pct": raw_agree_pct,
        "cohens_kappa": kappa,
        "confusion_matrix": {
            "rows": "labeller_A",
            "cols": "labeller_B",
            "categories": categories,
            "matrix": matrix
        },
        "num_disagreements": len(disagreements),
        "disagreements": disagreements
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    # Print summary
    print(f"Raw agreement: {raw_agree_pct}%")
    print(f"Cohen's kappa: {kappa}")
    print(f"Disagreements: {len(disagreements)}")
    print()
    print("Confusion matrix (rows=A, cols=B):")
    header = "          "
    for c in categories:
        header += f"{c:<10}"
    print(header)
    for c1 in categories:
        row = f"{c1:<10}"
        for c2 in categories:
            row += f"{matrix[c1][c2]:<10}"
        print(row)
    print()
    for d in disagreements:
        print(f"  {d['qid']} ({d['type']}): A={d['labeller_a']}, B={d['labeller_b']}")

    print(f"\nOutput saved to: {out_path}")

if __name__ == "__main__":
    main()
