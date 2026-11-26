import { NarrativeBlock } from "../components/shared/narrative-block"
import { AccordionGrid } from "../components/shared/accordion-grid"
import { DecisionTimeline, type Decision } from "../components/visualization/decision-timeline"
import { StatusBadge } from "../components/shared/status-badge"

// Everything on this page restates README.md or reports/PHASE_*_REPORT.md. Nothing here is a live measurement.
const REPO = "https://github.com/cherub3/SDG_Align"

const results: [string, string][] = [
  ["Retrieval Recall@5, dense vs hybrid (44 answerable TEST items)", "0.57 vs 0.77 (paired gain 95% CI +0.09 to +0.32, exact McNemar p = 0.004)"],
  ["Cloud Run retrieval vs offline retrieval", "Same retrieved chunks on all 66 gold queries; Recall@5 identical on the 56 answerable ones (TEST 0.7727, DEV 0.8333)"],
  ["Answer correctness, 44 answerable TEST items", "31 correct (70.5%, 95% CI 55.8-81.8%), 37 correct or partial, 6 refused, 1 wrong out of 38 answered. Labels are AI-produced, not human-verified. Template 2.1.0 was chosen after 2.0.0 failed on TEST, so these numbers are optimistic"],
  ["Abstention on unanswerable items", "8/8 refused (n = 8, so the interval is wide)"],
  ["False refusals on answerable items", "6/44 (13.6%). The pre-registered target of 4/44 or fewer was not met"],
  ["Planner vs no planner", "No change in refusals (6/44 both); 2.96 vs 1 LLM calls per request. The planner is off by default"],
  ["Tests", "1045 tests, about 87% coverage of scripts/. The mutation probe runs a no-op control first"],
]

const principles = [
  {
    headline: "Plain code before probabilistic models",
    visibleSummary: "Ingestion, retrieval bookkeeping, caching and orchestration are tested code.",
    detailContent: "The LLM is called in one step: answering from the retrieved context. Everything around it is deterministic code covered by pytest.",
  },
  {
    headline: "Measure before claiming",
    visibleSummary: "A frozen gold set, DEV/TEST split, TEST scored once per configuration.",
    detailContent: "66 gold items over 6 documents; 52 in TEST (44 answerable, 8 unanswerable). Tuning used DEV only.",
  },
  {
    headline: "Say what failed",
    visibleSummary: "The abstention target was missed and the reports say so.",
    detailContent: "The 2.0.0 prompt template had 13/44 false refusals. The 2.1.0 template, chosen afterwards, has 6/44 (13.6%); the pre-registered limit was 4/44.",
  },
]

const decisions: Decision[] = [
  {
    date: "Phase 2",
    headline: "Hybrid retrieval (BM25 + dense, reciprocal rank fusion) is the served default",
    why: "Recall@5 rose from 0.57 to 0.77 on the TEST split. The reranker is off by default.",
    alternativesRejected: "Dense-only retrieval",
  },
  {
    date: "Phase 3",
    headline: "Prompt template 2.1.0 is served, and it did not meet the keep rule",
    why: "It cut false refusals from 13/44 to 6/44, but the pre-registered target was 4/44 or fewer. It was chosen after 2.0.0 failed, so it is a post-hoc choice.",
    alternativesRejected: "Template 2.0.0 (13/44 false refusals)",
  },
  {
    date: "Phase 3",
    headline: "The LLM planner is off by default",
    why: "Refusals were identical (6/44) and the planner tripled the LLM calls per request.",
    alternativesRejected: "Planner on by default (PLANNER_ENABLED=true opts in)",
  },
  {
    date: "Phase 3",
    headline: "Cloud Run service with IAM-only access, scale to zero, daily LLM call cap",
    why: "Keeps the free-tier quota and the service private. Cold start measured at 41.3 s.",
    alternativesRejected: "Public access; always-on instance",
  },
]

