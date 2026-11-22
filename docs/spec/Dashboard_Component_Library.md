# Dashboard Component Library

> Part of the split Dashboard Specification v1.0. See also: [Dashboard_PRD.md](./Dashboard_PRD.md) ·
> [Dashboard_UI_Spec.md](./Dashboard_UI_Spec.md) · [Dashboard_Wireframes.md](./Dashboard_Wireframes.md) ·
> [Dashboard_Roadmap.md](./Dashboard_Roadmap.md) ·
> [Dashboard_Frontend_Architecture.md](./Dashboard_Frontend_Architecture.md)

## Component Categorization

**Reusable:** MetricCard, StatusBadge, ObservationRecord, NarrativeBlock, AccordionGrid, ExpandoPanel,
CodeBlock, TooltipOverlay, FilterBar

**Page-specific:** StageCard, CitationCard, PlannerStateCard (Pipeline Explorer) · ArchitectureDoc
(Architecture Phase Detail) · RequestLogTable (Observability) · DecisionLogEntry (About) ·
SystemHealthPanel (Home)

**Visualization:** PipelineSwimlane, ExecutionTimeline, ArchitecturePreviewMini, DecisionTimeline

**Layout/Navigation:** SectionHeader, Breadcrumb, LoadingSkeleton, EmptyState, DrawerPanel, PhaseTimeline

## Core Display Components

**MetricCard** — Inputs: label, value, unit?, trend?. Variants: default/highlight/warning. Used on:
Home strip, Observability summary strip.

**StatusBadge** — Inputs: status (SUCCESS/PARTIAL_SUCCESS/FAILED/COMPLETED/QUARANTINED/FROZEN). Color
mapping: SUCCESS→green, PARTIAL_SUCCESS→amber, FAILED→red, FROZEN→blue, QUARANTINED→orange.

**StageCard** — Inputs: stage_number, stage_name, status, elapsed_ms, summary_line, detail (expandable
JSON). States: pending/running/completed/failed. Expand reveals raw output JSON.

**ObservationRecord** — Inputs: correlation_id, outcome, duration, timestamp. Sub-components:
CorrelationBadge (truncated UUID + copy), OutcomePill. Named after and renders the Phase 2.3 artifact —
the shared name is intentional.

**CitationCard** — Inputs: chunk_text, source_doc_title, source_doc_id, retrieval_rank, similarity_score.
Expand: full chunk text.

**PlannerStateCard** — Inputs: state (INITIALIZING/PLANNING/EXECUTING/EVALUATING/COMPLETED/FAILED),
timestamp, transition_from. Shows state machine, current state highlighted.

**PipelineSwimlane** — Static SVG diagram, 3 swim lanes, adapter boundary crossing lines. Interactive:
hover tooltip, click to scroll.

**PhaseTimeline** — Inputs: phases[] (name, status, href). Horizontal pill strip with FROZEN badges.

**ArchitectureDoc** — Inputs: phase_name, responsibilities[], non_responsibilities[], lifecycle_steps[],
contract_signature, limitations[], known_defects[]. Sub-components: LifecycleStepList, ContractBox,
DefectPanel (amber, severity badge).

**RequestLogTable** — Inputs: records[]. Interactive: row click, filter, sort.

**DecisionLogEntry** — Inputs: date, decision, why, alternatives_rejected. Timeline layout, collapsible
detail.

**ExecutionTimeline** [shared] — Inputs: stages[] ({stage_number, stage_name, elapsed_ms, status,
summary_line}). Renders horizontal Gantt bars, proportional to elapsed_ms. Readability guarantee: every
stage stays visible/legible regardless of proportion. Dominant stage auto-highlighted. Colors:
green/red/amber/grey. Interactive: hover tooltip, click → Card view. Used on: Home inline demo, Pipeline
Explorer Timeline view — one canonical implementation.

**SystemHealthPanel** — Inputs: components[] ({name, status, detail_line}). Two-column table, status
dot. Summary badge always computed from the row list — never hardcoded.

**ArchitecturePreviewMini** — Compact 3-row swimlane, abbreviated labels, adapter-boundary dashes, phase
layer callout. Hover tooltip. Mobile: grouped numbered list.

**NarrativeBlock** — Inputs: headline, body. Full-width block, --text-lg body. Used at top of every page
other than Home (Home carries the same principle via its Hero copy).

**AccordionGrid** — Inputs: items[] ({headline, visible_summary, detail_content}). Card grid, expand on
click. Used on About (Principles, Limitations), Architecture Phase Detail.

**DecisionTimeline** — Inputs: decisions[] ({date, headline, why, alternatives_rejected[]}). Vertical
timeline, headline+why always visible, alternatives in ExpandoPanel.

## Utility / Layout Components

SectionHeader (title+subtitle) · Breadcrumb (Architecture sub-pages) · LoadingSkeleton (Observability
table) · EmptyState (illustration + headline + CTA) · ExpandoPanel (generic collapsible) · CodeBlock
(monospace, copy button) · TooltipOverlay (hover) · FilterBar (pill filters) · DrawerPanel (right-side
slide-in, Observability record detail).

