const stack = ["Python 3.14", "faiss-cpu", "Gemini API", "PyMuPDF", "pytest", "GitHub Actions"]

export function TechStackStrip() {
  return (
    <section aria-labelledby="tech-stack-heading" className="py-8 px-4 bg-muted/20 border-t border-border">
      <div className="max-w-7xl mx-auto">
        <h2 id="tech-stack-heading" className="sr-only">
          Technology Stack
        </h2>
        <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-2 text-sm font-medium text-muted-foreground">
          {stack.map((tech) => (
            <span key={tech}>{tech}</span>
          ))}
        </div>
      </div>
    </section>
  )
}
