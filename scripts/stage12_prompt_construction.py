"""Stage 12 — Prompt Construction.

Transforms a Stage 11 ContextPackage into a deterministic PromptPackage.
"""

import sys
import math
import hashlib
import json
import logging
import os
from typing import Any, Dict, List, Tuple, Optional
from pathlib import Path

# Adjust path to import from src
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage1_integrity import get_now_iso

PROMPT_PIPELINE_VERSION = "1.0.0"
DEFAULT_TEMPLATE_VERSION = "1.0.0"
DEFAULT_PROMPT_BUDGET_TOKENS = 8000
MAX_PROMPT_BUDGET_TOKENS = 100000
CHARS_PER_TOKEN_ESTIMATE = 4.0
BLOCK_SEPARATOR = "\n\n---\n\n"
SYSTEM_USER_SEPARATOR = "\n\n"
PROMPT_TEMPLATES_DIR = "config/prompt_templates"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("stage12_prompt_construction")

class PromptConstructionInputError(Exception):
    pass

class PromptConstructionInternalError(Exception):
    pass

def validate_context_package(package: Dict[str, Any]) -> None:
    """Raises PromptConstructionInputError if malformed."""
    required_keys = [
        "context_package_id", "status", "query", 
        "context_blocks", "findings"
    ]
    for k in required_keys:
        if k not in package:
            raise PromptConstructionInputError(f"CONTEXT_PACKAGE_MALFORMED: missing key {k}")
            
    if not isinstance(package["context_blocks"], list):
        raise PromptConstructionInputError("CONTEXT_PACKAGE_MALFORMED: context_blocks is not a list")
        
    # We assume if it made it out of Stage 11, individual block structure is correct,
    # but we will check basic presence of what we need to render.
    if not isinstance(package["query"], str):
        raise PromptConstructionInputError("CONTEXT_PACKAGE_MALFORMED: query is not a string")
    if not isinstance(package["status"], str):
        raise PromptConstructionInputError("CONTEXT_PACKAGE_MALFORMED: status is not a string")
    if not isinstance(package["findings"], list):
        raise PromptConstructionInputError("CONTEXT_PACKAGE_MALFORMED: findings is not a list")
        
    for i, block in enumerate(package["context_blocks"]):
        if not isinstance(block, dict):
            raise PromptConstructionInputError(f"CONTEXT_PACKAGE_MALFORMED: block {i} is not a dict")
        for k in ["rank", "doc_id", "chunk_id", "title", "heading_path", "page_start", "page_end", "text"]:
            if k not in block:
                raise PromptConstructionInputError(f"CONTEXT_PACKAGE_MALFORMED: block {i} missing {k}")

def load_prompt_template(template_version: str) -> Tuple[str, str, str]:
    """Reads templates and metadata from disk."""
    base_dir = Path(PROMPT_TEMPLATES_DIR) / template_version
    
    if not base_dir.is_dir():
        raise PromptConstructionInputError("PROMPT_TEMPLATE_NOT_FOUND: directory does not exist")
        
    sys_path = base_dir / "system_prompt.txt"
    user_path = base_dir / "user_prompt.txt"
    meta_path = base_dir / "template_metadata.json"
    
    for p in [sys_path, user_path, meta_path]:
        if not p.is_file():
            raise PromptConstructionInputError(f"PROMPT_TEMPLATE_NOT_FOUND: missing {p.name}")
            
    with open(meta_path, 'r', encoding='utf-8') as f:
        try:
            meta = json.load(f)
        except json.JSONDecodeError:
            raise PromptConstructionInputError("PROMPT_TEMPLATE_NOT_FOUND: malformed template_metadata.json")
            
    resolved_version = meta.get("template_version")
    if resolved_version != template_version:
        raise PromptConstructionInputError("TEMPLATE_VERSION_MISMATCH")
        
    with open(sys_path, 'r', encoding='utf-8') as f:
        sys_prompt = f.read()
        
    with open(user_path, 'r', encoding='utf-8') as f:
        user_prompt = f.read()
        
    return sys_prompt, user_prompt, resolved_version

def render_system_prompt(system_template_text: str) -> str:
    """Verbatim passthrough."""
    return system_template_text

def render_context_text(context_blocks: List[Dict[str, Any]]) -> str:
    """Renders blocks into a single string."""
    if not context_blocks:
        return ""
        
    rendered_blocks = []
    for block in context_blocks:
        heading_path = " > ".join(block["heading_path"])
        b = (
            f"[Block {block['rank']}] Source: {block['title']} ({block['doc_id']})\n"
            f"Section: {heading_path}\n"
            f"Pages: {block['page_start']}-{block['page_end']}\n"
            f"Chunk ID: {block['chunk_id']}\n\n"
            f"{block['text']}"
        )
        rendered_blocks.append(b)
        
    return BLOCK_SEPARATOR.join(rendered_blocks)

def render_user_prompt(user_template_text: str, query: str, context_text: str) -> str:
    """Literal substring replacement."""
    out = user_template_text.replace("{{query}}", query)
    out = out.replace("{{context_text}}", context_text)
    return out

