# Dashboard Frontend Architecture

> Part of the split Dashboard Specification v1.0. See also: [Dashboard_PRD.md](./Dashboard_PRD.md) ·
> [Dashboard_UI_Spec.md](./Dashboard_UI_Spec.md) ·
> [Dashboard_Component_Library.md](./Dashboard_Component_Library.md) ·
> [Dashboard_Wireframes.md](./Dashboard_Wireframes.md) · [Dashboard_Roadmap.md](./Dashboard_Roadmap.md)
>
> This file holds implementation-level architecture (folder structure, exact tokens' consuming
> mechanism, chunking/code-splitting strategy, component ownership at the file-system level) — product
> requirements and user-facing behavior live in the other 5 files, not here.

## Frontend Technology Decisions

| Technology | Role | Rationale |
|---|---|---|
| React | UI framework | Component model maps to dashboard's visual components |
| TypeScript | Type safety | Typed ObservationRecord/stage shapes matching the Python layer |
| Tailwind CSS | Styling | Enforces 8px rhythm and tokens without a separate CSS layer |
| shadcn/ui | Primitives | Accessible, unstyled-by-default (Accordion, Drawer, Table, Badge) |
| Lucide Icons | Iconography | Same vocabulary as Heroicons, tree-shakeable |
| Framer Motion | Animation | ExecutionTimeline growth, stage entrance, pipeline demo only |
| React Router | Routing | URL-addressable Architecture sub-pages, Explorer views, Obs records |
| Recharts | Data viz | ExecutionTimeline bars, Observability sparklines |
| React Flow | Node graph | Conditional — only if Planner state becomes an interactive graph; deferred to Track B Phase 2 |

These are implementation decisions only — no effect on the Python pipeline, the Phase 1.1–2.3
application shell, `observe_request()`, adapter boundaries, or the ObservationRecord schema.

## Routing Strategy

```
/                                    → Home
/architecture                        → Architecture Overview
/architecture/:phaseId                → Phase Detail (1-1..2-3)
/architecture/principles             → Principles
/pipeline-explorer                   → Pipeline Explorer (view state as ?view= query param)
/observability                       → Observability
/observability?record=:correlationId → deep-links a Record Detail drawer open on load
/about                                → About
```

**Code-splitting boundary:** each top-level route (and each Architecture Phase Detail page) is its own
route-level chunk. Home is never split — required first paint for every entry scenario.

**Unresolved-route handling:** falls through to the EmptyState treatment; no new component introduced.

## Component Hierarchy

```
Root Layout
├── NavBar (global) · Breadcrumb (Architecture routes only)
├── Home → HeroSection, MetricCard×10, Animated Pipeline Demo (ExecutionTimeline+ResultStrip+
│          ObservationRecord badge), SystemHealthPanel, ArchitecturePreviewMini, Feature Highlights,
│          Tech Stack Strip
├── Architecture Overview → NarrativeBlock, PhaseTimeline, PipelineSwimlane, 22 stage detail cards
├── Architecture Phase Detail (×9) → Breadcrumb, sidebar PhaseTimeline, ArchitectureDoc
├── Pipeline Explorer → NarrativeBlock, Query+Document Panel, ExecutionTimeline (Timeline view,
│                        same instance as Home), StageCard×12 (Cards view), CitationCard,
│                        PlannerStateCard, Result panel → ObservationRecord, StatusBadge
├── Observability → NarrativeBlock, FilterBar, MetricCard×3, RequestLogTable → ObservationRecord rows,
│                     DrawerPanel → Record Detail
└── About → NarrativeBlock, comparison table, AccordionGrid×2, DecisionTimeline → DecisionLogEntry×8,
             Tech Stack, Contact/Source
```

No component here is new relative to the Component Library. ExecutionTimeline is one implementation,
imported by both Home and Pipeline Explorer, never duplicated.

## Folder Structure

