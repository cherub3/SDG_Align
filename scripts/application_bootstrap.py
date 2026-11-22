from typing import Dict, Any, Optional, Sequence
from scripts.composition_root import compose_application
from scripts.phase1_1_configuration_layer import ProviderRegistration

# Holds the fully-wired dependency-object set produced by the composition root.
# Represents exactly one ready application instance. 
# Owned as a single unit for the lifetime of the process holding it.
ApplicationInstance = Dict[str, Any]

def bootstrap_application(
    registrations: Sequence[ProviderRegistration],
    env: Optional[Dict[str, str]] = None,
    dotenv_path: Optional[str] = None
) -> ApplicationInstance:
    """
    Application bootstrap entrypoint.
    
    1. Invokes the composition root exactly once.
    2. Makes a binary readiness decision: success yields an ApplicationInstance, failure raises.
    3. Propagates any composition-root exception unmodified.
    4. Introduces no retry, fallback, or shutdown logic.
    """
    dependencies = compose_application(
        registrations=registrations,
        env=env,
        dotenv_path=dotenv_path
    )
    
    return dependencies
