interface BreadcrumbItem {
  label: string
  href?: string
}

export function Breadcrumb({ items }: { items: BreadcrumbItem[] }) {
  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex items-center gap-2 text-sm text-muted-foreground">
        {items.map((item, i) => (
          <li key={item.label} className="flex items-center gap-2">
            {item.href ? (
              <a href={item.href} className="hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded">
                {item.label}
              </a>
            ) : (
              <span aria-current="page" className="text-foreground font-medium">
                {item.label}
              </span>
            )}
            {i !== items.length - 1 && <span aria-hidden="true">&gt;</span>}
          </li>
        ))}
      </ol>
    </nav>
  )
}
