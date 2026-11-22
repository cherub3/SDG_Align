# Phase 1 metric definitions (frozen before any measurement)

Written and committed **before** the baseline run (step A). They are not to be changed afterwards.
If a change turns out to be unavoidable, it is listed in `reports/PHASE_1_REPORT.md` under "Deviations from the frozen definitions", with the reason.

All metrics are computed by one script, `tools/chunk_metrics.py`, from the files on disk. The same code and the same rules run on the "before" data and the "after" data.

## 0. What "before" and "after" mean

| | Before | After |
|---|---|---|
| Chunks | the 429 chunks of the 5 documents indexed at the end of Phase 0 (parent repo commit `3659c21`, `data/proposals/chunks/`) | the chunks produced by the Phase 1 pipeline, for every document that ingests |
| Index | the committed index with fingerprint `afcb8eee107b17a36a7392fa1b58ae327f42c5e18e71be71fda4eee92e739c7d` (BGE-small v1.5, 384 dimensions, vectors built through the HF API) | an index rebuilt locally with `BAAI/bge-small-en-v1.5` through sentence-transformers |
| Retrieval | the real `scripts.stage10_retrieval.retrieve()`, `top_k = 5`, no BGE query prefix, no score threshold | identical |
| Questions | the 15 fixed questions below | identical |

The "before" vectors and local vectors were measured as identical on 30 sampled chunks (min cosine 1.00000, REVIEW.md section 3.3), so the embedding source does not confound the comparison.

## 1. The 15 fixed questions

`E` = expected document stem when the question names a document; `any` = the question is not scoped to one document; `NOT INDEXED` = the answer is in a scanned PDF that the pipeline cannot read (no OCR yet).

| # | Question | E |
|---|---|---|
| 1 | What are the main components of the planetGOLD project in Mozambique? | mozambique_planetgold |
| 2 | How will the project reduce mercury use in artisanal gold mining? | mozambique_planetgold |
| 3 | Which indigenous peoples and local communities are involved in the Cameroon project? | cameroon_biodiversity_iplc_conservation |
| 4 | What protected areas or landscapes does the Cameroon project target? | cameroon_biodiversity_iplc_conservation |
| 5 | What renewable energy technologies will be deployed in Cuba? | cuba_clean_energy |
| 6 | How does the Cuba project contribute to the country's NDC? | cuba_clean_energy |
| 7 | What marine protected areas are covered in Ecuador? | ecuador_marine_biodiversity |
| 8 | What threats do Ecuador's coastal and marine ecosystems face? | ecuador_marine_biodiversity |
| 9 | What is the total GEF financing requested? | any |
| 10 | How will gender equality be mainstreamed in the project? | any |
| 11 | What are the key risks and mitigation measures? | any |
| 12 | How many hectares of landscape will be under improved management? | any |
| 13 | Which SDGs does the Ecuador biodiversity project contribute to? | ecuador_biodiversity |
| 14 | What water supply improvements are planned in Kathmandu? | NOT INDEXED |
| 15 | How will the project improve public schools in Karnataka? | NOT INDEXED |

Questions 1 to 13 are "answerable" (13 questions); 14 and 15 are "unanswerable from the index" (2 questions).

## 2. Chunk-level metrics (computed over all chunks of the indexed documents)

Text normalisation used below, "norm": replace every run of whitespace by one space and strip both ends. Case is kept.

| Metric | Exact definition |
|---|---|
| **chunk_count** | number of chunks |
| **fragment** | a chunk with `len(text.strip()) < 300` (300 is `MIN_CHUNK_CHARS` in stage 7). Reported as a count and as a share of chunk_count |
| **duplicate_chunks** | the number of *surplus* copies: group chunks by `norm(text)`; for each group of size n > 1 add n - 1. Also report the number of duplicated groups |
| **mid_sentence_ending_rate** | share of chunks whose stripped text does **not** end with `.`, `!` or `?`, optionally followed by any of the characters `" ' ) ] * ”` `’`. A chunk that ends with a colon, a comma, a letter, a digit, a table pipe or a heading counts as "mid-sentence". This is deliberately strict: a chunk ending on a list item or table row without a final full stop counts against it |
| **table_markup_chunks** | chunks with at least 2 lines whose stripped text starts with `\|` |
| **html_residue_chunks** | chunks matching the regular expression `</?(mark\|br\|b\|u\|i\|p\|span\|div\|sup\|sub\|a\|strong\|em)\b[^>]*>` or containing `&nbsp;` |
| **footer_residue_chunks** | chunks matching `Page \d+ of \d+` |
| **replacement_char_chunks** | chunks containing U+FFFD (the "?" diamond produced by a broken apostrophe or dash). Reported for information; Phase 1 is not required to fix it |
| **boilerplate_chunks** | see section 3 |
| **size_stats** | min, median, max of `len(text)` |

## 3. Boilerplate (line-based, automatic)

A **boilerplate line** is a non-empty line (after strip) that matches any rule below:

