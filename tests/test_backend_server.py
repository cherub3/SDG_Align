import json
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
from scripts.stage21_agent_planning import AgentDependencies, AgentPlanningInputError, PlannerLLMAdapter


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

    def _post(self, body, **kw):
        planner = _ScriptedPlannerAdapter([{"decision": "COMPLETE"}])
        with self._client_with_planner(planner, **kw) as client:
            return client.post("/run-query", json=body)

    def test_empty_query_is_a_client_error_422(self):
        resp = self._post({"query": ""})
        self.assertEqual(resp.status_code, 422)

    def test_whitespace_only_query_is_422(self):
        for blank in ("   ", chr(10) + chr(9) + " ", chr(160)):
            with self.subTest(blank=repr(blank)):
                self.assertEqual(self._post({"query": blank}).status_code, 422)

    def test_query_at_the_limit_is_accepted_and_one_over_is_rejected(self):
        limit = backend_server.DEFAULT_MAX_QUERY_CHARS
        self.assertEqual(limit, 4000)
        self.assertEqual(self._post({"query": "a" * limit}).status_code, 200)
        resp = self._post({"query": "a" * (limit + 1)})
        self.assertEqual(resp.status_code, 422)
        self.assertIn("too long", json.dumps(resp.json()))

    def test_max_query_chars_is_configurable_via_environment(self):
        with patch.dict(os.environ, {"MAX_QUERY_CHARS": "10"}):
            self.assertEqual(self._post({"query": "a" * 10}).status_code, 200)
            self.assertEqual(self._post({"query": "a" * 11}).status_code, 422)

    def test_invalid_max_query_chars_falls_back_to_default(self):
        for bad in ("abc", "0", "-5"):
            with self.subTest(value=bad), patch.dict(os.environ, {"MAX_QUERY_CHARS": bad}):
                self.assertEqual(backend_server._max_query_chars(), backend_server.DEFAULT_MAX_QUERY_CHARS)

    def test_empty_conversation_id_is_422(self):
        self.assertEqual(self._post({"query": "hi", "conversation_id": ""}).status_code, 422)

    def test_planning_input_error_maps_to_422_not_500(self):
        with patch.object(backend_server, "observe_request",
                          side_effect=AgentPlanningInputError("CONVERSATION_CLOSED")):
            resp = self._post({"query": "hi"})
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["category"], "invalid_request")
        self.assertIn("CONVERSATION_CLOSED", resp.json()["message"])

    def test_unexpected_exception_is_still_500_and_hides_details(self):
        with patch.object(backend_server, "observe_request", side_effect=RuntimeError("secret detail")):
            resp = self._post({"query": "hi"})
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.json()["category"], "execution_failure")
        self.assertNotIn("secret detail", resp.text)

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
