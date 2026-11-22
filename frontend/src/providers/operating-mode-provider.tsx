import { createContext, useContext, useEffect, useState } from "react"
import { detectLiveBackend } from "../lib/mode-detection"

type OperatingMode = "Mode A (Live)" | "Mode B (Recorded Demonstration)" | "Mode C (Static)"

type OperatingModeProviderProps = {
  children: React.ReactNode
  defaultMode?: OperatingMode
}

type OperatingModeState = {
  mode: OperatingMode
  setMode: (mode: OperatingMode) => void
}

const initialState: OperatingModeState = {
  mode: "Mode C (Static)",
  setMode: () => null,
}

const OperatingModeContext = createContext<OperatingModeState>(initialState)

export function OperatingModeProvider({
  children,
  defaultMode = "Mode C (Static)",
}: OperatingModeProviderProps) {
  const [mode, setMode] = useState<OperatingMode>(defaultMode)

  useEffect(() => {
    // Startup-only detection (Dashboard_Frontend_Architecture.md: Operating Mode persistence is
    // "None, re-detected per session", reset behavior "Only at startup fallback") -- runs once per
    // mount, never re-polls mid-session, and never downgrades an explicit Mode A default.
    if (defaultMode === "Mode A (Live)") return
    let cancelled = false
    detectLiveBackend().then((reachable) => {
      if (!cancelled && reachable) setMode("Mode A (Live)")
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <OperatingModeContext.Provider value={{ mode, setMode }}>
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
