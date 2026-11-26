import { useState } from "react"

interface ObservationRecordProps {
  // null means the backend did not supply it for this call. Rendered as "unavailable", never a made-up value.
  correlationId: string | null
  outcome: "completed" | "failed" | "unavailable"
  duration: number | null
  timestamp: string | null
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
      {correlationId} {copied && <span className="text-primary">(copied)</span>}
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

export function ObservationRecord({ correlationId, outcome, duration, timestamp }: ObservationRecordProps) {
  return (
    <span className="inline-flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      Request: <CorrelationBadge correlationId={correlationId} /> · {timestamp ?? "time unavailable"} ·{" "}
      {duration === null ? "duration unavailable" : `${Math.round(duration * 1000)} ms`} · <OutcomePill outcome={outcome} />
    </span>
  )
}
