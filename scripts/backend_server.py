"""
Track B Phase 6 — Backend Foundation.

Implements the transport and process required by the approved Version 1.3 Transport
Resolution Amendment: one long-running FastAPI process, bootstrapped exactly once, exposing
one synchronous request/response operation per BackendAdapter method that has a Mode A
equivalent (runQuery -> POST /run-query, getObservationRecords -> GET /observation-records).
getSampleQuery has no Mode A equivalent (Decision 4) and is intentionally not exposed here.

This module knows nothing about the frontend, `QueryResult`, or `BackendAdapter.ts`. It returns
the native `AgentResult` dict produced by `scripts.stage21_agent_planning.plan_and_execute` (via
`observe_request`) unchanged. Any translation into a frontend-facing shape belongs to a future,
separate `LiveBackendAdapter` implementation milestone.

Route paths (`/run-query`, `/observation-records`) and HTTP status-code choices below are this
milestone's own implementation decisions, not architectural requirements frozen by Version 1.3 —
Version 1.3 named no endpoint, no payload schema, and no wire format.
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from scripts.application_bootstrap import ApplicationInstance, bootstrap_application
from scripts.embedding_provider_gemini import get_provider_registration as get_embedding_registration
from scripts.llm_provider_gemini import get_provider_registration as get_llm_registration
from scripts.planner_provider_gemini import get_provider_registration as get_planner_registration
from scripts.llm_provider_groq import get_provider_registration as get_groq_llm_registration
from scripts.planner_provider_groq import get_provider_registration as get_groq_planner_registration
from scripts.embedding_provider_huggingface import get_provider_registration as get_huggingface_embedding_registration
from scripts.embedding_provider_local import get_provider_registration as get_local_embedding_registration
from scripts.llm_provider_openrouter import get_provider_registration as get_openrouter_llm_registration
from scripts.planner_provider_openrouter import get_provider_registration as get_openrouter_planner_registration
from scripts.request_observability import get_observation_records, observe_request
from scripts.stage21_agent_planning import AgentPlanningInputError

logger = logging.getLogger("backend_server")

DEFAULT_REQUEST_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_QUERY_CHARS = 4000


def _max_query_chars() -> int:
    """Upper bound on query length (characters), read per request so it can be set via the
    MAX_QUERY_CHARS environment variable. An invalid or non-positive value falls back to the default."""
    try:
        value = int(os.environ.get("MAX_QUERY_CHARS", DEFAULT_MAX_QUERY_CHARS))
    except ValueError:
        return DEFAULT_MAX_QUERY_CHARS
    return value if value > 0 else DEFAULT_MAX_QUERY_CHARS


def _build_registrations() -> List[Any]:
    """Every available provider registration (Gemini, Groq, OpenRouter, Hugging Face, local); the
    configured LLM_PROVIDER / PLANNER_LLM_PROVIDER / EMBEDDING_PROVIDER decide which are used."""
    return [
        get_llm_registration(),
        get_embedding_registration(),
        get_planner_registration(),
        get_groq_llm_registration(),
        get_groq_planner_registration(),
        get_huggingface_embedding_registration(),
        get_local_embedding_registration(),
        get_openrouter_llm_registration(),
        get_openrouter_planner_registration(),
    ]


def _create_application_instance() -> ApplicationInstance:
    """Bootstraps the application exactly once (Decision 2: one long-running shared process).
    Any exception here (missing credentials, a provider-registration failure, any
    `compose_application` error) is intentionally not caught — it must prevent the server from
    ever starting, never yield a partially-initialized instance."""
    return bootstrap_application(
        registrations=_build_registrations(),
        env=None,
        dotenv_path=".env",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.application_instance = _create_application_instance()
    app.state.request_timeout_seconds = float(
        os.environ.get("REQUEST_TIMEOUT_SECONDS", DEFAULT_REQUEST_TIMEOUT_SECONDS)
    )
    logger.info("Backend foundation started: application bootstrapped once.")
    try:
        yield
    finally:
        # No held connections or resources to release, so nothing beyond this log line is needed
        # for a graceful shutdown. (Application state - conversation memory, response cache,
        # observation records - lives in process memory and is simply discarded with the process.)
        logger.info("Backend foundation shutting down.")


app = FastAPI(lifespan=lifespan)

# Decision 8 (Version 1.3): no authentication, trusted-context only -- this dashboard's own
# frontend dev server (Vite, default port 5173) is the only expected browser caller. Without
# this, the browser's CORS preflight (OPTIONS) receives no Access-Control-Allow-Origin header,
# FastAPI has no route for OPTIONS, and every POST /run-query from a real browser fails as
# net::ERR_FAILED before it ever reaches this server -- curl/server-to-server calls are
# unaffected since CORS is a browser-enforced restriction, not a server-side one.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class RunQueryRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None

    @field_validator("query")
    @classmethod
    def _query_not_blank_and_bounded(cls, value: str) -> str:
        # Client errors are rejected here (HTTP 422) before any planner/LLM work starts.
        if not value.strip():
            raise ValueError("query must not be empty or whitespace-only")
        limit = _max_query_chars()
        if len(value) > limit:
            raise ValueError(f"query is too long ({len(value)} characters; maximum is {limit})")
        return value

    @field_validator("conversation_id")
    @classmethod
    def _conversation_id_not_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("conversation_id must not be empty when provided")
        return value


def _timeout_response() -> JSONResponse:
    return JSONResponse(status_code=504, content={"category": "timeout"})


def _execution_failure_response(message: str) -> JSONResponse:
    return JSONResponse(status_code=500, content={"category": "execution_failure", "message": message})


@app.post("/run-query")
async def run_query(payload: RunQueryRequest, request: Request) -> JSONResponse:
    application_instance: ApplicationInstance = request.app.state.application_instance
    timeout_seconds: float = request.app.state.request_timeout_seconds
    agent_request: Dict[str, Any] = {"query": payload.query}
    if payload.conversation_id is not None:
        agent_request["conversation_id"] = payload.conversation_id

    try:
        # observe_request is synchronous/blocking — run it in a worker thread so the event loop
        # isn't blocked, and bound how long this HTTP request waits for it.
        result = await asyncio.wait_for(
            asyncio.to_thread(observe_request, application_instance, agent_request),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        # This only abandons the coroutine waiting on the worker thread — it does not stop the
        # thread itself. If observe_request() is still running, it keeps running in the
        # background (Gemini call, CPU/network usage, and its ObservationRecord may still be
        # appended later), consistent with Decision 7 (no cancellation exists at this layer).
        logger.warning("run-query exceeded %.1fs timeout; underlying thread not cancelled.", timeout_seconds)
        return _timeout_response()
    except AgentPlanningInputError as exc:
        # Invalid input detected downstream (e.g. unknown or closed conversation) is a client
        # error, not a server failure.
        return JSONResponse(status_code=422, content={"category": "invalid_request", "message": str(exc)})
    except Exception as exc:
        # Every other failure (AgentPlanningInputError, AgentPlanningInternalError, or any
        # unexpected exception) folds into the single "execution failure" category per Decision
        # 6. The real exception is logged server-side only — never leaked across the boundary.
        logger.exception("run-query failed with an unhandled exception: %s", exc)
        return _execution_failure_response("The request could not be completed.")

    # Native AgentResult, returned unchanged — no frontend-shaped mapping happens here.
    return JSONResponse(content=result)


@app.get("/observation-records")
async def observation_records() -> JSONResponse:
    records = get_observation_records()
    return JSONResponse(content=[
        {"correlation_id": r.correlation_id, "outcome": r.outcome, "duration": r.duration}
        for r in records
    ])
