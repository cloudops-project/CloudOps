# CloudOps Current UI Design

> Per [ADR-010](docs/architecture/decisions/ADR-010-cloudops-product-name.md), the implemented UI is
> branded **CloudOps**. This document describes only `apps/web`.

See [PRD.md](PRD.md), [architecture.md](architecture.md), [rules.md](rules.md), and
[memory.md](memory.md).

## Direction and tokens

The application uses a dense dark security-operations style: slate surfaces, blue primary actions,
colored status/severity badges, compact tables, and monospaced technical identifiers.

Source: `apps/web/tailwind.config.ts` and `apps/web/src/index.css`.

| Token | Value | Use |
|---|---|---|
| `canvas` | `#0F172A` | Page background |
| `surface` | `#111827` | Header/input surface |
| `sidebar` | `#0B1220` | Navigation |
| `card` | `#1E293B` | Cards/tables |
| `border` | `#334155` | Dividers |
| `primary` / hover | `#2563EB` / `#1D4ED8` | Primary action |
| `success` | `#22C55E` | Success |
| `warning` | `#F59E0B` | Warning |
| `critical` | `#DC2626` | Destructive/critical |
| Card/button radius | `16px` / `12px` | Containers/controls |

Only a dark theme is implemented. A light theme and theme switcher are gaps.

## Typography, spacing, and layout

- Inter (400–800) with system sans-serif fallback; technical evidence uses monospace.
- Tailwind's standard spacing scale; no custom spacing-token layer.
- `.card`, `.button`, `.button-secondary`, `.input`, and `.label` are shared patterns.
- Authenticated layout becomes a `240px + 1fr` grid at the medium breakpoint.
- Responsive grids use `sm`, `md`, `lg`, and `xl`; tables use overflow containers.
- Minimum body width is 320px; interactive controls have at least 44px height.

Self-hosted fonts and a formal component/token catalog are not implemented.

## Implemented patterns

- `AppShell`, `AuthCard`, `FormField`, status badges, metric cards, tables, filters,
  pagination, confirmation dialogs, query loading/error/empty states, and evidence blocks.
- React Hook Form and Zod provide typed form validation.
- Findings use critical red, high orange, medium yellow, low green, informational blue.
- Job/account states use visible text plus green/amber/blue/red/slate styling.
- Destructive or sensitive flows use confirmation; API authorization remains authoritative.

No reusable charting dependency exists. Dashboard visuals are cards, counts, summaries, and lists;
interactive charts must not be described as implemented.

## State and accessibility behavior

- Loading uses visible text and `aria-live`.
- Errors generally use red text and `role="alert"`.
- Dialogs use `role="dialog"`, `aria-modal`, and labels; some implement focus trapping.
- `:focus-visible` has a 3px blue outline with 2px offset.
- Decorative icons are hidden from assistive technology where marked.
- Severity/status always needs text, not color alone.
- New UI must preserve keyboard access, focus visibility, and WCAG 2.1 AA contrast.

Gaps: repository-wide automated axe coverage, screen-reader matrix, reduced-motion policy,
consistent dialog focus restoration, global error boundary, and centralized retry/toast patterns.

## Tables, forms, and tenant context

- Asset and audit views use semantic tables.
- IDs/account identifiers are monospaced.
- Labels and validation messages are visible.
- Organization context is supplied by the shell/routes, but client selection is never
  authorization; server-side RBAC and tenant predicates are authoritative.

Gap: a persistent organization switcher/context banner and shared data-grid abstraction are not
consistent across all views.
