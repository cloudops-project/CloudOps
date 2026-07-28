# CloudOps Visual Design System

> This is an aspirational interaction specification. [../../design.md](../../design.md) is the authoritative inventory of tokens and components actually present in frontend code; any pattern below absent from that inventory is a gap, not an implemented capability.

## Official status, purpose, and audience

This document is the official UI standard for all current and future CloudOps frontend work. Product designers, frontend engineers, accessibility reviewers, product owners, and security reviewers must use these tokens, patterns, and interaction rules unless an approved design-system decision records an exception. Stage 1 implements identity and organization administration only; security analytics are future-stage specifications.

CloudOps is the current product and visual-system name under ADR-010. Stage 1 React components implement the foundation tokens in this document; later security-dashboard components remain specifications only.

## Design philosophy

CloudOps uses a modern enterprise cloud-security dashboard aesthetic informed by common patterns in AWS Console, GitHub, Datadog, Prisma Cloud, Wiz, and Microsoft Defender for Cloud. These products are references for information architecture and interaction quality, not templates to copy.

The experience must be:

- **Professional:** credible for security analysts, cloud engineers, auditors, and executives.
- **Minimal:** remove decoration that does not help interpretation or action.
- **High-density:** show useful security context without sacrificing hierarchy, legibility, or touch targets.
- **Accessible:** target WCAG 2.2 AA and support keyboard, screen-reader, zoom, contrast, and reduced-motion needs.
- **Security-first:** prioritize evidence, provenance, freshness, authorization, and consequences over decorative scores.
- **Dark-theme-first:** use the official dark palette by default; do not improvise per-feature colors.
- **Responsive:** preserve essential context and safe workflows from narrow screens through wide operations displays.

Deterministic evidence remains visually authoritative. AI-generated content is clearly labeled as advisory, visually separated from evidence, and never presented as an autonomous security decision.

## Typography

### Font family

Primary font: `Inter`. Fallback stack: `Inter, system-ui, sans-serif`.

Approved weights are `400`, `500`, `600`, `700`, and `800`. Use 400 for body text, 500 for controls and metadata emphasis, 600 for section headings, 700 for primary page headings and KPI values, and 800 sparingly for executive emphasis. Do not simulate unavailable weights.

| Token | Size | Recommended weight | Use |
|---|---:|---:|---|
| H1 | 36px | 700 | Page title |
| H2 | 30px | 700 | Major page section |
| H3 | 24px | 600 | Widget group or detail section |
| H4 | 20px | 600 | Card/panel title |
| Body | 16px | 400 | Primary reading text |
| Caption | 14px | 400–500 | Labels, table metadata, chart annotation |
| Small | 12px | 500 | Dense secondary metadata only |

Body line height should be at least 1.5; headings should use approximately 1.2–1.3. Never reduce essential evidence or control labels below 14px. Use tabular numerals for aligned metrics where supported.

## Color palette

Use semantic design tokens rather than hardcoded color values inside feature code. Dark theme is the official default.

### Surfaces and borders

| Token | Value | Use |
|---|---|---|
| Background primary | `#0F172A` | Main application canvas |
| Background secondary | `#111827` | Raised layout regions and navigation support |
| Sidebar | `#0B1220` | Persistent left navigation |
| Card | `#1E293B` | Cards, panels, table containers |
| Hover | `#334155` | Interactive hover/selected surface, with non-color cue |
| Border | `#334155` | Dividers, card borders, control outlines |

### Text

| Token | Value | Use |
|---|---|---|
| Text primary | `#F8FAFC` | Headings and primary values |
| Text secondary | `#CBD5E1` | Body content and table values |
| Text muted | `#94A3B8` | Supporting metadata |
| Text disabled | `#64748B` | Disabled content only; never essential information |

### Brand and feedback

| Token | Value | Use |
|---|---|---|
| Brand primary blue | `#2563EB` | Primary action, active navigation, selected data |
| Brand hover blue | `#1D4ED8` | Primary action hover |
| Brand accent blue | `#60A5FA` | Focused emphasis, links, chart accent |
| Success | `#22C55E` | Verified success or healthy state |
| Warning | `#F59E0B` | Caution or attention required |
| Critical feedback | `#DC2626` | Destructive actions and critical error feedback |
| Information | `#06B6D4` | Neutral informational state |

### Risk colors

| Risk | Value |
|---|---|
| Critical | `#DC2626` |
| High | `#F97316` |
| Medium | `#FACC15` |
| Low | `#22C55E` |
| Informational | `#3B82F6` |

Risk, status, and compliance state must never be communicated by color alone. Pair color with text, icon, shape/pattern, and accessible name. Validate every foreground/background combination at implementation time; a listed token is not automatic proof of contrast in every pairing.

## Spacing, grid, and density

Use a 4px base spacing scale: `4`, `8`, `12`, `16`, `20`, `24`, `32`, `48`, and `64` pixels. The responsive grid uses 12 columns on desktop, 8 on tablet, and 4 on mobile. Default content gutters are 24px desktop, 20px tablet, and 16px mobile, subject to accessibility testing.

Information density may be compact or comfortable at the page level, but touch targets, focus rings, labels, and evidence must remain accessible. Do not compress critical actions into icon-only controls without an accessible name and visible tooltip.

## Cards

Official card treatment:

- Border radius: `16px`.
- Internal padding: `20px`.
- Shadow: `0 8px 30px rgba(0,0,0,0.35)`.
- Surface: Card `#1E293B` with Border `#334155`.
- Hover elevation is permitted only for interactive cards; static cards must not imply clickability.

Cards need a clear title, optional description/freshness timestamp, content region, and explicit action area. KPI cards must state metric scope and comparison period and must not imply measured results when data is unavailable.

