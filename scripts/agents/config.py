"""Caps and settings of the ADK path, and the hash that freezes them before a scored run."""
import dataclasses
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

ENV_FLAG = "AGENTS_ENABLED"
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass(frozen=True)
class AgentsConfig:
    max_llm_calls: int = 6            # hard cap per question; by construction the maximum used is 5
    max_searches: int = 2             # search_proposals calls per question
    max_revisions: int = 1            # verifier -> answerer revision requests per question
    timeout_s: float = 240.0          # wall clock per question (5 model calls of up to 45 s each, plus retries)
    top_k: int = 10                   # same as the single-call pipeline
    context_budget_tokens: int = 4000  # same as the single-call pipeline
    temperature: float = 0.0
    retriever_max_tokens: int = 256
    answer_max_tokens: int = 512
    verifier_max_tokens: int = 512
    snippet_chars: int = 400          # what the retriever model sees of each hit (the answerer sees the full chunk)
    template_version: str = "2.1.0"


def agents_enabled(values: Optional[Dict[str, Any]] = None) -> bool:
    """AGENTS_ENABLED=true (case and spaces ignored) turns the path on; anything else, or unset, leaves it off."""
    env = os.environ if values is None else values
    return str(env.get(ENV_FLAG, "false")).strip().lower() == "true"


def _sha256_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def config_hash(cfg: AgentsConfig, model_name: str, files: Iterable[str] = (), extra: Optional[Dict[str, Any]] = None) -> str:
    """SHA-256 over: every cap, the model name, the instruction texts, the 2.1.0 template files, the hashes of `files`, ADK version."""
    from scripts.agents import prompts
    try:
        import google.adk as adk
        adk_version = getattr(adk, "__version__", "unknown")
    except ImportError:  # pragma: no cover
        adk_version = "not installed"
    tpl_dir = os.path.join(REPO, "config", "prompt_templates", cfg.template_version)
    tpl = {n: _sha256_file(os.path.join(tpl_dir, n)) for n in ("system_prompt.txt", "user_prompt.txt", "template_metadata.json")
           if os.path.exists(os.path.join(tpl_dir, n))}
    payload = {"config": dataclasses.asdict(cfg), "model_name": model_name, "adk_version": adk_version,
               "instructions": prompts.frozen_texts(), "template_files": tpl,
               "files": {os.path.basename(f): _sha256_file(f) for f in sorted(files)}, "extra": extra or {}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
