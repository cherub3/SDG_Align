type HealthStatus = "OPERATIONAL" | "DEGRADED" | "FAILED" | "PENDING"

const dotColor: Record<HealthStatus, string> = {
  OPERATIONAL: "bg-emerald-500",
  DEGRADED: "bg-amber-500",
  FAILED: "bg-destructive",
  PENDING: "bg-muted-foreground",
}

interface HealthRow {
  name: string
  status: HealthStatus
  detail: string
}

const rows: HealthRow[] = [
  { name: "Retrieval", status: "OPERATIONAL", detail: "faiss index loaded · 6 docs" },
  { name: "Embedding", status: "OPERATIONAL", detail: "Gemini embedding adapter wired" },
  { name: "LLM", status: "OPERATIONAL", detail: "Gemini LLM adapter wired" },
  { name: "Planner", status: "OPERATIONAL", detail: "PlannerLLMAdapter wired" },
  { name: "Vector Index", status: "OPERATIONAL", detail: "477879bb… · 6 documents" },
  { name: "Observability", status: "OPERATIONAL", detail: "Phase 2.3 · observe_request()" },
  { name: "Pipeline", status: "OPERATIONAL", detail: "575 tests passing" },
  { name: "Gold Set Eval", status: "PENDING", detail: "evaluation.md not yet authored" },
]

function summaryBadge(): { text: string; tone: "success" | "warning" | "error" } {
  const failed = rows.filter((r) => r.status === "FAILED").length
  const degraded = rows.filter((r) => r.status === "DEGRADED").length
  const pending = rows.filter((r) => r.status === "PENDING").length

  if (failed > 0) return { text: `✗ ${failed} Failed`, tone: "error" }
  if (degraded > 0) return { text: `⚠ ${degraded} Component${degraded > 1 ? "s" : ""} Degraded`, tone: "warning" }
  if (pending > 0) return { text: `⚠ ${pending} Component${pending > 1 ? "s" : ""} Pending`, tone: "warning" }
  return { text: "● All Operational", tone: "success" }
}

const toneClass: Record<string, string> = {
  success: "text-emerald-700 dark:text-emerald-400",
  warning: "text-amber-700 dark:text-amber-400",
  error: "text-destructive",
}

export function SystemHealthPanel() {
  const badge = summaryBadge()

  return (
    <section aria-labelledby="system-health-heading" className="py-12 px-4 bg-muted/20 border-t border-border">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h2 id="system-health-heading" className="text-2xl font-bold tracking-tight">
            System Health
          </h2>
          <span className={`text-sm font-semibold ${toneClass[badge.tone]}`}>{badge.text}</span>
        </div>
        <div className="border rounded-lg bg-card shadow-sm overflow-hidden">
          {rows.map((row, i) => (
            <div
              key={row.name}
              className={`flex items-center justify-between px-4 py-3 ${i !== rows.length - 1 ? "border-b border-border" : ""}`}
            >
              <span className="font-medium">{row.name}</span>
              <span className="inline-flex items-center gap-2 text-sm text-muted-foreground">
                <span className={`w-2 h-2 rounded-full ${dotColor[row.status]}`} aria-hidden="true" />
                <span className="font-medium text-foreground">{row.status}</span>
                <span className="hidden md:inline">{row.detail}</span>
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
