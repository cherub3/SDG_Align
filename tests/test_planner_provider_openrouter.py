import pytest
import json
from unittest.mock import MagicMock
from openai import OpenAI, APIError

from scripts.planner_provider_openrouter import (
    OpenRouterPlannerLLMAdapter,
    openrouter_planner_factory,
    get_provider_registration
)
from scripts.stage21_agent_planning import PlannerInvocationError

def test_openrouter_planner_adapter_plan_success():
    mock_client = MagicMock()
    mock_response = MagicMock()
    
    mock_choice = MagicMock()
    valid_decision = {
        "decision": "EXECUTE_STEP",
        "next_step": {
            "step_type": "QUERY_PIPELINE",
            "step_input": {"query": "test"},
            "step_rationale": "testing"
        }
    }
    mock_choice.message.content = json.dumps(valid_decision)
    mock_choice.finish_reason = "stop"
    mock_response.choices = [mock_choice]
    
    mock_client.chat.completions.create.return_value = mock_response
    
    adapter = OpenRouterPlannerLLMAdapter(mock_client)
    
    config = {
        "model_name": "openrouter/llama3",
        "temperature": 0.1
    }
    
    result = adapter.plan("User prompt", config)
    
    assert result["decision"] == "EXECUTE_STEP"
    assert result["next_step"]["step_type"] == "QUERY_PIPELINE"
    assert result["next_step"]["step_input"] == {"query": "test"}
    assert result["next_step"]["step_rationale"] == "testing"

def test_openrouter_planner_adapter_invalid_json():
    mock_client = MagicMock()
    mock_response = MagicMock()
    
    mock_choice = MagicMock()
    mock_choice.message.content = "{ invalid json"
    mock_response.choices = [mock_choice]
    
    mock_client.chat.completions.create.return_value = mock_response
    
    adapter = OpenRouterPlannerLLMAdapter(mock_client)
    
    with pytest.raises(PlannerInvocationError, match="Malformed JSON output"):
        adapter.plan("Prompt", {"model_name": "llama3"})

def test_openrouter_planner_factory():
    settings = {
        "seam": "PLANNER_LLM_PROVIDER",
        "provider_name": "openrouter",
        "credential_ref": "env:OPENROUTER_API_KEY",
        "extra": {}
    }
    
    with pytest.raises(ValueError, match="requires a credential"):
        openrouter_planner_factory(settings, None)
        
    adapter = openrouter_planner_factory(settings, "fake-key")
    assert isinstance(adapter, OpenRouterPlannerLLMAdapter)

def test_get_provider_registration():
    reg = get_provider_registration()
    assert reg["seam"] == "PLANNER_LLM_PROVIDER"
    assert reg["provider_name"] == "openrouter"
    assert reg["network_dependent"] is True
    assert reg["factory"] == openrouter_planner_factory
