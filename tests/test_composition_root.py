import sys
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.composition_root import compose_application, _discover_index_fingerprints
from scripts.phase1_1_configuration_layer import (
    ConfigurationInputError,
    ConfigurationWiringError,
    ConfigurationInternalError,
    ProviderRegistration
)
from scripts.stage21_agent_planning import AgentDependencies


class TestCompositionRoot(unittest.TestCase):
    def setUp(self):
        self.valid_env = {
            "LLM_PROVIDER": "gemini",
            "EMBEDDING_PROVIDER": "gemini",
            "PLANNER_LLM_PROVIDER": "gemini",
            "LLM_PROVIDER_CREDENTIAL_REF": "env:LLM_KEY",
            "EMBEDDING_PROVIDER_CREDENTIAL_REF": "env:EMB_KEY",
            "PLANNER_LLM_PROVIDER_CREDENTIAL_REF": "env:PLAN_KEY",
            "LLM_KEY": "dummy_key",
            "EMB_KEY": "dummy_key",
            "PLAN_KEY": "dummy_key",
            "DEFAULT_PLANNER_MODEL_NAME": "gemini-test-model"
        }
        
        self.mock_llm_reg = {"seam": "LLM_PROVIDER", "provider_name": "gemini", "network_dependent": False, "factory": Mock()}
        self.mock_emb_reg = {"seam": "EMBEDDING_PROVIDER", "provider_name": "gemini", "network_dependent": False, "factory": Mock()}
        self.mock_planner_reg = {"seam": "PLANNER_LLM_PROVIDER", "provider_name": "gemini", "network_dependent": False, "factory": Mock()}
        self.registrations = [self.mock_llm_reg, self.mock_emb_reg, self.mock_planner_reg]

    def test_successful_composition(self):
        app_graph = compose_application(self.registrations, env=self.valid_env)
        
        self.assertIn("llm_adapter", app_graph)
        self.assertIn("embedding_adapter", app_graph)
        self.assertIn("agent_dependencies", app_graph)
        
        agent_deps = app_graph["agent_dependencies"]
        self.assertIsInstance(agent_deps, AgentDependencies)
        self.assertEqual(agent_deps.default_planner_model_name, "gemini-test-model")
        self.assertIsNotNone(agent_deps.planner_llm_adapter)

    def test_duplicate_registration_propagates(self):
        # Return duplicate registrations
        dup_registrations = [self.mock_llm_reg, self.mock_llm_reg, self.mock_planner_reg]
        
        with self.assertRaises(ConfigurationWiringError) as cm:
            compose_application(dup_registrations, env=self.valid_env)
        self.assertTrue(str(cm.exception).startswith("PROVIDER_ALREADY_REGISTERED"))

    def test_missing_provider_propagates(self):
        # We request "openai" in env, but only "gemini" is registered
        bad_env = dict(self.valid_env)
        bad_env["LLM_PROVIDER"] = "openai"
        
        with self.assertRaises(ConfigurationWiringError) as cm:
            compose_application(self.registrations, env=bad_env)
        self.assertTrue(str(cm.exception).startswith("PROVIDER_NOT_REGISTERED"))

    def test_wiring_failure_propagates(self):
        def failing_factory(settings, cred):
            raise ValueError("Network error in SDK construction")
            
        failing_reg = {"seam": "LLM_PROVIDER", "provider_name": "gemini", "network_dependent": False, "factory": failing_factory}
        registrations = [failing_reg, self.mock_emb_reg, self.mock_planner_reg]

        with self.assertRaisesRegex(ValueError, "Network error"):
            compose_application(registrations, env=self.valid_env)

    def test_dependency_ownership(self):
        # Ensure that the assembled AgentDependencies holds the exact planner adapter
        mock_planner_adapter = Mock()
        planner_reg = {"seam": "PLANNER_LLM_PROVIDER", "provider_name": "gemini", "network_dependent": False, "factory": lambda s, c: mock_planner_adapter}
        registrations = [self.mock_llm_reg, self.mock_emb_reg, planner_reg]
        
        app_graph = compose_application(registrations, env=self.valid_env)
        self.assertIs(app_graph["agent_dependencies"].planner_llm_adapter, mock_planner_adapter)

    def test_startup_failure_propagation(self):
        # Provide invalid seam to trigger UNKNOWN_SEAM
        with self.assertRaises(ConfigurationInputError) as cm:
            compose_application([], env={"UNKNOWN_SEAM_PROVIDER": "something"})
        self.assertTrue(str(cm.exception).startswith("UNKNOWN_SEAM"))
        
    def test_network_calls_disabled_coverage(self):
        # F5 - NETWORK_CALLS_DISABLED coverage
        bad_env = dict(self.valid_env)
        bad_env["NETWORK_CALLS_PERMITTED"] = "false"
        
        network_dep_reg = {"seam": "LLM_PROVIDER", "provider_name": "gemini", "network_dependent": True, "factory": Mock()}
        registrations = [network_dep_reg, self.mock_emb_reg, self.mock_planner_reg]
        
        with self.assertRaises(ConfigurationWiringError) as cm:
            compose_application(registrations, env=bad_env)
        self.assertTrue(str(cm.exception).startswith("NETWORK_CALLS_DISABLED"))

    @patch('scripts.composition_root.validate_wiring_result')
    def test_validate_wiring_result_propagation(self, mock_validate):
        # F6 - ConfigurationInternalError from validate_wiring_result propagates
        mock_validate.side_effect = ConfigurationInternalError("WIRING_SETTINGS_FINGERPRINT_MISMATCH")
        
        with self.assertRaises(ConfigurationInternalError) as cm:
            compose_application(self.registrations, env=self.valid_env)
        self.assertTrue(str(cm.exception).startswith("WIRING_SETTINGS_FINGERPRINT_MISMATCH"))

    def test_full_agent_dependencies_wiring(self):
        """compose_application() now wires all AgentDependencies fields (Phase 13)."""
        app_graph = compose_application(self.registrations, env=self.valid_env)
        agent_deps = app_graph["agent_dependencies"]

        # Conversation hooks — bound partials, callable with the Stage 21 calling convention
        self.assertIsNotNone(agent_deps.get_conversation)
        self.assertIsNotNone(agent_deps.select_memory)
        self.assertIsNotNone(agent_deps.append_turn)
        self.assertTrue(callable(agent_deps.get_conversation))
        self.assertTrue(callable(agent_deps.select_memory))
        self.assertTrue(callable(agent_deps.append_turn))

        # Tool execution — Stage 20's execute_tool assigned directly
        self.assertIsNotNone(agent_deps.execute_tool)
        self.assertTrue(callable(agent_deps.execute_tool))

        # Tool registry and adapter — empty but non-None
        self.assertIsNotNone(agent_deps.tool_registry)
        self.assertIsNotNone(agent_deps.tool_adapter)

        # PipelineDependencies — built when both LLM and embedding adapters are present
        self.assertIsNotNone(agent_deps.pipeline_deps)
        self.assertIn("retrieve", agent_deps.pipeline_deps)
        self.assertIn("llm_adapter", agent_deps.pipeline_deps)
        self.assertIn("cache_adapter", agent_deps.pipeline_deps)
        self.assertIn("default_model_name", agent_deps.pipeline_deps)

        # handle_request — Stage 18's function assigned directly
        self.assertIsNotNone(agent_deps.handle_request)
        self.assertTrue(callable(agent_deps.handle_request))