## Component Ownership Matrix

| Component | Owner Folder | Shared/Page-specific | Depends On | Consumers |
|---|---|---|---|---|
| MetricCard | `components/shared/` | Shared | StatusBadge (coloring only) | Home strip, Observability summary strip |
| StatusBadge | `components/shared/` | Shared | none | MetricCard, StageCard, SystemHealthPanel, ArchitectureDoc, RequestLogTable |
| ObservationRecord | `components/shared/` | Shared | StatusBadge (OutcomePill) | Pipeline Explorer, Observability, Home demo badge |
| NarrativeBlock | `components/shared/` | Shared | none | Architecture Overview, Pipeline Explorer, Observability, About |
| AccordionGrid | `components/shared/` | Shared | ExpandoPanel | About, Architecture Phase Detail |
| ExpandoPanel | `components/shared/` | Shared | none | StageCard, ArchitectureDoc, AccordionGrid, DecisionTimeline |
| CodeBlock | `components/shared/` | Shared | none | ArchitectureDoc (ContractBox) |
| TooltipOverlay | `components/shared/` | Shared | none | PipelineSwimlane, ArchitecturePreviewMini, MetricCard |
| FilterBar | `components/shared/` | Shared | none | Observability |
| StageCard | `components/page/pipeline-explorer/` | Page-specific | StatusBadge, ExpandoPanel | Pipeline Explorer Cards view |
| CitationCard | `components/page/pipeline-explorer/` | Page-specific | ExpandoPanel | Pipeline Explorer result panel |
| PlannerStateCard | `components/page/pipeline-explorer/` | Page-specific | none | Pipeline Explorer Stage 21 expanded |
| ArchitectureDoc | `components/page/architecture/` | Page-specific | CodeBlock, StatusBadge | Architecture Phase Detail ×9 |
| RequestLogTable | `components/page/observability/` | Page-specific | ObservationRecord, FilterBar | Observability |
| DecisionLogEntry | `components/page/about/` | Page-specific | ExpandoPanel | About Decision Timeline |
| SystemHealthPanel | `components/page/home/` | Page-specific | StatusBadge | Home Section 4 |
| PipelineSwimlane | `components/visualization/` | Visualization | TooltipOverlay, stage-metadata dataset | Architecture Overview |
| ExecutionTimeline | `components/visualization/` | Visualization (shared, 2 consumers) | TooltipOverlay, pipeline-trace dataset | Home, Pipeline Explorer |
| ArchitecturePreviewMini | `components/visualization/` | Visualization | TooltipOverlay, stage-metadata dataset | Home |
| DecisionTimeline | `components/visualization/` | Visualization | ExpandoPanel, decision-log dataset | About |
| PhaseTimeline | `components/layout/` | Navigation | StatusBadge (FROZEN) | Architecture Overview, Phase Detail sidebar |
| SectionHeader | `components/layout/` | Layout | none | every page |
| Breadcrumb | `components/layout/` | Navigation | none | Architecture Phase Detail, Principles |
| LoadingSkeleton | `components/layout/` | Layout | none | Observability table |
| EmptyState | `components/layout/` | Layout | none | Observability |
| DrawerPanel | `components/layout/` | Layout | none | Observability Record Detail |

**Visualization shared-status note:** PipelineSwimlane, ArchitecturePreviewMini, and DecisionTimeline
each have only one consuming page today but are categorized as Visualization by type, not consumer
count. ExecutionTimeline is the only Visualization component with 2+ consumers today, and the one the
single-source-of-truth requirement protects most directly.

## Component Reverse-Lookup Index

| Component | Used By |
|---|---|
| MetricCard | Home (Executive Metrics Strip), Observability (summary strip) — **not** Architecture |
| StatusBadge | MetricCard, StageCard, SystemHealthPanel, ArchitectureDoc, RequestLogTable |
| ObservationRecord | Pipeline Explorer (result strip), Observability (table rows), Home (demo badge) |
| NarrativeBlock | Architecture Overview, Pipeline Explorer, Observability, About |
| ExecutionTimeline | Home (demo), Pipeline Explorer (Timeline view) — single shared instance |
| ArchitecturePreviewMini | Home only |
| PipelineSwimlane | Architecture Overview only |
| DecisionTimeline | About only |
| TooltipOverlay | ExecutionTimeline, ArchitecturePreviewMini, PipelineSwimlane, MetricCard |
| PhaseTimeline | Architecture Overview (top strip), Phase Detail (sidebar) |
| StageCard | Pipeline Explorer (Cards view) only |
| CitationCard | Pipeline Explorer only |
| PlannerStateCard | Pipeline Explorer (Stage 21 expanded) only |
| ArchitectureDoc | Architecture Phase Detail only |
| RequestLogTable | Observability only |
| DecisionLogEntry | About (Decision Timeline) only |
| SystemHealthPanel | Home only |
