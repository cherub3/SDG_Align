import { useEffect, useMemo, useState } from "react"
import { NarrativeBlock } from "../components/shared/narrative-block"
import { MetricCard } from "../components/shared/metric-card"
import { FilterBar } from "../components/shared/filter-bar"
import { DrawerPanel } from "../components/layout/drawer-panel"
import { RequestLogTable } from "../components/page/observability/request-log-table"
import { useBackendAdapter } from "../lib/backend-adapter"
import { useOperatingMode } from "../providers/operating-mode-provider"
import { BackendOfflineNotice } from "../components/shared/backend-offline-notice"
import type { ObservationRecordItem } from "../content/demo-data/pipeline-trace"

const FILTERS = ["All", "Completed", "Failed"] as const
type Filter = (typeof FILTERS)[number]

export function ObservabilityPage() {
  const adapter = useBackendAdapter()
  const { backendStatus } = useOperatingMode()
  const online = backendStatus === "live"
  const [records, setRecords] = useState<ObservationRecordItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>("All")
  const [selected, setSelected] = useState<ObservationRecordItem | null>(null)

  useEffect(() => {
    if (!online) return
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
  }, [adapter, online])

  const filtered = useMemo(() => {
    if (!records) return []
    if (filter === "Completed") return records.filter((r) => r.outcome === "completed")
    if (filter === "Failed") return records.filter((r) => r.outcome === "failed")
    return records
  }, [filter, records])

  if (!online) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-12">
        <h1 className="sr-only">Observability</h1>
        <BackendOfflineNotice waking={backendStatus === "checking" || backendStatus === "waking"} />
      </div>
    )
  }

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
  const avgMs = total === 0 ? 0 : (records.reduce((sum, r) => sum + r.duration, 0) / total) * 1000

  return (
    <div className="max-w-6xl mx-auto px-4 py-12 space-y-8">
      <h1 className="sr-only">Observability</h1>

      <NarrativeBlock
        headline="Each request through the backend gets a correlation ID, a timestamp, an outcome and a duration."
        body="Live records from the backend process, kept in memory and cleared when it restarts. Retrieval-only requests are short, so their durations are short."
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard label="Total Requests" value={total} />
        <MetricCard label="Success Rate" value={`${successRate}%`} variant="highlight" />
        <MetricCard label="Avg Duration" value={`${avgMs.toFixed(avgMs < 10 ? 1 : 0)} ms`} />
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
              <span>{(selected.duration * 1000).toFixed(1)} ms</span>
            </div>
            <div>
              <span className="text-muted-foreground block text-xs">timestamp</span>
              <span className="font-mono">{selected.timestamp ?? "unavailable"}</span>
            </div>
          </div>
        )}
      </DrawerPanel>
    </div>
  )
}
