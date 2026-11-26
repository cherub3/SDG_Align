// Restated from docs/pipeline_principles.md (sections 1 and 4).
const principles = [
  {
    title: "Deterministic",
    text: "Each stage's output is a function of its inputs. Timestamps are the one exception. Hosted embedding and LLM APIs are not covered.",
  },
  {
    title: "Read-only on artifacts a stage does not own",
    text: "A stage writes only the artifacts it produces. Upstream artifacts are opened read-only, with two documented exceptions (stages 3 and 5 extend their own artifact in place).",
  },
  {
    title: "No PDF reopening past stage 2",
    text: "Only stage 1 (integrity) and stage 2 (extraction) read the original PDF. Later stages work from the extracted JSON.",
  },
  {
    title: "Idempotent",
    text: "Re-running a stage on the same input gives the same output, apart from timestamps.",
  },
  {
    title: "Deterministic before probabilistic",
    text: "Every heuristic in the ingestion stages is a fixed, named rule: a regex, a threshold, a structural walk. Where a signal is missing, the stage reports that it does not know instead of inventing a value.",
  },
]

const tiers = [
  { title: "Critical finding", text: "Downstream use would be unsafe or impossible. The document fails and is quarantined." },
  { title: "Recoverable finding", text: "An imperfection that does not block downstream use. The document passes with a warning." },
  { title: "No findings", text: "The document passes." },
]

export function PrinciplesPage() {
  return (
    <div className="max-w-4xl mx-auto px-4 py-12 space-y-10">
      <h1 className="text-3xl font-bold tracking-tight">Pipeline principles</h1>
      <p className="text-muted-foreground">
        Shared conventions for the ingestion stages, from <code className="font-mono text-xs">docs/pipeline_principles.md</code>.
      </p>

      <section aria-labelledby="design-heading" className="space-y-4">
        <h2 id="design-heading" className="text-2xl font-bold">Design rules</h2>
        <ul className="space-y-3">
          {principles.map((p) => (
            <li key={p.title} className="border rounded-lg bg-card p-4">
              <h3 className="font-semibold">{p.title}</h3>
              <p className="text-sm text-muted-foreground mt-1">{p.text}</p>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="tiers-heading" className="space-y-4">
        <h2 id="tiers-heading" className="text-2xl font-bold">Validation outcomes</h2>
        <p className="text-sm text-muted-foreground">Every check runs to completion; there is no fail-fast.</p>
        <ul className="space-y-3">
          {tiers.map((t) => (
            <li key={t.title} className="border rounded-lg bg-card p-4">
              <h3 className="font-semibold">{t.title}</h3>
              <p className="text-sm text-muted-foreground mt-1">{t.text}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
