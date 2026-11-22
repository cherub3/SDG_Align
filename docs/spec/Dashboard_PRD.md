# Dashboard PRD

> Part of the split Dashboard Specification v1.0. See also: [Dashboard_UI_Spec.md](./Dashboard_UI_Spec.md) ·
> [Dashboard_Component_Library.md](./Dashboard_Component_Library.md) ·
> [Dashboard_Wireframes.md](./Dashboard_Wireframes.md) · [Dashboard_Roadmap.md](./Dashboard_Roadmap.md) ·
> [Dashboard_Frontend_Architecture.md](./Dashboard_Frontend_Architecture.md)
>
> Full planning-session history (how this was derived, all reviews) remains in the original plan file.
> This split is reorganization only — no content, terminology, or value was changed.

## 0. Definitions

| Term | Definition |
|------|-----------|
| **Snapshot** | A metric or panel value fixed at capture time; does not update as the system runs |
| **Recorded Demonstration** | Mode B — the dashboard plays from pre-recorded trace JSON; no live backend involved |
| **Live Mode** | Mode A — the dashboard calls the real backend via `observe_request()` and displays actual results |
| **Static Mode** | Mode C — the dashboard runs entirely from build-time static assets; no backend exists at all |
| **Observation Record** | The Phase 2.3 artifact (correlation_id, outcome, duration) produced once per request by `observe_request()` |
| **Execution Timeline** | The Gantt-style visualization of per-stage elapsed time for one query (Pipeline Explorer) |
| **System Health** | The Home-page panel summarizing operational status of each wired component (adapter, index, pipeline) |
| **Architecture Phase** | One of the 8 frozen application-shell layers (1.1–2.3) documented under `docs/architecture/` |

**Illustrative vs. canonical values.** Unless stated otherwise, all numeric values in this specification
(durations, counts, percentages, correlation IDs) are illustrative examples captured from a recorded
demonstration and are not normative requirements. Canonical values are stated explicitly with their own
provenance below. Live values only exist in Mode A.

### Project Facts (Canonical — Single Source)

| Fact | Value | Type | Provenance |
|------|-------|------|------------|
| Pipeline stages | 22 (Stages 0–21) | [CANONICAL] | Frozen pipeline architecture |
| Tests passing | 575 | [CANONICAL] | GitHub CI · confirmed 2026-07-23 |
| Architecture phases | 8 (Phases 1.1–2.3) | [CANONICAL] | Frozen application-shell architecture |
| Documents ingested | 13 | [CANONICAL] | Corpus manifest |
| Documents indexed | 6 | [CANONICAL] | Corpus manifest (7 quarantined as scanned) |
| AI providers | 3 (LLM, Embedding, Planner) | [CANONICAL] | Phase 1.2/1.3/1.4 |
| Adapter boundaries | 6 (LLM, Cache, Tool, Index, Planner, Conversation) | [CANONICAL] | Frozen adapter contracts |
| Agent steps | 3 (Memory, Tool, Planner) | [CANONICAL] | Stage 19–21 |
| Engineering thesis | "Deterministic before probabilistic" | [CANONICAL] | Architecture Principle #2 |
| Sample query duration | 984ms (n=1) | [RECORDED DEMO] | Metric Methodology, Dashboard_UI_Spec.md §Metric Methodology |

This table is the single canonical source; every other occurrence of these facts elsewhere in the split
documents is a restatement, not an independent value.

## 1. Product Requirements Document

### Vision

SDG Align Dashboard is a professional AI observability and portfolio showcase built on top of the frozen
22-stage RAG + agent-orchestration pipeline. It is the primary interactive interface into an otherwise
invisible system — presenting a deterministic Python library as an inspectable, runnable artifact.

### Target Users

1. **Recruiters** — 30-second scan; need visual proof the project is real, working, and substantial.
2. **Hiring managers** — 3-minute read; need evidence of architectural thinking, not just execution.
3. **Technical interviewers** — 15-minute deep dive; want to probe every decision.
4. **Engineers** — peer review; want clean, honest telemetry.
5. **Portfolio visitors (general)** — want to understand what "SDG alignment" means before caring how it works.

### User Personas

**Alex, Senior ML Engineer (Technical Interviewer)** — validates distributed state, determinism, failure
modes; inspects the planner's decision trace, the observability record, and asks "why did you do X here?"

**Jamie, Recruiting Manager (Non-Technical)** — confirms the candidate built something relevant to
development-sector AI; reads the hero, watches a sample query run, downloads the architecture PDF.

**Morgan, Principal Architect (Deep Reviewer)** — reviews every architectural boundary; reads the
architecture explorer phase-by-phase, checks whether known limitations are documented.

### User Stories

