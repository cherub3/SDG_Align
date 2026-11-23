"""The pinned default Gemini model id lives in config/llm_model.json (one place), with a safe in-code fallback."""
import json
from pathlib import Path

FALLBACK_MODEL = "gemini-3.5-flash-lite"
_PATH = Path(__file__).resolve().parent.parent / "config" / "llm_model.json"
_UNPINNED = {"latest", "stable", "preview", "beta"}


def _load() -> dict:
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def default_gemini_model() -> str:
    name = str(_load().get("model_name") or "").strip()
    return name if name and name.lower() not in _UNPINNED else FALLBACK_MODEL


def default_pace_rpm() -> int:
    try:
        v = int(_load().get("pace_rpm", 12))
    except (TypeError, ValueError):
        return 12
    return v if v >= 1 else 12
