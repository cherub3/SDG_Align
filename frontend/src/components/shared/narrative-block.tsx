interface NarrativeBlockProps {
  headline: string
  body: string
}

export function NarrativeBlock({ headline, body }: NarrativeBlockProps) {
  return (
    <div className="max-w-3xl space-y-2">
      <p className="text-lg font-medium text-foreground">{headline}</p>
      <p className="text-lg text-muted-foreground">{body}</p>
    </div>
  )
}
