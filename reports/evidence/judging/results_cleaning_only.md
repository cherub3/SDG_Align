# Cleaning-only comparison (tools/compute_cleaning_only.py)

after_5doc = after pipeline, index of the original 5 documents only (jaguar excluded). after_6doc = the full 6-document result.

## Labels: final (headline)

| metric (13 answerable questions) | before | after_5doc (cleaning only) | after_6doc |
|---|---|---|---|
| useful_at_5 | 0.3385 | 0.3231 | 0.3385 |
| useful_or_partial_at_5 | 0.6 | 0.7231 | 0.7077 |
| mean_score_0_to_2 | 0.9385 | 1.0462 | 1.0462 |
| questions_served | 7 | 8 | 8 |
| counts_UPN_of_65 | [22, 17, 26] | [21, 26, 18] | [22, 24, 19] |

before vs after_5doc (headline): wins / losses / ties 7 / 3 / 3; mean diff 0.1077; sign test p = 0.3438; exact Wilcoxon p = 0.3223

before vs after_6doc: wins / losses / ties 7 / 4 / 2; mean diff 0.1077; sign test p = 0.5488; exact Wilcoxon p = 0.4346

| Q | before | after_5doc | diff |
|---|---|---|---|
| 1 | 0.8 | 0.8 | 0.0 |
| 2 | 1.6 | 1.4 | -0.2 |
| 3 | 0.2 | 0.2 | 0.0 |
| 4 | 1.2 | 1.4 | 0.2 |
| 5 | 0.6 | 1.0 | 0.4 |
| 6 | 0.6 | 0.8 | 0.2 |
| 7 | 0.2 | 0.4 | 0.2 |
| 8 | 0.2 | 0.4 | 0.2 |
| 9 | 2.0 | 1.6 | -0.4 |
| 10 | 0.8 | 1.6 | 0.8 |
| 11 | 2.0 | 2.0 | 0.0 |
| 12 | 2.0 | 1.8 | -0.2 |
| 13 | 0.0 | 0.2 | 0.2 |

## Labels: judge1_frozen

| metric (13 answerable questions) | before | after_5doc (cleaning only) | after_6doc |
|---|---|---|---|
| useful_at_5 | 0.3385 | 0.3231 | 0.3385 |
| useful_or_partial_at_5 | 0.5846 | 0.7385 | 0.7231 |
| mean_score_0_to_2 | 0.9231 | 1.0615 | 1.0615 |
| questions_served | 7 | 8 | 8 |
| counts_UPN_of_65 | [22, 16, 27] | [21, 27, 17] | [22, 25, 18] |

before vs after_5doc (headline): wins / losses / ties 8 / 3 / 2; mean diff 0.1385; sign test p = 0.2266; exact Wilcoxon p = 0.1895

before vs after_6doc: wins / losses / ties 8 / 3 / 2; mean diff 0.1385; sign test p = 0.2266; exact Wilcoxon p = 0.2402

| Q | before | after_5doc | diff |
|---|---|---|---|
| 1 | 0.6 | 0.6 | 0.0 |
| 2 | 1.6 | 1.4 | -0.2 |
| 3 | 0.2 | 0.6 | 0.4 |
| 4 | 1.2 | 1.4 | 0.2 |
| 5 | 0.6 | 1.0 | 0.4 |
| 6 | 0.6 | 0.8 | 0.2 |
| 7 | 0.2 | 0.4 | 0.2 |
| 8 | 0.2 | 0.4 | 0.2 |
| 9 | 2.0 | 1.6 | -0.4 |
| 10 | 0.8 | 1.6 | 0.8 |
| 11 | 2.0 | 2.0 | 0.0 |
| 12 | 2.0 | 1.8 | -0.2 |
| 13 | 0.0 | 0.2 | 0.2 |

## Labels: judge2

| metric (13 answerable questions) | before | after_5doc (cleaning only) | after_6doc |
|---|---|---|---|
| useful_at_5 | 0.3538 | 0.3538 | 0.3692 |
| useful_or_partial_at_5 | 0.6308 | 0.7231 | 0.7077 |
| mean_score_0_to_2 | 0.9846 | 1.0769 | 1.0769 |
| questions_served | 9 | 9 | 9 |
| counts_UPN_of_65 | [23, 18, 24] | [23, 24, 18] | [24, 22, 19] |

before vs after_5doc (headline): wins / losses / ties 6 / 2 / 5; mean diff 0.0923; sign test p = 0.2891; exact Wilcoxon p = 0.3906

before vs after_6doc: wins / losses / ties 6 / 3 / 4; mean diff 0.0923; sign test p = 0.5078; exact Wilcoxon p = 0.5312

| Q | before | after_5doc | diff |
|---|---|---|---|
| 1 | 0.8 | 0.8 | 0.0 |
| 2 | 1.4 | 1.4 | 0.0 |
| 3 | 0.2 | 0.2 | 0.0 |
| 4 | 1.2 | 1.4 | 0.2 |
| 5 | 1.2 | 1.2 | 0.0 |
| 6 | 1.0 | 1.0 | 0.0 |
| 7 | 0.2 | 0.4 | 0.2 |
| 8 | 0.2 | 0.4 | 0.2 |
| 9 | 2.0 | 1.6 | -0.4 |
| 10 | 0.8 | 1.6 | 0.8 |
| 11 | 1.8 | 2.0 | 0.2 |
| 12 | 2.0 | 1.8 | -0.2 |
| 13 | 0.0 | 0.2 | 0.2 |

## Automatic metrics (frozen rules)

| metric | before | after_5doc | after_6doc |
|---|---|---|---|
| boilerplate_share_top5_all15 | 0.0267 | 0.0 | 0.0 |
| fragments_in_top5 | 3 | 2 | 3 |
| duplicates_in_top5 | 0 | 0 | 0 |
| expected_doc_rank1 | 9/9 | 8/9 | 8/9 |
