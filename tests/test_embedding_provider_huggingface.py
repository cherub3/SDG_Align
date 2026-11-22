import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import requests

# Adjust path to import from src/scripts
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.embedding_provider_huggingface import HuggingFaceEmbeddingAdapter, huggingface_factory, get_provider_registration


class TestHuggingFaceEmbeddingProvider(unittest.TestCase):
    def setUp(self):
        self.adapter = HuggingFaceEmbeddingAdapter(
            token="fake-token",
            model_name="BAAI/bge-small-en-v1.5",
            model_version="v1.5"
        )
        
    def test_provider_identity(self):
        self.assertEqual(self.adapter.provider_name, "huggingface")
        self.assertEqual(self.adapter.model_name, "BAAI/bge-small-en-v1.5")
        self.assertEqual(self.adapter.model_version, "v1.5")
        
    @patch('scripts.embedding_provider_huggingface.requests.post')
    def test_embed_batch(self, mock_post):
        # Setup mock response
        mock_response = Mock()
        mock_response.json.return_value = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        mock_post.return_value = mock_response
        
        texts = ["hello", "world"]
        vectors = self.adapter.embed_batch(texts)
        
        mock_post.assert_called_once_with(
            self.adapter._url,
            headers={"Authorization": "Bearer fake-token"},
            json={"inputs": texts}
        )
        mock_response.raise_for_status.assert_called_once()
        self.assertEqual(vectors, [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
        self.assertEqual(self.adapter.embedding_dimension, 3)
        
    def test_embedding_dimension_before_discovery_raises(self):
        with self.assertRaisesRegex(RuntimeError, "not yet discovered"):
            _ = self.adapter.embedding_dimension
            
    def test_is_transient_error_api_errors(self):
        # Transient cases
        for code in (429, 500, 502, 503, 504):
            response = Mock()
            response.status_code = code
            exc = requests.exceptions.HTTPError(response=response)
            self.assertTrue(self.adapter.is_transient_error(exc))
            
        # Fatal cases
        for code in (400, 401, 403, 404):
            response = Mock()
            response.status_code = code
            exc = requests.exceptions.HTTPError(response=response)
            self.assertFalse(self.adapter.is_transient_error(exc))
            
    def test_is_transient_error_network_errors(self):
        self.assertTrue(self.adapter.is_transient_error(requests.exceptions.ConnectionError("test")))
        self.assertTrue(self.adapter.is_transient_error(requests.exceptions.Timeout("test")))
        self.assertFalse(self.adapter.is_transient_error(ValueError("test")))

    def test_adapter_properties(self):
        self.assertEqual(self.adapter.requests_per_minute, 500)
        self.assertEqual(self.adapter.max_batch_size, 32)
        self.assertEqual(self.adapter.config_fingerprint_fields, {})

    # --- Architectural compliance tests ---

    def test_provider_identity_immutable(self):
        """Phase 1.3 § Provider Identity: triple is fixed for adapter lifetime; no setter exists."""
        with self.assertRaises(AttributeError):
            self.adapter.provider_name = "other"
        with self.assertRaises(AttributeError):
            self.adapter.model_name = "other-model"
        with self.assertRaises(AttributeError):
            self.adapter.model_version = "999"

    def test_config_fingerprint_fields_deterministic(self):
        """Phase 1.3 § Determinism: config_fingerprint_fields is a pure function of the instance."""
        result1 = self.adapter.config_fingerprint_fields
        result2 = self.adapter.config_fingerprint_fields
        self.assertEqual(result1, result2)

    def test_sdk_client_not_exposed_as_public_attribute(self):
        """Phase 1.3 § SDK client ownership: the client never escapes the adapter instance."""
        public_attrs = [a for a in dir(self.adapter) if not a.startswith("_")]
        for attr in public_attrs:
            try:
                val = getattr(self.adapter, attr)
            except (RuntimeError, Exception):
                # Properties that raise before discovery (e.g. embedding_dimension) are acceptable
                continue
            self.assertIsNot(
                val, "fake-token",
                msg=f"SDK client/credential escaped via public attribute '{attr}'"
            )

    @patch('scripts.embedding_provider_huggingface.requests.post')
    def test_embed_batch_dimension_discovered_only_once(self, mock_post):
        """Phase 1.3 § Embedding Lifecycle: dimension is cached after first discovery."""
        mock_response = Mock()
        mock_response.json.return_value = [[0.1, 0.2, 0.3]]
        mock_post.return_value = mock_response

        self.adapter.embed_batch(["first"])
        self.assertEqual(self.adapter.embedding_dimension, 3)

        # Change what the mock returns (different dimension) — cached value must not change
        mock_response2 = Mock()
        mock_response2.json.return_value = [[0.1, 0.2]]
        mock_post.return_value = mock_response2

        self.adapter.embed_batch(["second"])
        # Dimension must remain the originally discovered value
        self.assertEqual(self.adapter.embedding_dimension, 3)


class TestHuggingFaceFactory(unittest.TestCase):
    def setUp(self):
        self.valid_settings = {
            "extra": {
                "model_name": "BAAI/bge-small-en-v1.5",
                "model_version": "v1.5"
            }
        }
        
    def test_factory_success(self):
        adapter = huggingface_factory(self.valid_settings, "fake-api-key")
        
        self.assertIsInstance(adapter, HuggingFaceEmbeddingAdapter)
        self.assertEqual(adapter.model_name, "BAAI/bge-small-en-v1.5")
        self.assertEqual(adapter.model_version, "v1.5")
        
    def test_factory_defaults(self):
        # Test that omitting model_name and model_version correctly uses the defaults
        settings = {"extra": {}}
        adapter = huggingface_factory(settings, "fake-api-key")
        self.assertEqual(adapter.model_name, "BAAI/bge-small-en-v1.5")
        self.assertEqual(adapter.model_version, "v1.5")

    def test_factory_latest_model_version_rejected(self):
        settings = {"extra": {"model_name": "model", "model_version": "latest"}}
        with self.assertRaisesRegex(ValueError, "must be pinned"):
            huggingface_factory(settings, "fake-api-key")

    def test_factory_all_unpinned_aliases_rejected(self):
        """Phase 1.3 § Model Pinning: 'stable', 'preview', 'beta' are floating aliases."""
        for alias in ("stable", "preview", "beta", "LATEST", "STABLE", "Preview"):
            settings = {"extra": {"model_name": "model", "model_version": alias}}
            with self.subTest(alias=alias):
                with self.assertRaisesRegex(ValueError, "must be pinned"):
                    huggingface_factory(settings, "fake-api-key")

    def test_factory_missing_credential(self):
        with self.assertRaisesRegex(ValueError, "requires a credential"):
            huggingface_factory(self.valid_settings, None)
        with self.assertRaisesRegex(ValueError, "requires a credential"):
            huggingface_factory(self.valid_settings, "")

    def test_factory_returned_adapter_does_not_expose_credential(self):
        """Phase 1.3 § Security: no public attribute on returned adapter holds raw credential."""
        credential = "top-secret-key"
        adapter = huggingface_factory(self.valid_settings, credential)
        public_attrs = [a for a in dir(adapter) if not a.startswith("_")]
        for attr in public_attrs:
            try:
                val = getattr(adapter, attr)
            except (RuntimeError, Exception):
                continue
            if isinstance(val, str):
                self.assertNotEqual(
                    val, credential,
                    msg=f"Raw credential leaked via public attribute '{attr}'"
                )


class TestHuggingFaceRegistration(unittest.TestCase):
    def test_get_provider_registration(self):
        reg = get_provider_registration()
        self.assertEqual(reg["seam"], "EMBEDDING_PROVIDER")
        self.assertEqual(reg["provider_name"], "huggingface")
        self.assertTrue(reg["network_dependent"])
        self.assertEqual(reg["factory"], huggingface_factory)


if __name__ == '__main__':
    unittest.main()
