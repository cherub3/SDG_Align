# Dashboard Roadmap

> Part of the split Dashboard Specification v1.0. See also: [Dashboard_PRD.md](./Dashboard_PRD.md) ·
> [Dashboard_UI_Spec.md](./Dashboard_UI_Spec.md) ·
> [Dashboard_Component_Library.md](./Dashboard_Component_Library.md) ·
> [Dashboard_Wireframes.md](./Dashboard_Wireframes.md) ·
> [Dashboard_Frontend_Architecture.md](./Dashboard_Frontend_Architecture.md)

## Consolidated Roadmap Lookup (NEW — reconciles every planning vocabulary in one table)

Week 1 MVP, Track A/B, Phase 1–5, and Implementation-Plan Milestones M0–M9 all describe the same
underlying work at different granularities. This table is additive documentation only — no term is
renamed or reclassified; it maps each existing vocabulary onto the others so a newcomer does not have
to mentally translate between systems.

| Milestone (M#) | Week 1 MVP? | Track | Track Phase | Depends on Architecture Phase | Status |
|---|---|---|---|---|---|
| M0 Foundation | Partial (routing/theme scaffold) | A | Phase 1 | — | ✅ Complete |
| M1 Home — Static Content | Yes (items 1–3, 8) | A | Phase 1 | — | ✅ Complete |
| M2 Home — Demo + Health | Yes (items 4–6) | A | Phase 1 | — | ✅ Complete |
| M3 Home — Preview + Polish | Yes (Definition of Done) | A | Phase 1 | — | ✅ Complete |
| M4 Architecture Overview | No | A | Phase 1 | 1.1–2.3 (read-only) | ✅ Complete |
| M5 Architecture Phase Detail ×9 | No | A | Phase 1 | 1.1–2.3 (read-only) | ✅ Complete |
| M6 Pipeline Explorer | No (sample mode only) | A | Phase 1 | — | ✅ Complete |
| M7 Observability | No (sample mode only) | A | Phase 1 | 2.3 (read-only) | 🔄 In progress |
| M8 About | No | A | Phase 1 | — | ⏳ Not started |
| M9 Cross-Page Hardening | No | A | Phase 1 (closes it) | — | ⏳ Not started |
| — Track A Phase 2 (README/GitHub assets) | No | A | Phase 2 | — | ⏳ Not started |
| — Track A Phase 3 (Poster/Deck/Video) | No | A | Phase 3 | — | ⏳ Not started |
| — Track B Phase 1 (Live Pipeline Integration) | No | B | Phase 1 | 2.1, 2.2, 2.3 (live calls) | ⏳ Future |
| — Track B Phase 2 (Planner Inspector + Analytics) | No | B | Phase 2 | Stage 21 | ⏳ Future |
| — Track B Phase 3 (Document Upload + Ingestion Trace) | No | B | Phase 3 | Stages 0–9 | ⏳ Future |
| — Track B Phase 4 (Evaluation Results) | No | B | Phase 4 | — | ⏳ Future |

**Reading the table:** "Week 1 MVP" is a subset of Track A Phase 1's own scope, not a separate track —
it is the smallest slice of Track A Phase 1 that is independently shippable. "Track A" (Portfolio
Deliverables) and "Track B" (Functional Features) run in parallel or in sequence; Track A Phase 1 is
always shippable even if Track B never begins. "Architecture Phase" (1.1–2.3) is a different axis
entirely — the backend application-shell layers some dashboard pages read from or link to; most Track A
milestones only read them (Architecture Overview, Phase Detail), while Track B Phase 1 is the first
milestone that actually calls into them live.

## Week 1 MVP

Smallest shippable portfolio artifact, completable in one iteration — see the Milestone table above
(M0 partial, M1–M3 full) for exactly which pieces qualify.

**Scope:** Landing Page, Executive Metrics, Tech Stack, Architecture Preview Mini, Animated Sample
Pipeline, Feature Highlights, README screenshots, responsive layout at all 3 breakpoints.

**Definition of done:** all components render without placeholder text; light/dark both complete; zero
console errors; Home screenshots committed (D3, D4); deployable as a static site.

## Roadmap Philosophy

Track A (Portfolio Deliverables) runs first — every phase produces tangible, shareable assets
independent of whether the live pipeline is wired. Track B (Functional Features) runs in parallel with
or after Track A, wiring the live backend and adding interactive depth on top of Track A's static
scaffold.

## TRACK A — Portfolio Deliverables

### Phase 1 — Static Dashboard + Core Assets
All 5 pages built from static/pre-recorded data; full design system; 6 new components
(ExecutionTimeline, SystemHealthPanel, ArchitecturePreviewMini, NarrativeBlock, AccordionGrid,
DecisionTimeline); mobile responsive; WCAG 2.1 AA baseline. See the Portfolio Deliverables Catalog
below for D1–D8.

### Phase 2 — README + GitHub Assets
README hero image, architecture diagram embed, pipeline flow diagram, CI badge, live dashboard link,
case-study section.

### Phase 3 — Technical Poster + Presentation Deck
Technical poster (A3/US-Letter PDF), Architecture PDF (multi-page), presentation deck (8–10 slides),
demo video (90s), dark-theme hero graphic.

## TRACK B — Functional Features

### Phase 1 — Live Pipeline Integration
Real query execution via Phase 2.3's `observe_request()` contract; ExecutionTimeline populates from
real latencies; ObservationRecord captured live; Observability populates from live session records.

### Phase 2 — Planner Inspector + Session Analytics
Animated PlannerState machine (Stage 21 card); PlanDecision cards; session analytics sub-page.

### Phase 3 — Document Upload + Ingestion Trace
Upload panel; Stages 0–9 ingestion trace view; quarantine detection card.

### Phase 4 — Evaluation Results + Gold Set
Precision/recall table, per-goal breakdown, failure analysis, version-stamped results.

## Portfolio Deliverables Catalog (D1–D14)

**Production dependency order:** D1 (Live URL) and D2 (Swimlane SVG/PDF) can be built in parallel — D2
needs no live site. D3–D8 (screenshots) all require D1 live and styled. D9–D14 depend on combinations of
D2–D8 (see below).

```
D1 (Live URL)
└→ D2 (Swimlane SVG/PDF) — can start before D1
└→ D3 (Metrics screenshot) → D4 (Hero) → D5 (Explorer trace) → D6 (Observability)
   → D7 (Phase Detail) → D8 (Mobile) — each requires D1 live and styled
D2–D8 → D9 (Poster, needs D2+D3) · D10 (Deck, needs D4+D5+D7) · D11 (Video, needs D1+D5+D7)
      → D12 (README, needs D2+D4+D1) · D13 (Architecture PDF, needs D2) · D14 (Hero graphic, needs D3)
```

| # | Deliverable | Format | Primary Audience |
|---|---|---|---|
| D1 | Live Dashboard | Web | All |
| D2 | 22-Stage Swimlane Diagram | SVG + PDF | Technical |
| D3 | Executive Metrics Screenshot | PNG 1280×800 | Recruiters |
| D4 | Home Page Hero Screenshot | PNG 1440×900 | All |
| D5 | Pipeline Explorer Trace Screenshot | PNG 1440×900 | Technical |
| D6 | Observability Screenshot | PNG 1440×900 | Engineers |
| D7 | Architecture Phase Detail Screenshot | PNG 1440×900 | Technical |
| D8 | Mobile Screenshots (3 breakpoints) | PNG | All |
| D9 | Technical Poster | PDF A3/Letter | Technical interviews |
| D10 | Presentation Deck | PDF + source | Hiring managers |
| D11 | Demo Video (90s) | MP4 | All |
| D12 | README Case Study | Markdown | All |
| D13 | Architecture PDF | PDF, multi-page | Architects |
| D14 | Dark Theme Hero Graphic | PNG 2400×800 | All |

Full per-deliverable expected-quality notes and screenshot capture checklist (S1–S15, priorities,
capture tool) live in the original plan-file history — carried forward unabridged there since it is
implementation-report material, not permanent product-specification content.

## Milestone Plan Summary

M0 Foundation → M1–M3 Home → M4–M5 Architecture → M6 Pipeline Explorer → M7 Observability → M8 About →
M9 Cross-Page Hardening. M4–M8 depend only on M0 and may build in any order or in parallel. Full
milestone-by-milestone dependency/output/completion-criteria detail lives in
[Dashboard_Frontend_Architecture.md](./Dashboard_Frontend_Architecture.md) (Frontend Implementation Plan
§2).