if __name__ == "__main__":
    unittest.main()


class TestDiscoverIndexFingerprints(unittest.TestCase):
    """Only indexes built by the SAME embedding provider, model AND version may be searched by default."""

    class _Adapter:
        provider_name = "huggingface"
        model_name = "BAAI/bge-small-en-v1.5"
        model_version = "v1.5"

    def setUp(self):
        import os
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._cwd = os.getcwd()
        os.chdir(self._tmp.name)
        self.addCleanup(os.chdir, self._cwd)
        self.root = Path("data/proposals/vector_index")

    def _write_index(self, fp, **meta):
        d = self.root / fp
        d.mkdir(parents=True)
        (d / "index_metadata.json").write_text(__import__("json").dumps({"index_fingerprint": fp, **meta}), encoding="utf-8")

    def test_only_the_exactly_matching_index_is_returned(self):
        self._write_index("good", provider="huggingface", model_name="BAAI/bge-small-en-v1.5", model_version="v1.5")
        self._write_index("other_provider", provider="gemini", model_name="BAAI/bge-small-en-v1.5", model_version="v1.5")
        self._write_index("other_model", provider="huggingface", model_name="BAAI/bge-base-en-v1.5", model_version="v1.5")
        self._write_index("other_version", provider="huggingface", model_name="BAAI/bge-small-en-v1.5", model_version="v2.0")
        self._write_index("stub", provider="stub_provider", model_name="stub-model", model_version="v1.0")
        self.assertEqual(_discover_index_fingerprints(self._Adapter()), ["good"])

    def test_missing_directory_no_adapter_and_corrupt_metadata_yield_nothing_or_are_skipped(self):
        self.assertEqual(_discover_index_fingerprints(self._Adapter()), [])      # no vector_index dir yet
        self._write_index("good", provider="huggingface", model_name="BAAI/bge-small-en-v1.5", model_version="v1.5")
        bad = self.root / "corrupt"
        bad.mkdir()
        (bad / "index_metadata.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(_discover_index_fingerprints(self._Adapter()), ["good"])
        self.assertEqual(_discover_index_fingerprints(None), [])

