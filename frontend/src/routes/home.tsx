import { HeroSection } from "../components/page/home/hero-section"
import { ExecutiveMetricsStrip } from "../components/page/home/executive-metrics-strip"
import { AnimatedPipelineDemo } from "../components/page/home/animated-pipeline-demo"
import { SystemHealthPanel } from "../components/page/home/system-health-panel"
import { ArchitecturePreviewMini } from "../components/page/home/architecture-preview-mini"
import { FeatureHighlights } from "../components/page/home/feature-highlights"
import { TechStackStrip } from "../components/page/home/tech-stack-strip"

export function HomePage() {
  return (
    <div className="flex flex-col min-h-screen">
      <HeroSection />
      <ExecutiveMetricsStrip />
      <AnimatedPipelineDemo />
      <SystemHealthPanel />
      <ArchitecturePreviewMini />
      <FeatureHighlights />
      <TechStackStrip />
    </div>
  )
}
