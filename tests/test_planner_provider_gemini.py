import sys
import unittest
import json
from pathlib import Path
from unittest.mock import Mock, patch

src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from google.genai import errors

from scripts.planner_provider_gemini import (
    GeminiPlannerLLMAdapter,
    gemini_planner_factory,
    get_provider_registration
)
from scripts.stage21_agent_planning import PlannerInvocationError
from scripts.phase1_1_configuration_layer import ProviderSettings


class TestGeminiPlannerFactory(unittest.TestCase):
    def setUp(self):
        self.settings: ProviderSettings = {
            "seam": "PLANNER_LLM_PROVIDER",
            "provider_name": "gemini",
            "credential_ref": "secret/gemini-api-key",
            "extra": {}
        }

    @patch('scripts.planner_provider_gemini.genai.Client')
    def test_factory_success(self, mock_client_cls):
        adapter = gemini_planner_factory(self.settings, "valid_key")
        self.assertIsInstance(adapter, GeminiPlannerLLMAdapter)
        mock_client_cls.assert_called_once_with(api_key="valid_key")

    def test_factory_missing_credential(self):
        with self.assertRaisesRegex(ValueError, "requires a credential"):
            gemini_planner_factory(self.settings, None)
            
    def test_registration(self):
        reg = get_provider_registration()
        self.assertEqual(reg["seam"], "PLANNER_LLM_PROVIDER")
        self.assertEqual(reg["provider_name"], "gemini")
        self.assertTrue(reg["network_dependent"])
        self.assertIs(reg["factory"], gemini_planner_factory)


