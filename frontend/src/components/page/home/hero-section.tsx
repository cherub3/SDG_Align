
export function HeroSection() {
  return (
    <section 
      aria-labelledby="hero-heading" 
      className="flex flex-col items-center justify-center text-center py-24 px-4 bg-muted/30"
    >
      <div className="max-w-4xl mx-auto space-y-6">
        <p className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          SDG Align
        </p>
        <h1
          id="hero-heading"
          className="text-4xl md:text-6xl font-extrabold tracking-tight"
        >
          Grounded AI analysis for UN SDG proposal alignment
        </h1>
        <p className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto">
          A 22-stage RAG + agent pipeline with content-deterministic ingestion —
          every stage tested, every boundary documented.
        </p>
        <div className="flex flex-col sm:flex-row gap-4 justify-center pt-4">
          <button className="px-6 py-3 bg-primary text-primary-foreground font-medium rounded-md hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            Watch it run ▶
          </button>
          <button className="px-6 py-3 bg-secondary text-secondary-foreground font-medium rounded-md hover:bg-secondary/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            Run your own query →
          </button>
        </div>
        <p className="text-sm text-muted-foreground max-w-2xl mx-auto pt-2">
          The UN's 169 SDG targets describe humanity's most important goals.
          This system tells you which ones your project actually addresses — and shows its work.
        </p>
      </div>
    </section>
  )
}
