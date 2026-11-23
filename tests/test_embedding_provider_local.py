"""Local sentence-transformers embedding adapter. Unit tests use a fake model (no torch needed);
the last test runs the real model and is skipped when requirements-local.txt is not installed."""
import math
import os
import sys

import numpy as np
import pytest

from scripts.embedding_provider_local import (
    DEFAULT_MODEL_NAME, DEFAULT_MODEL_VERSION, DEFAULT_REVISION, LocalEmbeddingAdapter,
    get_provider_registration, local_factory,
)
from scripts.pipeline_deps_factory import make_provider_adapter_factory
from scripts.stage8_embedding_generation import ProviderAdapter
from scripts.stage10_retrieval import EmbeddingModelMismatchError


class FakeModel:
    def __init__(self):
        self.calls = []

    def encode(self, texts, batch_size, convert_to_numpy, normalize_embeddings, show_progress_bar):
        self.calls.append((list(texts), batch_size, normalize_embeddings))
        return np.array([[3.0, 4.0, 0.0] if t != "zero" else [0.0, 0.0, 0.0] for t in texts])


def _adapter(**kw):
    model = FakeModel()
    return LocalEmbeddingAdapter(model_loader=lambda: model, **kw), model


def test_identity_and_contract():
    a, _ = _adapter()
    assert isinstance(a, ProviderAdapter)
    assert (a.provider_name, a.model_name, a.model_version) == ("local", DEFAULT_MODEL_NAME, DEFAULT_MODEL_VERSION)
    assert a.is_transient_error(RuntimeError("x")) is False
    assert a.config_fingerprint_fields["revision"] == DEFAULT_REVISION


def test_vectors_are_l2_normalised_and_dimension_is_discovered():
    a, _ = _adapter()
    with pytest.raises(RuntimeError):
        a.embedding_dimension
    vecs = a.embed_batch(["a", "b"])
    assert a.embedding_dimension == 3
    for v in vecs:
        assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, rel_tol=1e-6)
    assert vecs[0] == pytest.approx([0.6, 0.8, 0.0])


def test_zero_vector_stays_zero_not_nan():
    a, _ = _adapter()
    assert a.embed_batch(["zero"])[0] == [0.0, 0.0, 0.0]


def test_empty_input_returns_empty_without_loading_the_model():
    loaded = []
    a = LocalEmbeddingAdapter(model_loader=lambda: loaded.append(1) or FakeModel())
    assert a.embed_batch([]) == [] and loaded == []


def test_model_is_loaded_lazily_once_and_batch_size_is_passed():
    loads = []
    model = FakeModel()
    a = LocalEmbeddingAdapter(batch_size=7, model_loader=lambda: loads.append(1) or model)
    assert loads == []
    a.embed_batch(["x"]); a.embed_batch(["y"])
    assert loads == [1] and model.calls[0][1] == 7 and model.calls[0][2] is False
    assert a.max_batch_size == 7


def test_construction_does_not_import_the_heavy_libraries():
    before = "sentence_transformers" in sys.modules
    LocalEmbeddingAdapter()
    assert ("sentence_transformers" in sys.modules) == before


def test_floating_version_alias_and_bad_batch_size_rejected():
    with pytest.raises(ValueError):
        LocalEmbeddingAdapter(model_version="latest")
    with pytest.raises(ValueError):
        LocalEmbeddingAdapter(batch_size=0)


def test_factory_and_registration():
    reg = get_provider_registration()
    assert (reg["seam"], reg["provider_name"], reg["network_dependent"]) == ("EMBEDDING_PROVIDER", "local", False)
    a = local_factory({"extra": {"batch_size": "8", "model_version": "v9"}}, None)
    assert a.model_version == "v9" and a.max_batch_size == 8


def test_index_guard_accepts_the_local_adapter_and_rejects_another_model():
    a, _ = _adapter()
    factory = make_provider_adapter_factory(a)
    assert factory("local", DEFAULT_MODEL_NAME, DEFAULT_MODEL_VERSION) is a
    with pytest.raises(EmbeddingModelMismatchError):
        factory("local", "BAAI/bge-base-en-v1.5", DEFAULT_MODEL_VERSION)
    with pytest.raises(EmbeddingModelMismatchError):
        factory("huggingface", DEFAULT_MODEL_NAME, DEFAULT_MODEL_VERSION)   # same model, other provider
    with pytest.raises(EmbeddingModelMismatchError):
        factory("local", DEFAULT_MODEL_NAME, "v2")


