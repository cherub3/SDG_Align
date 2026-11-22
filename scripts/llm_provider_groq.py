import sys
from typing import Any, Dict, Optional
from pathlib import Path

from groq import Groq, APIError, APIConnectionError, RateLimitError, InternalServerError

src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage13_llm_execution import (
    LLMAdapter,
    RawLLMResult,
    LLMTransientError,
    LLMAuthError,
    LLMInvalidRequestError,
)
from scripts.phase1_1_configuration_layer import ProviderSettings, ProviderRegistration


class GroqLLMAdapter(LLMAdapter):
    def __init__(self, client: Groq):
        self._client = client
        self._model_version_reported: Optional[str] = None

    @property
    def provider_name(self) -> str:
        return "groq"

    @property
    def model_version_reported(self) -> Optional[str]:
        return self._model_version_reported

    def invoke(self, system_prompt: str, user_prompt: str, config: Dict[str, Any]) -> RawLLMResult:
        model_name = config["model_name"]
        
        temperature = config.get("temperature")
        max_output_tokens = config.get("max_output_tokens")
        
        # 1. Native Request Mapping
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        kwargs = {
            "model": model_name,
            "messages": messages,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_output_tokens is not None:
            kwargs["max_tokens"] = max_output_tokens

        # 2. Invoke provider
        try:
            response = self._client.chat.completions.create(**kwargs)
        except RateLimitError as e:
            raise LLMTransientError(str(e)) from e
        except InternalServerError as e:
            raise LLMTransientError(str(e)) from e
        except APIConnectionError as e:
            raise LLMTransientError(str(e)) from e
        except APIError as e:
            # Check for Auth error status codes if applicable, Groq might throw specific errors.
            # Typically 401/403 maps to APIError with a status code
            status_code = getattr(e, "status_code", None)
            if status_code in (401, 403):
                raise LLMAuthError(str(e)) from e
            elif status_code in (429, 500, 502, 503, 504):
                raise LLMTransientError(str(e)) from e
            else:
                raise LLMInvalidRequestError(str(e)) from e
        except Exception as e:
            exc_type = type(e).__name__
            if exc_type in ("ConnectError", "TimeoutException", "ReadTimeout", "ConnectionError"):
                raise LLMTransientError(str(e)) from e
            raise LLMInvalidRequestError(str(e)) from e

        # 3. RawLLMResult Mapping
        choice = response.choices[0] if response.choices else None
        response_text = choice.message.content if choice and choice.message else ""
        if response_text is None:
            response_text = ""

        native_finish_reason = choice.finish_reason if choice else ""
        str_finish = str(native_finish_reason).upper()
        
        if str_finish == "STOP":
            finish_reason = "complete"
        elif str_finish in ("LENGTH", "MAX_TOKENS"):
            finish_reason = "length"
        elif str_finish in ("CONTENT_FILTER", "SAFETY"):
            finish_reason = "content_filter"
        elif not choice and not response_text:
            finish_reason = "content_filter"
        else:
            finish_reason = "other"

        # token counts
        prompt_tokens = None
        completion_tokens = None
        total_tokens = None
        
        usage = getattr(response, "usage", None)
        if usage:
            prompt_tokens = getattr(usage, "prompt_tokens", None)
            completion_tokens = getattr(usage, "completion_tokens", None)
            total_tokens = getattr(usage, "total_tokens", None)

        if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
            total_tokens = prompt_tokens + completion_tokens

        # metadata updates
        self._model_version_reported = response.model if hasattr(response, "model") else None
        
        return RawLLMResult(
            response_text=response_text,
            finish_reason=finish_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            provider_request_id=response.id if hasattr(response, "id") else None
        )


def groq_llm_factory(settings: ProviderSettings, raw_credential: Optional[str]) -> LLMAdapter:
    """
    Factory invoked by Phase 1.1 wire_dependencies().
    Consumes raw_credential exactly once to build the client.
    """
    if not raw_credential:
        raise ValueError("Groq provider requires a credential (API key)")
    
    client = Groq(api_key=raw_credential)
    return GroqLLMAdapter(client)


def get_provider_registration() -> ProviderRegistration:
    """
    Registration dict for Phase 1.1.
    """
    return {
        "seam": "LLM_PROVIDER",
        "provider_name": "groq",
        "network_dependent": True,
        "factory": groq_llm_factory
    }
