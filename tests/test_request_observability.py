import sys
import unittest
from typing import Dict, Any
from unittest.mock import patch, Mock
from pathlib import Path

src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.request_observability import observe_request, ObservationRecord

class TestRequestObservability(unittest.TestCase):
    def setUp(self):
        self.dummy_app_instance: Dict[str, Any] = {}
        self.dummy_request: Dict[str, Any] = {"input": "test"}
        self.dummy_result: Dict[str, Any] = {"output": "result"}

    @patch('scripts.request_observability.execute_request')
    @patch('scripts.request_observability.ObservationRecord')
    def test_successful_request_observation(self, mock_record_class, mock_execute):
        mock_execute.return_value = self.dummy_result
        
        result = observe_request(self.dummy_app_instance, self.dummy_request)
        
        # Verify underlying result unchanged
        self.assertIs(result, self.dummy_result)
        
        # Verify record produced with completed outcome
        mock_record_class.assert_called_once()
        kwargs = mock_record_class.call_args.kwargs
        self.assertIn("correlation_id", kwargs)
        self.assertEqual(kwargs["outcome"], "completed")
        self.assertIsInstance(kwargs["duration"], float)

    @patch('scripts.request_observability.execute_request')
    @patch('scripts.request_observability.ObservationRecord')
    def test_failed_request_observation_and_exception_identity(self, mock_record_class, mock_execute):
        class DummyError(Exception):
            pass
            
        dummy_exc = DummyError("test error")
        mock_execute.side_effect = dummy_exc
        
        with self.assertRaises(DummyError) as cm:
            observe_request(self.dummy_app_instance, self.dummy_request)
            
        # Verify exception identity unchanged
        self.assertIs(cm.exception, dummy_exc)
        
        # Verify record produced with failed outcome
        mock_record_class.assert_called_once()
        kwargs = mock_record_class.call_args.kwargs
        self.assertEqual(kwargs["outcome"], "failed")

    @patch('scripts.request_observability.execute_request')
    @patch('scripts.request_observability.ObservationRecord')
    def test_unique_correlation_identities(self, mock_record_class, mock_execute):
        mock_execute.return_value = self.dummy_result
        
        observe_request(self.dummy_app_instance, self.dummy_request)
        observe_request(self.dummy_app_instance, self.dummy_request)
        
        self.assertEqual(mock_record_class.call_count, 2)
        id1 = mock_record_class.call_args_list[0].kwargs["correlation_id"]
        id2 = mock_record_class.call_args_list[1].kwargs["correlation_id"]
        self.assertNotEqual(id1, id2)

    def test_immutable_observation_records(self):
        record = ObservationRecord("cid", "completed", 1.0)
        
        with self.assertRaises(AttributeError):
            record.correlation_id = "new"  # type: ignore
            
        with self.assertRaises(AttributeError):
            record.outcome = "failed"  # type: ignore

    @patch('scripts.request_observability.execute_request')
    @patch('scripts.request_observability.ObservationRecord')
    def test_no_payload_leakage(self, mock_record_class, mock_execute):
        mock_execute.return_value = self.dummy_result
        observe_request(self.dummy_app_instance, self.dummy_request)
        
        kwargs = mock_record_class.call_args.kwargs
        for val in kwargs.values():
            self.assertIsNot(val, self.dummy_request)
            self.assertIsNot(val, self.dummy_result)

    @patch('scripts.request_observability.execute_request')
    def test_runtime_invocation_count_unchanged(self, mock_execute):
        mock_execute.return_value = self.dummy_result
        observe_request(self.dummy_app_instance, self.dummy_request)
        mock_execute.assert_called_once_with(
            application_instance=self.dummy_app_instance, 
            agent_request=self.dummy_request
        )

if __name__ == "__main__":
    unittest.main()
