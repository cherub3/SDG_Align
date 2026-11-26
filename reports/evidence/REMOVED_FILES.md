# Files removed from the public repo

These files held verbatim text from the source proposals, which are not licensed for redistribution. They were removed. The scripts that read them are kept and show how the files were made, but they cannot run on a clean checkout without the corpus.

| Removed file | What it held | How to regenerate locally (needs the PDFs under `data/proposals/` and a built index) |
|---|---|---|
| `reports/evidence/retrieval_before.json` | top-5 chunks for 15 questions, Phase 0 pipeline | Not reproducible at the current commit (it came from the pre-Phase-1 pipeline). Its summary numbers stay in `reports/PHASE_1_REPORT.md` |
| `reports/evidence/retrieval_after.json`, `retrieval_after_5doc.json` | top-5 chunks for 15 questions, after-cleaning pipeline | `tools/retrieval_eval.py` |
| `reports/evidence/blind_judging.jsonl`, `reports/evidence/judging/packet.jsonl` | the 144 passages shown to the blind judges | `tools/make_blind_files.py`, then `tools/make_judging_packet.py` |
| `reports/evidence/judging/packet_cleaning_only_new.jsonl` | 4 extra passages for the cleaning-only comparison | `tools/cleaning_only_new_items.py` |
| `reports/evidence/judging/prompts/*.md` | judge prompts with the passages embedded | `tools/build_judge_prompt.py` |
| `reports/evidence/blind_for_owner.md` | 5 questions with their passages for a manual blind labelling pass | `tools/make_blind_files.py` |

Also changed: `eval/results/step6_smoke.json` keeps its timings, status codes and chunk ids, but the chunk `text` fields were replaced with `[removed: corpus text]`. The latency figures quoted in `reports/PHASE_3_REPORT.md` do not depend on them.

Kept because they hold only ids, scores, labels or short quotes: the judge label files and raw outputs under `reports/evidence/judging/`, `reports/evidence/blind_key.json`, and `eval/gold_set.jsonl` (66 short answer quotes, about 150 characters each).
