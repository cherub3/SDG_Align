import os
import json
import hashlib
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, TypedDict

try:
    from dotenv import load_dotenv, dotenv_values
except ImportError:
    load_dotenv = None
    dotenv_values = None

# =================================================================================================
# Constants
# =================================================================================================
CONFIGURATION_LAYER_VERSION = "1.0.0"

DEFAULT_DOTENV_FILENAME = ".env"

SUPPORTED_SEAMS = (
    "EMBEDDING_PROVIDER",
    "INDEX_BACKEND",
    "LLM_PROVIDER",
    "CACHE_BACKEND",
    "CONVERSATION_STORE",
    "TOOL_REGISTRY",
    "TOOL_ADAPTER",
    "PLANNER_LLM_PROVIDER",
)

REDACTED_FIELD_NAMES = ()

# =================================================================================================
# Exceptions
# =================================================================================================
class ConfigurationInputError(ValueError):
    """Raised by validate_settings() on structural or range violations."""
    pass

class ConfigurationWiringError(RuntimeError):
    """Raised by build_provider_registry(), resolve_provider_settings(), or wire_dependencies()."""
    pass

class ConfigurationInternalError(RuntimeError):
    """Raised by validate_wiring_result() on internal invariant violations."""
    pass

# =================================================================================================
# Schemas
# =================================================================================================
class RawSettings(TypedDict):
    values: Dict[str, str]
    dotenv_path_loaded: Optional[str]

class ProviderSettings(TypedDict):
    seam: str
    provider_name: str
    credential_ref: Optional[str]
    extra: Dict[str, Any]

class RuntimeConfig(TypedDict):
    dotenv_path_loaded: Optional[str]
    network_calls_permitted: bool
    configuration_layer_version: str

class ApplicationSettings(TypedDict):
    settings_fingerprint: str
    runtime: RuntimeConfig
    providers: Dict[str, ProviderSettings]

class ProviderRegistration(TypedDict):
    seam: str
    provider_name: str
    network_dependent: bool
    factory: Callable[[ProviderSettings, Optional[str]], Any]

ProviderRegistry = Dict[str, Dict[str, ProviderRegistration]]

class WiringResult(TypedDict):
    settings_fingerprint: str
    wired: Dict[str, Any]

# =================================================================================================
# Lifecycle Helpers
# =================================================================================================
def redacted_view(settings: ApplicationSettings) -> Dict[str, Any]:
    """Returns a copy of settings with redacted fields masked."""
    def redact_dict(d: Dict[str, Any]) -> Dict[str, Any]:
        out = {}
        for k, v in d.items():
            if k in REDACTED_FIELD_NAMES:
                out[k] = "<redacted>"
            elif isinstance(v, dict):
                out[k] = redact_dict(v)
            else:
                out[k] = v
        return out
    
    return redact_dict(settings)  # type: ignore

def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(',', ':'))

def _compute_settings_fingerprint(redacted_settings_dict: Dict[str, Any]) -> str:
    canonical = _canonical_json(redacted_settings_dict)
    return "cfg_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

