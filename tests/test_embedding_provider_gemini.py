import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from google.genai import errors

# Adjust path to import from src/scripts
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.embedding_provider_gemini import GeminiEmbeddingAdapter, gemini_factory, get_provider_registration


class TestGeminiEmbeddingProvider(unittest.TestCase):
    def setUp(self):
        self.mock_client = Mock()
        self.adapter = GeminiEmbeddingAdapter(
            client=self.mock_client,
            model_name="text-embedding-004",
            model_version="004"
        )
        
    def test_provider_identity(self):
        self.assertEqual(self.adapter.provider_name, "gemini")
        self.assertEqual(self.adapter.model_name, "text-embedding-004")
        self.assertEqual(self.adapter.model_version, "004")
        
    def test_embed_batch(self):
        # Setup mock response
        mock_response = Mock()
        mock_emb1 = Mock()
        mock_emb1.values = [0.1, 0.2, 0.3]
        mock_emb2 = Mock()
        mock_emb2.values = [0.4, 0.5, 0.6]
        mock_response.embeddings = [mock_emb1, mock_emb2]
        self.mock_client.models.embed_content.return_value = mock_response
        
        texts = ["hello", "world"]
        vectors = self.adapter.embed_batch(texts)
        
        self.mock_client.models.embed_content.assert_called_once_with(
            model="text-embedding-004",
            contents=texts
        )
        self.assertEqual(vectors, [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
        self.assertEqual(self.adapter.embedding_dimension, 3)
        
    def test_embedding_dimension_before_discovery_raises(self):
        with self.assertRaisesRegex(RuntimeError, "not yet discovered"):
            _ = self.adapter.embedding_dimension
            
    def test_is_transient_error_api_errors(self):
        # Transient cases
        for code in (429, 500, 502, 503, 504):
            exc = errors.APIError(code, None, None)
            self.assertTrue(self.adapter.is_transient_error(exc))
            
        # Fatal cases
        for code in (400, 401, 403, 404):
            exc = errors.APIError(code, None, None)
            self.assertFalse(self.adapter.is_transient_error(exc))
            
    def test_is_transient_error_network_errors(self):
        class ConnectError(Exception): pass
        class TimeoutException(Exception): pass
        
        self.assertTrue(self.adapter.is_transient_error(ConnectError("test")))
        self.assertTrue(self.adapter.is_transient_error(TimeoutException("test")))
        self.assertFalse(self.adapter.is_transient_error(ValueError("test")))

    def test_adapter_properties(self):
        self.assertEqual(self.adapter.requests_per_minute, 1500)
        self.assertEqual(self.adapter.max_batch_size, 100)
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
                val, self.mock_client,
                msg=f"SDK client escaped via public attribute '{attr}'"
            )

    def test_embed_batch_dimension_discovered_only_once(self):
        """Phase 1.3 § Embedding Lifecycle: dimension is cached after first discovery."""
        mock_response = Mock()
        mock_emb = Mock()
        mock_emb.values = [0.1, 0.2, 0.3]
        mock_response.embeddings = [mock_emb]
        self.mock_client.models.embed_content.return_value = mock_response

        self.adapter.embed_batch(["first"])
        self.assertEqual(self.adapter.embedding_dimension, 3)

        # Change what the mock returns (different dimension) — cached value must not change
        mock_emb2 = Mock()
        mock_emb2.values = [0.1, 0.2]
        mock_response2 = Mock()
        mock_response2.embeddings = [mock_emb2]
        self.mock_client.models.embed_content.return_value = mock_response2

        self.adapter.embed_batch(["second"])
        # Dimension must remain the originally discovered value
        self.assertEqual(self.adapter.embedding_dimension, 3)


class TestGeminiFactory(unittest.TestCase):
    def setUp(self):
        self.valid_settings = {
            "extra": {
                "model_name": "text-embedding-004",
                "model_version": "004"
            }
        }
        
    @patch('scripts.embedding_provider_gemini.genai.Client')
    def test_factory_success(self, mock_client_cls):
        adapter = gemini_factory(self.valid_settings, "fake-api-key")
        
        mock_client_cls.assert_called_once_with(api_key="fake-api-key")
        self.assertIsInstance(adapter, GeminiEmbeddingAdapter)
        self.assertEqual(adapter.model_name, "text-embedding-004")
        self.assertEqual(adapter.model_version, "004")
        
    def test_factory_missing_model_name(self):
        settings = {"extra": {"model_version": "004"}}
        with self.assertRaisesRegex(ValueError, "requires 'model_name'"):
            gemini_factory(settings, "fake-api-key")
            
    def test_factory_missing_model_version(self):
        settings = {"extra": {"model_name": "text-embedding-004"}}
        with self.assertRaisesRegex(ValueError, "requires 'model_version'"):
            gemini_factory(settings, "fake-api-key")

    def test_factory_latest_model_version_rejected(self):
        settings = {"extra": {"model_name": "text-embedding-004", "model_version": "latest"}}
        with self.assertRaisesRegex(ValueError, "must be pinned"):
            gemini_factory(settings, "fake-api-key")

    def test_factory_all_unpinned_aliases_rejected(self):
        """Phase 1.3 § Model Pinning: 'stable', 'preview', 'beta' are floating aliases."""
        for alias in ("stable", "preview", "beta", "LATEST", "STABLE", "Preview"):
            settings = {"extra": {"model_name": "text-embedding-004", "model_version": alias}}
            with self.subTest(alias=alias):
                with self.assertRaisesRegex(ValueError, "must be pinned"):
                    gemini_factory(settings, "fake-api-key")

    def test_factory_missing_credential(self):
        with self.assertRaisesRegex(ValueError, "requires a credential"):
            gemini_factory(self.valid_settings, None)
        with self.assertRaisesRegex(ValueError, "requires a credential"):
            gemini_factory(self.valid_settings, "")

    @patch('scripts.embedding_provider_gemini.genai.Client')
    def test_factory_credential_consumed_only_once(self, mock_client_cls):
        """Phase 1.3 § Security: credential consumed exactly once at SDK client construction."""
        gemini_factory(self.valid_settings, "secret-key-123")
        mock_client_cls.assert_called_once_with(api_key="secret-key-123")
        self.assertEqual(mock_client_cls.call_count, 1)

    @patch('scripts.embedding_provider_gemini.genai.Client')
    def test_factory_returned_adapter_does_not_expose_credential(self, mock_client_cls):
        """Phase 1.3 § Security: no public attribute on returned adapter holds raw credential."""
        credential = "top-secret-key"
        adapter = gemini_factory(self.valid_settings, credential)
        public_attrs = [a for a in dir(adapter) if not a.startswith("_")]
        for attr in public_attrs:
            try:
                val = getattr(adapter, attr)
            except (RuntimeError, Exception):
                # Properties that raise before discovery (e.g. embedding_dimension) are acceptable
                continue
            if isinstance(val, str):
                self.assertNotEqual(
                    val, credential,
                    msg=f"Raw credential leaked via public attribute '{attr}'"
                )


class TestGeminiRegistration(unittest.TestCase):
    def test_get_provider_registration(self):
        reg = get_provider_registration()
        self.assertEqual(reg["seam"], "EMBEDDING_PROVIDER")
        self.assertEqual(reg["provider_name"], "gemini")
        self.assertTrue(reg["network_dependent"])
        self.assertEqual(reg["factory"], gemini_factory)


if __name__ == '__main__':
    unittest.main()
