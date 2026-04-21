---
name: frontend-production
description: Use when building or reviewing frontend UIs that must feel production-ready, distinctive, and trustworthy. Applies to Angular, React, Vue, or plain HTML/CSS work where strong hierarchy, live state, API-driven behavior, accessibility, and polished interaction matter.
---

# Frontend Production

Use this skill for frontend work that must move beyond prototype quality.
It is optimized for dashboards, control consoles, admin surfaces, product UIs, and any interface where the user needs clear status, actionable controls, and trustworthy feedback.

## Core mindset

- Start with a clear product thesis: what this UI helps someone do, and what must be visible at a glance.
- Choose a deliberate visual direction. Avoid generic dashboards, generic cards, and default UI stacks.
- Treat the frontend as a working instrument, not a mockup.
- If the backend contract is incomplete, surface the gap instead of faking the data.

## Source priorities

When working in this repository, prefer these sources in order:

1. Backend API docs and runtime docs in `docs/`
2. Existing app code and types in `frontend/angelus/src/app/`
3. Current backend response shapes in `core/` and `web/`
4. Any live examples or traces the app already emits

## Workflow

### 1. Define the UI contract

Before coding, identify:

- primary user goal
- primary data sources
- live-updating surfaces
- loading, empty, error, and retry states
- what the user can act on directly

### 2. Pick one strong visual direction

Choose one coherent direction and execute it consistently:

- restrained and technical
- editorial and information-dense
- dark operator console
- clean enterprise control room
- tactile and atmospheric

Avoid mixing styles. Do not default to the same card-grid dashboard every time.

### 3. Build around state, not static layout

Production frontends should expose these states clearly:

- initial loading
- partial loading
- success
- empty
- recoverable error
- fatal error
- live updating
- stale data

### 4. Make API behavior explicit

- Use typed request/response models.
- Normalize backend data before rendering.
- Never display raw object serialization errors to users.
- Prefer one API service layer and one state layer.
- Keep route paths and payload shapes aligned with backend docs.

### 5. Make live data legible

If the UI must show current execution or runtime activity:

- show a stable snapshot of the full graph or resource list
- highlight the active node, item, or branch
- show recent events or trace items in order
- include timestamps, status labels, and causal context
- refresh by polling, SSE, or WebSocket depending on backend support

If live updates are not available yet, make that limitation obvious.

### 6. Finish like production

Check:

- responsive behavior
- keyboard accessibility
- focus visibility
- readable contrast
- sensible empty states
- actionable error messages
- retry affordances
- no placeholder-only content
- no fake metrics
- no mismatched states between UI and backend

## Project-specific guidance for Angelus

This repository is a backend-driven swarm runtime with a thin Angular console.
The frontend should behave like an operations panel for a real system.

### The frontend should be able to show

- API root and readiness
- loaded swarms
- swarm detail
- current execution graph
- currently executing node or branch
- run results and trace history
- agent round output
- errors with enough detail to debug

### The frontend should not pretend

- do not invent live graph state if the backend does not expose it
- do not render completed output as if it were real-time progress
- do not hide backend load or execution failures behind generic banners

### If the UI needs more data

Prefer to propose a backend endpoint or shape update instead of hardcoding local assumptions.

## Design rules

- Use strong hierarchy first, then motion, then decoration.
- Prefer a few clear regions over many boxes.
- Avoid generic purple gradients and stock dashboard layouts.
- Use typography, spacing, and alignment as the main design tools.
- If a panel can be plain layout without losing meaning, remove the card treatment.
- Make the primary action unmistakable.

## Review checklist

Before marking frontend work done, confirm:

- the user can tell what the app is for in one glance
- the main status is visible without clicking
- the main action is obvious
- the data shown is real and contract-aligned
- loading and error states are implemented
- the layout works on narrow and wide screens
- the UI feels like a product, not a prototype

