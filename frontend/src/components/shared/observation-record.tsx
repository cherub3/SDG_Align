import { useState } from "react"

interface ObservationRecordProps {
  // null means this data is not available for this call (Mode A — Track B Phase 7 plan,
  // Finding 3). Rendered as an explicit "unavailable" state, never a fabricated value.
  correlationId: string | null
  outcome: "completed" | "failed" | "unavailable"
  duration: number | null
}

function CorrelationBadge({ correlationId }: { correlationId: string | null }) {
  const [copied, setCopied] = useState(false)
  if (correlationId === null) {
    return <span className="font-mono text-muted-foreground">unavailable</span>
  }
  const copy = async () => {
    await navigator.clipboard.writeText(correlationId)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <button
      type="button"
      onClick={copy}
      className="font-mono hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
      title="Copy correlation ID"
    >
      {correlationId}… {copied && <span className="text-primary">(copied)</span>}
    </button>
  )
}

function OutcomePill({ outcome }: { outcome: ObservationRecordProps["outcome"] }) {
  const tone =
    outcome === "completed"
      ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
      : outcome === "failed"
        ? "bg-destructive/15 text-destructive"
        : "bg-muted text-muted-foreground"
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${tone}`}>{outcome}</span>
}

export function ObservationRecord({ correlationId, outcome, duration }: ObservationRecordProps) {
  return (
    <span className="inline-flex items-center gap-2 text-xs text-muted-foreground">
      Obs: <CorrelationBadge correlationId={correlationId} /> · {duration === null ? "unavailable" : `${duration}s`} ·{" "}
      <OutcomePill outcome={outcome} />
    </span>
  )
}
