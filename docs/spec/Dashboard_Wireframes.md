# Dashboard Wireframes (Visual Only)

> Part of the split Dashboard Specification v1.0. See also: [Dashboard_PRD.md](./Dashboard_PRD.md) ·
> [Dashboard_UI_Spec.md](./Dashboard_UI_Spec.md) ·
> [Dashboard_Component_Library.md](./Dashboard_Component_Library.md) ·
> [Dashboard_Roadmap.md](./Dashboard_Roadmap.md) ·
> [Dashboard_Frontend_Architecture.md](./Dashboard_Frontend_Architecture.md)
>
> **These are layout diagrams only.** For section behavior, data, interactions, states, and acceptance
> criteria, see the matching page in [Dashboard_UI_Spec.md](./Dashboard_UI_Spec.md) — this file does not
> restate any of it.

## Home Page — see Dashboard_UI_Spec.md § Page: Home

```
┌──────────────────────────────────────────────────────────────────┐
│ [●] SDG Align      Home  Architecture  Explorer  Obs  About      │
├──────────────────────────────────────────────────────────────────┤
│ SECTION 1 — HERO: headline, sub-headline, 2 CTAs, context line   │
├──────────────────────────────────────────────────────────────────┤
│ SECTION 2 — EXECUTIVE METRICS: 10 MetricCards, 5×2 desktop grid  │
├──────────────────────────────────────────────────────────────────┤
│ SECTION 3 — PIPELINE DEMO: query line + 12 animating stage cards│
│             + result strip + Obs badge + [Replay ↺] [Explorer →]│
├──────────────────────────────────────────────────────────────────┤
│ SECTION 4 — SYSTEM HEALTH: 8-row two-column status table        │
├──────────────────────────────────────────────────────────────────┤
│ SECTION 5 — ARCHITECTURE PREVIEW: 3-row mini swimlane            │
├──────────────────────────────────────────────────────────────────┤
│ SECTION 6 — FEATURE HIGHLIGHTS: 3-column card grid               │
├──────────────────────────────────────────────────────────────────┤
│ TECH STACK STRIP (horizontal badges)                             │
└──────────────────────────────────────────────────────────────────┘
```

## Architecture Overview — see Dashboard_UI_Spec.md § Page: Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Nav bar                                                      │
├─────────────────────────────────────────────────────────────┤
│  PHASE TIMELINE STRIP — 8 clickable FROZEN pills               │
├─────────────────────────────────────────────────────────────┤
│  INGESTION (0–9) swimlane row                                  │
│  QUERY/RAG (10–18) swimlane row                                │
│  AGENT (19–21) swimlane row                     [Download SVG] │
├─────────────────────────────────────────────────────────────┤
│  Stage detail cards (22, collapsed by default, grid)           │
└─────────────────────────────────────────────────────────────┘
```

## Pipeline Explorer — see Dashboard_UI_Spec.md § Page: Pipeline Explorer

```
┌───────────────────────┬──────────────────────────────────────────┐
│  QUERY PANEL           │  VIEW: [Timeline ▤]  [Cards ▦]           │
│  query textarea         │  ─────────────────────────────────────  │
│  document selector       │  TIMELINE VIEW: 12 proportional bars,  │
│  [Run Query ▶]            │  dominant stage callout                │
│                            │  ─────────────────────────────────────  │
│                            │  RESULT: answer, citations, badges,    │
│                            │  ObservationRecord strip                │
└───────────────────────┴──────────────────────────────────────────┘

CARD VIEW (when selected): 12 collapsed StageCards, expand on click.
```

## Observability — see Dashboard_UI_Spec.md § Page: Observability

```
┌─────────────────────────────────────────────────────────────┐
│  Nav bar                                                      │
├─────────────────────────────────────────────────────────────┤
│  Summary strip: [total] [completed ✓] [failed ✗] [avg]        │
├─────────────────────────────────────────────────────────────┤
│  Filter bar: [All ▼] [Completed] [Failed]                     │
├──────────────────────┬────────────┬──────────┬─────────────┤
│  Correlation ID       │  Outcome   │  Duration │  When        │
├──────────────────────┴────────────┴──────────┴─────────────┤
│  … rows (row click → Record Detail drawer)                    │
└─────────────────────────────────────────────────────────────┘
```

## About Page — see Dashboard_UI_Spec.md § Page: About

```
┌──────────────────────────────────────────────────────────────────┐
│  Nav bar                                                          │
├──────────────────────────────────────────────────────────────────┤
│  NARRATIVE LEAD                                                   │
├──────────────────────────────────────────────────────────────────┤
│  ENGINEERING THESIS blockquote (always visible)                   │
├──────────────────────────────────────────────────────────────────┤
│  ARCHITECTURE PRINCIPLES — 5-card accordion grid                  │
├──────────────────────────────────────────────────────────────────┤
│  DECISION TIMELINE — 8 vertical entries                           │
├──────────────────────────────────────────────────────────────────┤
│  KNOWN LIMITATIONS — accordion list                               │
├──────────────────────────────────────────────────────────────────┤
│  TECH STACK — expandable badge cards                              │
├──────────────────────────────────────────────────────────────────┤
│  CONTACT / SOURCE links                                            │
└──────────────────────────────────────────────────────────────────┘
```
