import type { LucideIcon } from "lucide-react"

interface FeatureCardProps {
  title: string
  description: string
  icon: LucideIcon
  href?: string
}

export function FeatureCard({ title, description, icon: Icon, href }: FeatureCardProps) {
  return (
    <div className="flex flex-col p-6 bg-card border rounded-xl shadow-sm text-card-foreground">
      <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center mb-4">
        <Icon className="w-6 h-6 text-primary" aria-hidden="true" />
      </div>
      <h3 className="text-xl font-bold tracking-tight mb-2">{title}</h3>
      <p className="text-muted-foreground">{description}</p>
      {href && (
        <a href={href} className="mt-4 text-sm font-medium text-primary hover:underline">
          Learn more →
        </a>
      )}
    </div>
  )
}
