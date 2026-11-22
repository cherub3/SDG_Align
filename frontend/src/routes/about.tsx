import { NarrativeBlock } from "../components/shared/narrative-block"
import { AccordionGrid } from "../components/shared/accordion-grid"
import { DecisionTimeline, type Decision } from "../components/visualization/decision-timeline"
import { StatusBadge } from "../components/shared/status-badge"

const principles = [
  {
    headline: "Human before AI",
    visibleSummary: "The evidence package can only read approved rows.",
    detailContent: "The evidence package can only read approved rows.",
  },
  {
    headline: "Plain code before probabilistic models",
    visibleSummary: "Everything that enforces trust is plain, testable code.",
    detailContent:
      "Plain code before probabilistic models — everything that enforces trust is plain, testable code. The LLM is confined to the narrow steps where judgment is genuinely required.",
  },
  {
    headline: "Simple before scalable",
    visibleSummary: "NumPy over vector DBs until measured need exists.",
    detailContent: "NumPy over vector DBs until measured need exists.",
  },
  {
    headline: "Evidence before confidence",
    visibleSummary: "No citation, no suggestion.",
    detailContent: "No citation, no suggestion.",
  },
  {
    headline: "Ship before optimize",
    visibleSummary: "One flawless path beats ten half-features.",
    detailContent: "One flawless path beats ten half-features.",
  },
]

const decisions: Decision[] = [
  {
    date: "2025-Q4",
    headline: "faiss over NumPy-only for vector indexing",
    why: "Measured need exceeded NumPy threshold.",
    alternativesRejected: "faiss over NumPy-only for vector indexing (Phase 1 delivery)",
  },
  {
    date: "2025-Q4",
    headline: "Gemini adapter behind a frozen LLMAdapter contract",
    why: "Provider neutrality — adapters, not hard-wires.",
    alternativesRejected: "Gemini adapter behind a frozen LLMAdapter contract (provider neutrality)",
  },
  {
    date: "2026-Q1",
    headline: "No retry inside the Runtime Orchestration layer (Phase 2.2)",
    why: "Retry ownership belongs to the adapter, not runtime.",
    alternativesRejected: "No retry inside the Runtime Orchestration layer (Phase 2.2)",
  },
  {
    date: "2026-Q1",
    headline: "Observation as non-authoritative / non-participatory (Phase 2.3)",
    why: "Observer never participates in completion decision.",
    alternativesRejected: "Observation as non-authoritative / non-participatory (Phase 2.3)",
  },
  {
    date: "2026-Q2",
    headline: "try/finally defect documented and frozen rather than silently patched",
    why: "Audit honesty.",
    alternativesRejected: "try/finally defect documented and frozen rather than silently patched (audit honesty)",
  },
  {
    date: "2026-Q2",
    headline: "No hot-reload / re-bootstrap",
    why: "Process-lifetime model.",
    alternativesRejected: "No hot-reload / re-bootstrap (process-lifetime model)",
  },
  {
    date: "2026-Q2",
    headline: "Binary-completion guarantee in execute_request()",
    why: "Phase 2.2 contract.",
    alternativesRejected: "Binary-completion guarantee in execute_request() (Phase 2.2 contract)",
  },
  {
    date: "2026-Q2",
    headline: "Phase 2.4 ruled out — architecture at natural stopping point",
    why: "Roadmap honesty.",
    alternativesRejected: "Phase 2.4 ruled out — architecture at natural stopping point (roadmap honesty)",
  },
]

const limitations = [
  {
    headline: "7 of 13 corpus documents quarantined as scanned",
    visibleSummary: "Stage 3 guard working as designed",
    detailContent: "7 of 13 corpus documents quarantined as scanned (Stage 3 guard working as designed)",
  },
  {
    headline: "Query stages tested against in-memory adapters, not live LLM",
    visibleSummary: "Test isolation, not a live-integration claim",
    detailContent: "Query stages tested against in-memory adapters, not live LLM",
  },
  {
    headline: "Phase 2.3 has two known unresolved code-level defects",
    visibleSummary: "try/finally, discarded record",
    detailContent: "Phase 2.3 has two known unresolved code-level defects (try/finally, discarded record)",
  },
  {
    headline: "No hot-reload, no re-bootstrap between requests",
    visibleSummary: "Process-lifetime model",
    detailContent: "No hot-reload, no re-bootstrap between requests",
  },
  {
    headline: "Product goal (SDG alignment UI) not yet implemented",
    visibleSummary: "This is the pipeline foundation",
    detailContent: "Product goal (SDG alignment UI) not yet implemented — this is the pipeline foundation",
  },
  {
    headline: "Test count: the latest recorded run is the source",
    visibleSummary: "795 passing in a local run, 2026-11-23",
    detailContent:
      "Test count: 795 passing in a local run on 2026-11-23. The GitHub Actions workflow is defined but has not been run yet, so this figure is not CI-confirmed.",
  },
]

