import os
import pytest
from scripts.phase1_1_configuration_layer import (
    load_raw_settings,
    validate_settings,
    build_provider_registry,
    resolve_provider_settings,
    wire_dependencies,
    validate_wiring_result,
    redacted_view,
    ConfigurationInputError,
    ConfigurationWiringError,
    ConfigurationInternalError,
    REDACTED_FIELD_NAMES,
    SUPPORTED_SEAMS
)

# Mock factory for testing
def mock_factory(settings, credential):
    return {"configured_provider": settings["provider_name"], "credential": credential}

def test_load_raw_settings():
    # Test dictionary input
    env = {"LLM_PROVIDER": "test_provider", "LLM_PROVIDER_CREDENTIAL_REF": "env:MOCK_KEY"}
    raw = load_raw_settings(env=env)
    assert raw["values"]["LLM_PROVIDER"] == "test_provider"
    assert raw["values"]["LLM_PROVIDER_CREDENTIAL_REF"] == "env:MOCK_KEY"
    assert raw["dotenv_path_loaded"] is None

def test_validate_settings_success():
    raw = {
        "values": {
            "LLM_PROVIDER": "mock_llm",
            "LLM_PROVIDER_CREDENTIAL_REF": "env:MOCK_API_KEY",
            "LLM_PROVIDER_EXTRA_MODEL_NAME": "mock-model",
            "NETWORK_CALLS_PERMITTED": "false"
        },
        "dotenv_path_loaded": None
    }
    app_settings = validate_settings(raw)
    assert app_settings["runtime"]["network_calls_permitted"] is False
    assert "LLM_PROVIDER" in app_settings["providers"]
    provider = app_settings["providers"]["LLM_PROVIDER"]
    assert provider["provider_name"] == "mock_llm"
    assert provider["credential_ref"] == "env:MOCK_API_KEY"
    assert provider["extra"]["model_name"] == "mock-model"
    assert "settings_fingerprint" in app_settings

def test_validate_settings_failures():
    # Unknown seam
    with pytest.raises(ConfigurationInputError, match="UNKNOWN_SEAM"):
        validate_settings({"values": {"INVALID_PROVIDER": "value"}, "dotenv_path_loaded": None})
    
    # Malformed credential ref
    with pytest.raises(ConfigurationInputError, match="CREDENTIAL_REF_MALFORMED"):
        validate_settings({
            "values": {
                "LLM_PROVIDER": "mock",
                "LLM_PROVIDER_CREDENTIAL_REF": "wrong_prefix:API_KEY"
            },
            "dotenv_path_loaded": None
        })
        
    # Bad types
    with pytest.raises(ConfigurationInputError, match="FIELD_TYPE_INVALID"):
        validate_settings([]) # type: ignore

def test_required_field_missing():
    # M2: A credential_ref key for a seam is present, but the provider_name key is absent.
    # Architecture §Configuration Validation §1: this must raise REQUIRED_FIELD_MISSING.
    with pytest.raises(ConfigurationInputError, match="REQUIRED_FIELD_MISSING"):
        validate_settings({
            "values": {
                # LLM_PROVIDER key is absent — no provider_name supplied.
                # LLM_PROVIDER_CREDENTIAL_REF is present — the seam is "configured" but incomplete.
                "LLM_PROVIDER_CREDENTIAL_REF": "env:SOME_KEY"
            },
            "dotenv_path_loaded": None
        })

    # Also verify that an EXTRA_ key alone triggers REQUIRED_FIELD_MISSING.
    with pytest.raises(ConfigurationInputError, match="REQUIRED_FIELD_MISSING"):
        validate_settings({
            "values": {
                "EMBEDDING_PROVIDER_EXTRA_DIM": "768"
            },
            "dotenv_path_loaded": None
        })

def test_build_provider_registry():
    regs = [
        {"seam": "LLM_PROVIDER", "provider_name": "mock_llm", "network_dependent": False, "factory": mock_factory}
    ]
    registry = build_provider_registry(regs)
    assert "mock_llm" in registry["LLM_PROVIDER"]
    
    # Duplicate
    regs.append({"seam": "LLM_PROVIDER", "provider_name": "mock_llm", "network_dependent": True, "factory": mock_factory})
    with pytest.raises(ConfigurationWiringError, match="PROVIDER_ALREADY_REGISTERED"):
        build_provider_registry(regs)