class TestGeminiPlannerAdapter(unittest.TestCase):
    def setUp(self):
        self.mock_client = Mock()
        self.adapter = GeminiPlannerLLMAdapter(self.mock_client)
        self.config = {
            "model_name": "gemini-2.0-flash",
            "temperature": 0.2,
            "max_plan_steps": 10
        }
        self.prompt = '{"query": "test"}'

    def test_invoke_success_execute_step(self):
        mock_response = Mock()
        valid_json = {
            "decision": "EXECUTE_STEP",
            "next_step": {
                "step_type": "QUERY_PIPELINE",
                "step_input": {"q": "search"},
                "step_rationale": "need info"
            }
        }
        mock_response.text = json.dumps(valid_json)
        self.mock_client.models.generate_content.return_value = mock_response

        result = self.adapter.plan(self.prompt, self.config)
        
        self.mock_client.models.generate_content.assert_called_once()
        self.assertEqual(result["decision"], "EXECUTE_STEP")
        self.assertEqual(result["next_step"]["step_type"], "QUERY_PIPELINE")
        self.assertEqual(result["next_step"]["step_input"], {"q": "search"})
        self.assertEqual(result["next_step"]["step_rationale"], "need info")
        
    def test_invoke_success_complete(self):
        mock_response = Mock()
        valid_json = {
            "decision": "COMPLETE",
            "final_answer_step_index": 2
        }
        mock_response.text = json.dumps(valid_json)
        self.mock_client.models.generate_content.return_value = mock_response

        result = self.adapter.plan(self.prompt, self.config)
        self.assertEqual(result["decision"], "COMPLETE")
        self.assertEqual(result["final_answer_step_index"], 2)
        
    def test_invoke_success_fail(self):
        mock_response = Mock()
        valid_json = {"decision": "FAIL"}
        mock_response.text = json.dumps(valid_json)
        self.mock_client.models.generate_content.return_value = mock_response

        result = self.adapter.plan(self.prompt, self.config)
        self.assertEqual(result["decision"], "FAIL")
        
    def test_invoke_invalid_decision_normalized_to_fail(self):
        mock_response = Mock()
        valid_json = {"decision": "SOMETHING_ELSE"}
        mock_response.text = json.dumps(valid_json)
        self.mock_client.models.generate_content.return_value = mock_response

        result = self.adapter.plan(self.prompt, self.config)
        self.assertEqual(result["decision"], "FAIL")
        
    def test_invoke_invalid_step_type_normalized_to_fail(self):
        mock_response = Mock()
        valid_json = {
            "decision": "EXECUTE_STEP",
            "next_step": {
                "step_type": "UNKNOWN_TYPE",
                "step_input": {}
            }
        }
        mock_response.text = json.dumps(valid_json)
        self.mock_client.models.generate_content.return_value = mock_response

        result = self.adapter.plan(self.prompt, self.config)
        self.assertEqual(result["decision"], "FAIL")
        
    def test_invoke_json_decode_error(self):
        mock_response = Mock()
        mock_response.text = "NOT JSON"
        self.mock_client.models.generate_content.return_value = mock_response

        with self.assertRaises(PlannerInvocationError) as cm:
            self.adapter.plan(self.prompt, self.config)
        self.assertEqual(cm.exception.code, "JSON_DECODE_ERROR")
        
    def test_invoke_api_error_translation(self):
        self.mock_client.models.generate_content.side_effect = errors.APIError(503, "Unavailable", None)
        with self.assertRaises(PlannerInvocationError) as cm:
            self.adapter.plan(self.prompt, self.config)
        self.assertEqual(cm.exception.code, "503")

    def test_invoke_generic_exception_translation(self):
        class ConnectError(Exception): pass
        self.mock_client.models.generate_content.side_effect = ConnectError("Connection refused")
        with self.assertRaises(PlannerInvocationError) as cm:
            self.adapter.plan(self.prompt, self.config)
        self.assertEqual(cm.exception.code, "ConnectError")

    def test_invoke_safety_block_prompt(self):
        mock_response = Mock()
        mock_response.text = ""
        mock_response.candidates = []
        mock_feedback = Mock()
        mock_feedback.block_reason = "SAFETY"
        mock_response.prompt_feedback = mock_feedback
        
        type(mock_response).text = property(lambda self: (_ for _ in ()).throw(ValueError("Cannot get text")))
        
        self.mock_client.models.generate_content.return_value = mock_response

        with self.assertRaises(PlannerInvocationError) as cm:
            self.adapter.plan(self.prompt, self.config)
        self.assertEqual(cm.exception.code, "SAFETY_BLOCK")
        
    def test_sdk_client_not_exposed(self):
        public_attrs = [a for a in dir(self.adapter) if not a.startswith("_")]
        for attr in public_attrs:
            val = getattr(self.adapter, attr)
            self.assertIsNot(val, self.mock_client)
            
    def test_no_identity_property_exposed(self):
        self.assertFalse(hasattr(self.adapter, "provider_name"))
        self.assertFalse(hasattr(self.adapter, "model_version_reported"))

    def test_invoke_execute_step_without_next_step(self):
        mock_response = Mock()
        valid_json = {"decision": "EXECUTE_STEP"}
        mock_response.text = json.dumps(valid_json)
        self.mock_client.models.generate_content.return_value = mock_response

        result = self.adapter.plan(self.prompt, self.config)
        self.assertEqual(result["decision"], "FAIL")

    def test_invoke_invalid_structure(self):
        mock_response = Mock()
        mock_response.text = "[1, 2, 3]"
        self.mock_client.models.generate_content.return_value = mock_response

        with self.assertRaises(PlannerInvocationError) as cm:
            self.adapter.plan(self.prompt, self.config)
        self.assertEqual(cm.exception.code, "INVALID_STRUCTURE")

    def test_invoke_empty_response(self):
        mock_response = Mock()
        mock_response.text = ""
        mock_response.candidates = []
        mock_response.prompt_feedback = None
        self.mock_client.models.generate_content.return_value = mock_response

        with self.assertRaises(PlannerInvocationError) as cm:
            self.adapter.plan(self.prompt, self.config)
        self.assertEqual(cm.exception.code, "EMPTY_RESPONSE")

    def test_invoke_step_input_normalization(self):
        mock_response = Mock()
        valid_json = {
            "decision": "EXECUTE_STEP",
            "next_step": {
                "step_type": "QUERY_PIPELINE",
                "step_input": None
            }
        }
        mock_response.text = json.dumps(valid_json)
        self.mock_client.models.generate_content.return_value = mock_response

        result = self.adapter.plan(self.prompt, self.config)
        self.assertEqual(result["decision"], "EXECUTE_STEP")
        self.assertEqual(result["next_step"]["step_input"], {})


if __name__ == "__main__":
    unittest.main()