```
app/
├── routes/                 one directory per top-level page; architecture/ holds phase-detail and
│                            principles sub-routes
├── components/
│   ├── shared/              Reusable-category components
│   ├── layout/               SectionHeader, Breadcrumb, LoadingSkeleton, EmptyState, DrawerPanel, NavBar
│   ├── visualization/       PipelineSwimlane, ExecutionTimeline, ArchitecturePreviewMini, DecisionTimeline
│   └── page/                page-specific components, one subdirectory per page
├── design-system/           color/typography/spacing tokens, dark/light theme definitions
├── content/
│   ├── architecture-docs/   8 frozen phase .md files + Principles, compiled at build time
│   └── demo-data/           pre-recorded trace, executive metrics, system health, stage metadata
├── lib/                     mode detection/fallback, duration/date formatting
└── assets/                  fonts, icons, screenshot output location
```

Page-specific subdirectories exist because page-scoped components must not be interchangeable across
pages (e.g. Pipeline Explorer's own StageCard is never reused elsewhere), while shared
ExecutionTimeline is the deliberate opposite — one implementation, imported by both consumers, never
duplicated per page.

## State Management Strategy

No state management library — only React's built-in Context/state primitives.

- **Tier 1 (local component state):** query input, active view toggle, drawer open/closed, filter
  selection — page-local, never lifted.
- **Tier 2 (React Context):** theme (light/dark), Operating Mode (A/B/C, with startup-only fallback),
  the in-process ObservationRecord list (explicitly ephemeral, no external database).
- **Tier 3 (server state):** none in Track A Phase 1 (Mode C has no server). Track B Phase 1's single
  `observe_request()` call is one-shot, not cache-requiring — no data-fetching library warranted.

## State Ownership Matrix

| State | Owner | Persistence | Reset Behavior |
|---|---|---|---|
| Theme | ThemeProvider (Context, Tier 2) | `localStorage` | Only on explicit toggle |
| Operating Mode | Mode Context (Tier 2) | None, re-detected per session | Only at startup fallback |
| ObservationRecord list | Context (Tier 2) | None, in-process | Cleared only by process restart |
| Drawer state | Local (Tier 1), owning page | None | Closed on route navigation away |
| Accordion state | Local (Tier 1), owning instance | None | Collapsed on remount |
| Query input (Explorer) | Local (Tier 1) | None (pre-filled with sample) | Sample default on remount |
| Timeline animation state | Local (Tier 1), owning ExecutionTimeline | None | Pre-run state on remount; `[Replay ↺]` re-triggers |
| Observability filter | Local (Tier 1) | None | "All" on remount |
| Navigation/active route | React Router | Browser history (URL) | N/A — URL is the state |

## Static Asset Organization

```
assets/
├── images/       diagrams/       animations/
├── icons/        screenshots/    logos/
```

Referenced from README and Portfolio Deliverables D2–D8/D14.

## Demo Data Organization

Four datasets, all bundled at build time (Mode C requirement), none fetched at runtime:
1. **Pre-recorded trace** (Stages 10–21) — one source, consumed identically by Home's demo and Pipeline
   Explorer's Timeline/Cards views.
2. **Executive metrics** — 10 MetricCard values, carrying provenance sub-label fields as data.
3. **System health** — 8 rows; summary badge always computed at render time, never a literal.
4. **Stage metadata** (22 entries) — shared by ArchitecturePreviewMini and full PipelineSwimlane.

## Animation Architecture

Framer Motion is the sole mechanism. Governed surfaces: ExecutionTimeline bar growth, stage-card
staggered entrance, mobile nav drawer transition, tooltip appearance. Single top-level reduced-motion
gate wired to `prefers-reduced-motion`, consumed by every governed surface — never a per-component
duplicate check.

## Accessibility Architecture

Single shared focus-trap mechanism (mobile nav drawer + Observability DrawerPanel). Single live-region
strategy (Animated Pipeline Demo's completion announcement is the only `aria-live` surface). Status
never relies on color alone — enforced inside StatusBadge itself. One skip-to-content instance, at root
layout, ahead of NavBar.

## Theme Architecture

Light/dark via CSS custom properties, switched by a single application-root mechanism (State
Management Tier 2). Every color reference resolves through the same token set — no component defines
its own color value.

## Performance Strategy

Route-level code splitting (per Routing Strategy) keeps Phase Detail, Pipeline Explorer, Observability,
About out of Home's initial bundle. Swap-based font loading. Only the specific Framer Motion APIs the
governed surfaces need are bundled. React Flow deferred entirely out of Track A Phase 1 bundles. The
four demo datasets are the only bundled data, each small by construction (12-stage trace, 10 metrics, 8
health rows, 22 stage-metadata entries) — none scales with usage.

## Performance Budget

| Budget Area | Target |
|---|---|
| Lighthouse Performance/Accessibility/Best Practices | ≥90 / ≥95 / ≥95 |
| First Contentful Paint | < 1.5s simulated Fast 3G |
| CLS | ≤ 0.1 |
| Animation frame rate | 60fps target, ExecutionTimeline |
| Initial JS bundle size | Unspecified — no byte ceiling frozen anywhere |
| Code splitting strategy | Route-level; Home never split |
| Image strategy | Only the swimlane asset + screenshots are raster images |
| Heavy dependency deferral | React Flow excluded from every Track A Phase 1 bundle |

## Route Ownership

| Route | Owner (Milestone) | Page-Level Providers Consumed |
|---|---|---|
| `/` | Home (M1–M3) | Theme, Mode, Reduced Motion (all root-level) |
| `/architecture` | Overview (M4) | same 3 |
| `/architecture/:phaseId` | Phase Detail (M5) | same 3; sidebar reads route param, not a provider |
| `/architecture/principles` | Principles (stub since M0) | same 3 |
| `/pipeline-explorer` | Explorer (M6) | same 3; view-toggle state lives in URL, not Context |
| `/observability` | Observability (M7) | same 3 |
| `/about` | About (stub since M0, M8) | same 3 |

No route owns a page-specific Context provider anywhere — every Tier 2 Context mounts once at
RootLayout.

## Component Build Order (Implementation Plan §4)

Order: StatusBadge → MetricCard → ObservationRecord → NarrativeBlock → (SectionHeader, Breadcrumb,
LoadingSkeleton, EmptyState, ExpandoPanel, CodeBlock, TooltipOverlay, FilterBar, DrawerPanel, parallel)
→ ExecutionTimeline → SystemHealthPanel → ArchitecturePreviewMini → PipelineSwimlane → PhaseTimeline →
ArchitectureDoc → StageCard → CitationCard → PlannerStateCard → RequestLogTable → AccordionGrid →
DecisionTimeline. Orders 1–5 complete before any page-specific milestone begins.

## Milestone Plan (Implementation Plan §2)

| # | Milestone | Dependencies | Completion Criteria |
|---|---|---|---|
| M0 | Foundation | None | All 5 routes resolve; theme toggle works; no content yet |
| M1 | Home — Static | M0 | Week 1 MVP items 1–3, 8 |
| M2 | Home — Demo + Health | M1 | Week 1 MVP items 4–6; Definition of Done met |
| M3 | Home — Preview + Polish | M2 | Week 1 MVP fully complete/deployable |
| M4 | Architecture Overview | M0 | Overview Acceptance Criteria |
| M5 | Architecture Phase Detail ×9 | M4 | 6-section structure on all 9 pages |
| M6 | Pipeline Explorer | M0 | Explorer Acceptance Criteria, sample mode |
| M7 | Observability | M0, M6 | Observability Acceptance Criteria |
| M8 | About | M0 | About Acceptance Criteria |
| M9 | Cross-Page Hardening | M1–M8 | Implementation Success Criteria fully met |

M4–M8 depend only on M0 and may build in parallel.

## Risk Register (Implementation Plan §13, abridged)

| Risk | Mitigation |
|---|---|
| ExecutionTimeline built twice instead of shared | Build once at Component Build Order step, import at both sites |
| Tablet Executive Metrics column count undecided | Escalate to spec-level decision before tablet pass; do not silently pick a value |
| Reduced-motion gate built per-component | Build once at M0; every milestone imports the same gate |
| ObservationRecord Context built as page-local state | Verify Context, not local state, before M7 |
| Stage-metadata dataset diverges between Home/Architecture | Single dataset, both components import the same source |

## Implementation Decisions Required (open, non-blocking)

1. Executive Metrics grid column count at 768–1279px (spec-level, not architecture-level).
2. Server-state trigger mechanism for Track B Phase 1's `observe_request()` call.
3. Render-optimization remediation technique if a Lighthouse/CLS threshold is missed.
4. Linting/formatting tooling choice.
5. Automated test suite existence and framework.
6. Target browser list for compatibility verification.
7. Screenshot capture tooling automation.
