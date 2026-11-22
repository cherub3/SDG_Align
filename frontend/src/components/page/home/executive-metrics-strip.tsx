import { MetricCard } from "../../shared/metric-card"

export function ExecutiveMetricsStrip() {
  return (
    <section aria-labelledby="metrics-heading" className="py-12 px-4 bg-background">
      <div className="max-w-7xl mx-auto">
        <h2 id="metrics-heading" className="sr-only">
          Executive Metrics
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">
          <MetricCard label="Pipeline Stages" value={22} description="Stages 0–21 · fully frozen" />
          <MetricCard label="Tests Passing" value={795} description="Local run 2026-11-23 · not yet run on GitHub CI" variant="highlight" />
          <MetricCard label="Documents Indexed" value={6} description="of 13 ingested" />
          <MetricCard label="AI Providers" value={3} description="LLM · Embedding · Planner" />
          <MetricCard label="Adapter Boundaries" value={6} description="LLM · Cache · Tool · Index · Planner · Conversation" />
          <MetricCard label="Avg Response Time" value="~0.85s" description="Recorded demonstration · 1 query · cold cache · Gemini · 2026-07-23" />
          <MetricCard label="Grounded Responses" value="100%" description="Recorded demonstration · 1 sample query · corpus n=6 · cold cache" variant="highlight" />
          <MetricCard label="Pipeline Health" value="● Operational" description="all adapters wired" />
          <MetricCard label="Architecture Phases" value={8} description="Phases 1.1–2.3 · all frozen" />
          <MetricCard label="Agent Steps" value={3} description="Memory · Tool · Planner" />
        </div>
      </div>
    </section>
  )
}
