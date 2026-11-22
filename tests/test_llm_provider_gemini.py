import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from unittest.mock import Mock, patch

from scripts.llm_provider_gemini import (
    GeminiLLMAdapter,
    gemini_llm_factory,
    get_provider_registration
)
from scripts.stage13_llm_execution import (
    LLMTransientError,
    LLMAuthError,
    LLMInvalidRequestError,
)
from scripts.phase1_1_configuration_layer import ProviderSettings
from google.genai import errors


class TestGeminiLLMFactory(unittest.TestCase):
    def setUp(self):
        self.settings: ProviderSettings = {
            "seam": "LLM_PROVIDER",
            "provider_name": "gemini",
            "credential_ref": "secret/gemini-api-key",
            "extra": {}
        }

    @patch('scripts.llm_provider_gemini.genai.Client')
    def test_factory_success(self, mock_client_cls):
        adapter = gemini_llm_factory(self.settings, "valid_key")
        self.assertIsInstance(adapter, GeminiLLMAdapter)
        mock_client_cls.assert_called_once_with(api_key="valid_key")

    def test_factory_missing_credential(self):
        with self.assertRaisesRegex(ValueError, "requires a credential"):
            gemini_llm_factory(self.settings, None)

    def test_factory_floating_alias_in_default(self):
        self.settings["extra"]["default_model_name"] = "latest"
        with self.assertRaisesRegex(ValueError, "must be pinned"):
            gemini_llm_factory(self.settings, "valid_key")


class TestGeminiLLMAdapter(unittest.TestCase):
    def test_model_version_reported_initial_state(self):
        mock_client = Mock()
        adapter = GeminiLLMAdapter(mock_client)
        self.assertIsNone(adapter.model_version_reported)

    def setUp(self):
        self.mock_client = Mock()
        self.adapter = GeminiLLMAdapter(self.mock_client)
        self.config = {
            "model_name": "gemini-2.0-flash",
            "temperature": 0.7,
            "max_output_tokens": 1000
        }

    def test_invoke_success(self):
        mock_response = Mock()
        mock_response.text = "Hello world"
        mock_response.model_version = "gemini-2.0-flash-001"
        
        mock_candidate = Mock()
        mock_candidate.finish_reason = "STOP"
        mock_response.candidates = [mock_candidate]
        
        mock_usage = Mock()
        mock_usage.prompt_token_count = 10
        mock_usage.candidates_token_count = 5
        mock_usage.total_token_count = 15
        mock_response.usage_metadata = mock_usage
        mock_response.prompt_feedback = None

        self.mock_client.models.generate_content.return_value = mock_response

        result = self.adapter.invoke("system prompt", "user prompt", self.config)

        self.mock_client.models.generate_content.assert_called_once()
        self.assertEqual(result.response_text, "Hello world")
        self.assertEqual(result.finish_reason, "complete")
        self.assertEqual(result.prompt_tokens, 10)
        self.assertEqual(result.completion_tokens, 5)
        self.assertEqual(result.total_tokens, 15)
        self.assertEqual(self.adapter.model_version_reported, "gemini-2.0-flash-001")
        self.assertIsNone(result.provider_request_id)

    def test_invoke_missing_usage(self):
        mock_response = Mock()
        mock_response.text = "Hello"
        mock_response.model_version = None
        mock_candidate = Mock()
        mock_candidate.finish_reason = "MAX_TOKENS"
        mock_response.candidates = [mock_candidate]
        mock_response.usage_metadata = None
        
        self.mock_client.models.generate_content.return_value = mock_response

        result = self.adapter.invoke("", "test", self.config)
        self.assertEqual(result.finish_reason, "length")
        self.assertIsNone(result.prompt_tokens)
        self.assertIsNone(result.completion_tokens)
        self.assertIsNone(result.total_tokens)
        self.assertIsNone(self.adapter.model_version_reported)

    def test_invoke_computed_total_tokens(self):
        mock_response = Mock()
        mock_response.text = "Hello"
        mock_candidate = Mock()
        mock_candidate.finish_reason = "STOP"
        mock_response.candidates = [mock_candidate]
        
        mock_usage = Mock()
        mock_usage.prompt_token_count = 10
        mock_usage.candidates_token_count = 5
        mock_usage.total_token_count = None  # Missing
        mock_response.usage_metadata = mock_usage
        
        self.mock_client.models.generate_content.return_value = mock_response

        result = self.adapter.invoke("", "test", self.config)
        self.assertEqual(result.total_tokens, 15)  # Computed

    def test_invoke_safety_block_finish_reason(self):
        mock_response = Mock()
        mock_response.text = ""
        mock_candidate = Mock()
        mock_candidate.finish_reason = "SAFETY"
        mock_response.candidates = [mock_candidate]
        self.mock_client.models.generate_content.return_value = mock_response

        result = self.adapter.invoke("", "test", self.config)
        self.assertEqual(result.finish_reason, "content_filter")

    def test_invoke_safety_block_prompt(self):
        # Triggered via prompt_feedback
        mock_response = Mock()
        mock_response.text = ""
        mock_response.candidates = []
        mock_feedback = Mock()
        mock_feedback.block_reason = "SAFETY"
        mock_response.prompt_feedback = mock_feedback
        
        # Simulating SDK raising ValueError on response.text when no parts
        type(mock_response).text = property(lambda self: (_ for _ in ()).throw(ValueError("Cannot get text")))
        
        self.mock_client.models.generate_content.return_value = mock_response

        result = self.adapter.invoke("", "test", self.config)
        self.assertEqual(result.response_text, "")
        self.assertEqual(result.finish_reason, "content_filter")

    def test_invoke_exception_translation_transient(self):
        self.mock_client.models.generate_content.side_effect = errors.APIError(503, "Unavailable", None)
        with self.assertRaises(LLMTransientError):
            self.adapter.invoke("", "test", self.config)

    def test_invoke_exception_translation_auth(self):
        self.mock_client.models.generate_content.side_effect = errors.APIError(403, "Forbidden", None)
        with self.assertRaises(LLMAuthError):
            self.adapter.invoke("", "test", self.config)

    def test_invoke_exception_translation_invalid_request(self):
        self.mock_client.models.generate_content.side_effect = errors.APIError(400, "Bad Request", None)
        with self.assertRaises(LLMInvalidRequestError):
            self.adapter.invoke("", "test", self.config)

    def test_invoke_exception_translation_network(self):
        class ConnectError(Exception): pass
        self.mock_client.models.generate_content.side_effect = ConnectError("Connection refused")
        with self.assertRaises(LLMTransientError):
            self.adapter.invoke("", "test", self.config)

    def test_sdk_client_not_exposed(self):
        public_attrs = [a for a in dir(self.adapter) if not a.startswith("_")]
        for attr in public_attrs:
            val = getattr(self.adapter, attr)
            self.assertIsNot(val, self.mock_client)


class TestGeminiLLMRegistration(unittest.TestCase):
    def test_registration(self):
        reg = get_provider_registration()
        self.assertEqual(reg["seam"], "LLM_PROVIDER")
        self.assertEqual(reg["provider_name"], "gemini")
        self.assertTrue(reg["network_dependent"])
        self.assertIs(reg["factory"], gemini_llm_factory)

if __name__ == "__main__":
    unittest.main()
