import pytest
import json
from unittest.mock import MagicMock
from groq import APIError

from scripts.planner_provider_groq import (
    GroqPlannerLLMAdapter,
    groq_planner_factory,
    get_provider_registration
)
from scripts.stage21_agent_planning import PlannerInvocationError


def test_groq_planner_adapter_plan_success():
    mock_client = MagicMock()
    mock_response = MagicMock()
    
    mock_choice = MagicMock()
    
    expected_output = {
        "decision": "EXECUTE_STEP",
        "next_step": {
            "step_type": "QUERY_PIPELINE",
            "step_input": {"test": "val"},
            "step_rationale": "I am testing"
        }
    }
    mock_choice.message.content = json.dumps(expected_output)
    mock_choice.finish_reason = "stop"
    mock_response.choices = [mock_choice]
    
    mock_client.chat.completions.create.return_value = mock_response
    
    adapter = GroqPlannerLLMAdapter(mock_client)
    
    config = {
        "model_name": "llama3-70b-8192",
        "temperature": 0.0,
    }
    
    result = adapter.plan("User prompt", config)
    
    assert result["decision"] == "EXECUTE_STEP"
    assert result["next_step"]["step_type"] == "QUERY_PIPELINE"
    
    mock_client.chat.completions.create.assert_called_once()
    kwargs = mock_client.chat.completions.create.call_args[1]
    assert kwargs["model"] == "llama3-70b-8192"
    assert kwargs["response_format"] == {"type": "json_object"}
    assert len(kwargs["messages"]) == 2
    assert kwargs["messages"][1]["content"] == "User prompt"


def test_groq_planner_adapter_invalid_json():
    mock_client = MagicMock()
    mock_response = MagicMock()
    
    mock_choice = MagicMock()
    mock_choice.message.content = "{ invalid json"
    mock_choice.finish_reason = "stop"
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response
    
    adapter = GroqPlannerLLMAdapter(mock_client)
    
    with pytest.raises(PlannerInvocationError) as exc_info:
        adapter.plan("Prompt", {"model_name": "llama"})
        
    assert exc_info.value.code == "JSON_DECODE_ERROR"


def test_groq_planner_adapter_safety_block():
    mock_client = MagicMock()
    mock_response = MagicMock()
    
    mock_choice = MagicMock()
    mock_choice.message.content = ""
    mock_choice.finish_reason = "content_filter"
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response
    
    adapter = GroqPlannerLLMAdapter(mock_client)
    
    with pytest.raises(PlannerInvocationError) as exc_info:
        adapter.plan("Prompt", {"model_name": "llama"})
        
    assert exc_info.value.code == "SAFETY_BLOCK"


def test_groq_planner_factory():
    settings = {
        "seam": "PLANNER_LLM_PROVIDER",
        "provider_name": "groq",
        "credential_ref": "env:GROQ_API_KEY",
        "extra": {}
    }
    
    with pytest.raises(ValueError, match="requires a credential"):
        groq_planner_factory(settings, None)
        
    adapter = groq_planner_factory(settings, "fake-key")
    assert isinstance(adapter, GroqPlannerLLMAdapter)


def test_get_provider_registration():
    reg = get_provider_registration()
    assert reg["seam"] == "PLANNER_LLM_PROVIDER"
    assert reg["provider_name"] == "groq"
    assert reg["network_dependent"] is True
    assert reg["factory"] == groq_planner_factory