def test_resolve_provider_settings():
    raw = {"values": {"LLM_PROVIDER": "mock_llm"}, "dotenv_path_loaded": None}
    app_settings = validate_settings(raw)
    
    provider = resolve_provider_settings(app_settings, "LLM_PROVIDER")
    assert provider["provider_name"] == "mock_llm"
    
    with pytest.raises(ConfigurationWiringError, match="SEAM_NOT_CONFIGURED"):
        resolve_provider_settings(app_settings, "EMBEDDING_PROVIDER")

def test_wire_dependencies(monkeypatch):
    monkeypatch.setenv("MOCK_API_KEY", "secret-value")
    
    raw = {
        "values": {
            "LLM_PROVIDER": "mock_llm",
            "LLM_PROVIDER_CREDENTIAL_REF": "env:MOCK_API_KEY",
            "NETWORK_CALLS_PERMITTED": "true"
        },
        "dotenv_path_loaded": None
    }
    app_settings = validate_settings(raw)
    
    registry = build_provider_registry([
        {"seam": "LLM_PROVIDER", "provider_name": "mock_llm", "network_dependent": True, "factory": mock_factory}
    ])
    
    result = wire_dependencies(app_settings, registry)
    assert "LLM_PROVIDER" in result["wired"]
    instance = result["wired"]["LLM_PROVIDER"]
    assert instance["configured_provider"] == "mock_llm"
    assert instance["credential"] == "secret-value"
    
def test_wire_dependencies_failures():
    raw = {
        "values": {
            "LLM_PROVIDER": "mock_llm",
            "NETWORK_CALLS_PERMITTED": "false"
        },
        "dotenv_path_loaded": None
    }
    app_settings = validate_settings(raw)
    
    # Provider not registered
    registry = build_provider_registry([])
    with pytest.raises(ConfigurationWiringError, match="PROVIDER_NOT_REGISTERED"):
        wire_dependencies(app_settings, registry)
        
    # Network calls disabled
    registry = build_provider_registry([
        {"seam": "LLM_PROVIDER", "provider_name": "mock_llm", "network_dependent": True, "factory": mock_factory}
    ])
    with pytest.raises(ConfigurationWiringError, match="NETWORK_CALLS_DISABLED"):
        wire_dependencies(app_settings, registry)

def test_validate_wiring_result():
    raw = {"values": {"LLM_PROVIDER": "mock"}, "dotenv_path_loaded": None}
    app_settings = validate_settings(raw)
    
    registry = build_provider_registry([
        {"seam": "LLM_PROVIDER", "provider_name": "mock", "network_dependent": False, "factory": mock_factory}
    ])
    result = wire_dependencies(app_settings, registry)
    
    # Success
    validate_wiring_result(result, app_settings)
    
    # Fingerprint mismatch
    import copy
    bad_result = copy.deepcopy(result)
    bad_result["settings_fingerprint"] = "bad"
    with pytest.raises(ConfigurationInternalError, match="WIRING_SETTINGS_FINGERPRINT_MISMATCH"):
        validate_wiring_result(bad_result, app_settings)
        
    # Count mismatch
    bad_result2 = copy.deepcopy(result)
    bad_result2["wired"]["EMBEDDING_PROVIDER"] = {}
    with pytest.raises(ConfigurationInternalError, match="WIRING_SEAM_COUNT_MISMATCH"):
        validate_wiring_result(bad_result2, app_settings)

    # M5: Content tampering — the settings object's providers dict is mutated but the stored
    # fingerprint string is left unchanged. With fresh recomputation, this must be detected.
    import copy as _copy
    tampered_settings = _copy.deepcopy(app_settings)
    # Corrupt the providers content without touching the stored fingerprint string.
    tampered_settings["providers"]["LLM_PROVIDER"]["provider_name"] = "tampered"
    with pytest.raises(ConfigurationInternalError, match="WIRING_SETTINGS_FINGERPRINT_MISMATCH"):
        validate_wiring_result(result, tampered_settings)

def test_redacted_view():
    raw = {"values": {"LLM_PROVIDER": "mock"}, "dotenv_path_loaded": None}
    app_settings = validate_settings(raw)
    
    # Since REDACTED_FIELD_NAMES is currently empty, it should be identical (except ignoring some types if any)
    view = redacted_view(app_settings)
    assert view["providers"]["LLM_PROVIDER"]["provider_name"] == "mock"
