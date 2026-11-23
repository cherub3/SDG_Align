"""Script checks for Phase 3 step 4 (answer-level abstention). No model is called here.

Per answer, four judgments (all deterministic, all PROXIES; none is a human or LLM judge):
  decision          scripts.abstention.decision(): ANSWERED / NOT_IN_CONTEXT / MIXED / EMPTY. THE metric for the keep rule.
  implicit_refusal  an ANSWERED reply that refuses in free text ("the excerpts do not mention ...") instead of the sentinel.
  correct_proxy     answerable items only: share of the gold quote's FACT tokens (content words and numbers that are in the gold
                    quote(s) but not in the question) that appear in the answer is >= SUPPORT_THRESHOLD.
  term_in_answer    unanswerable items only: the answer contains one of the item's hand-listed absence_terms (a sign it invented
                    the missing detail). A fabricated value that uses none of the listed terms is NOT caught (known false negative).
Usage:  python tools/answer_checks.py --fpfn        checks the judgments against eval/step4_checker_cases.json (hand labels, DEV items)
"""
import json
import math
import os
import re
import sys
import unicodedata

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from scripts.abstention import decision  # noqa: E402

SUPPORT_THRESHOLD = 0.5
BOOT, SEED = 10000, 1
_STOP = set("""about above after again also among because been before being between both could does each from have into least more most
much only other over said same should some such than that their them then there these they this those through under until upon very
were what when where which while will with within would your according project projects""".split())
_REFUSAL = re.compile(
    r"\b(does|do|did|doesn't|don't)\s+not\s+(contain|mention|provide|specify|state|include|say|give|list|name|describe|address)"
    r"|\b(not|n't)\s+(stated|mentioned|specified|provided|available|given|included|reported|described)"
    r"|\bno\s+(information|mention|data|details?|figure|number|specific)\b"
    r"|\b(cannot|can't|unable to|could not|couldn't)\s+(find|determine|be\s+determined|answer|identify)"
    r"|\b(is|are)\s+not\s+(in|within|part of)\s+the\s+(context|excerpts?|provided)", re.IGNORECASE)


def _fold(t):
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()


def _num(s):
    s = s.replace(",", "")
    return re.sub(r"(\.\d*?)0+$", r"\1", s).rstrip(".") if "." in s else s


def tokens(text):
    """Content words (>=4 letters, minus stop words, trailing 's' removed) and numbers (commas dropped, '.00' dropped)."""
    f = _fold(text)
    out = set()
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?%?|[a-z]{4,}", f):
        w = m.group(0)
        if w[0].isdigit():
            out.add(_num(w.rstrip("%")) + ("%" if w.endswith("%") else ""))
        elif w not in _STOP:
            out.add(w[:-1] if w.endswith("s") and len(w) > 4 else w)
    return out


def support_recall(answer, question, quotes):
    fact = set().union(*[tokens(q) for q in quotes]) - tokens(question) if quotes else set()
    return (len(fact & tokens(answer)) / len(fact)) if fact else None


def implicit_refusal(text):
    return bool(_REFUSAL.search(text or ""))


def check_item(item, response_text):
    """item: a gold-set row (needs question, type, evidence or absence_terms). Returns the judgments for one answer."""
    d = decision(response_text)
    out = {"qid": item["qid"], "type": item["type"], "kind": item.get("kind"), "decision": d,
           "implicit_refusal": d == "ANSWERED" and implicit_refusal(response_text)}
    if item["type"] == "unanswerable":
        txt = _fold(response_text)
        out["term_in_answer"] = d in ("ANSWERED", "MIXED") and not out["implicit_refusal"] and any(_fold(t) in txt for t in item.get("absence_terms", []))
    else:
        rec = support_recall(response_text, item["question"], [e["answer_quote"] for e in item["evidence"]])
        out["support_recall"] = None if rec is None else round(rec, 3)
        out["correct_proxy"] = d in ("ANSWERED", "MIXED") and not out["implicit_refusal"] and rec is not None and rec >= SUPPORT_THRESHOLD
    return out


def ci(flags, rng):
    x = np.asarray(flags, float)
    if not len(x):
        return None
    m = x[rng.integers(0, len(x), (BOOT, len(x)))].mean(axis=1)
    return [round(float(np.percentile(m, 2.5)), 3), round(float(np.percentile(m, 97.5)), 3)]


def rate(flags, rng):
    return {"k": int(sum(flags)), "n": len(flags), "rate": round(float(np.mean(flags)), 3) if flags else None, "ci95": ci(flags, rng)}


