# Phase 1 results (computed by tools/compute_phase1_results.py)

## Labels: final (headline)

| metric (13 answerable questions) | before | after |
|---|---|---|
| useful_at_5 | 0.3385 | 0.3385 |
| useful_or_partial_at_5 | 0.6 | 0.7077 |
| mean_score_0_to_2 | 0.9385 | 1.0462 |
| weighted_useful_at_5_frozen | 0.4692 | 0.5231 |
| questions_served | 7 | 8 |
| first_useful_rank_mean | 1.714 | 1.375 |
| counts_UPN_of_65 | [22, 17, 26] | [22, 24, 19] |

Per-question wins / losses / ties (after vs before, mean score): 7 / 4 / 2; mean difference 0.1077; sign test p = 0.5488; exact Wilcoxon p = 0.4346

| Q | before | after | diff |
|---|---|---|---|
| 1 | 0.8 | 0.8 | 0.0 |
| 2 | 1.6 | 1.4 | -0.2 |
| 3 | 0.2 | 0.0 | -0.2 |
| 4 | 1.2 | 1.4 | 0.2 |
| 5 | 0.6 | 1.0 | 0.4 |
| 6 | 0.6 | 0.8 | 0.2 |
| 7 | 0.2 | 0.4 | 0.2 |
| 8 | 0.2 | 0.4 | 0.2 |
| 9 | 2.0 | 1.6 | -0.4 |
| 10 | 0.8 | 1.8 | 1.0 |
| 11 | 2.0 | 2.0 | 0.0 |
| 12 | 2.0 | 1.8 | -0.2 |
| 13 | 0.0 | 0.2 | 0.2 |

## Labels: judge1_frozen

| metric (13 answerable questions) | before | after |
|---|---|---|
| useful_at_5 | 0.3385 | 0.3385 |
| useful_or_partial_at_5 | 0.5846 | 0.7231 |
| mean_score_0_to_2 | 0.9231 | 1.0615 |
| weighted_useful_at_5_frozen | 0.4615 | 0.5308 |
| questions_served | 7 | 8 |
| first_useful_rank_mean | 1.714 | 1.375 |
| counts_UPN_of_65 | [22, 16, 27] | [22, 25, 18] |

Per-question wins / losses / ties (after vs before, mean score): 8 / 3 / 2; mean difference 0.1385; sign test p = 0.2266; exact Wilcoxon p = 0.2402

| Q | before | after | diff |
|---|---|---|---|
| 1 | 0.6 | 0.6 | 0.0 |
| 2 | 1.6 | 1.4 | -0.2 |
| 3 | 0.2 | 0.4 | 0.2 |
| 4 | 1.2 | 1.4 | 0.2 |
| 5 | 0.6 | 1.0 | 0.4 |
| 6 | 0.6 | 0.8 | 0.2 |
| 7 | 0.2 | 0.4 | 0.2 |
| 8 | 0.2 | 0.4 | 0.2 |
| 9 | 2.0 | 1.6 | -0.4 |
| 10 | 0.8 | 1.8 | 1.0 |
| 11 | 2.0 | 2.0 | 0.0 |
| 12 | 2.0 | 1.8 | -0.2 |
| 13 | 0.0 | 0.2 | 0.2 |

## Labels: judge2

| metric (13 answerable questions) | before | after |
|---|---|---|
| useful_at_5 | 0.3538 | 0.3692 |
| useful_or_partial_at_5 | 0.6308 | 0.7077 |
| mean_score_0_to_2 | 0.9846 | 1.0769 |
| weighted_useful_at_5_frozen | 0.4923 | 0.5385 |
| questions_served | 9 | 9 |
| first_useful_rank_mean | 1.889 | 1.222 |
| counts_UPN_of_65 | [23, 18, 24] | [24, 22, 19] |

Per-question wins / losses / ties (after vs before, mean score): 6 / 3 / 4; mean difference 0.0923; sign test p = 0.5078; exact Wilcoxon p = 0.5312

| Q | before | after | diff |
|---|---|---|---|
| 1 | 0.8 | 0.8 | 0.0 |
| 2 | 1.4 | 1.4 | 0.0 |
| 3 | 0.2 | 0.0 | -0.2 |
| 4 | 1.2 | 1.4 | 0.2 |
| 5 | 1.2 | 1.2 | 0.0 |
| 6 | 1.0 | 1.0 | 0.0 |
| 7 | 0.2 | 0.4 | 0.2 |
| 8 | 0.2 | 0.4 | 0.2 |
| 9 | 2.0 | 1.6 | -0.4 |
| 10 | 0.8 | 1.8 | 1.0 |
| 11 | 1.8 | 2.0 | 0.2 |
| 12 | 2.0 | 1.8 | -0.2 |
| 13 | 0.0 | 0.2 | 0.2 |

## Labels: judge1_asis (deviation)

| metric (13 answerable questions) | before | after |
|---|---|---|
| useful_at_5 | 0.3077 | 0.3385 |
| useful_or_partial_at_5 | 0.5538 | 0.7231 |
| mean_score_0_to_2 | 0.8615 | 1.0615 |
| weighted_useful_at_5_frozen | 0.4308 | 0.5308 |
| questions_served | 6 | 8 |
| first_useful_rank_mean | 1.833 | 1.375 |
| counts_UPN_of_65 | [20, 16, 29] | [22, 25, 18] |

Per-question wins / losses / ties (after vs before, mean score): 10 / 2 / 1; mean difference 0.2; sign test p = 0.0386; exact Wilcoxon p = 0.0591

| Q | before | after | diff |
|---|---|---|---|
| 1 | 0.4 | 0.6 | 0.2 |
| 2 | 1.2 | 1.4 | 0.2 |
| 3 | 0.2 | 0.4 | 0.2 |
| 4 | 1.2 | 1.4 | 0.2 |
| 5 | 0.6 | 1.0 | 0.4 |
| 6 | 0.4 | 0.8 | 0.4 |
| 7 | 0.2 | 0.4 | 0.2 |
| 8 | 0.2 | 0.4 | 0.2 |
| 9 | 2.0 | 1.6 | -0.4 |
| 10 | 0.8 | 1.8 | 1.0 |
| 11 | 2.0 | 2.0 | 0.0 |
| 12 | 2.0 | 1.8 | -0.2 |
| 13 | 0.0 | 0.2 | 0.2 |

## Automatic metrics (frozen rules)

| metric | before | after |
|---|---|---|
| boilerplate_share_top5_all15 | 0.0267 | 0.0 |
| boilerplate_share_top5_answerable13 | 0.0154 | 0.0 |
| fragments_in_top5 | 3 | 3 |
| duplicates_in_top5 | 0 | 0 |
| expected_doc_rank1 | 9/9 | 8/9 |

## Unanswerable questions (14, 15): top-1 that came back (no abstention exists)

* before Q14: top-1 score 0.575 from ecuador_marine_biodiversity: '###### _<u>Indicators:</u>_\n\n_CI 4.1: 60,312 hectares of landscapes under improved managem'
* before Q15: top-1 score 0.684 from cameroon_biodiversity_iplc_conservation: '##### **Project description**\n\nThis section asks for a theory of change as part of a joine'
* after Q14: top-1 score 0.6084 from ecuador_jaguar_landscape_connectivity: '40. Output 1.1.1: Management plans revised and updated, and patrolling and monitoring capa'
* after Q15: top-1 score 0.6807 from cameroon_biodiversity_iplc_conservation: '##### B. PROJECT DESCRIPTION\n\n##### **Project description**\n\nThis section asks for a theor'
