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


# ---- splitting: prefer sentence ends, keep table rows whole, avoid tiny pieces ------------------

def _check_cover(text, pieces):
    assert pieces[0][0] == 0 and pieces[-1][1] == len(text)
    assert all(a[1] == b[0] for a, b in zip(pieces, pieces[1:]))
    assert all(e - s <= s7.MAX_CHUNK_CHARS for s, e in pieces)


def test_cut_prefers_a_sentence_end_over_a_paragraph_break_after_an_unfinished_line():
    sentence = "The project will train miners in safer processing. "
    first = sentence * 24                                       # about 1200 characters, ends on a full stop
    unfinished = "A heading-like line without a full stop\n\n"
    rest = sentence * 40
    text = first + unfinished + rest
    pieces = s7._split_text_at_boundaries(text, s7.MAX_CHUNK_CHARS, s7.TARGET_CHUNK_CHARS)
    _check_cover(text, pieces)
    first_end = pieces[0][1]
    assert text[:first_end].rstrip().endswith("."), text[first_end - 30:first_end]


def test_table_rows_are_split_between_rows_never_inside_one():
    row = "Component: Component 1; Budget: 500,000; Outcome: Policy adopted and published"
    text = "\n".join(f"{row} number {i}" for i in range(80))          # one block, no punctuation, no blank lines
    pieces = s7._split_text_at_boundaries(text, s7.MAX_CHUNK_CHARS, s7.TARGET_CHUNK_CHARS)
    _check_cover(text, pieces)
    assert len(pieces) >= 2
    for s, e in pieces[:-1]:
        assert text[e - 1] == "\n" or text[e] == "\n" or text[e - 1].isdigit() and text[e] == "\n"
        assert not text[s:e].rstrip().endswith("number") and text[s:e].count("Component: ") == text[s:e].count("number")


def test_a_piece_is_not_cut_tiny_when_a_larger_boundary_exists():
    sentence = "Mercury use will be reduced through better practices. "
    text = "Short intro paragraph.\n\n" + sentence * 120               # a paragraph break after 24 characters
    pieces = s7._split_text_at_boundaries(text, s7.MAX_CHUNK_CHARS, s7.TARGET_CHUNK_CHARS)
    _check_cover(text, pieces)
    assert pieces[0][1] - pieces[0][0] >= s7.MIN_CHUNK_CHARS


def test_when_no_boundary_exists_it_still_cuts_at_the_maximum():
    text = "x" * (s7.MAX_CHUNK_CHARS * 2 + 10)
    pieces = s7._split_text_at_boundaries(text, s7.MAX_CHUNK_CHARS, s7.TARGET_CHUNK_CHARS)
    _check_cover(text, pieces)
    assert pieces[0][1] == s7.MAX_CHUNK_CHARS


# ---- exact duplicates -----------------------------------------------------------------------

def _chunk(cid, start, end, text):
    return {"chunk_id": cid, "text": text, "char_start": start, "char_end": end, "page_start": 1, "page_end": 1,
            "section_ids": ["1"]}


def test_exact_duplicate_span_is_dropped_first_copy_kept_and_range_reported():
    a, dup, b = "Same paragraph.\n\n" + BODY, "Same   paragraph.\n\n" + BODY, "Different text. " * 30
    full, bounds = text_for(a, b, dup)                        # the duplicate comes last
    spans = [span(*bounds[0], "1"), span(*bounds[1], "2"), span(*bounds[2], "3")]
    kept, dropped = s7.drop_duplicate_spans(spans, full)
    assert [s["anchor_section_id"] for s in kept] == ["1", "2"]
    assert dropped == [bounds[2]]


def test_similar_but_not_identical_text_is_kept():
    full, bounds = text_for("Alpha beta gamma.", "Alpha beta gamma!", "alpha beta gamma.")
    spans = [span(*bounds[i], str(i)) for i in range(3)]
    kept, dropped = s7.drop_duplicate_spans(spans, full)
    assert len(kept) == 3 and dropped == []


def test_validation_accepts_a_gap_only_when_it_is_a_recorded_duplicate():
    clean = {"full_text_char_count": 30, "pages": [{"page_number": 1}], "section_tree": [{"section_id": "1"}]}
    chunks = [_chunk("c0", 0, 10, "x" * 10), _chunk("c1", 20, 30, "y" * 10)]       # gap 10..20
    findings, outcome = s7.validate_chunks(chunks, clean)
    assert any(f["code"] == "CHUNK_COVERAGE_EXACT" for f in findings)
    findings, outcome = s7.validate_chunks(chunks, clean, [(10, 20)])
    assert not any(f["code"] == "CHUNK_COVERAGE_EXACT" for f in findings)
    findings, outcome = s7.validate_chunks(chunks, clean, [(10, 19)])                # recorded range too small
    assert any(f["code"] == "CHUNK_COVERAGE_EXACT" for f in findings)


def test_validation_accepts_two_consecutive_dropped_ranges_and_a_dropped_tail():
    clean = {"full_text_char_count": 40, "pages": [{"page_number": 1}], "section_tree": [{"section_id": "1"}]}
    chunks = [_chunk("c0", 0, 10, "x" * 10), _chunk("c1", 30, 35, "y" * 5)]
    findings, _ = s7.validate_chunks(chunks, clean, [(10, 20), (20, 30), (35, 40)])
    assert not any(f["code"] == "CHUNK_COVERAGE_EXACT" for f in findings)


# ---- end to end: a repeated section is dropped and the document still validates ------------------

def test_chunk_document_drops_a_repeated_section_and_still_passes_validation(tmp_path, monkeypatch):
    import json
    from src.ingestion_types import ManifestRecord, DocumentStatus
    monkeypatch.setattr(s7, "CHUNKS_DIR", tmp_path / "chunks")
    body = "The same repeated section describes the project approach in detail. " * 12
    page1 = "# Approach\n\n" + body + "\n\n"
    page2 = "# Approach\n\n" + body + "\n\n"                       # identical text, so identical chunk
    page3 = "# Results\n\n" + "A different section reports the project results clearly. " * 14 + "\n\n"
    pages, cursor = [], 0
    for i, txt in enumerate([page1, page2, page3], start=1):
        pages.append({"page_number": i, "text": txt, "char_start": cursor, "char_end": cursor + len(txt),
                      "is_excluded": False, "headings": []})
        cursor += len(txt)
    metadata = {"classification": {"category": "climate", "doc_type": None}, "title": "T"}
    section_tree = [
        {"section_id": "1", "section_level": 1, "parent_section": None, "title": "Approach", "start_page": 1},
        {"section_id": "2", "section_level": 1, "parent_section": None, "title": "Approach", "start_page": 2},
        {"section_id": "3", "section_level": 1, "parent_section": None, "title": "Results", "start_page": 3},
    ]
    clean = {"doc_id": "doc_dup", "full_text_char_count": cursor, "section_tree": section_tree, "pages": pages}
    record = ManifestRecord(doc_id="doc_dup", category="climate", status=DocumentStatus.READY_FOR_CHUNKING,
                            artifact_paths={})
    s7.chunk_document(record, clean, metadata)
    assert record.status == DocumentStatus.READY_FOR_CHUNKING, record.error_code
    report = json.loads((tmp_path / "chunks" / "doc_dup" / "chunk_validation_report.json").read_text(encoding="utf-8"))
    chunks = json.loads((tmp_path / "chunks" / "doc_dup" / "chunks.json").read_text(encoding="utf-8"))["chunks"]
    assert len(report["dropped_duplicate_ranges"]) == 1
    assert report["overall_status"] in ("PASS", "WARNING")
    assert len(chunks) == 2
