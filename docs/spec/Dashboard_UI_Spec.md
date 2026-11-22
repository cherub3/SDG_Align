# Dashboard UI Specification

> Part of the split Dashboard Specification v1.0. See also: [Dashboard_PRD.md](./Dashboard_PRD.md) ·
> [Dashboard_Component_Library.md](./Dashboard_Component_Library.md) ·
> [Dashboard_Wireframes.md](./Dashboard_Wireframes.md) · [Dashboard_Roadmap.md](./Dashboard_Roadmap.md) ·
> [Dashboard_Frontend_Architecture.md](./Dashboard_Frontend_Architecture.md)

## Global Acceptance Criteria (inherited by every page)

- ✓ Matches its documented wireframe ([Dashboard_Wireframes.md](./Dashboard_Wireframes.md)) and this
  feature spec's content
- ✓ Responsive at 375px / 768px / 1280px, no horizontal scroll
- ✓ Keyboard accessible, correct focus order
- ✓ Lighthouse Performance ≥ 90, Accessibility ≥ 95
- ✓ Zero console errors
- ✓ No layout shift (CLS ≤ 0.1)

Each page's own Acceptance Criteria subsection below lists only what is additional or different.

## Interaction Priority Matrix

| Priority | Meaning | Examples |
|----------|---------|----------|
| **Required (Week 1 MVP)** | Blocks Week 1 MVP | Home hero CTAs, `[Watch it run ▶]`, `[Replay ↺]`, theme toggle, nav bar links |
| **Required (Track A Phase 1)** | Blocks Track A Phase 1 | Pipeline Explorer `[Run Query]` (sample mode), view toggle, Architecture phase-tile nav, Observability row click/drawer, About accordions |
| **Recommended** | Strengthens but non-blocking | Hover tooltips, `[Inspect Planner →]` deep link, tech-badge expand |
| **Future (Track B)** | Not built in Track A Phase 1 | Live query submission, Planner state animation, document upload, Evaluation Results page |

## Page: Home

**Purpose:** tell the complete project story without requiring navigation.

**Sections (order, top to bottom):**
1. **Hero** — wordmark, headline "Grounded AI analysis for UN SDG proposal alignment", sub-headline,
   two CTAs (`[Watch it run ▶]`, `[Run your own query →]`), context sentence.
2. **Executive Metrics Strip** — 10 `MetricCard`s (5×2 desktop, 2-col mobile; tablet column count is an
   **open Implementation Decision**, unresolved — see Design System tablet note below). See Metric
   Methodology below for how the two timing/quality metrics were produced.
3. **Interactive Pipeline Demo** — inline animated sample trace (query, 12 stage cards, result strip,
   ObservationRecord badge, `[Replay ↺]`, `[Open in Explorer →]`).
4. **System Health Panel** — 8 rows, status dot (green/amber/red), summary badge always computed from
   row list, never hardcoded "All Operational."
5. **Architecture Preview** — compact 3-row mini swimlane, hover tooltips, `[View full architecture →]`.
6. **Feature Highlights** — 3 cards ("Deterministic before probabilistic", "Grounded by design",
   "Built to be inspected"), each linking to Architecture Principles / Pipeline Explorer / Observability.
7. **Tech Stack Strip** — Python 3.14 · faiss-cpu · Gemini API · PyMuPDF · pytest · GitHub Actions.

**Metric Methodology:** wall-clock, Stage 10 start → Stage 21 completion; excludes frontend render/
network/process startup; cold cache; zero retries; Gemini (illustrative); n=1 sample; capture date
2026-07-23.

**Empty/Loading/Error states:** entirely static (no empty state); sample trace auto-plays 1s after load,
renders instantly under reduced motion; CI badge unreachable falls back to a static count.

**Out of scope:** auth, persistence beyond session, in-page editing, upload, admin panel, analytics,
backend calls in Mode B/C.

## Page: Architecture Overview

**Purpose:** authoritative visual reference; entry point for architecture-focused reviewers.

**Functionality:** full-width 22-stage swimlane (Ingestion/RAG/Agent lanes); phase timeline strip
(1.1→1.5→2.1→2.2→2.3, FROZEN badges); clickable phase tiles → Phase Detail; SVG/PDF download; stage
cards collapsed by default.

**Interactions:** hover stage node → tooltip; click stage node → scroll to summary card; click phase
tile → navigate.

**Out of scope:** auth, persistence, editing, upload, admin panel, analytics, backend calls.

## Page: Architecture > Phase Detail

**Standard 6-section structure, same order on all 8 phase pages:**
1. Summary (2–3 sentences)
2. Architecture Diagram (lifecycle or swimlane, downloadable)
3. Responsibilities + Non-Responsibilities (side-by-side lists)
4. Public Contract (entrypoint signature, CodeBlock, read-only)
5. Known Limitations + Confirmed Defects (combined, severity-badged)
6. `[View on GitHub →]`

