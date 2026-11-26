import { useEffect, useState } from "react"
import { probeBackend } from "../../../lib/backend-adapter"
import { INDEXED_DOCUMENT_COUNT } from "../../../content/corpus-documents"

type Row = { name: string; state: "ok" | "warn" | "down" | "static"; detail: string }

const dot: Record<Row["state"], string> = {
  ok: "bg-emerald-500",
  warn: "bg-amber-500",
  down: "bg-destructive",
  static: "bg-muted-foreground",
}

// Rows marked "static" are facts about the build (README.md, data/proposals), not read from the running backend.
const STATIC_ROWS: Row[] = [
  { name: "Planner", state: "static", detail: "Direct (no LLM planner) unless PLANNER_ENABLED=true · static, from README" },
  { name: "Index", state: "static", detail: `${INDEXED_DOCUMENT_COUNT} documents · 497 chunks · static` },
]

export function SystemHealthPanel() {
  const [rows, setRows] = useState<Row[] | null>(null)

  useEffect(() => {
    let cancelled = false
    probeBackend().then((p) => {
      if (cancelled) return
      if (p === null) {
        setRows([{ name: "Backend", state: "down", detail: "not reachable from this page" }, ...STATIC_ROWS])
        return
      }
      const c = p.capabilities
      setRows([
        { name: "Backend", state: "ok", detail: "/health ok" },
        c === null
          ? { name: "Capabilities", state: "warn", detail: "this backend does not report /capabilities" }
          : { name: "Retrieval", state: c.retrievalAvailable ? "ok" : "down", detail: c.retrievalAvailable ? "available" : "not available" },
        ...(c === null
          ? []
          : [{ name: "LLM", state: c.llmConfigured ? "ok" : "warn", detail: c.llmConfigured ? "configured" : "not configured: retrieval only" } as Row]),
        ...STATIC_ROWS,
      ])
    })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section aria-labelledby="system-health-heading" className="py-12 px-4 bg-muted/20 border-t border-border">
      <div className="max-w-7xl mx-auto">
        <h2 id="system-health-heading" className="text-2xl font-bold tracking-tight mb-6">
          Backend Status
        </h2>
        <div className="border rounded-lg bg-card shadow-sm overflow-hidden">
          {rows === null ? (
            <p className="px-4 py-3 text-sm text-muted-foreground">Checking the backend…</p>
          ) : (
            rows.map((row, i) => (
              <div key={row.name} className={`flex items-center justify-between px-4 py-3 ${i !== rows.length - 1 ? "border-b border-border" : ""}`}>
                <span className="font-medium">{row.name}</span>
                <span className="inline-flex items-center gap-2 text-sm text-muted-foreground">
                  <span className={`w-2 h-2 rounded-full ${dot[row.state]}`} aria-hidden="true" />
                  <span>{row.detail}</span>
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  )
}
