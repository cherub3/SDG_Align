"""Planner OFF (the default): a deterministic stand-in for the LLM planner. It makes NO model call.

First decision: run one QUERY_PIPELINE step with the user's question unchanged. Next decision: COMPLETE with that step's answer.
This keeps the served result shape identical to the planner path while costing 1 Gemini call per request instead of 3.
Why it is the default: Phase 3 step 5 measured the planner as no change in refusals on the TEST set (6/44 -> 6/44) at about 3x calls and latency.
"""
import json
from typing import Any, Dict

from scripts.stage21_agent_planning import PlannerLLMAdapter


class DirectPlannerAdapter(PlannerLLMAdapter):
    def plan(self, planner_prompt: str, config: Dict[str, Any]) -> Dict[str, Any]:
        ctx = json.loads(planner_prompt)
        executed = ctx.get("executed_steps") or []
        if not executed:
            return {"decision": "EXECUTE_STEP",
                    "next_step": {"step_type": "QUERY_PIPELINE", "step_input": {"query": ctx["query"]}, "step_rationale": "direct"}}
        return {"decision": "COMPLETE", "final_answer_step_index": len(executed) - 1}
