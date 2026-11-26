// From requirements.txt, requirements-local.txt, frontend/package.json and .github/workflows/test.yml.
const stack = [
  "Python 3.11+",
  "PyMuPDF",
  "faiss-cpu",
  "NumPy / pandas / PyArrow",
  "sentence-transformers (local embeddings)",
  "Gemini (google-genai)",
  "FastAPI + Pydantic",
  "React 19 + TypeScript",
  "Vite",
  "Tailwind CSS",
  "pytest",
  "GitHub Actions",
]

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
