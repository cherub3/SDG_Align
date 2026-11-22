import sys
import unittest
from typing import Dict, Any
from unittest.mock import patch, Mock
from pathlib import Path

src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.runtime_orchestration import execute_request
from scripts.stage21_agent_planning import AgentPlanningInternalError, AgentPlanningInputError

class TestRuntimeOrchestration(unittest.TestCase):
    def setUp(self):
        self.mock_deps = Mock()
        self.dummy_application_instance: Dict[str, Any] = {
            "agent_dependencies": self.mock_deps
        }
        self.dummy_request: Dict[str, Any] = {"user_message": "Hello"}
        self.dummy_result: Dict[str, Any] = {"status": "SUCCESS"}

    @patch('scripts.runtime_orchestration.plan_and_execute')
    def test_successful_request_execution(self, mock_plan_and_execute):
        # 1. successful request execution
        # 3. exactly one invocation
        mock_plan_and_execute.return_value = self.dummy_result
        
        result = execute_request(self.dummy_application_instance, self.dummy_request)
        
        self.assertEqual(result, self.dummy_result)
        mock_plan_and_execute.assert_called_once_with(
            agent_request=self.dummy_request,
            agent_dependencies=self.mock_deps
        )

    @patch('scripts.runtime_orchestration.plan_and_execute')
    def test_failure_propagation(self, mock_plan_and_execute):
        # 2. failure propagation
        # 9. no retries
        exceptions = [
            AgentPlanningInputError("Invalid input"),
            AgentPlanningInternalError("Internal error"),
            ValueError("Other error")
        ]
        
        for exc in exceptions:
            mock_plan_and_execute.side_effect = exc
            mock_plan_and_execute.reset_mock()
            
            with self.assertRaises(type(exc)) as cm:
                execute_request(self.dummy_application_instance, self.dummy_request)
                
            self.assertIs(cm.exception, exc)
            mock_plan_and_execute.assert_called_once()  # Asserts no retries

    @patch('scripts.runtime_orchestration.plan_and_execute')
    def test_deterministic_execution(self, mock_plan_and_execute):
        # 4. deterministic execution
        mock_plan_and_execute.return_value = self.dummy_result
        
        result1 = execute_request(self.dummy_application_instance, self.dummy_request)
        result2 = execute_request(self.dummy_application_instance, self.dummy_request)
        
        self.assertEqual(result1, result2)

    @patch('scripts.runtime_orchestration.plan_and_execute')
    def test_request_isolation_and_ownership(self, mock_plan_and_execute):
        # 5. request ownership
        # 6. request isolation
        # 7. repeated request execution
        # Ensure that repeated requests produce isolated results
        result_obj_1 = {"id": 1}
        result_obj_2 = {"id": 2}
        mock_plan_and_execute.side_effect = [result_obj_1, result_obj_2]
        
        res1 = execute_request(self.dummy_application_instance, {"req": 1})
        res2 = execute_request(self.dummy_application_instance, {"req": 2})
        
        self.assertIsNot(res1, res2)
        self.assertNotEqual(res1, res2)
        self.assertEqual(mock_plan_and_execute.call_count, 2)

    @patch('scripts.runtime_orchestration.plan_and_execute')
    def test_binary_completion(self, mock_plan_and_execute):
        # 8. binary completion
        # Success yields a result object
        mock_plan_and_execute.return_value = self.dummy_result
        mock_plan_and_execute.side_effect = None
        res = execute_request(self.dummy_application_instance, self.dummy_request)
        self.assertIsInstance(res, dict)
        
        # Failure yields an exception
        mock_plan_and_execute.side_effect = ValueError("FAIL")
        with self.assertRaises(ValueError):
            execute_request(self.dummy_application_instance, self.dummy_request)



    @patch('scripts.runtime_orchestration.plan_and_execute')
    def test_malformed_application_instance_caller_violation(self, mock_plan_and_execute):
        # Caller contract violation: ApplicationInstance missing "agent_dependencies" key.
        # This KeyError originates in the runtime before the frozen public request-processing
        # contract is ever invoked. The architecture states the runtime introduces no new
        # validation layer and receives an already-bootstrapped instance as a finished, opaque
        # object — a missing key is a caller's responsibility, not the runtime's.
        malformed_instance: Dict[str, Any] = {}  # "agent_dependencies" key absent

        with self.assertRaises(KeyError):
            execute_request(malformed_instance, self.dummy_request)

        mock_plan_and_execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