Sidebar: fixed phase nav, sticky on scroll (layout element, not one of the 6 content sections).
Breadcrumb: `Architecture > Phase X.Y > [Phase Name]`.

**Out of scope:** auth, persistence, editing, upload, admin panel, analytics, backend calls; long-form
rationale stays in the GitHub `.md` source.

## Page: Pipeline Explorer

**Purpose:** the centerpiece interactive showcase.

**Functionality:** query input panel (text + doc selector + `[Run Query]`); Execution Timeline
(Gantt-style, default view); trace panel (per-stage cards, alternate view); result panel; Planner
sub-panel; view toggle `[Timeline ▤]/[Cards ▦]`.

**Execution Timeline:** 12 query-time stages as proportional colored bars (green completed / red failed
/ amber cache-miss-or-partial / grey pending); dominant stage auto-highlighted ("↑ X% of total time");
readability guarantee — every stage stays visible/legible regardless of proportional duration; hover →
tooltip; click → jumps to Card view for that stage.

**Result panel:** answer text, citation cards, groundedness classification, quality score, outcome
badge, ObservationRecord strip.

**Interactions:** `[Run Query]`, stage card expand, citation card expand, `[Inspect Planner →]`,
`[View in Observability →]`.

**Error state:** stage failure turns card red, downstream marked "— (did not run)"; e.g. "Stage 13 (LLM
Execution) raised LLMTransientError. The request completed as FAILED."

**Out of scope:** auth, document upload (Track B Phase 3), query-history persistence, admin panel,
analytics. Live backend calls exist only in Mode A.

## Page: Observability

**Purpose:** read-only window into Phase 2.3 — every request's correlation identity, outcome, and timing.

**Functionality:** request log table (10 records static MVP; 25/page paginated Track B live mode);
summary metrics strip (total, success rate, avg duration); record detail drawer.

**Table columns:** Correlation ID (truncated, copy button), Outcome (color-coded badge), Duration (ms,
sparkline), Timestamp (relative, absolute on hover).

**Interactions:** row click → drawer; copy button; outcome filter (All/Completed/Failed);
`[View trace →]`.

**Empty state:** "No requests recorded yet. Submit a query in Pipeline Explorer to see your first
observation record."

**Error state:** "Unable to load observation records. The observability service may not be running."

**Out of scope:** auth, persistent storage beyond in-process session list, editing/deleting records,
admin panel, analytics beyond the summary strip.

## Page: About

**Purpose:** project case study for portfolio visitors and interviewers.

**Sections:** Engineering Thesis blockquote (always visible); 5 Architecture Principles (card grid,
expandable rationale); Decision Timeline (8 dated entries, headline+why visible, alternatives
collapsed); Known Limitations (accordion, headline visible, rationale on expand); Tech Stack (expandable
badge cards); "What Makes SDG Align Different?" comparison table (near top); Contact/Source links.

**Out of scope:** auth, persistence, editing, admin panel, analytics; Evaluation Results content is
named only as future work (Track B Phase 4), not built here.

## Design System

### Color Palette

```
/* Core */
--color-brand-primary:    #1A56DB
--color-brand-secondary:  #0E9F6E
--color-brand-accent:     #7E3AF2

/* Semantic */
--color-success: #057A55  --color-warning: #B45309
--color-error:   #C81E1E  --color-info:    #1C64F2

/* Neutrals (light) */
--color-bg: #FFFFFF  --color-bg-subtle: #F9FAFB  --color-bg-elevated: #F3F4F6
--color-border: #E5E7EB
--color-text-primary: #111827  --color-text-secondary: #6B7280  --color-text-disabled: #9CA3AF

/* Neutrals (dark) */
--color-bg: #111827  --color-bg-subtle: #1F2937  --color-bg-elevated: #374151
--color-border: #374151
--color-text-primary: #F9FAFB  --color-text-secondary: #9CA3AF  --color-text-disabled: #6B7280
```

Design rationale: government-grade clarity — clean, high-contrast, minimal, no dark-neon anything.

### Typography

```
--font-sans: "Inter", ui-sans-serif, system-ui, sans-serif
--font-mono: "JetBrains Mono", "Fira Code", ui-monospace, monospace

--text-xs: 12px/16px   --text-sm: 14px/20px   --text-base: 16px/24px
--text-lg: 18px/28px   --text-xl: 20px/28px   --text-2xl: 24px/32px   --text-4xl: 36px/40px
(no --text-3xl — scale steps 2xl → 4xl directly)

--font-normal: 400  --font-medium: 500  --font-semibold: 600  --font-bold: 700
```

Monospace used exclusively for: contract signatures, correlation IDs, code blocks, JSON, fingerprints,
version identifiers — never prose or UI labels.

### Spacing

