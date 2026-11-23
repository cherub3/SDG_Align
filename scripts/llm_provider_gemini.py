import sys
from typing import Any, Dict, Optional
from pathlib import Path

from google import genai
from google.genai import types
from google.genai import errors

src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage13_llm_execution import (
    LLMAdapter,
    RawLLMResult,
    LLMTransientError,
    LLMAuthError,
    LLMInvalidRequestError,
    LLMQuotaExhaustedError,
)
from scripts.phase1_1_configuration_layer import ProviderSettings, ProviderRegistration


def _enum_name(value) -> str:
    """'STOP' for both the SDK enum (str() gives 'FinishReason.STOP') and a plain string."""
    if not value:
        return ""
    return str(getattr(value, "name", value)).upper().rsplit(".", 1)[-1]


class GeminiLLMAdapter(LLMAdapter):
    def __init__(self, client: genai.Client):
        self._client = client
        self._model_version_reported: Optional[str] = None

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_version_reported(self) -> Optional[str]:
        return self._model_version_reported

    def invoke(self, system_prompt: str, user_prompt: str, config: Dict[str, Any]) -> RawLLMResult:
        model_name = config["model_name"]
        
        # We recommend pinned models per Phase 1.2 Model Pinning
        # but Stage 13 does not require it strictly for LLMs. 
        # For gemini, floating aliases are latest, stable, preview, beta.
        
        temperature = config.get("temperature")
        max_output_tokens = config.get("max_output_tokens")
        
        # 1. Native Request Mapping
        gemini_config = types.GenerateContentConfig()
        if system_prompt:
            gemini_config.system_instruction = system_prompt
        if temperature is not None:
            gemini_config.temperature = temperature
        if max_output_tokens is not None:
            gemini_config.max_output_tokens = max_output_tokens

        # 2. Invoke provider
        try:
            response = self._client.models.generate_content(
                model=model_name,
                contents=user_prompt,
                config=gemini_config
            )
        except errors.APIError as e:
            code = getattr(e, "code", None)
            if code == 429:
                # Quota exhausted (free tier: 20 requests/day). Retrying only burns more quota, so never transient.
                raise LLMQuotaExhaustedError(str(e)) from e
            if code in (500, 502, 503, 504):
                raise LLMTransientError(str(e)) from e
            elif code in (401, 403):
                raise LLMAuthError(str(e)) from e
            elif code == 400:
                # 400 is typically invalid request. It could be safety if provider uses 400 for safety,
                # but google-genai usually uses specific error objects or FinishReason for safety.
                raise LLMInvalidRequestError(str(e)) from e
            else:
                # Fallback mapping for unknown APIError codes
                raise LLMInvalidRequestError(str(e)) from e
        except Exception as e:
            exc_type = type(e).__name__
            if exc_type in ("ConnectError", "TimeoutException", "ReadTimeout", "ConnectionError"):
                raise LLMTransientError(str(e)) from e
            raise LLMInvalidRequestError(str(e)) from e

        # 3. RawLLMResult Mapping
        # response_text normalization
        try:
            response_text = response.text or ""
        except ValueError:
            # SDK raises ValueError("Cannot get the text of a response...") when parts are empty (e.g. safety blocked)
            response_text = ""

        # finish_reason normalization
        candidate = response.candidates[0] if response.candidates else None
        native_finish_reason = candidate.finish_reason if candidate else None
        
        # For prompt block (no candidates) due to safety
        prompt_blocked = False
        if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
            block_reason = getattr(response.prompt_feedback, 'block_reason', None)
            if block_reason:
                prompt_blocked = True

        str_finish = _enum_name(native_finish_reason)
        
        if str_finish == "STOP":
            finish_reason = "complete"
        elif str_finish == "MAX_TOKENS":
            finish_reason = "length"
        elif str_finish in ("SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "IMAGE_SAFETY", "IMAGE_PROHIBITED_CONTENT") or prompt_blocked:
            finish_reason = "content_filter"
        elif not candidate and not response_text:
            # Safety block usually results in no candidates and no text. 
            finish_reason = "content_filter"
        else:
            finish_reason = "other"

        # token counts
        prompt_tokens = None
        completion_tokens = None
        total_tokens = None
        
        usage = getattr(response, "usage_metadata", None)
        if usage:
            prompt_tokens = getattr(usage, "prompt_token_count", None)
            completion_tokens = getattr(usage, "candidates_token_count", None)
            total_tokens = getattr(usage, "total_token_count", None)

        if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
            total_tokens = prompt_tokens + completion_tokens

        # metadata updates
        self._model_version_reported = getattr(response, "model_version", None)
        
        return RawLLMResult(
            response_text=response_text,
            finish_reason=finish_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            provider_request_id=None
        )


def gemini_llm_factory(settings: ProviderSettings, raw_credential: Optional[str]) -> LLMAdapter:
    """
    Factory invoked by Phase 1.1 wire_dependencies().
    Consumes raw_credential exactly once to build the client.
    """
    extra = settings.get("extra", {})

    # Construction-time validation
    if not raw_credential:
        raise ValueError("Gemini provider requires a credential (API key)")
    
    # We could validate default_model_name here if supplied
    default_model_name = extra.get("default_model_name")
    if default_model_name:
        _UNPINNED_ALIASES = {"latest", "stable", "preview", "beta"}
        if default_model_name.lower() in _UNPINNED_ALIASES:
            raise ValueError(
                f"Gemini provider 'default_model_name' must be pinned; "
                f"floating alias '{default_model_name}' is not permitted"
            )

    client = genai.Client(api_key=raw_credential)
    return GeminiLLMAdapter(client)


def get_provider_registration() -> ProviderRegistration:
    """
    Registration dict for Phase 1.1.
    """
    return {
        "seam": "LLM_PROVIDER",
        "provider_name": "gemini",
        "network_dependent": True,
        "factory": gemini_llm_factory
    }