def test_backend_registers_the_local_provider():
    from scripts.backend_server import _build_registrations
    assert ("EMBEDDING_PROVIDER", "local") in [(r["seam"], r["provider_name"]) for r in _build_registrations()]


def test_real_model_is_deterministic_and_normalised():
    pytest.importorskip("sentence_transformers", reason="optional: pip install -r requirements-local.txt")
    a = LocalEmbeddingAdapter()
    texts = ["Mercury use in artisanal gold mining.", "Marine protected areas of Ecuador."]
    v1, v2 = a.embed_batch(texts), a.embed_batch(texts)
    assert v1 == v2 and a.embedding_dimension == 384
    assert math.isclose(sum(x * x for x in v1[0]), 1.0, rel_tol=1e-5)


# ---------------- fix 6: offline at query time, a missing model is a clear error, never a silent download ----------------

@pytest.fixture(autouse=True)
def _restore_offline_env():
    """The loader sets HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE in os.environ on purpose; do not leak that into other tests."""
    keys = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "ALLOW_MODEL_DOWNLOAD")
    saved = {k: os.environ.get(k) for k in keys}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class _FakeTorch:
    def __init__(self):
        self.threads = None

    def set_num_threads(self, n):
        self.threads = n


def _install_fake_st(monkeypatch, behaviour):
    """Puts fake torch / sentence_transformers modules in sys.modules; records the env and kwargs the loader sees."""
    import types
    seen = {}

    class FakeST:
        def __init__(self, name, **kw):
            seen["kwargs"] = kw
            seen["env"] = (os.environ.get("HF_HUB_OFFLINE"), os.environ.get("TRANSFORMERS_OFFLINE"))
            behaviour(name, kw)

        def eval(self):
            seen["eval"] = True

    st = types.ModuleType("sentence_transformers")
    st.SentenceTransformer = FakeST
    monkeypatch.setitem(sys.modules, "sentence_transformers", st)
    monkeypatch.setitem(sys.modules, "torch", _FakeTorch())
    return seen


def test_loader_is_offline_by_default(monkeypatch):
    from scripts.embedding_provider_local import _load_sentence_transformer
    for v in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "ALLOW_MODEL_DOWNLOAD"):
        monkeypatch.delenv(v, raising=False)
    seen = _install_fake_st(monkeypatch, lambda n, kw: None)
    _load_sentence_transformer("m", "rev", 1)
    assert seen["kwargs"]["local_files_only"] is True
    assert seen["env"] == ("1", "1")                      # set before the model is touched, not left to the caller
    assert seen["kwargs"]["revision"] == "rev" and seen["eval"] is True


def test_offline_flags_override_a_hostile_environment(monkeypatch):
    from scripts.embedding_provider_local import _load_sentence_transformer
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    monkeypatch.delenv("ALLOW_MODEL_DOWNLOAD", raising=False)
    seen = _install_fake_st(monkeypatch, lambda n, kw: None)
    _load_sentence_transformer("m", "rev", 1)
    assert seen["env"][0] == "1" and seen["kwargs"]["local_files_only"] is True


def test_a_model_missing_from_the_cache_gives_a_clear_error(monkeypatch):
    from scripts.embedding_provider_local import LocalModelUnavailableError, _load_sentence_transformer
    monkeypatch.delenv("ALLOW_MODEL_DOWNLOAD", raising=False)

    def boom(name, kw):
        raise OSError("not in cache")
    _install_fake_st(monkeypatch, boom)
    with pytest.raises(LocalModelUnavailableError, match="not in the local Hugging Face cache") as e:
        _load_sentence_transformer("BAAI/x", "rev", 1)
    assert "ALLOW_MODEL_DOWNLOAD" in str(e.value) and "BAAI/x" in str(e.value)


def test_download_needs_an_explicit_opt_in(monkeypatch):
    from scripts.embedding_provider_local import _load_sentence_transformer
    monkeypatch.setenv("ALLOW_MODEL_DOWNLOAD", "true")
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    seen = _install_fake_st(monkeypatch, lambda n, kw: None)
    _load_sentence_transformer("m", "rev", 1)
    assert seen["kwargs"]["local_files_only"] is False and seen["env"][0] is None


def test_warm_up_loads_the_model_once_and_surfaces_a_load_failure():
    calls = []
    a = LocalEmbeddingAdapter(model_loader=lambda: calls.append(1) or FakeModel())
    a.warm_up()
    a.warm_up()
    assert calls == [1]

    def bad():
        raise RuntimeError("model missing")
    with pytest.raises(RuntimeError, match="model missing"):
        LocalEmbeddingAdapter(model_loader=bad).warm_up()