Base unit 4px. Scale: 1/2/3/4/5/6/8/10/12/16/20/24 → 4px/8px/12px/16px/24px/32px/48px/64px at the named
tiers used most often (`--space-4` = 16px card padding default, `--space-8` = 32px card-to-card,
`--space-12` = 48px section-to-section, `--space-16` = 64px hero padding).

### Additional Design Tokens

```
/* Radius */    --radius-sm:8px --radius-md:12px --radius-lg:16px --radius-xl:24px --radius-full:9999px
/* Shadow */     --shadow-sm / --shadow-md / --shadow-lg (reserved for overlay surfaces only)
/* Border */     --border-thin:1px --border-thick:2px
/* Duration */   --duration-fast:150ms --duration-normal:250ms --duration-slow:400ms
/* Easing */     --ease-standard / --ease-decelerate / --ease-accelerate
/* Named tiers */ --type-display-xl/-l, --type-heading, --type-body, --type-caption
```

### Responsive Behavior Rules

| Component | Desktop (≥1280px) | Tablet (768–1279px) | Mobile (<768px) |
|-----------|--------------------|-----------------------|-------------------|
| Executive Metrics grid | 5×2 | **UNDEFINED — open Implementation Decision** | 2 columns, 5 rows |
| Execution Timeline | Full-width horizontal bars, no scroll | unchanged | Vertical stacked list, bar as horizontal fill per row |
| System Health Panel | Two-column table, 8 rows | unchanged | unchanged |
| Architecture Preview Mini | 3-row mini swimlane | unchanged | Numbered stage list, 3 group headers |
| Navigation | Sticky horizontal, 5 items | unchanged | Hamburger → full-screen drawer |
| Architecture sidebar nav | Persistent sticky sidebar | unchanged | Collapsible in-page list |

### Animation Specification

| Animation | Duration | Curve | Trigger |
|-----------|----------|-------|---------|
| Stage card entrance (Home, Explorer) | 400ms staggered | ease-decelerate | Auto-play on load / `[Run Query]` |
| Timeline bar growth | 400ms | ease-standard | Stage completion |
| Card fade-in | 250ms | ease-decelerate | Page load |
| Accordion/drawer expand-collapse | 250ms | ease-standard | Click |
| Planner state expand | 250ms | ease-standard | `[Inspect Planner →]` |
| Tooltip appearance | 150ms | ease-decelerate | Hover |
| Replay ↺ | 400ms staggered | ease-decelerate | Click |
| Mobile nav drawer slide | 400ms | ease-standard | Hamburger click |

All render end-state instantly, no stagger, under `prefers-reduced-motion: reduce`.

### Iconography

Heroicons (MIT, SVG sprite). No custom icons in MVP.

### Layout Grid

Desktop (≥1280px): 12-col, 64px gutters, max-width 1280px. Tablet (768–1279px): 8-col, 32px gutters —
Executive Metrics column count at this breakpoint is **UNDEFINED**. Mobile (<768px): 4-col, 16px gutters,
single-column everything, no horizontal scroll.

### Accessibility

WCAG 2.1 AA minimum contrast; visible focus rings (2px solid brand-primary); logical focus/tab order
matching visual order; landmark roles on every page; every interactive control has an accessible name;
status never color-only; SVG diagrams carry `<title>`/`aria-label`; reduced-motion end-state rendering;
alt text on all images; skip-to-main-content as first focusable element.

**Detailed mechanism notes:** one skip-link instance at root layout, ahead of NavBar, never duplicated;
one shared focus-trap mechanism for the mobile nav drawer and the Observability DrawerPanel; the
Animated Pipeline Demo's completion announcement is the only `aria-live` surface in the app.

### Visual Design Principles

| Principle | Guidance |
|-----------|----------|
| Enterprise software aesthetic | Clear hierarchy, not flashy |
| Government-grade clarity | High contrast, nothing hidden |
| High information density | Tables over prose, cards over walls |
| Minimal but meaningful animation | Animate only to communicate state change |
| Flat surfaces, subtle elevation | Sparing box-shadow, no neumorphism |
| Consistent 8px spacing rhythm | No ad-hoc pixel values |
| Limited accent colors | 3 semantic colors max per component |
| Motion communicates state only | Remove decoration-only animation |
| Accessibility before decoration | Effect removed before accessibility compromised |
| Avoid glassmorphism / excessive gradients / marketing visuals | No blur panels, no floating orbs |

## Implementation Success Criteria

| Target | Threshold |
|--------|-----------|
| Responsive (1280/768/375px) | No layout break, no horizontal scroll |
| Lighthouse Performance/Accessibility/Best Practices | ≥90 / ≥95 / ≥95 |
| Keyboard accessibility | All interactive elements reachable/operable |
| CLS | ≤ 0.1 |
| Dark/Light parity | Every component renders correctly in both |
| Animation performance | 60fps target, no dropped frames |
| Zero console errors | On every page |
| Static deployment | Mode C deployable with zero backend |
| First Contentful Paint | < 1.5s on simulated Fast 3G |
