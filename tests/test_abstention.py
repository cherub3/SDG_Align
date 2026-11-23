"""Answer-level abstention parser (Phase 3 step 4). Every case is a reply the model could actually produce."""
import pytest

from scripts.abstention import SENTINEL, decision, describe, is_abstention


@pytest.mark.parametrize("text", [
    "NOT_IN_CONTEXT", "not_in_context", "  NOT_IN_CONTEXT\n", "NOT_IN_CONTEXT.", "`NOT_IN_CONTEXT`", "**NOT_IN_CONTEXT**",
    '"NOT_IN_CONTEXT"', "Not_In_Context!",
])
def test_the_bare_sentinel_is_an_abstention(text):
    assert decision(text) == "NOT_IN_CONTEXT"
    assert is_abstention(text) is True


@pytest.mark.parametrize("text", [
    "NOT_IN_CONTEXT The salary is 500 XAF.", "The salary is unknown. NOT_IN_CONTEXT", "Answer: not in context, but probably 5",
])
def test_the_sentinel_with_other_text_is_mixed_and_not_an_abstention(text):
    assert decision(text) == "MIXED"
    assert is_abstention(text) is False


@pytest.mark.parametrize("text", [None, "", "   \n\t"])
def test_no_text_is_empty_never_a_refusal(text):
    assert decision(text) == "EMPTY"
    assert is_abstention(text) is False


@pytest.mark.parametrize("text", [
    "More than 75% of the elephants were lost.", "The context does not mention a salary.", "Not applicable in this context window.",
])
def test_ordinary_answers_and_free_text_refusals_are_answered(text):
    assert decision(text) == "ANSWERED"


def test_describe_and_constant():
    assert SENTINEL == "NOT_IN_CONTEXT"
    assert describe("NOT_IN_CONTEXT") == {"decision": "NOT_IN_CONTEXT", "abstained": True}
    assert describe("42 hectares") == {"decision": "ANSWERED", "abstained": False}
