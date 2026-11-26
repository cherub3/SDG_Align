import { ExpandoPanel } from "../../shared/expando-panel"
import type { Citation } from "../../../content/demo-data/pipeline-trace"

export function CitationCard({ citation }: { citation: Citation }) {
  return (
    <ExpandoPanel
      summary={
        <span className="flex flex-col items-start text-left">
          <span className="font-medium text-foreground">{citation.sourceDocTitle}</span>
          <span className="text-xs text-muted-foreground">
            rank {citation.retrievalRank} · score {citation.similarityScore.toFixed(2)}
          </span>
        </span>
      }
    >
      <p>{citation.chunkText}</p>
      <p className="mt-1 text-xs">
        {citation.section ? `Section: ${citation.section} · ` : ""}
        {citation.pages ? `page ${citation.pages} · ` : ""}chunk {citation.sourceDocId}
      </p>
    </ExpandoPanel>
  )
}
