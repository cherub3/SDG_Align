import { useOperatingMode } from "../../providers/operating-mode-provider"

// Visible replacement for the old silent fallback: whenever the page is not talking to a live backend, say so.
export function BackendStatusBanner() {
  const { backendStatus } = useOperatingMode()
  if (backendStatus === "live" || backendStatus === "checking") return null
  const waking = backendStatus === "waking"
  const text = waking
    ? "Waking up the backend (it can take about a minute after being idle). Live pages are unavailable until it responds."
    : "Backend offline: start it to run queries."
  return (
    <div
      role="status"
      data-testid="backend-status-banner"
      className="border-b bg-amber-500/15 text-amber-900 dark:text-amber-200 px-4 py-2 text-sm text-center"
    >
      {text}
    </div>
  )
}
