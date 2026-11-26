"""Test doubles for the ADK path. No network: the model is a scripted BaseLlm and retrieval is a canned function."""
import asyncio
from typing import Any, Dict, List, Optional

from google.adk.models import BaseLlm, LlmResponse
from google.genai import types


def call(name: str, **args) -> Dict[str, Any]:
    return {"call": name, "args": args}


def usage(i: int = 100, o: int = 10, thoughts: int = 0):
    return types.GenerateContentResponseUsageMetadata(
        prompt_token_count=i, candidates_token_count=o, total_token_count=i + o + thoughts, thoughts_token_count=thoughts or None)


class ScriptedLlm(BaseLlm):
    """Returns the scripted items in call order. An item is a string (text reply), call(...) (one function call), a list of
    call(...) (parallel function calls), or an Exception (raised). Every request the agents send is kept in `requests`."""
    model: str = "scripted-test-model"
    script: List[Any] = []
    requests: List[Any] = []
    delay_s: float = 0.0
    tokens_in: int = 100
    tokens_out: int = 10
    tokens_thought: int = 0

    async def generate_content_async(self, llm_request, stream: bool = False):
        self.requests.append(llm_request)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if not self.script:
            raise AssertionError("scripted model called more often than the test scripted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        items = item if isinstance(item, list) else [item]
        parts = []
        for it in items:
            if isinstance(it, dict):
                parts.append(types.Part(function_call=types.FunctionCall(name=it["call"], args=it["args"])))
            else:
                parts.append(types.Part(text=it))
        yield LlmResponse(content=types.Content(role="model", parts=parts),
                          usage_metadata=usage(self.tokens_in, self.tokens_out, self.tokens_thought))

    def system_text(self, n: int) -> str:
        si = self.requests[n].config.system_instruction
        return si if isinstance(si, str) else str(si)


def make_chunk(cid: str, rank: int, text: str = "", doc: str = "doc_a") -> Dict[str, Any]:
    return {"rank": rank, "score": 1.0 / rank, "index_fingerprint": "fp", "embedding_id": f"e_{cid}", "chunk_id": cid, "doc_id": doc,
            "text": text or f"Text of chunk {cid}. The project covers {cid}.", "heading_path": ["H"], "section_ids": ["s1"],
            "page_start": 1, "page_end": 1, "category": "c", "doc_type": "proposal", "title": "Title A"}


class FakeRetrieve:
    """retrieve(request) -> the same shape as scripts.stage10_retrieval.retrieve. `by_query` maps a query to chunk ids."""

    def __init__(self, by_query: Optional[Dict[str, List[str]]] = None, default: Optional[List[str]] = None):
        self.by_query = by_query or {}
        self.default = default or ["c1", "c2", "c3"]
        self.requests: List[Dict[str, Any]] = []

    def __call__(self, request: Dict[str, Any]) -> Dict[str, Any]:
        self.requests.append(request)
        ids = self.by_query.get(request["query"], self.default)
        return {"status": "SUCCESS", "results": [make_chunk(c, i + 1) for i, c in enumerate(ids)]}


PASS = '{"verdict": "PASS", "unsupported": []}'


def revise(sentence: str = "Unsupported claim.") -> str:
    return '{"verdict": "REVISE", "unsupported": [{"sentence": "%s", "reason": "not in the cited chunk"}]}' % sentence
