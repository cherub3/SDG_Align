import sys
import json
from typing import Any, Dict, Optional
from pathlib import Path

from groq import Groq, APIError, APIConnectionError, RateLimitError, InternalServerError

src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage21_agent_planning import (
    PlannerLLMAdapter,
    PlannerInvocationError
)
from scripts.phase1_1_configuration_layer import ProviderSettings, ProviderRegistration


class GroqPlannerLLMAdapter(PlannerLLMAdapter):
    def __init__(self, client: Groq):
        self._client = client

    def plan(self, planner_prompt: str, config: Dict[str, Any]) -> Dict[str, Any]:
        model_name = config["model_name"]
        temperature = config.get("temperature", 0.0)
        
        # System instruction to guide the planner
        system_instruction = (
            "You are an agentic planner orchestrating a sequence of steps. "
            "You are provided with a context including the query, conversation memory, available tools, "
            "and executed steps. Determine the next step by returning a JSON object with EXACTLY this schema:\n"
            '{"decision": "EXECUTE_STEP" | "COMPLETE" | "FAIL",\n'
            ' "next_step": {"step_type": "QUERY_PIPELINE" | "CONVERSATION_MEMORY" | "CONVERSATION_APPEND" | "TOOL_INVOCATION",\n'
            '               "step_input": {...}, "step_rationale": "why"},\n'
            ' "final_answer_step_index": <int>}\n'
            "Rules: 'next_step' is required when decision is EXECUTE_STEP and must use one of the four "
            "step_type values verbatim. Use QUERY_PIPELINE (step_input: {\"query\": ...}) to answer the "
            "user's query via retrieval-augmented generation. Use CONVERSATION_MEMORY to load prior turns "
            "when a conversation_id exists. Use TOOL_INVOCATION only for a tool listed in available_tools. "
            "After a QUERY_PIPELINE step succeeds and the context has a conversation_id, plan one "
            "CONVERSATION_APPEND step (step_input: {\"user_content\": <the user's query>, "
            "\"assistant_content\": <the answer text>, \"provenance\": {\"request_id\": <the "
            "'request_id' from that QUERY_PIPELINE step's step_result>}}) "
            "to persist the turn — memory is never persisted implicitly. A failed CONVERSATION_MEMORY "
            "step on a first turn just means no history exists yet; continue with QUERY_PIPELINE. "
            "When the query has been answered (and any append is done), return decision COMPLETE with "
            "final_answer_step_index set to the answering step's index. Do not invent other keys or step types."
        )

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": planner_prompt}
        ]

        try:
            response = self._client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"}
            )
        except Exception as e:
            exc_type = type(e).__name__
            code = getattr(e, "status_code", exc_type)
            # Differentiate APIError vs SDKError if needed, but keeping it simple for Groq
            if isinstance(e, APIError):
                raise PlannerInvocationError(f"APIError: {e}", str(code)) from e
            raise PlannerInvocationError(f"SDKError: {e}", exc_type) from e

        choice = response.choices[0] if response.choices else None
        response_text = choice.message.content if choice and choice.message else ""
        if response_text is None:
            response_text = ""
            
        if not response_text:
            native_finish_reason = str(choice.finish_reason).upper() if choice else ""
            if native_finish_reason in ("CONTENT_FILTER", "SAFETY", "LENGTH"):
                raise PlannerInvocationError("Planner output blocked by safety filter.", "SAFETY_BLOCK")
            raise PlannerInvocationError("Empty response from provider.", "EMPTY_RESPONSE")

        # Parse JSON
        try:
            decision_dict = json.loads(response_text)
        except json.JSONDecodeError as e:
            raise PlannerInvocationError(f"Malformed JSON output: {e}", "JSON_DECODE_ERROR") from e
            
        if not isinstance(decision_dict, dict):
            raise PlannerInvocationError("JSON output is not an object", "INVALID_STRUCTURE")
            
        # Enforce exact normalization
        decision_val = decision_dict.get("decision")
        if decision_val not in ("EXECUTE_STEP", "COMPLETE", "FAIL"):
            decision_val = "FAIL"
            
        normalized = {"decision": decision_val}
        
        if decision_val == "EXECUTE_STEP":
            next_step = decision_dict.get("next_step")
            if isinstance(next_step, dict):
                step_type_val = next_step.get("step_type")
                if step_type_val not in ("QUERY_PIPELINE", "CONVERSATION_MEMORY", "CONVERSATION_APPEND", "TOOL_INVOCATION"):
                    return {"decision": "FAIL"}
                
                step_input_val = next_step.get("step_input")
                if not isinstance(step_input_val, dict):
                    step_input_val = {}
                    
                normalized_next_step = {
                    "step_type": step_type_val,
                    "step_input": step_input_val
                }
                
                rationale = next_step.get("step_rationale")
                if rationale is not None:
                    normalized_next_step["step_rationale"] = str(rationale)
                    
                normalized["next_step"] = normalized_next_step
            else:
                return {"decision": "FAIL"}
                
        elif decision_val == "COMPLETE":
            idx = decision_dict.get("final_answer_step_index")
            if idx is not None and isinstance(idx, int):
                normalized["final_answer_step_index"] = idx
                
        return normalized


def groq_planner_factory(settings: ProviderSettings, raw_credential: Optional[str]) -> PlannerLLMAdapter:
    """
    Factory invoked by Phase 1.1 wire_dependencies().
    Consumes raw_credential exactly once to build the client.
    """
    if not raw_credential:
        raise ValueError("Groq Planner provider requires a credential (API key)")
    
    client = Groq(api_key=raw_credential)
    return GroqPlannerLLMAdapter(client)


def get_provider_registration() -> ProviderRegistration:
    """
    Registration dict for Phase 1.1.
    """
    return {
        "seam": "PLANNER_LLM_PROVIDER",
        "provider_name": "groq",
        "network_dependent": True,
        "factory": groq_planner_factory
    }