## Buttons and controls

- **Primary:** Brand primary blue background with tested high-contrast text; use for one dominant action per region.
- **Secondary:** Slate/card surface with visible border and high-contrast text.
- **Danger:** Critical red, reserved for destructive or security-sensitive confirmed actions.
- **Text/tertiary:** Low emphasis for reversible supporting actions.

Every variant supports default, hover, active, focus-visible, disabled, and loading states. Loading retains the button label or an equivalent accessible name. Danger actions show target, scope, consequences, permission/approval state, and a clear confirmation step.

Inputs use persistent labels, optional descriptions, accessible validation messages, and no placeholder-only labeling. Tables provide semantic headers, keyboard-accessible sorting/filtering, bounded pagination, and responsive alternatives without losing evidence.

## Icons

Use **Lucide React** as the official icon system when frontend dependencies are initialized in Stage 1. Preferred icons include:

- `Shield`
- `Cloud`
- `Server`
- `Users`
- `Lock`
- `Bell`
- `Database`
- `Scan`
- `Terminal`
- `AlertTriangle`
- `CheckCircle`

Icons support labels; they do not replace them for primary navigation, risk, or unfamiliar actions. Use a consistent stroke width and optical size. Decorative icons are hidden from assistive technology; informative icons have an accessible name through adjacent or programmatic text.

## Dashboard layout

The official application shell contains:

1. **Left sidebar:** CloudOps/approved product mark, Dashboard, Assets, Scans, Findings, Risk, Compliance, Remediation, Reports, Audit Logs, Users, and Settings. Visibility may reflect permission, but authorization remains server-side.
2. **Top navigation:** Global organization-scoped search, notifications, organization selector, current AWS account/scope indicator, and user profile.
3. **Main content:** Page title, scope/freshness controls, top KPI cards, charts, AWS region asset map, risk/compliance panels, activity, advisory AI recommendations, and audit timeline.
4. **Responsive grid:** 12-column desktop, 8-column tablet, and 4-column mobile composition. Widgets reorder by importance rather than simply shrinking.

The executive dashboard specification and layout are defined in [`dashboard-wireframes.md`](dashboard-wireframes.md).

## Dashboard widgets

The standard widget catalogue includes:

- KPI cards for Total Assets, Connected AWS Accounts, Active Scans, Critical Findings, Compliance Score, and Security Score.
- Findings by Severity, Asset Distribution, Security Trend, Scan History, Compliance Status, Risk Distribution, and Remediation Success widgets.
- AWS region map showing discovered resources, active/scanned regions, scan freshness, and contextual risk.
- EC2, S3, IAM Users, IAM Roles, and Security Groups inventory summary.
- Recent activity feed and audit timeline.
- Compliance framework status with source/version/coverage caveats; percentages are not certifications.
- AI recommendation panel based only on current deterministic findings and labeled advisory.

Security Score and Compliance Score require approved, versioned calculation methods and scope disclosure before displaying real values. Until then, designs use `—` or explicitly labeled mock data.

## Charts and data visualization

Approved chart forms are donut, pie, line, area, and bar. Use the simplest form that answers the question; do not use a pie/donut when precise comparison matters. Avoid excessive colors and use a maximum of one decorative accent color per chart. Semantic risk charts may use the defined risk colors because those colors encode risk categories, not decoration.

Every chart includes:

- Title, time range, organization/account scope, and last-updated state.
- Visible labels or an accessible legend.
- Text summary and tabular alternative where meaningful.
- Empty, partial-data, loading, stale-data, permission-denied, and error states.
- No unsupported precision, misleading truncated axes, decorative 3D, or compliance/certification claims.

## Motion and animation

Use subtle motion only:

- Hover elevation for interactive elements.
- `150–200ms` transitions for color, border, opacity, and small transforms.
- Skeleton loading that reflects the expected content layout.
- Respect `prefers-reduced-motion`; remove non-essential animation when enabled.
- No flashing, parallax, auto-playing decoration, exaggerated card movement, or flashy effects.

Motion must not delay security information or obscure a state change.

## Loading, empty, error, and partial states

Skeletons announce loading once and do not mimic real values. Empty states explain the current organization/account/filter scope and a safe next action. Errors include a recovery path and correlation ID without secrets. Partial scans and stale data are visually prominent and cannot be mistaken for complete current coverage. Toasts never contain the only explanation of an error or approval outcome.

## Accessibility standard

All future frontend work must target WCAG 2.2 AA and include:

- Tested text and non-text contrast.
- Full keyboard navigation, logical focus order, skip links, and no focus traps.
- Visible focus indicators of at least 2px with sufficient contrast.
- Screen-reader-friendly landmarks, headings, labels, descriptions, live regions, tables, and chart summaries.
- Minimum `44px × 44px` touch targets for interactive controls.
- Reflow/zoom support, reduced-motion behavior, and no color-only meaning.
- Focus restoration after dialogs and drawers.
- Accessible names for icon controls, status changes, risk badges, and chart data.

Automated accessibility checks are required but do not replace keyboard and screen-reader manual testing.

## Governance and exceptions

This is the official CloudOps UI standard for current and future frontend work. Pull requests that introduce or alter visual tokens, navigation, card/button behavior, icon libraries, charts, scoring, accessibility behavior, or dashboard structure require review from the frontend/design owner and accessibility reviewer. Security-sensitive workflows also require the designated security reviewer.

Exceptions require a linked issue with rationale, user impact, accessibility/security assessment, owner, reviewer, and expiry or follow-up. Product copy uses CloudOps; ADR-010 preserves the former name only in historical context.
