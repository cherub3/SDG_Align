import { createBrowserRouter } from "react-router-dom"
import { RootLayout } from "./components/layout/root-layout"
import { LazyRoute } from "./components/layout/lazy-route"
import { HomePage } from "./routes/home"
import {
  ArchitecturePage,
  PhaseDetailPage,
  PrinciplesPage,
  PipelineExplorerPage,
  ObservabilityPage,
  AboutPage,
} from "./lazy-pages"

export const router = createBrowserRouter([
  {
    path: "/",
    element: <RootLayout />,
    children: [
      {
        index: true,
        element: <HomePage />,
      },
      {
        path: "architecture",
        element: (
          <LazyRoute>
            <ArchitecturePage />
          </LazyRoute>
        ),
      },
      {
        path: "architecture/principles",
        element: (
          <LazyRoute>
            <PrinciplesPage />
          </LazyRoute>
        ),
      },
      {
        path: "architecture/:phaseId",
        element: (
          <LazyRoute>
            <PhaseDetailPage />
          </LazyRoute>
        ),
      },
      {
        path: "pipeline-explorer",
        element: (
          <LazyRoute>
            <PipelineExplorerPage />
          </LazyRoute>
        ),
      },
      {
        path: "observability",
        element: (
          <LazyRoute>
            <ObservabilityPage />
          </LazyRoute>
        ),
      },
      {
        path: "about",
        element: (
          <LazyRoute>
            <AboutPage />
          </LazyRoute>
        ),
      },
    ],
  },
])
