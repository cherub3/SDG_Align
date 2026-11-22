import { Suspense, type ReactNode } from "react"

export function LazyRoute({ children }: { children: ReactNode }) {
  return <Suspense fallback={null}>{children}</Suspense>
}