# =================================================================================================
# Validations
# =================================================================================================
def validate_settings(raw: RawSettings) -> ApplicationSettings:
    """Validates RawSettings and produces an immutable ApplicationSettings."""
    
    if not isinstance(raw, dict):
        raise ConfigurationInputError("FIELD_TYPE_INVALID: RawSettings must be a dict")
        
    values = raw.get("values", {})
    if not isinstance(values, dict):
        raise ConfigurationInputError("FIELD_TYPE_INVALID: RawSettings.values must be a dict")
        
    network_calls_permitted = values.get("NETWORK_CALLS_PERMITTED", "false").lower() == "true"
    
    providers: Dict[str, ProviderSettings] = {}
    
    for seam in SUPPORTED_SEAMS:
        provider_name = values.get(seam)
        credential_ref_key = f"{seam}_CREDENTIAL_REF"
        extra_prefix = f"{seam}_EXTRA_"

        # Determine whether any peripheral key signals this seam is "present" in configuration.
        # Architecture §Configuration Validation §1: REQUIRED_FIELD_MISSING is triggered when
        # "a configured seam entry is present with no provider_name".
        seam_has_peripheral_keys = (
            credential_ref_key in values
            or any(k.startswith(extra_prefix) for k in values)
        )

        if provider_name is None and seam_has_peripheral_keys:
            # A seam's peripheral keys are present but the required provider_name is missing.
            raise ConfigurationInputError(
                f"REQUIRED_FIELD_MISSING: {seam} has configuration keys but no provider_name"
            )

        if provider_name:
            if not isinstance(provider_name, str):
                raise ConfigurationInputError(f"FIELD_TYPE_INVALID: {seam} must be a string")

            credential_ref = values.get(credential_ref_key)
            if credential_ref:
                if not isinstance(credential_ref, str):
                    raise ConfigurationInputError(f"FIELD_TYPE_INVALID: {credential_ref_key} must be a string")
                if not credential_ref.startswith("env:"):
                    raise ConfigurationInputError(f"CREDENTIAL_REF_MALFORMED: {credential_ref} must start with 'env:'")

            # Extract provider-specific extras via the EXTRA_ prefix passthrough.
            extra = {}
            for k, v in values.items():
                if k.startswith(extra_prefix):
                    extra_key = k[len(extra_prefix):].lower()
                    extra[extra_key] = v

            providers[seam] = {
                "seam": seam,
                "provider_name": provider_name,
                "credential_ref": credential_ref,
                "extra": extra
            }
            
    # Check if there are any unrecognized seams configured (using a heuristic or explicit configuration object mapping)
    # The architecture expects us to catch UNKNOWN_SEAM.
    # If the user supplied configuration for a seam not in SUPPORTED_SEAMS, we must raise.
    # Since we extract strictly based on SUPPORTED_SEAMS above, let's also scan all keys.
    for k in values.keys():
        if k.endswith("_PROVIDER") or k.endswith("_BACKEND") or k.endswith("_STORE") or k.endswith("_REGISTRY") or k.endswith("_ADAPTER"):
            # If it looks like a seam name, check if it's supported
            base_seam = k
            if base_seam not in SUPPORTED_SEAMS and not k.startswith("NETWORK_"):
                # Exception: it could be an extra or credential ref for a supported seam
                is_valid = False
                for s in SUPPORTED_SEAMS:
                    if k.startswith(s):
                        is_valid = True
                        break
                if not is_valid:
                    raise ConfigurationInputError(f"UNKNOWN_SEAM: {base_seam} is not a supported seam")
    
    runtime: RuntimeConfig = {
        "dotenv_path_loaded": raw.get("dotenv_path_loaded"),
        "network_calls_permitted": network_calls_permitted,
        "configuration_layer_version": CONFIGURATION_LAYER_VERSION
    }
    
    settings_without_fingerprint = {
        "runtime": runtime,
        "providers": providers
    }
    
    fingerprint = _compute_settings_fingerprint(redact_dict_func(settings_without_fingerprint))
    
    return {
        "settings_fingerprint": fingerprint,
        "runtime": runtime,
        "providers": providers
    }

