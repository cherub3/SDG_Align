import { MetricCard } from "../../shared/metric-card"

// Every figure here is from README.md / reports/PHASE_*_REPORT.md / eval/results/*.json.
export function ExecutiveMetricsStrip() {
  return (
    <section aria-labelledby="metrics-heading" className="py-12 px-4 bg-background">
      <div className="max-w-7xl mx-auto">
        <h2 id="metrics-heading" className="sr-only">
          Key facts
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          <MetricCard label="Pipeline Stages" value={22} description="Stages 0-21" />
          <MetricCard label="Tests" value={1045} description="About 87% coverage of scripts/ · run by a GitHub Actions workflow" variant="highlight" />
          <MetricCard label="Corpus" value="6 docs · 497 chunks" description="GEF/UNDP project proposals" />
          <MetricCard label="Retrieval Recall@5" value="0.77" description="Hybrid BM25 + dense. Dense only: 0.57 (44 answerable TEST items)" variant="highlight" />
          <MetricCard label="Answer correctness" value="31 / 44" description="70.5%, 95% CI 55.8-81.8%. AI-labelled, not human-verified" />
          <MetricCard label="False refusals" value="6 / 44" description="13.6%. The pre-registered target (4 or fewer) was not met" variant="warning" />
        </div>
      </div>
    </section>
  )
}
