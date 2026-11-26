"""ADK model for Gemini that goes through the project's own QuotaGuard (daily cap, 429 breaker, pacing).

ADK's bundled Gemini class builds its own client and would bypass those guards, so this BaseLlm subclass takes the already
constructed google-genai client (built by the existing Gemini provider from the existing credential mechanism) and the
QuotaGuard. It adds nothing else: the per-question call cap and the token accounting live in the agent callbacks.
"""
import asyncio
from typing import Any, AsyncGenerator, Optional

from google.adk.models import BaseLlm, LlmResponse


class GuardedGeminiLlm(BaseLlm):
    model: str
    client: Any = None
    guard: Optional[Any] = None
    max_retries: int = 2          # extra attempts after a 500/502/503/504; every attempt goes through the guard and is counted
    backoff_s: float = 4.0        # wait before retry 1; retry 2 waits three times as long
    call_timeout_s: float = 45.0  # one model call that takes longer is abandoned and retried like a 503 (the SDK has no default timeout)

    async def generate_content_async(self, llm_request, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        import httpx
        from google.genai import errors
        from scripts.agents.runtime import current_run
        from scripts.stage13_llm_execution import LLMQuotaExhaustedError
        for attempt in range(self.max_retries + 1):
            if self.guard is not None:
                # before_call may sleep for pacing, so it runs in a worker thread and never blocks the event loop
                await asyncio.to_thread(self.guard.before_call)
            try:
                response = await asyncio.wait_for(
                    self.client.aio.models.generate_content(model=self.model, contents=llm_request.contents, config=llm_request.config),
                    timeout=self.call_timeout_s)
                break
            except (asyncio.TimeoutError, httpx.TransportError) as e:
                if attempt >= self.max_retries:
                    raise
                run = current_run.get()
                if run is not None:
                    run.retries += 1
                await asyncio.sleep(self.backoff_s * (3 ** attempt))
            except errors.APIError as e:
                code = getattr(e, "code", None)
                if code == 429:
                    if self.guard is not None:
                        self.guard.trip()
                    raise LLMQuotaExhaustedError(str(e)) from e
                if code in (500, 502, 503, 504) and attempt < self.max_retries:
                    run = current_run.get()
                    if run is not None:
                        run.retries += 1
                    await asyncio.sleep(self.backoff_s * (3 ** attempt))
                    continue
                raise
        yield LlmResponse.create(response)
