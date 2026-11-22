# Gold set change log (Step 1, before freeze)

Drafter: isolated sub-agent (document text only), 70 items -> eval/gold_draft_raw.json (kept unmodified).
Pass 1 verifier on the 70: 0 errors (eval/gold_verify_pass1.txt).
Independent reviewer (isolated sub-agent, packet + document text): eval/gold_review_verdicts.json. 70 verdicts, 12 with comments.

| qid | reviewer finding | action |
|---|---|---|
| Q005 | ambiguous: the documents conflict on who executes (MAE leads, p26; GGGI "anticipated executing entity", p30) | DROPPED |
| Q037 | same conflict (p26 vs p30) | DROPPED |
| Q041 | second span alone answers; first span redundant, so not a real multi-passage item | DROPPED |
| Q054 | quotes do not say the executors are civil-society organizations (only a header tag outside the span): sufficiency "partial" | DROPPED |
| Q042 | first quote cut mid-sentence ("relevant to") | FIXED: quote extended to the end of the line; offsets recomputed by script |
| Q001 | other passage gives a different period for the same elephants; question wording matches the quoted span | KEPT (reviewer: not ambiguous) |
| Q061-Q065 | near-miss absence confirmed (answer_present = false) | KEPT |
| Q066-Q070 | off-corpus (no comment) | KEPT |

No replacements were drafted for the dropped items, so the final set is 66 items, not 70. Final files: eval/gold_draft_fixed.json -> eval/gold_set.jsonl (via tools/build_gold.py); verifier output eval/gold_verify.txt.

## Data-quality finding: conflicting executing-entity statements (Ecuador dry-forest / ecuador_biodiversity)

The same document states two different things about who executes the project: p.26 says the Ministry (MAE) leads execution;
p.30 calls GGGI the "anticipated executing entity". Found by the independent reviewer (Q005, Q037), both dropped as ambiguous.
This is a property of the source documents, not of the pipeline. Candidate future "conflicting sources" test: the right
behaviour is to surface both passages (all-spans@k) rather than pick one. Not in the frozen set.

## Freeze (see eval/GOLD_FROZEN.txt)

Frozen at 66 items (planned 70: 20 single_fact, 14 numbers_tables, 12 multi_passage, 14 cross_document, 10 unanswerable;
final 19 / 14 / 10 / 13 / 10). Dropped: Q005, Q037, Q041, Q054. No replacements drafted.
Split: seeded (seed 20261123), stratified by type (unanswerable by kind), 20% dev (14 items) / 80% test (52 items).
