"""Answer-level abstention: the model replies with the single token NOT_IN_CONTEXT when the retrieved excerpts do not contain
the requested detail. This module reads that reply. It never calls a model.

decision(text) ->
  "NOT_IN_CONTEXT"  the reply is the sentinel and nothing else (case, surrounding quotes/backticks/punctuation/whitespace ignored)
  "MIXED"           the sentinel appears together with other text (the model broke the output contract)
  "EMPTY"           no text at all (a failed or blocked generation is not a refusal)
  "ANSWERED"        anything else
Only "NOT_IN_CONTEXT" counts as an abstention. MIXED is treated as an answer (it is shown to the user) and is counted separately
so a prompt that produces it is visible in the evaluation.
"""
import re
from typing import Dict

SENTINEL = "NOT_IN_CONTEXT"
_STRIP = " \t\r\n\"'`*_.,;:!()[]{}<>"
_SENTINEL_ANYWHERE = re.compile(r"NOT[_\s-]?IN[_\s-]?CONTEXT", re.IGNORECASE)


def decision(response_text) -> str:
    text = (response_text or "").strip()
    if not text:
        return "EMPTY"
    core = text.strip(_STRIP)
    if core.upper() == SENTINEL:
        return "NOT_IN_CONTEXT"
    if _SENTINEL_ANYWHERE.search(text):
        return "MIXED"
    return "ANSWERED"


def is_abstention(response_text) -> bool:
    return decision(response_text) == "NOT_IN_CONTEXT"


def describe(response_text) -> Dict[str, object]:
    d = decision(response_text)
    return {"decision": d, "abstained": d == "NOT_IN_CONTEXT"}
