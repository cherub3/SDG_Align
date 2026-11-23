"""Phase 3.5: groundedness 0 / quality 0.11 on a correct answer is the metric being strict, not a defect.
Stage 14 cites a sentence when >= 60% of its character 5-grams occur in a chunk. Stage 15 calls it GROUNDED only when >= 80% of
the sentence is ONE contiguous verbatim run. A faithful paraphrase is cited but scores 0. These tests pin that behaviour, so the
UI wording ("verbatim overlap") stays honest. See reports/PHASE_3_5_REPORT.md."""
from scripts import stage14_citation_extraction as s14
from scripts import stage15_groundedness_validation as s15
from scripts.stage16_answer_quality_evaluation import compute_answer_quality_score

CHUNK = ("Between 2011 and 2015, Boumba Bek National Park lost over 75% of its elephants, "
         "driven by poaching, unsustainable hunting, deforestation and weak management of the protected area.")
PARAPHRASE = "Boumba Bek National Park lost over 75% of its elephants between 2011 and 2015 because of poaching and weak management."
VERBATIM = "Between 2011 and 2015, Boumba Bek National Park lost over 75% of its elephants"
BLOCK = {"context_block_id": "b1", "chunk_id": "c1", "doc_id": "d1", "text": CHUNK}


def test_paraphrase_is_cited_but_not_grounded():
    cited = s14.match_span_to_blocks({"text": PARAPHRASE}, [BLOCK], s14.DEFAULT_CITATION_MATCH_THRESHOLD)
    assert cited, "stage 14 should cite a faithful paraphrase"
    assert s15.compute_groundedness_overlap(PARAPHRASE, CHUNK) < s15.DEFAULT_GROUNDEDNESS_THRESHOLD


def test_verbatim_copy_is_grounded():
    assert s15.compute_groundedness_overlap(VERBATIM, CHUNK) >= s15.DEFAULT_GROUNDEDNESS_THRESHOLD


def test_cited_paraphrase_scores_the_citation_weight_only():
    # groundedness 0, every sentence cited -> 0.7*0 + 0.3*1 = 0.3 (the 0.3 seen in the eval rows)
    assert abs(compute_answer_quality_score(0.0, 1.0) - 0.3) < 1e-9
