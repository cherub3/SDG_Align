"""Regression for the Phase 3 step 5 finding: the live Gemini planner answered COMPLETE (or FAIL) at step 0 and never ran QUERY_PIPELINE.
The recorded outputs below are REAL raw planner responses saved by tools/planner_probe.py (eval/results/planner_probe_dev.json, DEV items)."""
import json
from unittest.mock import Mock

from scripts.planner_provider_gemini import GeminiPlannerLLMAdapter, SYSTEM_INSTRUCTION
from scripts.stage21_agent_planning import AgentDependencies, PlannerLLMAdapter, plan_and_execute

RECORDED_COMPLETE_NO_STEP = '{\n  "decision": "COMPLETE",\n  "final_answer_step_index": 0\n}'
RECORDED_FAIL_NO_TOOLS = ('{\n  "decision": "FAIL",\n  "next_step": {\n    "step_type": "CONVERSATION_MEMORY",\n    "step_input": {},\n'
                          '    "step_rationale": "No tools are available to query the required data for Ecuador\'s conservation projects."\n  }\n}')


class Recorded(PlannerLLMAdapter):
    def __init__(self, raws):
        self.raws = list(raws)
        client = Mock()
        self.inner = GeminiPlannerLLMAdapter(client)
        self.client = client

    def plan(self, prompt, config):
        self.client.models.generate_content.return_value = Mock(text=self.raws.pop(0))
        return self.inner.plan(prompt, config)


def _deps(raws):
    return AgentDependencies(handle_request=lambda r, d: {"status": "SUCCESS", "findings": []}, select_memory=None, append_turn=None,
                             get_conversation=None, execute_tool=None, tool_registry=None, tool_adapter=None,
                             planner_llm_adapter=Recorded(raws), pipeline_deps=None, default_planner_model_name="m")


def test_system_instruction_tells_the_planner_how_to_answer_a_question():
    s = SYSTEM_INSTRUCTION
    assert "QUERY_PIPELINE" in s and "final_answer_step_index" in s
    assert "never return complete or fail while executed_steps is empty" in s.lower() and "empty available_tools" in s.lower()      # an empty tool list must not be read as "nothing can be done"


def test_recorded_complete_without_a_step_is_reported_not_silent():
    out = plan_and_execute({"query": "Where does the jaguar rank?"}, _deps([RECORDED_COMPLETE_NO_STEP]))
    assert out["final_response"] is None
    assert "PLANNER_COMPLETE_WITHOUT_ANSWER" in [f["code"] for f in out["findings"]]


def test_recorded_fail_is_a_failed_plan():
    out = plan_and_execute({"query": "Rank the projects"}, _deps([RECORDED_FAIL_NO_TOOLS]))
    assert out["status"] == "FAIL"