const comparisonRows: [string, string][] = [
  ["Simple chatbot or Q&A demo", "22-stage observable pipeline"],
  ["No documented architecture", "8 frozen architecture phases (1.1–2.3)"],
  ["Black-box inference", "Full execution trace, stage by stage"],
  ["Minimal or no tests", "Automated test suite with an 80% coverage gate · CI workflow defined"],
  ["No observability", "Phase 2.3 request observability (correlation ID · outcome · duration)"],
  ["Single provider, hardwired", "6 adapter seams · provider-neutral contracts"],
  ["No known limitations documented", "Limitations published transparently (including known defects)"],
  ['"Production-ready" claim, no evidence', "Content-deterministic ingestion · per-stage validation reports"],
]

export function AboutPage() {
  return (
    <div className="max-w-6xl mx-auto px-4 py-12 space-y-12">
      <h1 className="sr-only">About</h1>

      <NarrativeBlock
        headline="SDG Align was built to answer a real gap in development-sector work: organizations spend significant time manually mapping proposals to SDG targets, with no consistent method and no audit trail."
        body="This is the engineering case study of how one evidence-backed pipeline was designed to change that."
      />

      <section aria-labelledby="comparison-heading" className="space-y-4">
        <h2 id="comparison-heading" className="text-2xl font-bold">
          What Makes SDG Align Different?
        </h2>
        <div className="border rounded-lg overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/30 text-left text-muted-foreground">
                <th scope="col" className="px-4 py-2 font-medium">Typical AI Portfolio Project</th>
                <th scope="col" className="px-4 py-2 font-medium">SDG Align</th>
              </tr>
            </thead>
            <tbody>
              {comparisonRows.map(([typical, sdgAlign]) => (
                <tr key={typical} className="border-b last:border-0">
                  <td className="px-4 py-2 text-muted-foreground">{typical}</td>
                  <td className="px-4 py-2 font-medium">{sdgAlign}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="thesis-heading">
        <h2 id="thesis-heading" className="sr-only">Engineering Thesis</h2>
        <blockquote className="border-l-4 border-primary bg-muted/30 rounded-lg p-6 text-lg">
          <p>
            &ldquo;Plain code before probabilistic models — everything that enforces trust is plain, testable
            code. The LLM is confined to the narrow steps where judgment is genuinely required.&rdquo;
          </p>
          <footer className="mt-3 text-sm text-muted-foreground">
            — Architecture Principle #2, ARCHITECTURE_BLUEPRINT.md
          </footer>
        </blockquote>
      </section>

      <section aria-labelledby="principles-heading" className="space-y-4">
        <h2 id="principles-heading" className="text-2xl font-bold">Architecture Principles</h2>
        <AccordionGrid items={principles} />
      </section>

      <section aria-labelledby="decisions-heading" className="space-y-4">
        <h2 id="decisions-heading" className="text-2xl font-bold">Decision Timeline</h2>
        <DecisionTimeline decisions={decisions} />
      </section>

      <section aria-labelledby="limitations-heading" className="space-y-4">
        <h2 id="limitations-heading" className="text-2xl font-bold">
          What this project doesn&rsquo;t do — and why that&rsquo;s intentional.
        </h2>
        <AccordionGrid items={limitations} columns={2} />
      </section>

      <section aria-labelledby="tech-heading" className="space-y-4">
        <h2 id="tech-heading" className="text-2xl font-bold">Tech Stack</h2>
        <div className="flex flex-wrap gap-2">
          {["Python 3.14", "faiss-cpu", "Gemini API", "PyMuPDF", "pytest", "GitHub Actions"].map((tech) => (
            <StatusBadge key={tech} status="FROZEN" label={tech} />
          ))}
        </div>
      </section>

      <section aria-labelledby="contact-heading" className="space-y-4">
        <h2 id="contact-heading" className="sr-only">Contact / Source</h2>
        <div className="flex flex-wrap gap-4">
          <a href="https://github.com" className="text-primary font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded">
            GitHub Repository →
          </a>
          <a href="https://github.com" className="text-primary font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded">
            View Architecture Docs →
          </a>
          <a href="#" className="text-primary font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded">
            Download PDF Poster →
          </a>
        </div>
      </section>
    </div>
  )
}
