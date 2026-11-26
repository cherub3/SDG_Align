// Shown instead of any result when the backend cannot be reached. There is no sample data to fall back to.
export function BackendOfflineNotice({ waking }: { waking: boolean }) {
  return (
    <div role="status" className="border rounded-lg bg-card p-6 text-sm space-y-2">
      <p className="font-semibold">{waking ? "Waking up the backend…" : "Backend offline: start it to run queries."}</p>
      <p className="text-muted-foreground">
        {waking
          ? "A backend that has been idle can take about a minute to start. This page updates when it responds."
          : "This page shows live results only. Start the backend (see the README quick start), then reload."}
      </p>
    </div>
  )
}
