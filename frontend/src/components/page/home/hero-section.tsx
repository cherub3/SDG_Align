import { Link } from "react-router-dom"

const primary =
  "px-6 py-3 bg-primary text-primary-foreground font-medium rounded-md hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"

export function HeroSection() {
  return (
    <section aria-labelledby="hero-heading" className="flex flex-col items-center justify-center text-center py-24 px-4 bg-muted/30">
      <div className="max-w-4xl mx-auto space-y-6">
        <p className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">SDG Align</p>
        <h1 id="hero-heading" className="text-4xl md:text-6xl font-extrabold tracking-tight">
          Question answering over GEF/UNDP project proposals
        </h1>
        <p className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto">
          Hybrid retrieval, answers with citations, and abstention when the documents
          do not contain the answer. Mapping to SDG targets is planned and not built.
        </p>
        <div className="flex flex-col sm:flex-row gap-4 justify-center pt-4">
          <Link to="/pipeline-explorer" className={primary}>
            Try a live query
          </Link>
        </div>
        <p className="text-sm text-muted-foreground max-w-2xl mx-auto pt-2">
          The SDG-target alignment product (mapping a proposal to specific SDG targets) is not built yet. What exists is
          the question-answering pipeline it would sit on.
        </p>
      </div>
    </section>
  )
}
