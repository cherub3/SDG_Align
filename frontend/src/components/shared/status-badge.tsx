import { cn } from "../../lib/utils"

export type StatusType =
  | "SUCCESS"
  | "PARTIAL_SUCCESS"
  | "FAILED"
  | "COMPLETED"
  | "QUARANTINED"
  | "FROZEN"

interface StatusBadgeProps {
  status: StatusType
  label: string
}

export function StatusBadge({ status, label }: StatusBadgeProps) {
  const statusConfig: Record<StatusType, string> = {
    SUCCESS: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800",
    COMPLETED: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800",
    PARTIAL_SUCCESS: "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800",
    FAILED: "bg-destructive/15 text-destructive border-destructive/30",
    QUARANTINED: "bg-orange-500/15 text-orange-700 dark:text-orange-400 border-orange-200 dark:border-orange-800",
    FROZEN: "bg-blue-500/15 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-800",
  }

  const dotConfig: Record<StatusType, string> = {
    SUCCESS: "bg-emerald-500",
    COMPLETED: "bg-emerald-500",
    PARTIAL_SUCCESS: "bg-amber-500",
    FAILED: "bg-destructive",
    QUARANTINED: "bg-orange-500",
    FROZEN: "bg-blue-500",
  }

  return (
    <div className={cn("inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full border text-xs font-semibold transition-colors", statusConfig[status])}>
      <span className={cn("w-1.5 h-1.5 rounded-full", dotConfig[status])} aria-hidden="true" />
      {label}
    </div>
  )
}
