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


# ---- table of contents -------------------------------------------------------------------

DOTS = "." * 60


def test_toc_block_is_removed_including_split_outline_markers_and_heading():
    text = "\n".join([
        "###### **TABLE OF CONTENTS**", "",
        f"|**GENERAL PROJECT INFORMATION {DOTS}3**|", "|---|",
        f"|Project Summary{DOTS}4|",
        "|B.", f"PROJECT DESCRIPTION{DOTS}12",
        "", "Real paragraph that must stay.",
    ])
    out = s4.remove_table_of_contents(text)
    assert "TABLE OF CONTENTS" not in out and "PROJECT DESCRIPTION" not in out and "|B." not in out
    assert "Project Summary" not in out
    assert "Real paragraph that must stay." in out


def test_a_single_dotted_line_in_prose_is_not_a_toc():
    text = f"A sentence trailing off{DOTS} and then more words.\n\nNext paragraph."
    assert s4.remove_table_of_contents(text) == text


def test_toc_threshold_is_exactly_three_leader_lines():
    two = f"a{DOTS}1\nb{DOTS}2\nkeep"
    three = f"a{DOTS}1\nb{DOTS}2\nc{DOTS}3\nkeep"
    assert s4.remove_table_of_contents(two) == two
    assert s4.remove_table_of_contents(three) == "keep"


# ---- GEF template instructions -------------------------------------------------------------

def test_instruction_paragraphs_are_removed_and_real_content_kept():
    text = "\n".join([
        "###### Project Summary", "",
        "Provide a brief summary description of the project, including: (i) the problem (max. 250 words, approximately 1/2 page)", "",
        "This project will protect elephants in Boumba Bek National Park.", "",
        "###### **<mark>Provide a brief summary and list of names and dates of consultations</mark>**",
        "Please provide justification", "Yes",
    ])
    out = s4.remove_template_instructions(text)
    assert "Provide a brief summary description" not in out
    assert "Please provide justification" not in out
    assert "Provide a brief summary and list" not in out         # also when wrapped in heading markup
    assert "###### Project Summary" in out                        # the heading stays
    assert "This project will protect elephants" in out
    assert "Yes" in out


def test_a_max_words_hint_marks_unlisted_instructions_too():
    text = "Explain the theory of change of the project and the assumptions behind it (max. 500 words)\nIn practice the project works through three components."
    out = s4.remove_template_instructions(text)
    assert "Explain the theory of change" not in out
    assert "three components" in out


def test_heading_is_kept_when_instruction_text_follows_it_on_the_same_line():
    line = "C. ALIGNMENT WITH GEF-8 PROGRAMMING STRATEGIES AND COUNTRY/REGIONAL PRIORITIES Describe how the proposed interventions are aligned with GEF-8 strategies"
    out = s4.remove_template_instructions(line)
    assert out == "C. ALIGNMENT WITH GEF-8 PROGRAMMING STRATEGIES AND COUNTRY/REGIONAL PRIORITIES"


def test_ordinary_sentences_that_use_the_same_verbs_are_not_removed():
    text = ("The project will provide a brief summary of results each year.\n"
            "Partners describe how the project is aligned with national plans in the annex.")
    assert s4.remove_template_instructions(text) == text           # only lines that START with an opener go


def test_short_line_with_a_max_words_hint_is_left_alone():
    text = "Summary (max. 250 words)"          # 24 chars: too short to be a template paragraph
    assert s4.remove_template_instructions(text) == text
