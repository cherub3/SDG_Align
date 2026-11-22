import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import gold_common as gc  # noqa: E402
import freeze_gold as fg  # noqa: E402


def test_overlap():
    assert gc.overlap(0, 10, 5, 20) == 5
    assert gc.overlap(0, 5, 5, 10) == 0


def test_is_hit_threshold_is_min_of_50_and_half_span():
    assert gc.is_hit(0, 50, 0, 200)           # 50 chars overlap on long span
    assert not gc.is_hit(0, 49, 0, 200)
    assert gc.is_hit(0, 20, 0, 40)            # 50% of a 40-char span = 20
    assert not gc.is_hit(0, 19, 0, 40)
    assert not gc.is_hit(100, 200, 0, 40)


def test_longest_shared_run():
    q = "How many hectares will be restored?"
    assert gc.longest_shared_run(q, ["It will restore 5000 hectares"]) == 1
    assert gc.longest_shared_run("the total area restored", ["the total area restored in 2030"]) == 4


def test_split_is_seeded_stratified_and_stable():
    items = [{"qid": f"Q{i:03d}", "type": "single_fact"} for i in range(10)]
    items += [{"qid": f"Q{i:03d}", "type": "unanswerable", "kind": "near_miss"} for i in range(10, 15)]
    a, b = fg.make_split(items), fg.make_split(list(reversed(items)))
    assert a == b
    assert sum(v == "dev" for v in a.values()) == 3          # 2 of 10 + 1 of 5
    assert sum(v == "dev" for k, v in a.items() if k < "Q010") == 2
    assert fg.make_split(items, seed=1) != a