def summarize(checks):
    """checks: output of check_item for items that produced a valid LLM reply. Bootstrap CIs over items (10000, seed 1)."""
    rng = np.random.default_rng(SEED)
    ans = [c for c in checks if c["type"] != "unanswerable"]
    un = [c for c in checks if c["type"] == "unanswerable"]
    refused = lambda c: c["decision"] == "NOT_IN_CONTEXT"  # noqa: E731
    s = {"refusal_rate_unanswerable": rate([refused(c) for c in un], rng),
         "false_refusal_rate_answerable": rate([refused(c) for c in ans], rng),
         "answered_correct_proxy_rate_answerable": rate([bool(c["correct_proxy"]) for c in ans], rng),
         "mixed_or_empty_or_implicit": {"mixed": sum(c["decision"] == "MIXED" for c in checks), "empty": sum(c["decision"] == "EMPTY" for c in checks),
                                        "implicit_refusals": sum(bool(c["implicit_refusal"]) for c in checks)},
         "unanswerable_answered_with_absence_term": rate([bool(c.get("term_in_answer")) for c in un if not refused(c)], rng)}
    for k in ("near_miss", "off_corpus"):
        s[f"refusal_rate_{k}"] = rate([refused(c) for c in un if c["kind"] == k], rng)
    for t in sorted({c["type"] for c in ans}):
        s[f"false_refusal_by_type:{t}"] = rate([refused(c) for c in ans if c["type"] == t], rng)
    return s


def keep_rule(summary):
    """PRE-STATED (Step 4 report, written before any TEST call): KEEP iff point estimates satisfy
    refusal on unanswerable > 50% (strictly more than half) AND false refusal on answerable <= 10%."""
    r, f = summary["refusal_rate_unanswerable"], summary["false_refusal_rate_answerable"]
    return {"refuses_majority_of_unanswerable": r["rate"] is not None and r["rate"] > 0.5,
            "false_refusal_le_10pct": f["rate"] is not None and f["rate"] <= 0.10,
            "KEEP": bool(r["rate"] is not None and r["rate"] > 0.5 and f["rate"] is not None and f["rate"] <= 0.10)}


def fpfn(cases_path, items_by_qid):
    """Confusion counts of each judgment against the hand labels in cases_path."""
    cases = json.load(open(cases_path, encoding="utf-8"))["cases"]
    judg = ("refused", "implicit_refusal", "correct_proxy", "term_in_answer")
    conf = {j: {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "n": 0} for j in judg}
    rows = []
    for c in cases:
        got = check_item(items_by_qid[c["qid"]], c["response"])
        got["refused"] = got["decision"] == "NOT_IN_CONTEXT"
        row = {"id": c["id"], "qid": c["qid"], "what": c["what"], "response": c["response"], "support_recall": got.get("support_recall")}
        for j in judg:
            if j in c["truth"]:
                t, g = bool(c["truth"][j]), bool(got.get(j))
                conf[j]["n"] += 1
                conf[j]["tp" if t and g else "fp" if g else "fn" if t else "tn"] += 1
                row[j] = {"truth": t, "checker": g, "ok": t == g}
        rows.append(row)
    return {"threshold": SUPPORT_THRESHOLD, "confusion": conf, "rows": rows}


if __name__ == "__main__":
    if "--fpfn" in sys.argv:
        gold = {r["qid"]: r for r in (json.loads(x) for x in open(os.path.join(REPO, "eval", "gold_set.jsonl"), encoding="utf-8") if x.strip())}
        res = fpfn(os.path.join(REPO, "eval", "step4_checker_cases.json"), gold)
        os.makedirs(os.path.join(REPO, "eval", "results"), exist_ok=True)
        out = os.path.join(REPO, "eval", "results", "step4_checker_fpfn.json")
        json.dump(res, open(out, "w", encoding="utf-8", newline=chr(10)), indent=1, ensure_ascii=False)
        print(json.dumps(res["confusion"], indent=1))
        for r in res["rows"]:
            print(r["id"], r["qid"], "recall=", r["support_recall"], {k: v["ok"] for k, v in r.items() if isinstance(v, dict)})


def compare_real(rows, labels, items_by_qid):
    """Checker vs hand labels on REAL replies. Judgments: refused (decision) and correct_proxy. Returns confusion counts."""
    conf = {"correct_proxy": {"tp": 0, "fp": 0, "fn": 0, "tn": 0}, "refused": {"tp": 0, "fp": 0, "fn": 0, "tn": 0}}
    detail = []
    for r in rows:
        it = items_by_qid[r["qid"]]
        if it["type"] == "unanswerable":
            continue
        c = check_item(it, r["response_text"])
        t_ref = r["response_text"].strip().strip("`*\"'. ").upper() == "NOT_IN_CONTEXT"      # the label is read from the text by eye, here the same bare-sentinel fact
        for j, truth, got in (("correct_proxy", bool(labels[r["qid"]]), bool(c["correct_proxy"])), ("refused", t_ref, c["decision"] == "NOT_IN_CONTEXT")):
            conf[j]["tp" if truth and got else "fp" if got else "fn" if truth else "tn"] += 1
        detail.append({"qid": r["qid"], "truth_correct": bool(labels[r["qid"]]), "checker_correct": bool(c["correct_proxy"]), "support_recall": c["support_recall"]})
    return {"confusion": conf, "detail": detail}
