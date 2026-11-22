import { CodeBlock } from "../../shared/code-block"
import type { PhaseDetailContent } from "../../../content/demo-data/architecture-phase-detail"

function LifecycleStepList({ steps }: { steps: string[] }) {
  return (
    <ol className="flex flex-wrap items-center gap-2 text-sm">
      {steps.map((step, i) => (
        <li key={step} className="flex items-center gap-2">
          <span className="px-2.5 py-1 rounded-md border border-border bg-muted/40">{step}</span>
          {i !== steps.length - 1 && (
            <span aria-hidden="true" className="text-muted-foreground">
              →
            </span>
          )}
        </li>
      ))}
    </ol>
  )
}

function ContractBox({ signature, illustrative }: { signature: string; illustrative: boolean }) {
  return (
    <div className="space-y-1">
      {illustrative && (
        <p className="text-xs italic text-muted-foreground">
          Illustrative shape only — no frozen document mandates this exact function name.
        </p>
      )}
      <CodeBlock code={signature} label="Public Contract" />
    </div>
  )
}

function DefectPanel({ defects }: { defects: string[] }) {
  if (defects.length === 0) {
    return (
      <p className="text-sm text-muted-foreground italic">
        No confirmed code-level defects are recorded against this phase in its frozen architecture
        document.
      </p>
    )
  }
  return (
    <ul className="space-y-2">
      {defects.map((defect) => (
        <li key={defect} className="rounded-md border border-amber-300 dark:border-amber-800 bg-amber-500/10 px-3 py-2 text-sm">
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/20 text-amber-800 dark:text-amber-300 px-2 py-0.5 text-xs font-semibold mr-2">
            CONFIRMED DEFECT
          </span>
          {defect}
        </li>
      ))}
    </ul>
  )
}

export function ArchitectureDoc({ content }: { content: PhaseDetailContent }) {
  return (
    <div className="space-y-8 min-w-0">
      <section aria-labelledby="phase-summary-heading">
        <h2 id="phase-summary-heading" className="text-xl font-bold tracking-tight mb-2">
          Summary
        </h2>
        <p className="text-muted-foreground">{content.summary}</p>
      </section>

      <section aria-labelledby="phase-lifecycle-heading">
        <h2 id="phase-lifecycle-heading" className="text-xl font-bold tracking-tight mb-2">
          Lifecycle
        </h2>
        <LifecycleStepList steps={content.lifecycleSteps} />
      </section>

      <section aria-labelledby="phase-responsibilities-heading" className="grid grid-cols-1 md:grid-cols-2 gap-6 min-w-0">
        <div className="min-w-0">
          <h2 id="phase-responsibilities-heading" className="text-xl font-bold tracking-tight mb-2">
            Responsibilities
          </h2>
          <ul className="space-y-1.5 text-sm text-muted-foreground list-disc pl-5">
            {content.responsibilities.map((item) => (
              <li key={item} className="break-words">
                {item}
              </li>
            ))}
          </ul>
        </div>
        <div className="min-w-0">
          <h2 className="text-xl font-bold tracking-tight mb-2">Non-Responsibilities</h2>
          <ul className="space-y-1.5 text-sm text-muted-foreground list-disc pl-5">
            {content.nonResponsibilities.map((item) => (
              <li key={item} className="break-words">
                {item}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section aria-labelledby="phase-contract-heading">
        <h2 id="phase-contract-heading" className="text-xl font-bold tracking-tight mb-2">
          Public Contract
        </h2>
        <ContractBox signature={content.contractSignature} illustrative={content.contractIsIllustrative} />
      </section>

      <section aria-labelledby="phase-limitations-heading">
        <h2 id="phase-limitations-heading" className="text-xl font-bold tracking-tight mb-2">
          Known Limitations &amp; Confirmed Defects
        </h2>
        <ul className="space-y-1.5 text-sm text-muted-foreground list-disc pl-5 mb-3">
          {content.limitations.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <DefectPanel defects={content.knownDefects} />
      </section>

      <section aria-labelledby="phase-source-heading">
        <h2 id="phase-source-heading" className="sr-only">
          Read Full Documentation
        </h2>
        <p className="text-sm text-muted-foreground">
          Full documentation: <code className="font-mono text-xs">docs/architecture/{content.sourceDoc}</code>
          <span className="italic"> (no repository URL is named in any frozen document — the "View on GitHub →" link target is an implementation decision left for a future pass, once a repository URL exists to link to.)</span>
        </p>
      </section>
    </div>
  )
}
