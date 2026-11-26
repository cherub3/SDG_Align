import { Link } from "react-router-dom"

// A plain description of the flow. No timings, scores or sample answers: real runs are in the Pipeline Explorer.
const steps = [
  { title: "1. Ingest", text: "PDFs are registered, extracted, cleaned, structured, chunked, embedded and indexed (stages 0-9)." },
  { title: "2. Retrieve", text: "A question is matched against the chunks with BM25 and dense vectors, fused into one ranking (stage 10)." },
  { title: "3. Answer", text: "The top chunks go into a prompt and one LLM call answers from them, or replies NOT_IN_CONTEXT (stages 11-13)." },
  { title: "4. Check", text: "Answer sentences are matched to chunks and scored for verbatim overlap; the response is cached and served (stages 14-18)." },
  { title: "5. Agent layer", text: "Conversation memory, tool calling and a planner wrap the above (stages 19-21). The planner is off by default." },
]

export function HowItWorks() {
  return (
    <section aria-labelledby="how-it-works-heading" className="py-16 px-4 bg-background">
      <div className="max-w-5xl mx-auto space-y-8">
        <div className="text-center space-y-2">
          <h2 id="how-it-works-heading" className="text-3xl font-bold tracking-tight">
            How a question is handled
          </h2>
        </div>
        <ol className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {steps.map((s) => (
            <li key={s.title} className="border rounded-lg bg-card p-4">
              <h3 className="font-semibold">{s.title}</h3>
              <p className="text-sm text-muted-foreground mt-1">{s.text}</p>
            </li>
          ))}
        </ol>
        <div className="text-center">
          <Link
            to="/pipeline-explorer"
            className="inline-block px-6 py-3 bg-primary text-primary-foreground font-medium rounded-md hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Try a live query
          </Link>
        </div>
      </div>
    </section>
  )
}