1. As Alex, submit a sample query and watch the full Stage 10→21 execution trace with per-stage latency/outcome.
2. As Alex, expand the agent planner node and read the PlannerState machine transitions.
3. As Alex, inspect a single ObservationRecord for any past request.
4. As Jamie, understand what SDG Align does in 10 seconds from the hero section.
5. As Jamie, see a sample query run against real documents and return a grounded answer with citations.
6. As Morgan, navigate to any of the 9 architecture pages and read responsibility/lifecycle/contract.
7. As Morgan, see the complete 22-stage pipeline as a labeled swimlane diagram.
8. As an Engineer, read the request observability timeline for any request.
9. As any user, see the live ingestion corpus status.
10. As any user, see the test suite health badge (575 passing) inline.

### Success Metrics

**Recruiter test (30s):** articulate what it does, what it built, and one reason it's technically
serious — from Home alone.

**Hiring manager test (3min):** identify the engineering thesis, scale (22 stages, 575 tests), and one
concrete architectural decision from About — without opening code.

**Technical interviewer test (15min):** fully explain the Phase 2.3 observability contract using only
the Architecture Phase Detail page and the Observability page; identify the dominant pipeline stage from
the ExecutionTimeline unprompted.

**Engineering test:** all pages load < 2s static; no horizontal scroll at 1280/768/375px; all 14
portfolio deliverables complete, not placeholders.

### MVP (Track A Phase 1 — full scope)

Home (hero, executive metrics strip, system health, architecture preview, animated trace, tech stack);
Architecture section (8 phase pages + Principles; 22-stage swimlane); Pipeline Explorer sample mode;
Observability with pre-recorded examples; responsive, accessible, dark/light theme; all Track A Phase 1
portfolio deliverables. See [Dashboard_Roadmap.md](./Dashboard_Roadmap.md) for the full roadmap.

### Future Roadmap

Track B Phase 2: live pipeline integration. Phase 3: planner inspector, session analytics. Phase 4:
document upload + ingestion trace. Phase 5: evaluation results page. Full detail in
[Dashboard_Roadmap.md](./Dashboard_Roadmap.md).

## 2. Information Architecture

### Site Map

```
SDG Align Dashboard
├── Home                    (landing; tells the entire story without navigation)
├── Architecture            (Overview + 8 phase pages 1.1–2.3 + Principles)
├── Pipeline Explorer       (query panel, Execution Timeline, Stage Cards, Result panel)
├── Observability           (summary strip, request log table, record detail drawer)
└── About                   (case study; visual-first)
```

Navigation note: Architecture Overview has a sidebar phase nav listing all 9 sub-pages. The top-level
nav bar shows "Architecture" as a single item, landing on Overview. Phase sub-pages are reached only via
the swimlane diagram or the sidebar nav — never as separate top-level nav items.

### Navigation

- **Top-level nav bar:** Logo/wordmark · Home · Architecture · Pipeline Explorer · Observability · About
- **Active state:** underline indicator on current top-level page
- **Breadcrumbs:** shown on Architecture sub-pages only (`Architecture > Phase 2.2 > Runtime Orchestration`)
- **Back to top:** floating button on long pages
- **Mobile:** hamburger → full-screen drawer, same 5 items, no nesting hidden

### Page Hierarchy

- Level 0: Home (single-column hero layout)
- Level 1: Architecture, Pipeline Explorer, Observability, About (two-column max-width layouts)
- Level 2: Architecture sub-pages (full-width prose + sidebar ToC), Record Detail (drawer/modal)

## 3. User Flows

Wireframe cross-references: Flow A → Home, Flow B → Pipeline Explorer (Timeline), Flow C → Pipeline
Explorer (Cards, Stage 21 expanded), Flow D → Architecture Overview, Flow E → Observability. See
[Dashboard_Wireframes.md](./Dashboard_Wireframes.md) for the visual layouts each flow drives.

**Flow A — "I want to understand what this is" (Jamie):** Land on Home → hero headline/sub-headline →
`[Watch it run ▶]` plays inline trace → corpus status strip → `[View full architecture →]`.

**Flow B — "Ask a question" (Alex, Pipeline Explorer):** Navigate to Explorer → pre-filled query/doc
selector → `[Run Query]` → 12 stage cards animate → Result Panel (answer, citations, quality) →
Observability badge → `[Inspect Planner →]`.

**Flow C — "Inspect the planner" (Alex's deep-dive):** Stage 21 expanded → PlannerState machine diagram
→ PlanDecision card → execution record → `[View ObservationRecord →]`.

**Flow D — "View the architecture" (Morgan):** Architecture Overview → 22-stage swimlane → phase map →
click phase tile → Phase Detail (responsibility, lifecycle, contract, limitations) → `[Read full doc →]`.

**Flow E — "View observability" (Engineer):** Navigate to Observability → Request Log table → click row
→ Record Detail drawer → `[associated trace: link to Pipeline Explorer]`. Empty state: "No requests
recorded yet."
