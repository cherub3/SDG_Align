
interface MetricCardProps {
  label: string
  value: string | number
  unit?: string
  trend?: string
  description?: string
  variant?: "default" | "highlight" | "warning"
}

const variantStyles: Record<NonNullable<MetricCardProps["variant"]>, string> = {
  default: "",
  highlight: "border-primary/40 bg-primary/5",
  warning: "border-amber-400/40 bg-amber-500/5",
}

export function MetricCard({ label, value, unit, trend, description, variant = "default" }: MetricCardProps) {
  return (
    <div className={`flex flex-col p-6 bg-card text-card-foreground border rounded-lg shadow-sm ${variantStyles[variant]}`}>
      <h3 className="text-sm font-medium text-muted-foreground">{label}</h3>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="text-3xl font-bold tracking-tight">{value}</span>
        {unit && <span className="text-sm text-muted-foreground">{unit}</span>}
        {trend && (
          <span className="text-sm font-medium text-emerald-600 dark:text-emerald-400">
            {trend}
          </span>
        )}
      </div>
      {description && (
        <p className="mt-1 text-xs text-muted-foreground">{description}</p>
      )}
    </div>
  )
}
