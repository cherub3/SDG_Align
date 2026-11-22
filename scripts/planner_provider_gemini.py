import sys
import json
from typing import Any, Dict, Optional
from pathlib import Path

from google import genai
from google.genai import types
from google.genai import errors

src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage21_agent_planning import (
    PlannerLLMAdapter,
    PlannerInvocationError
)
from scripts.phase1_1_configuration_layer import ProviderSettings, ProviderRegistration


# Schema for structured output
_PLANNER_DECISION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "decision": {
            "type": "STRING",
            "enum": ["EXECUTE_STEP", "COMPLETE", "FAIL"]
        },
        "next_step": {
            "type": "OBJECT",
            "properties": {
                "step_type": {
                    "type": "STRING",
                    "enum": ["QUERY_PIPELINE", "CONVERSATION_MEMORY", "CONVERSATION_APPEND", "TOOL_INVOCATION"]
                },
                "step_input": {
                    "type": "OBJECT"
                },
                "step_rationale": {
                    "type": "STRING"
                }
            },
            "required": ["step_type", "step_input"]
        },
        "final_answer_step_index": {
            "type": "INTEGER"
        }
    },
    "required": ["decision"]
}


class GeminiPlannerLLMAdapter(PlannerLLMAdapter):
    def __init__(self, client: genai.Client):
        self._client = client

    def plan(self, planner_prompt: str, config: Dict[str, Any]) -> Dict[str, Any]:
        model_name = config["model_name"]
        temperature = config.get("temperature", 0.0)
        
        # System instruction to guide the planner
        system_instruction = (
            "You are an agentic planner orchestrating a sequence of steps. "
            "You are provided with a context including the query, conversation memory, available tools, "
            "and executed steps. Determine the next step by returning a structured decision. "
            "Decision must be 'EXECUTE_STEP', 'COMPLETE', or 'FAIL'."
        )

        gemini_config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=_PLANNER_DECISION_SCHEMA,
        )

        try:
            response = self._client.models.generate_content(
                model=model_name,
                contents=planner_prompt,
                config=gemini_config
            )
        except errors.APIError as e:
            code = getattr(e, "code", None)
            raise PlannerInvocationError(f"APIError: {e}", str(code)) from e
        except Exception as e:
            exc_type = type(e).__name__
            raise PlannerInvocationError(f"SDKError: {e}", exc_type) from e

        # Extract and parse response text
        try:
            response_text = response.text or ""
        except ValueError:
            response_text = ""
            
        if not response_text:
            # Handle safety blocks or empty responses
            candidate = response.candidates[0] if response.candidates else None
            native_finish_reason = str(candidate.finish_reason).upper() if candidate else ""
            prompt_blocked = False
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                if getattr(response.prompt_feedback, 'block_reason', None):
                    prompt_blocked = True

            if native_finish_reason in ("SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII") or prompt_blocked:
                raise PlannerInvocationError("Planner output blocked by safety filter.", "SAFETY_BLOCK")
            
            raise PlannerInvocationError("Empty response from provider.", "EMPTY_RESPONSE")

        # Parse JSON
        try:
            decision_dict = json.loads(response_text)
        except json.JSONDecodeError as e:
            raise PlannerInvocationError(f"Malformed JSON output: {e}", "JSON_DECODE_ERROR") from e
            
        if not isinstance(decision_dict, dict):
            raise PlannerInvocationError("JSON output is not an object", "INVALID_STRUCTURE")
            
        # Clean up output: the LLM might hallucinate extra fields, but `validate_planner_decision` is strict 
        # on structural requirements, though it doesn't explicitly forbid extra keys. We rely on the adapter 
        # normalization to ensure output is mapped to exactly what Stage 21 requires.
        
        # Enforce exact normalization
        decision_val = decision_dict.get("decision")
        if decision_val not in ("EXECUTE_STEP", "COMPLETE", "FAIL"):
            # Normalize unrecognized decisions to FAIL rather than passing them through 
            # (which would just fail Stage 21 validation)
            decision_val = "FAIL"
            
        normalized = {"decision": decision_val}
        
        if decision_val == "EXECUTE_STEP":
            next_step = decision_dict.get("next_step")
            if isinstance(next_step, dict):
                step_type_val = next_step.get("step_type")
                if step_type_val not in ("QUERY_PIPELINE", "CONVERSATION_MEMORY", "CONVERSATION_APPEND", "TOOL_INVOCATION"):
                    # If LLM produces invalid step type, convert it to a FAIL decision
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


def gemini_planner_factory(settings: ProviderSettings, raw_credential: Optional[str]) -> PlannerLLMAdapter:
    """
    Factory invoked by Phase 1.1 wire_dependencies().
    Consumes raw_credential exactly once to build the client.
    """
    # Construction-time validation
    if not raw_credential:
        raise ValueError("Gemini Planner provider requires a credential (API key)")
    
    # Optional endpoint or timeouts could be read from `extra` here
    # For Gemini, genai.Client uses api_key.
    client = genai.Client(api_key=raw_credential)
    return GeminiPlannerLLMAdapter(client)


def get_provider_registration() -> ProviderRegistration:
    """
    Registration dict for Phase 1.1.
    """
    return {
        "seam": "PLANNER_LLM_PROVIDER",
        "provider_name": "gemini",
        "network_dependent": True,
        "factory": gemini_planner_factory
    }
