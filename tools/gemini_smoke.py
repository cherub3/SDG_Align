"""ONE live Gemini call (1 of the 20 free requests/day). Reads GEMINI_API_KEY from the environment or ./.env; never prints it.
Goes through the real adapter + daily-cap guard. A 429 stops immediately (no retry). Writes reports/evidence/gemini_smoke.json."""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.llm_provider_gemini import gemini_llm_factory  # noqa: E402
from scripts.model_config import default_gemini_model, default_pace_rpm  # noqa: E402
from scripts.quota_guard import GuardedLLMAdapter, QuotaGuard  # noqa: E402
from scripts.stage13_llm_execution import LLMQuotaExhaustedError  # noqa: E402

MODEL = default_gemini_model()


def _key():
    k = os.environ.get("GEMINI_API_KEY")
    if not k:
        from dotenv import dotenv_values
        k = (dotenv_values(ROOT / ".env") or {}).get("GEMINI_API_KEY")
    return k


def main():
    key = _key()
    if not key:
        print("GEMINI_API_KEY not set in the environment or .env; no call made.")
        return 2
    settings = {"seam": "LLM_PROVIDER", "provider_name": "gemini", "credential_ref": "", "extra": {}}
    adapter = GuardedLLMAdapter(gemini_llm_factory(settings, key), QuotaGuard(cap=1, pace=default_pace_rpm()))
    out = {"model": MODEL, "calls_made": 1}
    t0 = time.time()
    try:
        r = adapter.invoke("", "Reply with the single word OK.", {"model_name": MODEL, "temperature": 0, "max_output_tokens": 16})
        out.update(status="ok", response_text=r.response_text.strip()[:40], finish_reason=r.finish_reason,
                   prompt_tokens=r.prompt_tokens, completion_tokens=r.completion_tokens, total_tokens=r.total_tokens,
                   model_version_reported=adapter.model_version_reported)
    except LLMQuotaExhaustedError as e:
        out.update(status="QUOTA_EXHAUSTED_429", error=str(e).replace(key, "[REDACTED]")[:200])
    except Exception as e:
        out.update(status="error", error_type=type(e).__name__, error=str(e).replace(key, "[REDACTED]")[:300])
    out["latency_ms"] = int((time.time() - t0) * 1000)
    (ROOT / "reports/evidence/gemini_smoke.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0 if out["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
