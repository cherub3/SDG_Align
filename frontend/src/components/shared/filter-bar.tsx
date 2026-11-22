interface FilterBarProps<T extends string> {
  options: readonly T[]
  active: T
  onChange: (value: T) => void
  label?: string
}

export function FilterBar<T extends string>({ options, active, onChange, label = "Filter" }: FilterBarProps<T>) {
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option}
          type="button"
          onClick={() => onChange(option)}
          aria-pressed={active === option}
          className={`px-3 py-1.5 rounded-full text-sm font-medium border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
            active === option ? "bg-primary text-primary-foreground border-primary" : "border-border bg-card hover:bg-muted/40"
          }`}
        >
          {option}
        </button>
      ))}
    </div>
  )
}
