import { lazy } from "react"

// Home is never split — it is the required first paint for every entry scenario (recruiter
// scan, portfolio link, README link) per Architecture doc §4/§15. Every other route is its
// own lazy-loaded chunk, per the Performance Budget's code-splitting strategy.
export const ArchitecturePage = lazy(() => import("./routes/architecture").then((m) => ({ default: m.ArchitecturePage })))
export const PhaseDetailPage = lazy(() => import("./routes/phase-detail").then((m) => ({ default: m.PhaseDetailPage })))
export const PrinciplesPage = lazy(() => import("./routes/principles").then((m) => ({ default: m.PrinciplesPage })))
export const PipelineExplorerPage = lazy(() => import("./routes/pipeline-explorer").then((m) => ({ default: m.PipelineExplorerPage })))
export const ObservabilityPage = lazy(() => import("./routes/observability").then((m) => ({ default: m.ObservabilityPage })))
export const AboutPage = lazy(() => import("./routes/about").then((m) => ({ default: m.AboutPage })))
