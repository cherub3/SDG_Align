type PlannerState = "INITIALIZING" | "PLANNING" | "EXECUTING" | "EVALUATING" | "COMPLETED" | "FAILED"

const states: PlannerState[] = ["INITIALIZING", "PLANNING", "EXECUTING", "EVALUATING", "COMPLETED"]

// Illustrative — matches the exact sequence named in Dashboard Specification v1.0 §3 Flow C.
const currentState: PlannerState = "COMPLETED"

const planDecision = {
  stepType: "QUERY_PIPELINE",
  reasoning: "Retrieved context is sufficient to answer directly; no additional tool invocation required.",
  stepId: "8f2a1c…",
}

export function PlannerStateCard() {
  return (
    <div className="border rounded-lg bg-card p-4 space-y-4">
      <h3 className="font-medium">Stage 21 — Planner State</h3>

      <ol className="flex flex-wrap items-center gap-2 text-sm">
        {states.map((state, i) => (
          <li key={state} className="flex items-center gap-2">
            <span
              className={`px-2.5 py-1 rounded-md border text-xs font-semibold ${
                state === currentState
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-muted/40 border-border text-muted-foreground"
              }`}
              aria-current={state === currentState ? "step" : undefined}
            >
              {state}
            </span>
            {i !== states.length - 1 && (
              <span aria-hidden="true" className="text-muted-foreground">
                →
              </span>
            )}
          </li>
        ))}
      </ol>

      <div className="text-sm space-y-1">
        <p>
          <span className="text-muted-foreground">step_type:</span> {planDecision.stepType}
        </p>
        <p>
          <span className="text-muted-foreground">reasoning:</span> {planDecision.reasoning}
        </p>
        <p>
          <span className="text-muted-foreground">step_id:</span> <span className="font-mono">{planDecision.stepId}</span>
        </p>
      </div>
    </div>
  )
}
