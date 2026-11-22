import { ExpandoPanel } from "./expando-panel"

interface AccordionGridItem {
  headline: string
  visibleSummary: string
  detailContent: string
}

interface AccordionGridProps {
  items: AccordionGridItem[]
  columns?: 2 | 3 | 5
}

export function AccordionGrid({ items, columns = 3 }: AccordionGridProps) {
  const colsClass = columns === 5 ? "sm:grid-cols-3 lg:grid-cols-5" : columns === 2 ? "sm:grid-cols-2" : "sm:grid-cols-2 lg:grid-cols-3"

  return (
    <div className={`grid grid-cols-1 ${colsClass} gap-4`}>
      {items.map((item) => (
        <ExpandoPanel
          key={item.headline}
          summary={
            <div className="text-left">
              <p className="font-semibold text-foreground">{item.headline}</p>
              <p className="text-sm text-muted-foreground mt-1">{item.visibleSummary}</p>
            </div>
          }
        >
          {item.detailContent}
        </ExpandoPanel>
      ))}
    </div>
  )
}
