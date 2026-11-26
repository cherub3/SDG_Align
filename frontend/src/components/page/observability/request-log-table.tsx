import { useState } from "react"
import type { ObservationRecordItem } from "../../../content/demo-data/pipeline-trace"

function CopyCorrelationIdButton({ correlationId }: { correlationId: string }) {
  const [copied, setCopied] = useState(false)

  const copy = async (e: React.MouseEvent) => {
    e.stopPropagation()
    await navigator.clipboard.writeText(correlationId)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <button
      type="button"
      onClick={copy}
      aria-label="Copy Correlation ID"
      title="Copy Correlation ID"
      className="shrink-0 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded px-1"
    >
      {copied ? <span className="text-primary text-xs">copied</span> : <span aria-hidden="true">⧉</span>}
    </button>
  )
}

function relativeTime(iso: string | null): string {
  if (iso === null) return "unavailable"
  const diffMs = Date.now() - new Date(iso).getTime()
  const minutes = Math.round(diffMs / 60000)
  if (minutes < 1) return "just now"
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

interface RequestLogTableProps {
  records: ObservationRecordItem[]
  onSelect: (record: ObservationRecordItem) => void
}

export function RequestLogTable({ records, onSelect }: RequestLogTableProps) {
  return (
    <div className="border rounded-lg overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/30 text-left text-muted-foreground">
            <th scope="col" className="px-4 py-2 font-medium">Correlation ID</th>
            <th scope="col" className="px-4 py-2 font-medium">Outcome</th>
            <th scope="col" className="px-4 py-2 font-medium">Duration</th>
            <th scope="col" className="px-4 py-2 font-medium">When</th>
          </tr>
        </thead>
        <tbody>
          {records.map((record) => (
            <tr key={record.correlationId} className="border-b last:border-0 hover:bg-muted/20">
              <td className="px-4 py-2">
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => onSelect(record)}
                    className="font-mono text-left hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                  >
                    {record.correlationId}…
                  </button>
                  <CopyCorrelationIdButton correlationId={record.correlationId} />
                </div>
              </td>
              <td className="px-4 py-2">
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                    record.outcome === "completed"
                      ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
                      : "bg-destructive/15 text-destructive"
                  }`}
                >
                  {record.outcome}
                </span>
              </td>
              <td className="px-4 py-2">{(record.duration * 1000).toFixed(1)} ms</td>
              <td className="px-4 py-2 text-muted-foreground" title={record.timestamp ?? "unavailable"}>
                {relativeTime(record.timestamp)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
