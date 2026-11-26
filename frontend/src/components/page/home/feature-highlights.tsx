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
            title="22 explicit stages"
            description="Ingestion, chunking, retrieval bookkeeping, caching and orchestration are plain, tested code. The LLM is called in one step: answering from the retrieved context."
            icon={FlaskConical}
            href="/architecture/principles"
          />
          <FeatureCard
            title="Citations and an abstention rule."
            description="Stage 14 matches answer sentences to retrieved chunks and stage 15 scores verbatim overlap (strict: a correct paraphrase scores 0). When the context lacks the answer the model replies NOT_IN_CONTEXT. It still refuses 6 of 44 answerable test questions, which missed the target."
            icon={ShieldCheck}
            href="/pipeline-explorer"
          />
          <FeatureCard
            title="Every request is observable."
            description="Each request through the backend gets a correlation ID, an outcome and a duration, kept in memory for the life of the process and listed on the Observability page."
            icon={Eye}
            href="/observability"
          />
        </div>
      </div>
    </section>
  )
}
