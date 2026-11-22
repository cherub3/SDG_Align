import pytest
from unittest.mock import MagicMock
from openai import OpenAI, APIError

from scripts.llm_provider_openrouter import (
    OpenRouterLLMAdapter,
    openrouter_llm_factory,
    get_provider_registration
)
from scripts.stage13_llm_execution import (
    LLMTransientError,
    LLMAuthError,
    LLMInvalidRequestError
)

def test_openrouter_llm_adapter_invoke_success():
    mock_client = MagicMock()
    mock_response = MagicMock()
    
    mock_choice = MagicMock()
    mock_choice.message.content = "Test response"
    mock_choice.finish_reason = "stop"
    mock_response.choices = [mock_choice]
    
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 10
    mock_usage.completion_tokens = 20
    mock_usage.total_tokens = 30
    mock_response.usage = mock_usage
    mock_response.model = "openrouter/llama3"
    mock_response.id = "req_123"
    
    mock_client.chat.completions.create.return_value = mock_response
    
    adapter = OpenRouterLLMAdapter(mock_client)
    
    config = {
        "model_name": "openrouter/llama3",
        "temperature": 0.5,
        "max_output_tokens": 100
    }
    
    result = adapter.invoke("Sys prompt", "User prompt", config)
    
    assert result.response_text == "Test response"
    assert result.finish_reason == "complete"
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 20
    assert result.total_tokens == 30
    assert result.provider_request_id == "req_123"
    
    mock_client.chat.completions.create.assert_called_once_with(
        model="openrouter/llama3",
        messages=[
            {"role": "system", "content": "Sys prompt"},
            {"role": "user", "content": "User prompt"}
        ],
        temperature=0.5,
        max_tokens=100
    )

def test_openrouter_llm_adapter_auth_error():
    mock_client = MagicMock()
    error_request = MagicMock()
    
    mock_error = APIError("Auth failed", request=error_request, body={"error": "Auth failed"})
    mock_error.status_code = 401
    mock_client.chat.completions.create.side_effect = mock_error
    
    adapter = OpenRouterLLMAdapter(mock_client)
    
    with pytest.raises(LLMAuthError):
        adapter.invoke("", "prompt", {"model_name": "openrouter/llama3"})

def test_openrouter_llm_factory():
    settings = {
        "seam": "LLM_PROVIDER",
        "provider_name": "openrouter",
        "credential_ref": "env:OPENROUTER_API_KEY",
        "extra": {}
    }
    
    with pytest.raises(ValueError, match="requires a credential"):
        openrouter_llm_factory(settings, None)
        
    adapter = openrouter_llm_factory(settings, "fake-key")
    assert isinstance(adapter, OpenRouterLLMAdapter)

def test_get_provider_registration():
    reg = get_provider_registration()
    assert reg["seam"] == "LLM_PROVIDER"
    assert reg["provider_name"] == "openrouter"
    assert reg["network_dependent"] is True
    assert reg["factory"] == openrouter_llm_factory