* **F** (footer): matches `^(Official Use Only\s*)?Page \d+ of \d+$`, or is exactly `Official Use Only`.
* **T** (table of contents): contains a run of 5 or more consecutive dots (`\.{5,}`), or is the heading text `TABLE OF CONTENTS` / `Table of Contents` (with any `#` or `*` markup).
* **I** (GEF template instruction): after removing leading `#`, `*`, `|`, `<mark>` markup and spaces, the line starts with one of these fixed openers (case-insensitive):
  `Provide a brief summary`, `Briefly describe the current situation`, `If so, please describe`, `For projects aiming to generate biodiversity benefits`, `(Please upload to the portal`, `Describe how the proposed interventions are aligned`, `Describe how any "Investment Mobilized"`, `Please provide geo-referenced`, `Please provide justification`, `Please refer to separate file`, `# GEF-8 PROJECT IDENTIFICATION FORM`, `GEF-8 PROJECT IDENTIFICATION FORM`.

A **boilerplate chunk** is a chunk where boilerplate lines make up at least 50% of the characters of its non-empty lines, ignoring Markdown separator rows (`|---|---|`) and blank lines.

Known weakness, stated up front: the opener list in rule I was written by reading the "before" chunks, so the "before" share is measured by the rules that the Phase 1 cleaning is also built from. A drop in this metric therefore shows that the cleaning removes what it was designed to remove. The independent measure of usefulness is the blind judgement in section 5.

## 4. Retrieval-level metrics (per question, top 5 results)

* **boilerplate_share_top5** = (number of the 75 retrieved results that are boilerplate chunks) / 75. Reported over all 15 questions, and over the 13 answerable ones.
* **duplicate_in_top5** = number of (question, result) pairs whose `norm(text)` equals the `norm(text)` of a higher-ranked result for the same question.
* **fragment_in_top5** = number of retrieved results that are fragments (section 2).
* **expected_doc_rank1** = for the 8 questions with a named document stem plus Q13 (9 questions), is the rank-1 result from that document. Informational only.
* **top1_score** per question, plus the two out-of-corpus questions' top-1 scores (no abstention exists; this is reported to show it).

## 5. Usefulness (human-style judgement, blind, no LLM)

Every retrieved chunk, for every question, is judged at one of three levels. The judge reads **the question and the full chunk text only**, with no document name, no score and no version label.

| Level | Meaning | Example (Q2, "How will the project reduce mercury use in artisanal gold mining?") |
|---|---|---|
| **useful** (2) | The chunk text itself states information that directly answers the question, or a main part of the answer, and can be read without the surrounding page | "The project will promote mercury-free processing technologies, train miners in gravity concentration and support formalisation ..." |
| **partial** (1) | On topic and contains some relevant information, but it does not answer the question on its own: only background, a heading with little text, a fragment, an answer buried in noise, or an answer to a neighbouring question | A paragraph about the scale of mercury use in the sector with no description of how the project reduces it |
| **not useful** (0) | Off topic, template instruction text, table of contents, a footer, a title page, or content from a project that cannot answer the question | "Provide a brief summary description of the project, including: (i) what is the problem ..." |

Rules for edge cases:

* For the unscoped questions (9 to 12) a chunk from **any** document can be useful if it answers the question for the project it belongs to.
* For the two NOT INDEXED questions (14, 15) no chunk can be useful or partial, because the answer is not in the index; both are scored 0 for every result and are excluded from the usefulness averages below. They are reported separately through their top-1 scores.
* Table text counts as useful if the needed cell values are readable from the chunk text alone.
* When unsure between two levels, choose the lower one.

Metrics from the judgements (answerable questions only, so 13 questions x 5 = 65 results per version):

* **useful_at_5** = mean over the 13 questions of (number of useful results in the top 5) / 5.
* **weighted_useful_at_5** = mean over the 13 questions of (sum of levels in the top 5) / (2 x 5), so partial counts as half.
* **questions_served** = number of the 13 questions with at least one useful result in the top 5.
* **first_useful_rank** = mean over the questions that have one of the rank of the first useful result.

### Blind protocol

1. After both indexes exist, the top-5 results for all 15 questions from "before" and "after" are written into **one file** in shuffled order. Each entry has only an anonymous id, the question and the chunk text. Version labels, document names, ranks and scores are in a separate key file that is not opened until the judging is finished.
2. The judge (Claude) labels every entry. The labels are saved before the key is opened.
3. The user labels 5 of the 15 questions, chosen at random with a fixed seed from the 13 answerable questions, from a separate file with the same anonymisation. Where the user's label differs from Claude's, the user's label is used. The raw agreement rate (exact 3-level match) and the binary agreement (useful versus not useful) are both reported, with Cohen's kappa for the 3-level labels.
4. Only after the labels are fixed is the key opened and the metrics computed.

If the identical chunk text appears in both versions for the same question, it is shown once and receives one label for both.

## 6. Reproducibility notes

* Chunk metrics are deterministic and take only chunk files as input.
* Retrieval results depend on the index and the local model; the model is `BAAI/bge-small-en-v1.5`, loaded through sentence-transformers on CPU, no API call.
* Numbers are only quoted in reports together with the file they came from (`reports/evidence/`).
