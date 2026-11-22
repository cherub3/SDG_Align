"""Phase 1 chunk-quality rules in stage 7: heading-only merge, forward merge, exact-duplicate drop,
sentence-boundary cuts."""
from scripts import stage7_chunking as s7


def span(start, end, anchor, ancestors=None, appendix=False, degenerate=False):
    return {
        "char_start": start, "char_end": end, "section_ids": [anchor], "anchor_section_id": anchor,
        "ancestor_section_ids": ancestors or [anchor], "heading_path": [anchor],
        "degenerate": degenerate, "is_appendix": appendix, "is_references": False,
        "page_start": 1, "page_end": 1,
    }


def text_for(*pieces):
    """Concatenate pieces and return (full_text, list of (start, end))."""
    pos, out, bounds = "", [], []
    for piece in pieces:
        bounds.append((len(pos), len(pos) + len(piece)))
        pos += piece
    return pos, bounds


BODY = "This is a real paragraph of project text. " * 20     # about 840 characters


def test_heading_only_span_merges_forward_even_across_a_top_level_branch():
    full, b = text_for("#### ANNEX A: FINANCING TABLES\n\n", BODY)
    spans = [span(*b[0], "A", ["A"]), span(*b[1], "B", ["B"])]
    merged = s7.merge_undersized_spans(spans, full)
    assert len(merged) == 1
    m = merged[0]
    assert (m["char_start"], m["char_end"]) == (0, len(full))
    assert m["anchor_section_id"] == "B" and m["ancestor_section_ids"] == ["B"]   # labelled as the content
    assert m["section_ids"] == ["A", "B"]


def test_without_full_text_a_cross_branch_heading_is_left_alone():
    full, b = text_for(BODY, "#### ANNEX A: FINANCING TABLES\n\n", BODY)
    merged = s7.merge_undersized_spans([span(*b[0], "Z", ["Z"]), span(*b[1], "A", ["A"]), span(*b[2], "B", ["B"])])
    assert len(merged) == 3                         # old behaviour is unchanged when no text is given


def test_consecutive_heading_only_spans_collapse_into_the_content_after_them():
    full, b = text_for("# PART ONE\n\n", "## Background\n\n", BODY)
    spans = [span(*b[0], "1", ["1"]), span(*b[1], "1.1", ["1"]), span(*b[2], "1.2", ["1"])]
    merged = s7.merge_undersized_spans(spans, full)
    assert len(merged) == 1 and merged[0]["char_end"] - merged[0]["char_start"] == len(full)


def test_heading_only_span_stays_in_front_of_its_content_not_glued_to_the_previous_section():
    full, b = text_for(BODY, "### Output 1.2: Monitoring the plan\n\n", BODY)
    spans = [span(*b[0], "1.1", ["1"]), span(*b[1], "1.2", ["1"]), span(*b[2], "1.2x", ["1"])]
    merged = s7.merge_undersized_spans(spans, full)
    assert len(merged) == 2
    assert merged[1]["char_start"] == b[1][0]        # the heading starts the second chunk


def test_heading_merge_respects_the_maximum_chunk_size():
    heading = "#### ANNEX A\n\n"
    big = "x" * (s7.MAX_CHUNK_CHARS - 5)
    full, b = text_for(heading, big)
    merged = s7.merge_undersized_spans([span(*b[0], "A", ["A"]), span(*b[1], "B", ["B"])], full)
    assert len(merged) == 2
    assert all(m["char_end"] - m["char_start"] <= s7.MAX_CHUNK_CHARS for m in merged)


def test_heading_merge_never_crosses_an_appendix_boundary():
    full, b = text_for("#### Closing heading\n\n", BODY)
    merged = s7.merge_undersized_spans([span(*b[0], "1", ["1"]), span(*b[1], "2", ["2"], appendix=True)], full)
    assert len(merged) == 2


def test_an_all_caps_title_counts_as_heading_only_but_a_short_answer_does_not():
    full, b = text_for("PROJECT OUTLINE\n\n", BODY, "Yes\n\n", BODY)
    spans = [span(*b[0], "1", ["1"]), span(*b[1], "2", ["2"]), span(*b[2], "3", ["3"]), span(*b[3], "4", ["4"])]
    merged = s7.merge_undersized_spans(spans, full)
    # the title joins the content after it; the short "Yes" answer is not a heading and
    # may not cross a top-level branch, so it stays separate
    assert [m["char_start"] for m in merged] == [0, b[2][0], b[3][0]]


def test_remaining_small_span_merges_forward_into_the_same_branch():
    full, b = text_for("x" * (s7.MAX_CHUNK_CHARS - 10), "short tail section.\n\n", BODY)
    # span 0 is full-size, span 1 is small but cannot merge backward (would exceed MAX)
    # and span 2 is in the same branch, so it merges forward
    spans = [span(*b[0], "1", ["1"]), span(*b[1], "2", ["1"]), span(*b[2], "3", ["1"])]
    merged = s7.merge_undersized_spans(spans, full)
    assert len(merged) == 2
    assert merged[1]["char_start"] == b[1][0] and merged[1]["char_end"] == len(full)
    assert all(m["char_end"] - m["char_start"] <= s7.MAX_CHUNK_CHARS for m in merged)
