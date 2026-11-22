import { FlaskConical, ShieldCheck, Eye } from "lucide-react"
import { FeatureCard } from "../../shared/feature-card"

export function FeatureHighlights() {
  return (
    <section aria-labelledby="features-heading" className="py-24 px-4 bg-background">
      <div className="max-w-7xl mx-auto space-y-12">
        <div className="text-center space-y-4">
          <h2 id="features-heading" className="text-3xl font-bold tracking-tight">
            Feature Highlights
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          <FeatureCard
            title="22 Stages. Zero Guesswork."
            description="Every ingestion rule is plain, testable code. The LLM is isolated to exactly the steps where judgment is genuinely required — retrieval, grounding, and quality evaluation. Nothing probabilistic touches the audit trail."
            icon={FlaskConical}
            href="/architecture/principles"
          />
          <FeatureCard
            title="No citation, no answer."
            description="Stage 15 (Groundedness Validation) and Stage 14 (Citation Extraction) run on every response. If the answer can't be traced to a retrieved chunk, the pipeline doesn't surface it as a confirmed finding. Transparency is structural, not decorative."
            icon={ShieldCheck}
            href="/pipeline-explorer"
          />
          <FeatureCard
            title="Every request is observable."
            description="Phase 2.3 (Request Observability) wraps every execution with a correlation identity, outcome, and timing record — before delivery, export, or logging of that record is even defined. The observation contract is frozen; how records are used is a future decision."
            icon={Eye}
            href="/observability"
          />
        </div>
      </div>
    </section>
  )
}
