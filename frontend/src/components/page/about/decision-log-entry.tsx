import { ExpandoPanel } from "../../shared/expando-panel"

interface DecisionLogEntryProps {
  date: string
  headline: string
  why: string
  alternativesRejected: string
}

export function DecisionLogEntry({ date, headline, why, alternativesRejected }: DecisionLogEntryProps) {
  return (
    <div className="relative pl-6 border-l-2 border-border">
      <span aria-hidden="true" className="absolute -left-[5px] top-1.5 w-2 h-2 rounded-full bg-primary" />
      <p className="text-xs font-mono text-muted-foreground">{date}</p>
      <p className="font-semibold text-foreground mt-0.5">{headline}</p>
      <p className="text-sm text-muted-foreground mt-1">{why}</p>
      <ExpandoPanel summary={<span className="text-sm font-medium">Alternatives rejected</span>}>
        {alternativesRejected}
      </ExpandoPanel>
    </div>
  )
}
