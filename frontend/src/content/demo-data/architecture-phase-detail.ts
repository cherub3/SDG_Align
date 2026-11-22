export interface PhaseDetailContent {
  phaseId: string
  phaseName: string
  summary: string
  responsibilities: string[]
  nonResponsibilities: string[]
  lifecycleSteps: string[]
  contractSignature: string
  contractIsIllustrative: boolean
  limitations: string[]
  knownDefects: string[]
  sourceDoc: string
}

// Condensed from the frozen backend architecture documents under docs/architecture/.
// This is a derivative summary for dashboard display (per Dashboard Specification v1.0 §4:
// "Dashboard is intentionally concise... surfaces the signal... and links out for depth") —
// not a duplicate of the source .md files, which remain the full authoritative documents.
export const phaseDetailContent: Record<string, PhaseDetailContent> = {
  "1-1": {
    phaseId: "1-1",
    phaseName: "Configuration Layer",
    summary:
      "Every frozen stage from Stage 8 onward declares that its concrete adapter is runtime-supplied, never hard-coded, but none of them defines how a caller decides which instance to supply or how a secret reaches it safely. Phase 1.1 closes that gap with a closed configuration object model, a linear load → validate → wire lifecycle, and a provider registration mechanism.",
    responsibilities: [
      "Define a closed, versioned configuration object model for every deployment- and provider-level tunable",
      "Load configuration from a closed, ordered set of sources with no invented source",
      "Structurally and range-validate every loaded value before use",
      "Define a provider registration mechanism for future concrete adapter factories",
      "Construct concrete adapter instances from validated configuration and a supplied registry",
    ],
    nonResponsibilities: [
      "Select, implement, or import any concrete LLM/embedding/cache/tool/planner provider",
      "Implement retry, backoff, or timeout logic of any kind",
      "Construct a prompt, retrieve a document, or perform any stage's own orchestration job",
      "Expose an HTTP endpoint, CLI command, or UI of any kind",
      "Hold any global mutable state",
    ],
    lifecycleSteps: ["Load", "Validate", "Wire"],
    contractSignature:
      "load_raw_settings(env, dotenv_path) -> RawSettings\nvalidate_settings(raw) -> ApplicationSettings\nbuild_provider_registry(registrations) -> ProviderRegistry\nwire_dependencies(settings, registry) -> WiringResult",
    contractIsIllustrative: false,
    limitations: [
      "No hot-reload — a running process's configuration is fixed for its lifetime",
      "Single-process configuration only, no distributed configuration service",
      "No per-tenant or per-caller provider selection",
      "The provider registry ships with zero concrete registrations from this document alone",
      "No secret rotation support",
    ],
    knownDefects: [],
    sourceDoc: "phase1_1_configuration_layer.md",
  },
  "1-2": {
    phaseId: "1-2",
    phaseName: "LLM Provider",
    summary:
      "Stage 13 requires that its LLMAdapter be runtime-supplied, and Phase 1.1 defines how that supply happens, but neither defines what a concrete adapter must do internally to be correct. Phase 1.2 closes that gap: the architecture any concrete LLMAdapter implementation must follow, including SDK client ownership, the identity split between adapter and request, and the exception-raising discipline for Stage 13's four closed error types.",
    responsibilities: [
      "Define the architecture of a concrete LLMAdapter subclass implementing Stage 13's frozen contract",
      "Define SDK client ownership and lifecycle, from construction through disposal",
      "Separate adapter identity (provider_name) from request identity (provider_name + model_name)",
      "Define per-field ownership of every value a concrete implementation must produce on RawLLMResult",
      "Define the one-attempt-per-invoke() retry boundary explicitly",
    ],
    nonResponsibilities: [
      "Select, implement, or import any specific concrete LLM provider SDK",
      "Construct a prompt or budget it against a token ceiling (Stage 12's own job)",
      "Implement retry, backoff, or timeout looping logic (Stage 13's own Retry Policy owns the loop)",
      "Introduce streaming token generation or any streaming SDK API of any kind",
      "Define conversation history, chat sessions, or dialogue state of any kind",
    ],
    lifecycleSteps: ["Construction", "Credential Injection", "SDK Client Creation", "invoke()", "RawLLMResult Mapping", "Disposal"],
    contractSignature: "Callable[[ProviderSettings, Optional[str]], LLMAdapter]",
    contractIsIllustrative: false,
    limitations: [
      "No cross-provider abstraction beyond LLMAdapter itself",
      "No credential rotation support",
      "No multi-region, multi-endpoint, or provider-side failover architecture",
      "No response caching of any kind",
      "model_version_reported's usefulness is entirely provider-dependent",
    ],
    knownDefects: [],
    sourceDoc: "phase1_2_llm_provider.md",
  },
  "1-3": {
    phaseId: "1-3",
    phaseName: "Embedding Provider",
    summary:
      "Stage 8 declares the ProviderAdapter contract and explicitly declines to select or implement a default. Phase 1.1 closes the wiring half of that gap; Phase 1.3 closes the rest — the architecture any concrete embedding-provider implementation must follow internally to be a correct, production-grade adapter.",
    responsibilities: [
      "Define the architecture of a concrete ProviderAdapter subclass implementing Stage 8's frozen contract",
      "Define the ownership and lifecycle of the one SDK client a concrete adapter holds",
      "Define how a concrete adapter's constructor consumes the (ProviderSettings, Optional[str]) pair",
      "Define per-field ownership of every value a concrete implementation must produce",
      "Define the ProviderRegistration a concrete implementation supplies to build_provider_registry()",
    ],
    nonResponsibilities: [
      "Select, implement, or import any specific concrete embedding provider SDK",
      "Perform retrieval, chunking, or any other stage's own frozen job",
      "Implement retry, backoff, or timeout looping logic",
      "Choose which provider is active for the EMBEDDING_PROVIDER seam (Phase 1.1's own job)",
      "Hold any global mutable state",
    ],
    lifecycleSteps: ["Construction", "Credential Injection", "SDK Client Creation", "embed_batch()", "Result Mapping", "Disposal"],
    contractSignature: "Callable[[ProviderSettings, Optional[str]], ProviderAdapter]",
    contractIsIllustrative: false,
    limitations: [
      "No cross-provider abstraction beyond ProviderAdapter itself",
      "No credential rotation support",
      "No multi-region, multi-endpoint, or provider-side failover architecture",
      "No embedding-result caching of any kind",
      "No batch-level partial-failure recovery beyond what Stage 8 already defines",
    ],
    knownDefects: [],
    sourceDoc: "phase1_3_embedding_provider.md",
  },
  "1-4": {
    phaseId: "1-4",
    phaseName: "Planner Provider",
    summary:
      "Stage 21 declares the PlannerLLMAdapter contract in full. Phase 1.4 defines the architecture any concrete implementation of that contract must follow — construction, credential handling, and the exception-translation discipline — mirroring Phase 1.2's own shape for a differently-contracted seam.",
    responsibilities: [
      "Define the architecture of a concrete PlannerLLMAdapter subclass implementing Stage 21's frozen contract",
      "Define the ownership and lifecycle of the one SDK client a concrete adapter holds",
      "Define the ProviderRegistration a concrete implementation supplies to build_provider_registry()",
      "Define the exception-translation discipline a concrete adapter must follow",
      "Define planner result ownership per Stage 21's own frozen contract",
    ],
    nonResponsibilities: [
      "Select, implement, or import any specific concrete planning-capable LLM provider SDK",
      "Perform planning, tool execution, or any other stage's own frozen job",
      "Implement retry logic — by design of the source contract, not by omission",
      "Choose which provider is active for the PLANNER_LLM_PROVIDER seam",
      "Hold any global mutable state",
    ],
    lifecycleSteps: ["Construction", "Credential Injection", "SDK Client Creation", "invoke()", "Result Mapping", "Disposal"],
    contractSignature: "Callable[[ProviderSettings, Optional[str]], PlannerLLMAdapter]",
    contractIsIllustrative: false,
    limitations: [
      "No cross-provider abstraction beyond PlannerLLMAdapter itself",
      "No credential rotation support",
      "No retry, by design of the source this document builds against, not by omission",
      "No response caching of any kind",
      "No adapter-level identity for diagnostics or multi-adapter disambiguation",
    ],
    knownDefects: [],
    sourceDoc: "phase1_4_planner_provider.md",
  },
  "1-5": {
    phaseId: "1-5",
    phaseName: "Composition Root",
    summary:
      "Every prior phase's own Future Phase Boundaries section reserves the same remaining gap: the layer that actually calls the configuration pipeline, holds the result, and performs final assembly into the dependency objects each stage expects. Phase 1.5 is that final assembly layer.",
    responsibilities: [
      "Assemble the set of ProviderRegistration objects supplied by the current deployment",
      "Invoke load_raw_settings → validate_settings → build_provider_registry → wire_dependencies in order",
      "Map WiringResult's wired adapters onto the constructor arguments each stage expects",
      "Construct retrieval closures from the wired embedding and index adapters",
      "Return the fully wired application object graph",
    ],
    nonResponsibilities: [
      "Embedding generation, LLM execution, planner execution, or any stage's own frozen job",
      "Retry policies or provider SDK behavior of any kind",
      "Configuration validation (Phase 1.1's own job, only invoked here)",
      "The ProviderRegistration schema itself (Phase 1.2/1.3/1.4's own job)",
      "Stage orchestration of any kind",
    ],
    lifecycleSteps: ["Startup", "Configuration", "Provider Registration", "Dependency Wiring", "Application Object Assembly", "Application Ready"],
    contractSignature: "compose_application(registrations, env=None, dotenv_path=None) -> (illustrative name only)",
    contractIsIllustrative: true,
    limitations: [
      "No hot-reload, no dynamic re-registration",
      "No per-tenant or per-caller provider selection",
      "The current deployment supplies exactly three registrations",
      "No composition-root-level disposal, teardown, or shutdown mechanism",
    ],
    knownDefects: [],
    sourceDoc: "phase1_5_composition_root.md",
  },
  "2-1": {
    phaseId: "2-1",
    phaseName: "Application Bootstrap",
    summary:
      "Phase 1.5's own Composition Model ends with an assembled dependency graph returned to whatever process-level caller starts the application, and deliberately stops there. Phase 2.1 closes the gap between composing that graph and using it: the one-time act of invoking composition and deciding whether the application is ready.",
    responsibilities: [
      "Define the application bootstrap lifecycle as a strictly linear, one-time sequence",
      "Call the composition root's own public contract exactly once per application instance",
      "Hold the returned dependency-object set and expose it onward",
      "Define readiness as a binary, internal concept — never a network-facing probe",
      "Propagate any startup failure unmodified, never converting it into a degraded state",
    ],
    nonResponsibilities: [
      "Provider registration, dependency wiring, or adapter construction (Phase 1.5's own job)",
      "Any process entrypoint, CLI, REST API, or deployment surface of any kind",
      "Configuration loading or validation (Phase 1.1's own job)",
      "A second dependency-injection or composition mechanism",
      "Any shutdown or teardown contract — none exists anywhere in the frozen repository",
    ],
    lifecycleSteps: ["Startup", "Composition-Root Invocation", "Readiness Decision", "Ready / Failed", "Application Lifetime", "Shutdown (no contract exists)"],
    contractSignature: "bootstrap_application() -> ApplicationInstance (illustrative name only)",
    contractIsIllustrative: true,
    limitations: [
      "No hot-reload, no re-bootstrap",
      "No health-check or readiness-probe surface",
      "No multi-instance bootstrap coordination",
      "No composition-root-level disposal, teardown, or shutdown mechanism",
    ],
    knownDefects: [],
    sourceDoc: "phase2_1_application_bootstrap.md",
  },
  "2-2": {
    phaseId: "2-2",
    phaseName: "Runtime Orchestration",
    summary:
      "Phase 2.1's own Application Model defines what is held after bootstrap, but not what happens when that held instance is used to do work. Phase 2.2 closes that gap: the one-call-per-request lifecycle that invokes the frozen public request-processing contract and decides between exactly two outcomes.",
    responsibilities: [
      "Define the application runtime lifecycle across which one bootstrapped instance serves many requests",
      "Invoke the frozen public request-processing contract exactly once per request",
      "Return the contract's own result unmodified on success",
      "Propagate any raised exception through the entrypoint completely unmodified on failure",
      "Guarantee binary completion — every request ends in exactly one of two outcomes",
    ],
    nonResponsibilities: [
      "Any redesign of Stage 8/13/21's own orchestration",
      "Bootstrap or composition-root work of any kind",
      "Retry, streaming, batching, or cancellation of any kind",
      "Any process entrypoint, CLI, REST API, or deployment surface",
      "Any lifecycle step beyond the five this document names",
    ],
    lifecycleSteps: ["Request Boundary Begins", "Contract Invocation (unchanged)", "Completion Decision", "Completed / Failed", "Request Boundary Ends"],
    contractSignature: "execute_request(application_instance, agent_request) -> result (illustrative name only)",
    contractIsIllustrative: true,
    limitations: [
      "No cancellation",
      "No streaming",
      "No batching",
      "No cross-request state beyond the held application instance",
      "No concurrency guarantee beyond what the held instance's own wired adapters already provide",
      "No health-check, readiness, or liveness surface",
    ],
    knownDefects: [],
    sourceDoc: "phase2_2_runtime_orchestration.md",
  },
  "2-3": {
    phaseId: "2-3",
    phaseName: "Request Observability",
    summary:
      "Phase 2.2's own Request Lifecycle defines how a request executes, but not how that execution is observed by anything outside the request itself. Phase 2.3 closes that gap: a read-only observer that wraps the runtime's own call boundary, producing one immutable observation record per request without altering how the request executes.",
    responsibilities: [
      "Define what is observed about one request: start, end, outcome, duration, correlation identity",
      "Generate the per-request correlation identity as the observer's own responsibility",
      "Construct and own one immutable observation record per request",
      "Never participate in the request's own completion decision",
      "Keep observation records free of raw request/result content or credentials",
    ],
    nonResponsibilities: [
      "Streaming, cancellation, scheduling, or retry of any kind",
      "Any modification of the request or result content",
      "Any redesign of Phase 2.2's own Request Lifecycle",
      "A network-facing metrics endpoint or exporter of any kind",
      "Any error-isolation, exception-swallowing, fallback, or buffering mechanism — none exists anywhere in the frozen architecture today",
    ],
    lifecycleSteps: ["Request Boundary Begins", "Observation Starts", "Contract Invocation (untouched)", "Completion Decision (untouched)", "Observation Record Produced", "Request Boundary Ends"],
    contractSignature: "observe_request(application_instance, agent_request) -> result (illustrative name only)",
    contractIsIllustrative: true,
    limitations: [
      "No metrics aggregation, exporter, or dashboard",
      "No error-isolation mechanism between observation and request execution",
      "No tracing-backend integration",
      "No caller-supplied correlation identity",
    ],
    knownDefects: [],
    sourceDoc: "phase2_3_request_observability.md",
  },
}
