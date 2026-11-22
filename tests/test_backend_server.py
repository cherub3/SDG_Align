import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from fastapi.testclient import TestClient

from scripts import backend_server
from scripts.stage21_agent_planning import AgentDependencies, PlannerLLMAdapter


class _ScriptedPlannerAdapter(PlannerLLMAdapter):
    """A fake planner that returns pre-scripted decisions in order, standing in for a real
    Gemini call so tests are deterministic and require no network access or credentials."""

    def __init__(self, decisions):
        self._decisions = list(decisions)

    def plan(self, planner_prompt, config):
        return self._decisions.pop(0)


class _SlowPlannerAdapter(PlannerLLMAdapter):
    def __init__(self, delay_seconds):
        self._delay_seconds = delay_seconds

    def plan(self, planner_prompt, config):
        time.sleep(self._delay_seconds)
        return {"decision": "COMPLETE"}


def _fake_application_instance(planner_adapter):
    # Intentionally partially-wired: sets pipeline_deps/tool_registry/conversation-memory hooks
    # to None to exercise the graceful-degradation path (QUERY_PIPELINE step → FAIL, not 500).
    # compose_application() now wires all fields fully; this fixture tests the unwired edge case.
    agent_deps = AgentDependencies(
        handle_request=None,
        select_memory=None,
        append_turn=None,
        get_conversation=None,
        execute_tool=None,
        tool_registry=None,
        tool_adapter=None,
        planner_llm_adapter=planner_adapter,
        pipeline_deps=None,
        default_planner_model_name="test-model",
    )
    return {"agent_dependencies": agent_deps}


class TestBackendServer(unittest.TestCase):
    def _client_with_planner(self, planner_adapter, timeout_seconds=None):
        patcher = patch.object(
            backend_server,
            "_create_application_instance",
            return_value=_fake_application_instance(planner_adapter),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        if timeout_seconds is not None:
            os.environ["REQUEST_TIMEOUT_SECONDS"] = str(timeout_seconds)
            self.addCleanup(lambda: os.environ.pop("REQUEST_TIMEOUT_SECONDS", None))
        return TestClient(backend_server.app)

    def test_planner_only_query_succeeds(self):
        planner = _ScriptedPlannerAdapter([{"decision": "COMPLETE"}])
        with self._client_with_planner(planner) as client:
            resp = client.post("/run-query", json={"query": "hello"})

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["query"], "hello")
        self.assertEqual(body["plan"]["total_step_count"], 0)

    def test_rag_pipeline_required_returns_200_with_status_fail_not_500(self):
        # Proves the documented scope boundary: the unwired RAG pipeline (handle_request=None)
        # surfaces as a normal, successfully-transported response with status "FAIL" and a
        # PLAN_STEP_EXECUTION_FAILED finding — NOT an HTTP 500 execution_failure, because
        # stage21_agent_planning.execute_plan_step already catches the None-call TypeError
        # internally.
        planner = _ScriptedPlannerAdapter([
            {"decision": "EXECUTE_STEP", "next_step": {"step_type": "QUERY_PIPELINE", "step_input": {}}},
            {"decision": "COMPLETE", "final_answer_step_index": 0},
        ])
        with self._client_with_planner(planner) as client:
            resp = client.post("/run-query", json={"query": "needs the rag pipeline"})

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "FAIL")
        step = body["plan"]["steps"][0]
        self.assertEqual(step["step_status"], "FAILED")
        codes = [f["code"] for f in step["step_findings"]]
        self.assertIn("PLAN_STEP_EXECUTION_FAILED", codes)

    def test_malformed_request_returns_execution_failure(self):
        # An empty query passes FastAPI's own pydantic type check (still a str) but fails
        # validate_agent_request's non-empty check inside plan_and_execute, raising
        # AgentPlanningInputError uncaught — the genuine "execution_failure" (500) path.
        planner = _ScriptedPlannerAdapter([{"decision": "COMPLETE"}])
        with self._client_with_planner(planner) as client:
            resp = client.post("/run-query", json={"query": ""})

        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.json()["category"], "execution_failure")

    def test_timeout_returns_504_without_claiming_cancellation(self):
        planner = _SlowPlannerAdapter(delay_seconds=0.4)
        with self._client_with_planner(planner, timeout_seconds=0.05) as client:
            resp = client.post("/run-query", json={"query": "slow"})

        self.assertEqual(resp.status_code, 504)
        self.assertEqual(resp.json()["category"], "timeout")

    def test_observation_records_returns_snapshot(self):
        planner = _ScriptedPlannerAdapter([{"decision": "COMPLETE"}])
        with self._client_with_planner(planner) as client:
            client.post("/run-query", json={"query": "one"})
            resp = client.get("/observation-records")

        self.assertEqual(resp.status_code, 200)
        records = resp.json()
        self.assertGreaterEqual(len(records), 1)
        self.assertIn("correlation_id", records[-1])
        self.assertIn("outcome", records[-1])
        self.assertIn("duration", records[-1])

    def test_bootstrap_failure_prevents_startup(self):
        patcher = patch.object(
            backend_server,
            "_create_application_instance",
            side_effect=RuntimeError("missing Gemini credentials"),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        with self.assertRaises(RuntimeError):
            with TestClient(backend_server.app):
                pass


if __name__ == "__main__":
    unittest.main()
