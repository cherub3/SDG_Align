import { createContext, useContext, useEffect, useState } from "react"

type ReducedMotionProviderProps = {
  children: React.ReactNode
}

type ReducedMotionState = {
  reduceMotion: boolean
}

const initialState: ReducedMotionState = {
  reduceMotion: false,
}

const ReducedMotionContext = createContext<ReducedMotionState>(initialState)

export function ReducedMotionProvider({ children }: ReducedMotionProviderProps) {
  const [reduceMotion, setReduceMotion] = useState(false)

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)")
    setReduceMotion(mediaQuery.matches)

    const handler = (e: MediaQueryListEvent) => setReduceMotion(e.matches)
    mediaQuery.addEventListener("change", handler)
    return () => mediaQuery.removeEventListener("change", handler)
  }, [])

  return (
    <ReducedMotionContext.Provider value={{ reduceMotion }}>
      {children}
    </ReducedMotionContext.Provider>
  )
}

export const useReducedMotion = () => {
  const context = useContext(ReducedMotionContext)
  if (context === undefined)
    throw new Error("useReducedMotion must be used within a ReducedMotionProvider")
  return context
}