def assemble_prompt(system_prompt: str, user_prompt: str) -> str:
    return system_prompt + SYSTEM_USER_SEPARATOR + user_prompt

def estimate_prompt_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN_ESTIMATE)

def build_prompt_package(
    context_package: Dict[str, Any], 
    resolved_template_version: str,
    system_prompt: str, 
    user_prompt: str, 
    context_text: str, 
    assembled_prompt: str,
    prompt_budget_tokens: int
) -> Dict[str, Any]:

    hash_input = {
        "context_package_id": context_package["context_package_id"],
        "template_version": resolved_template_version,
        "prompt_budget_tokens": prompt_budget_tokens
    }
    canonical_json = json.dumps(hash_input, separators=(',', ':'), sort_keys=True)
    pkg_id = hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()
    
    estimated_prompt_tokens = estimate_prompt_tokens(assembled_prompt)
    prompt_utilization = estimated_prompt_tokens / prompt_budget_tokens if prompt_budget_tokens > 0 else 0.0
    
    findings = []
    if context_package["status"] == "FAIL":
        findings.append({
            "severity": "FAIL",
            "code": "CONTEXT_PACKAGE_STATUS_FAIL",
            "message": "ContextPackage status was FAIL"
        })
        
    if estimated_prompt_tokens > prompt_budget_tokens:
        findings.append({
            "severity": "WARNING",
            "code": "PROMPT_BUDGET_EXCEEDED",
            "message": f"Estimated tokens {estimated_prompt_tokens} exceeds budget {prompt_budget_tokens}"
        })
        
    package = {
        "prompt_package_id": pkg_id,
        "prompt_pipeline_version": PROMPT_PIPELINE_VERSION,
        "constructed_at": get_now_iso(),
        "template_version": resolved_template_version,
        "context_package_id": context_package["context_package_id"],
        "status": context_package["status"],
        "system_prompt": system_prompt,
        "context_text": context_text,
        "user_prompt": user_prompt,
        "assembled_prompt": assembled_prompt,
        "prompt_budget_tokens": prompt_budget_tokens,
        "estimated_prompt_tokens": estimated_prompt_tokens,
        "prompt_utilization": prompt_utilization,
        "findings": findings,
        "context_findings": context_package.get("findings", [])
    }
    
    return package

def validate_prompt_package(package: Dict[str, Any]) -> None:
    if package["assembled_prompt"] != package["system_prompt"] + SYSTEM_USER_SEPARATOR + package["user_prompt"]:
        raise PromptConstructionInternalError("ASSEMBLED_PROMPT_MISMATCH")
        
    if package["context_text"] and package["context_text"] not in package["user_prompt"]:
        raise PromptConstructionInternalError("CONTEXT_TEXT_NOT_SUBSTITUTED")
        
    est = estimate_prompt_tokens(package["assembled_prompt"])
    if package["estimated_prompt_tokens"] != est:
        raise PromptConstructionInternalError("TOKEN_ESTIMATE_MISMATCH")
        
    util = package["estimated_prompt_tokens"] / package["prompt_budget_tokens"] if package["prompt_budget_tokens"] > 0 else 0.0
    if package["prompt_utilization"] != util:
        raise PromptConstructionInternalError("PROMPT_UTILIZATION_MISMATCH")


def construct_prompt(
    context_package: Dict[str, Any], 
    template_version: Optional[str] = None,
    prompt_budget_tokens: Optional[int] = None
) -> Dict[str, Any]:
    
    validate_context_package(context_package)
    
    tv = template_version if template_version is not None else DEFAULT_TEMPLATE_VERSION
    
    if prompt_budget_tokens is None:
        budget = DEFAULT_PROMPT_BUDGET_TOKENS
    else:
        budget = min(max(1, prompt_budget_tokens), MAX_PROMPT_BUDGET_TOKENS)
        
    sys_text, user_text, resolved_tv = load_prompt_template(tv)
    
    sys_prompt = render_system_prompt(sys_text)
    
    context_text = render_context_text(context_package["context_blocks"])
        
    user_prompt = render_user_prompt(user_text, context_package["query"], context_text)
    
    assembled_prompt = assemble_prompt(sys_prompt, user_prompt)
    
    pkg = build_prompt_package(
        context_package, 
        resolved_tv, 
        sys_prompt, 
        user_prompt, 
        context_text, 
        assembled_prompt, 
        budget
    )
    
    # Check overhead
    # Base overhead is system + separator + user with empty context
    overhead_user = render_user_prompt(user_text, context_package["query"], "")
    overhead_assembled = assemble_prompt(sys_prompt, overhead_user)
    overhead_tokens = estimate_prompt_tokens(overhead_assembled)
    if overhead_tokens > budget:
        pkg["findings"].append({
            "severity": "WARNING",
            "code": "PROMPT_TEMPLATE_OVERHEAD_EXCEEDS_BUDGET",
            "message": "Base template overhead alone exceeds budget"
        })
    
    validate_prompt_package(pkg)
    if pkg["context_package_id"] != context_package["context_package_id"]:
        raise PromptConstructionInternalError("CONTEXT_PACKAGE_ID_MISMATCH")
        
    return pkg
