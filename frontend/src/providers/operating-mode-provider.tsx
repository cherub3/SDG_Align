import { createContext, useContext, useEffect, useState } from "react"
import { detectLiveBackend, WAKING_NOTICE_AFTER_MS } from "../lib/mode-detection"

type OperatingMode = "Mode A (Live)" | "Mode B (Recorded Demonstration)" | "Mode C (Static)"

type OperatingModeProviderProps = {
  children: React.ReactNode
  defaultMode?: OperatingMode
}

// checking: started, answered within the notice delay so far. waking: no answer yet, backend may be starting.
// live: reachable (Mode A). unavailable: check failed or timed out, so live pages show an offline message.
export type BackendStatus = "checking" | "waking" | "live" | "unavailable"

type OperatingModeState = {
  mode: OperatingMode
  setMode: (mode: OperatingMode) => void
  backendStatus: BackendStatus
}

const initialState: OperatingModeState = {
  mode: "Mode C (Static)",
  setMode: () => null,
  backendStatus: "checking",
}

const OperatingModeContext = createContext<OperatingModeState>(initialState)

export function OperatingModeProvider({
  children,
  defaultMode = "Mode C (Static)",
}: OperatingModeProviderProps) {
  const [mode, setMode] = useState<OperatingMode>(defaultMode)
  const [backendStatus, setBackendStatus] = useState<BackendStatus>(
    defaultMode === "Mode A (Live)" ? "live" : "checking",
  )

  useEffect(() => {
    // Startup-only detection (Dashboard_Frontend_Architecture.md: Operating Mode persistence is
    // "None, re-detected per session", reset behavior "Only at startup fallback") -- runs once per
    // mount, never re-polls mid-session, and never downgrades an explicit Mode A default.
    if (defaultMode === "Mode A (Live)") return
    let cancelled = false
    const wakingTimer = setTimeout(() => {
      if (!cancelled) setBackendStatus((s) => (s === "checking" ? "waking" : s))
    }, WAKING_NOTICE_AFTER_MS)
    detectLiveBackend().then((reachable) => {
      if (cancelled) return
      if (reachable) setMode("Mode A (Live)")
      setBackendStatus(reachable ? "live" : "unavailable")
    })
    return () => {
      cancelled = true
      clearTimeout(wakingTimer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <OperatingModeContext.Provider value={{ mode, setMode, backendStatus }}>
      {children}
    </OperatingModeContext.Provider>
  )
}

export const useOperatingMode = () => {
  const context = useContext(OperatingModeContext)
  if (context === undefined)
    throw new Error("useOperatingMode must be used within a OperatingModeProvider")
  return context
}