def redact_dict_func(d: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k, v in d.items():
        if k in REDACTED_FIELD_NAMES:
            out[k] = "<redacted>"
        elif isinstance(v, dict):
            out[k] = redact_dict_func(v)
        else:
            out[k] = v
    return out

def validate_wiring_result(result: WiringResult, settings: ApplicationSettings) -> None:
    # M5 fix: recompute the fingerprint fresh from the current ApplicationSettings object,
    # exactly as the architecture requires: "recomputed fresh" (§Configuration Validation §3).
    # This catches any tampering with the settings object's contents independent of the stored
    # fingerprint string — not merely a comparison of two previously stored strings.
    settings_without_fingerprint = {
        "runtime": settings["runtime"],
        "providers": settings["providers"]
    }
    recomputed_fingerprint = _compute_settings_fingerprint(redact_dict_func(settings_without_fingerprint))
    if result["settings_fingerprint"] != recomputed_fingerprint:
        raise ConfigurationInternalError("WIRING_SETTINGS_FINGERPRINT_MISMATCH")

    configured_seams = set(settings["providers"].keys())
    wired_seams = set(result["wired"].keys())

    if len(wired_seams) != len(configured_seams):
        raise ConfigurationInternalError("WIRING_SEAM_COUNT_MISMATCH")

    for seam in wired_seams:
        if seam not in SUPPORTED_SEAMS:
            raise ConfigurationInternalError("WIRING_UNKNOWN_SEAM_PRESENT")

# =================================================================================================
# Registry
# =================================================================================================
def build_provider_registry(registrations: Sequence[ProviderRegistration]) -> ProviderRegistry:
    registry: ProviderRegistry = {}
    
    for reg in registrations:
        seam = reg["seam"]
        provider_name = reg["provider_name"]
        
        if seam not in registry:
            registry[seam] = {}
            
        if provider_name in registry[seam]:
            raise ConfigurationWiringError(f"PROVIDER_ALREADY_REGISTERED: {seam} / {provider_name}")
            
        registry[seam][provider_name] = reg
        
    return registry

def resolve_provider_settings(settings: ApplicationSettings, seam: str) -> ProviderSettings:
    if seam not in settings["providers"]:
        raise ConfigurationWiringError(f"SEAM_NOT_CONFIGURED: {seam}")
    return settings["providers"][seam]

# =================================================================================================
# Public Entrypoints
# =================================================================================================
def load_raw_settings(env: Optional[Mapping[str, str]] = None, dotenv_path: Optional[str] = None) -> RawSettings:
    values: Dict[str, str] = {}
    loaded_path = None
    
    if dotenv_path and dotenv_values:
        parsed = dotenv_values(dotenv_path)
        if parsed:
            for k, v in parsed.items():
                if v is not None:
                    values[k] = v
            loaded_path = dotenv_path

            # Fold into the same key/value space os.environ occupies (Inputs: "never a second,
            # separately-merged configuration channel") so wire_dependencies()'s later direct
            # os.environ.get(var_name) credential lookup can see .env-sourced values. Only applies
            # in production mode (env=None) -- an explicit `env` mapping is the Determinism test
            # path and must never mutate real process state. load_dotenv()'s default
            # override=False preserves real os.environ entries over the .env file's.
            if env is None and load_dotenv:
                load_dotenv(dotenv_path)

    source_env = env if env is not None else os.environ
    for k, v in source_env.items():
        values[k] = v
        
    return {
        "values": values,
        "dotenv_path_loaded": loaded_path
    }

def wire_dependencies(settings: ApplicationSettings, registry: ProviderRegistry) -> WiringResult:
    wired = {}
    
    for seam, provider_settings in settings["providers"].items():
        provider_name = provider_settings["provider_name"]
        
        if seam not in registry or provider_name not in registry[seam]:
            raise ConfigurationWiringError(f"PROVIDER_NOT_REGISTERED: {seam} / {provider_name}")
            
        registration = registry[seam][provider_name]
        
        if registration["network_dependent"] and not settings["runtime"]["network_calls_permitted"]:
            raise ConfigurationWiringError(f"NETWORK_CALLS_DISABLED: {seam} / {provider_name}")
            
        raw_credential = None
        credential_ref = provider_settings.get("credential_ref")
        
        if credential_ref:
            # Format is "env:VAR_NAME"
            var_name = credential_ref[4:]
            raw_credential = os.environ.get(var_name)
            
        # Invoke factory
        instance = registration["factory"](provider_settings, raw_credential)
        wired[seam] = instance
        
        # Cleanup transient credential
        del raw_credential
        
    return {
        "settings_fingerprint": settings["settings_fingerprint"],
        "wired": wired
    }
