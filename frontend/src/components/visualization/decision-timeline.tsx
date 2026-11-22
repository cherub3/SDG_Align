import { DecisionLogEntry } from "../page/about/decision-log-entry"

export interface Decision {
  date: string
  headline: string
  why: string
  alternativesRejected: string
}

interface DecisionTimelineProps {
  decisions: Decision[]
}

export function DecisionTimeline({ decisions }: DecisionTimelineProps) {
  return (
    <div className="space-y-6">
      {decisions.map((decision) => (
        <DecisionLogEntry key={decision.headline} {...decision} />
      ))}
    </div>
  )
}
