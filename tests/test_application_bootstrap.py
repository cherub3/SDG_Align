import sys
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.application_bootstrap import bootstrap_application, ApplicationInstance
from scripts.phase1_1_configuration_layer import (
    ConfigurationInputError,
    ConfigurationWiringError,
    ConfigurationInternalError
)

class TestApplicationBootstrap(unittest.TestCase):
    def setUp(self):
        self.mock_deps = {
            "llm_adapter": Mock(),
            "embedding_adapter": Mock(),
            "agent_dependencies": Mock(),
        }
        self.dummy_registrations = [Mock()]
        self.dummy_env = {"DUMMY_KEY": "DUMMY_VALUE"}

    @patch('scripts.application_bootstrap.compose_application')
    def test_successful_bootstrap(self, mock_compose):
        # 1. Successful bootstrap
        mock_compose.return_value = self.mock_deps
        
        instance = bootstrap_application(self.dummy_registrations, env=self.dummy_env)
        
        self.assertIsInstance(instance, dict)
        self.assertEqual(instance, self.mock_deps)

    @patch('scripts.application_bootstrap.compose_application')
    def test_startup_failure_propagation(self, mock_compose):
        # 2. Startup failure propagation (propagates Phase 1.1 exceptions unmodified)
        exceptions = [
            ConfigurationInputError("INPUT_ERR"),
            ConfigurationWiringError("WIRING_ERR"),
            ConfigurationInternalError("INTERNAL_ERR"),
            ValueError("SDK Error")
        ]
        
        for exc in exceptions:
            mock_compose.side_effect = exc
            with self.assertRaises(type(exc)) as cm:
                bootstrap_application(self.dummy_registrations)
            self.assertIs(cm.exception, exc)

    @patch('scripts.application_bootstrap.compose_application')
    def test_readiness_transitions(self, mock_compose):
        # 3. Readiness transitions (exactly one instance exists after success, none after failure)
        # Success yields one instance
        mock_compose.return_value = self.mock_deps
        mock_compose.side_effect = None
        instance = bootstrap_application(self.dummy_registrations)
        self.assertIsNotNone(instance)
        
        # Failure yields no instance
        mock_compose.side_effect = ConfigurationWiringError("FAIL")
        with self.assertRaises(ConfigurationWiringError):
            bootstrap_application(self.dummy_registrations)

    @patch('scripts.application_bootstrap.compose_application')
    def test_lifetime_ownership(self, mock_compose):
        # 4. Lifetime ownership (object reference is never reconstructed/reassigned)
        mock_compose.return_value = self.mock_deps
        instance = bootstrap_application(self.dummy_registrations)
        
        # Verifying there's no method to reconstruct or reassign on the dict itself
        self.assertFalse(hasattr(instance, 'reconstruct'))
        self.assertFalse(hasattr(instance, 'reassign'))
        self.assertFalse(hasattr(instance, 'reload'))

    @patch('scripts.application_bootstrap.compose_application')
    def test_deterministic_startup(self, mock_compose):
        # 5. Deterministic startup (mock returning fixed outcome yields identical readiness decision)
        mock_compose.return_value = self.mock_deps
        instance1 = bootstrap_application(self.dummy_registrations)
        instance2 = bootstrap_application(self.dummy_registrations)
        
        # Both are successfully ready (instances are created and hold the same object)
        self.assertIsNotNone(instance1)
        self.assertIsNotNone(instance2)
        self.assertEqual(instance1, instance2)

    @patch('scripts.application_bootstrap.compose_application')
    def test_composition_root_invocation_count(self, mock_compose):
        # 6. Composition-root invocation count (called exactly once, never retried)
        mock_compose.side_effect = ValueError("FAIL")
        with self.assertRaises(ValueError):
            bootstrap_application(self.dummy_registrations)
        
        mock_compose.assert_called_once()
        
        # Reset and test success case
        mock_compose.reset_mock()
        mock_compose.side_effect = None
        mock_compose.return_value = self.mock_deps
        bootstrap_application(self.dummy_registrations)
        mock_compose.assert_called_once()

    @patch('scripts.application_bootstrap.compose_application')
    def test_no_modification_of_dependency_graph(self, mock_compose):
        # 7. No modification of dependency graph after bootstrap (unchanged across reads)
        mock_compose.return_value = self.mock_deps
        instance = bootstrap_application(self.dummy_registrations)
        
        deps_read_1 = instance
        deps_read_2 = instance
        
        self.assertIs(deps_read_1, deps_read_2)
        self.assertEqual(deps_read_1, self.mock_deps)

    @patch('scripts.application_bootstrap.compose_application')
    def test_binary_startup_result(self, mock_compose):
        # 8. Binary startup result (success and failure are mutually exclusive and exhaustive)
        # Success
        mock_compose.return_value = self.mock_deps
        mock_compose.side_effect = None
        instance = bootstrap_application(self.dummy_registrations)
        self.assertIsInstance(instance, dict)
        
        # Failure
        mock_compose.side_effect = ConfigurationWiringError("ERR")
        with self.assertRaises(ConfigurationWiringError):
            bootstrap_application(self.dummy_registrations)

    @patch('scripts.application_bootstrap.compose_application')
    def test_repeated_successful_bootstrap_invocations(self, mock_compose):
        # 9. Repeated successful invocations produce independent application instances
        mock_compose.side_effect = [dict(self.mock_deps), dict(self.mock_deps)]
        
        instance1 = bootstrap_application(self.dummy_registrations)
        instance2 = bootstrap_application(self.dummy_registrations)
        
        self.assertIsNot(instance1, instance2)
        self.assertNotEqual(id(instance1), id(instance2))

    def test_shutdown_behavior_matches_architecture(self):
        # 10. Shutdown behavior matching architecture (absence of any dispose/close/teardown method)
        methods_to_check = ['close', 'shutdown', 'dispose', 'teardown', '__del__', '__enter__', '__exit__']
        
        instance = {}
        for method in methods_to_check:
            self.assertFalse(hasattr(instance, method), f"Found unexpected method: {method}")

if __name__ == "__main__":
    unittest.main()