const limitations = [
  {
    headline: "Small gold set",
    visibleSummary: "66 items, 52 in TEST",
    detailContent: "Confidence intervals are wide. The 8 unanswerable items give a very wide interval for the abstention result.",
  },
  {
    headline: "Correctness is AI-labelled",
    visibleSummary: "Two blind runs, same model family, kappa 0.95",
    detailContent: "Two blind labelling runs by the same model family agreed on 43 of 44 items; one disagreement was adjudicated by the project owner. Not human-verified. Only the gold quotes were used, not the full source PDFs.",
  },
  {
    headline: "Abstention is not solved",
    visibleSummary: "6/44 false refusals; target missed",
    detailContent: "The model refuses 13.6% of answerable test questions. Four of the six partial answers and two of the six refusals are cross-document questions.",
  },
  {
    headline: "Groundedness score is strict by design",
    visibleSummary: "Paraphrase scores 0",
    detailContent: "A sentence counts as grounded only if at least 80% of it is one verbatim run from a chunk. Of the 31 answers labelled correct, 21 have groundedness 0. The UI labels it verbatim overlap.",
  },
  {
    headline: "Cold start and free-tier quota",
    visibleSummary: "41.3 s instance start; daily cap of 10 LLM calls",
    detailContent: "Cloud Run scales to zero. A request-level cold start was not measured. The LLM is Gemini on a free-tier key. No load test was run.",
  },
  {
    headline: "SDG-target alignment is not built",
    visibleSummary: "This is the question-answering pipeline",
    detailContent: "Mapping a proposal to specific SDG targets (target extraction, evidence validator, gap analysis) is the product goal. It is not implemented.",
  },
  {
    headline: "Six-document corpus",
    visibleSummary: "Text not licensed for redistribution",
    detailContent: "The repository does not include the PDFs or anything derived from them. State (observations, cache, conversations) is in memory per process.",
  },
]

const stack = [
  "Python 3.11+",
  "PyMuPDF",
  "faiss-cpu",
  "NumPy / pandas / PyArrow",
  "sentence-transformers",
  "google-genai (Gemini)",
  "FastAPI + Pydantic",
  "React 19",
  "TypeScript",
  "Vite",
  "Tailwind CSS",
  "React Router",
  "Recharts",
  "Framer Motion",
  "pytest",
  "GitHub Actions",
]

const linkClass =
  "text-primary font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"

export function AboutPage() {
  return (
    <div className="max-w-6xl mx-auto px-4 py-12 space-y-12">
      <h1 className="sr-only">About</h1>

      <NarrativeBlock
        headline="SDG Align answers questions about 6 GEF/UNDP project proposals with citations, and abstains when the documents do not contain the answer."
        body="This page restates the README and the phase reports: what was measured, and where it falls short."
      />

      <section aria-labelledby="results-heading" className="space-y-4">
        <h2 id="results-heading" className="text-2xl font-bold">Results</h2>
        <div className="border rounded-lg overflow-x-auto">
          <table className="w-full text-sm">
            <tbody>
              {results.map(([what, value]) => (
                <tr key={what} className="border-b last:border-0">
                  <td className="px-4 py-2 text-muted-foreground w-1/3">{what}</td>
                  <td className="px-4 py-2 font-medium">{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="principles-heading" className="space-y-4">
        <h2 id="principles-heading" className="text-2xl font-bold">Working Principles</h2>
        <AccordionGrid items={principles} />
      </section>

      <section aria-labelledby="decisions-heading" className="space-y-4">
        <h2 id="decisions-heading" className="text-2xl font-bold">Key Decisions</h2>
        <DecisionTimeline decisions={decisions} />
      </section>

      <section aria-labelledby="limitations-heading" className="space-y-4">
        <h2 id="limitations-heading" className="text-2xl font-bold">Limitations</h2>
        <AccordionGrid items={limitations} columns={2} />
      </section>

      <section aria-labelledby="tech-heading" className="space-y-4">
        <h2 id="tech-heading" className="text-2xl font-bold">Tech Stack</h2>
        <div className="flex flex-wrap gap-2">
          {stack.map((tech) => (
            <StatusBadge key={tech} status="FROZEN" label={tech} />
          ))}
        </div>
      </section>

      <section aria-labelledby="contact-heading" className="space-y-4">
        <h2 id="contact-heading" className="sr-only">Source</h2>
        <div className="flex flex-wrap gap-4">
          <a href={REPO} className={linkClass}>
            GitHub Repository →
          </a>
          <a href={`${REPO}#architecture`} className={linkClass}>
            Architecture (README) →
          </a>
        </div>
      </section>
    </div>
  )
}
