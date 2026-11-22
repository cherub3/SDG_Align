export interface ArchitecturePhase {
  phaseId: string
  label: string
  name: string
  status: "FROZEN"
}

export const architecturePhases: ArchitecturePhase[] = [
  { phaseId: "1-1", label: "1.1 Config", name: "Configuration Layer", status: "FROZEN" },
  { phaseId: "1-2", label: "1.2 LLM", name: "LLM Provider", status: "FROZEN" },
  { phaseId: "1-3", label: "1.3 Embed", name: "Embedding Provider", status: "FROZEN" },
  { phaseId: "1-4", label: "1.4 Plan", name: "Planner Provider", status: "FROZEN" },
  { phaseId: "1-5", label: "1.5 Root", name: "Composition Root", status: "FROZEN" },
  { phaseId: "2-1", label: "2.1 Boot", name: "Application Bootstrap", status: "FROZEN" },
  { phaseId: "2-2", label: "2.2 Runtime", name: "Runtime Orchestration", status: "FROZEN" },
  { phaseId: "2-3", label: "2.3 Obs", name: "Request Observability", status: "FROZEN" },
]
