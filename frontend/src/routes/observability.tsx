import { useEffect, useMemo, useState } from "react"
import { NarrativeBlock } from "../components/shared/narrative-block"
import { MetricCard } from "../components/shared/metric-card"
import { FilterBar } from "../components/shared/filter-bar"
import { DrawerPanel } from "../components/layout/drawer-panel"
import { RequestLogTable } from "../components/page/observability/request-log-table"
import { useBackendAdapter } from "../lib/backend-adapter"
import type { ObservationRecordItem } from "../content/demo-data/pipeline-trace"

const FILTERS = ["All", "Completed", "Failed"] as const
type Filter = (typeof FILTERS)[number]

export function ObservabilityPage() {
  const adapter = useBackendAdapter()
  const [records, setRecords] = useState<ObservationRecordItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>("All")
  const [selected, setSelected] = useState<ObservationRecordItem | null>(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    adapter
      .getObservationRecords()
      .then((r) => {
        if (!cancelled) setRecords(r)
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [adapter])

  const filtered = useMemo(() => {
    if (!records) return []
    if (filter === "Completed") return records.filter((r) => r.outcome === "completed")
    if (filter === "Failed") return records.filter((r) => r.outcome === "failed")
    return records
  }, [filter, records])

  if (error) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-12">
        <h1 className="sr-only">Observability</h1>
        <div className="text-sm text-destructive border border-destructive/30 rounded-lg p-4">{error}</div>
      </div>
    )
  }

  if (!records) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-12">
        <h1 className="sr-only">Observability</h1>
        <div className="text-sm text-muted-foreground">Loading…</div>
      </div>
    )
  }

  const total = records.length
  const completed = records.filter((r) => r.outcome === "completed").length
  const successRate = total === 0 ? 0 : Math.round((completed / total) * 100)
  const avgDuration = total === 0 ? "0.00" : (records.reduce((sum, r) => sum + r.duration, 0) / total).toFixed(2)

  return (
    <div className="max-w-6xl mx-auto px-4 py-12 space-y-8">
      <h1 className="sr-only">Observability</h1>

      <NarrativeBlock
        headline="Phase 2.3 (Request Observability) wraps every execution with a correlation identity, outcome, and timing record."
        body="This page is the read-only window into that layer. Every row here represents one call to observe_request() — written by the observer alone."
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard label="Total Requests" value={total} />
        <MetricCard label="Success Rate" value={`${successRate}%`} variant="highlight" />
        <MetricCard label="Avg Duration" value={`${avgDuration}s`} />
      </div>

      <FilterBar options={FILTERS} active={filter} onChange={setFilter} label="Outcome filter" />

      <RequestLogTable records={filtered} onSelect={setSelected} />

      <DrawerPanel open={selected !== null} onClose={() => setSelected(null)} title="Record Detail">
        {selected && (
          <div className="text-sm space-y-3">
            <div>
              <span className="text-muted-foreground block text-xs">correlation_id</span>
              <span className="font-mono">{selected.correlationId}</span>
            </div>
            <div>
              <span className="text-muted-foreground block text-xs">outcome</span>
              <span
                className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                  selected.outcome === "completed"
                    ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
                    : "bg-destructive/15 text-destructive"
                }`}
              >
                {selected.outcome}
              </span>
            </div>
            <div>
              <span className="text-muted-foreground block text-xs">duration</span>
              <span>{selected.duration}s</span>
            </div>
            <div>
              <span className="text-muted-foreground block text-xs">timestamp</span>
              <span className="font-mono">{selected.timestamp ?? "unavailable"}</span>
            </div>
            <a
              href="/pipeline-explorer"
              className="inline-block text-primary font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded pt-2"
            >
              View trace →
            </a>
          </div>
        )}
      </DrawerPanel>
    </div>
  )
}
