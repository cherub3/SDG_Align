"""Phase 1 cleaning rules in stage 4: page markers and HTML residue."""
import scripts.stage4_cleaning as s4


def test_page_marker_lines_are_removed_but_prose_mentioning_a_page_is_kept():
    text = "Intro line\n\nOfficial Use Only Page 3 of 31\n\nSee Page 3 of 31 for details.\nOfficial Use Only\nPage 12 of 40"
    out = s4.remove_page_markers(text)
    assert "Official Use Only" not in out
    assert "Page 12 of 40" not in out
    assert "See Page 3 of 31 for details." in out          # a sentence is not a marker
    assert out.startswith("Intro line")


def test_br_becomes_a_space_and_inline_tags_keep_their_content():
    text = "|A|B|\n|---|---|\n|Civil<br>society<br/>groups|<mark>High</mark> risk|\n<u>Steering</u> committee&nbsp;meets &amp; reports"
    out = s4.strip_html_markup(text)
    assert "<" not in out and "&nbsp;" not in out and "&amp;" not in out
    assert "|Civil society groups|High risk|" in out
    assert "Steering committee meets & reports" in out


def test_paragraph_tag_splits_prose_but_never_a_table_row():
    prose = s4.strip_html_markup("first<p>second")
    assert prose == "first\nsecond"
    row = s4.strip_html_markup("|a<p>b|c|")
    assert row == "|a b|c|"                                     # still one line


def test_text_with_a_comparison_is_not_treated_as_markup():
    text = "Values where x < 5 and y > 3 stay as written."
    assert s4.strip_html_markup(text) == text


def test_build_clean_text_applies_both_rules_and_keeps_offsets_consistent():
    raw = {"doc_id": "doc_x", "pages": [
        {"page_number": 1, "raw_text": "# Title\n\nSome <mark>important</mark> text.\n\nOfficial Use Only Page 1 of 2\n", "excluded": False},
        {"page_number": 2, "raw_text": "More text<br>here.\n\nOfficial Use Only Page 2 of 2\n", "excluded": False},
    ]}
    clean = s4.build_clean_text(raw)
    joined = "".join(p["text"] for p in clean["pages"])
    assert "Page 1 of 2" not in joined and "<mark>" not in joined and "<br>" not in joined
    assert "Some important text." in joined and "More text here." in joined
    assert clean["full_text_char_count"] == len(joined)
    for p in clean["pages"]:
        assert p["char_end"] - p["char_start"] == len(p["text"])
