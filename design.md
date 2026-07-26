# CloudOps Current UI Design

This design reflects the merged and regression-tested Stage 1–8 baseline in `main` at
`889660ecb8a378d107f6737b4466b70362066793`, plus Stages 9-12 (notifications, remediation,
scheduler, and audit explorer) committed on `feature/v1-demo-completion` (not yet merged into
`main`).

## Document role

This is the implementation-aligned frontend design summary. The detailed visual standard remains
in `docs/design/`.

The current UI implements Stage 1 administration, Stage 2 AWS onboarding, Stage 3 inventory,
Stage 4 deterministic findings, the Stage 5 compliance workflow, the Stage 6 risk dashboard, the
Stage 7 AI assistant, the Stage 8 security dashboard, the Stage 9 notifications page, the
Stage 10 remediation workflow, the Stage 11 schedules page, and the Stage 12 audit explorer.

The risk dashboard presents organization scores, explicit priority text, severity counts,
highest-risk findings/assets/accounts, bounded filters, stable pagination, and a keyboard
accessible confirmation dialog. Scores and status are never communicated by color alone, and
provider-derived labels render as escaped React text.

## Application layout

Authenticated pages use a responsive application shell:

- Left sidebar on desktop and stacked navigation on smaller screens
- CloudOps product identity
- Header with the signed-in email and logout action
- Constrained main content area for forms, tables, cards, and status views

Primary navigation exposes Dashboard, AWS Accounts, Assets, Security, Security Posture,
Compliance, Risk, AI Assistant, Notifications, Remediation, Schedules, Audit log (role-gated to
owner/admin/auditor, matching the `AUDIT_READ` capability), Members, and Profile. Discovery and
evaluation jobs, the rule catalog, finding details, compliance frameworks/controls, and
assessment history have dedicated routes.

### Compliance

- Framework cards with versions and official references
- Historical assessment list and PASS/FAIL/NOT_ASSESSED/ERROR counts
- Owner/admin/security-analyst/cloud-engineer assessment action
- Accessible account/framework confirmation dialog with initial focus, Escape handling,
  duplicate-submit prevention, and focus return
- Auditor/viewer read-only behavior aligned with backend capabilities

## Current screens

### Authentication

- Login
- Registration
- Invitation acceptance
- Unauthorized
- Not found

### Organization administration

- Organization creation
- Stage 1 dashboard
- Member list
- Invite member
- Role/status controls
- User profile

### AWS onboarding

- AWS account list
- Add account
- AWS account details
- IAM setup instructions
- Trust-policy viewer
- Permission-policy guidance
- Role ARN form
- Connection validation and failure
- Disconnect confirmation

### Inventory and discovery

- Asset list with account, type, region, status, active/stale, and search filters
- Stable bounded pagination
- Asset details with normalized fields, tags, metadata, and seen timestamps
- Discovery-job list and status/count summaries
- Account discovery action with confirmation before execution
- Pending, running, completed, partially completed, and failed states

### Findings and evaluations

- Security dashboard with severity and status counts
- Finding filters, search, pagination, details, escaped evidence, and remediation text
- Rule catalog and evaluation jobs
- Accessible evaluation confirmation and suppression dialogs
- Role-aware actions

### Risk

- Organization overview with numeric score, textual priority, and Critical/High/Medium/Low counts
- Deterministically ranked findings plus account and asset summaries
- Component reasons, unknown-input indicators, business-impact context, and historical snapshots
- Role-aware risk-assessment confirmation and bounded context/compensating-control actions
- Loading, empty, running, completed, and failed states
- Keyboard-operable dialogs with initial focus, Escape close, and focus return
- Status and priority labels that never rely on color alone

The Stage 7 AI assistant screen is implemented for advisory explanations and drafts. Jira
creation and real email delivery are not implemented.

### Notifications (Stage 9)

- Filterable (status), paginated table of `NotificationEvent` records
- Columns: template, event type, source, channel, recipient, status, attempts, created, action
- Approve action for `pending_approval` events and Deliver action for `approved` events,
  visible only to owner/admin/security-analyst roles (matching `NOTIFICATIONS_APPROVE`)
- Terminal states (`delivered`, `failed`) render text instead of an action button; a failed
  event shows its sanitized failure reason
- Loading, empty, and API-error states; a failed action surfaces its error inline without
  crashing the page

### Remediation (Stage 10)

- A "Propose remediation" action on a finding's detail page, visible only for `open` findings
  and only to roles holding `REMEDIATION_REQUEST` (owner/admin/security-analyst/cloud-engineer);
  on success it links to the remediation list
- Filterable (status), paginated `RemediationsPage` listing title, rule, status, attempts, and
  requested time
- Approve/Reject (with a required reason) actions for `pending_approval` requests, an Execute
  action for `approved` requests, and Cancel for `pending_approval`/`approved` requests — each
  gated to match backend RBAC exactly
- Terminal states (`succeeded`, `failed`, `rejected`, `cancelled`) render text instead of action
  buttons, including the sanitized failure/rejection reason where present

### Schedules (Stage 11)

- A create-schedule form (AWS account, name, interval in minutes, minimum 15) visible only to
  roles holding `SCHEDULE_MANAGE` (owner/admin/security-analyst/cloud-engineer)
- Paginated schedule table with Enable/Disable, Run now (only while enabled), and Delete actions
  gated the same way; last-run and next-run timestamps
- A recent scan-run history table showing trigger, status, started/finished time, and a
  sanitized failure summary for failed runs

### Audit log (Stage 12, committed on `feature/v1-demo-completion`)

- Role-gated to owner/admin/auditor (`AUDIT_READ`); other roles see an explanatory access
  message instead of an attempted API call
- Filter controls for event type, resource type, result, and a since/until date-time range
- Paginated table of event, resource, result, actor, and created time
- An Export CSV action that downloads the same filtered query (capped at 5,000 rows) using the
  existing authenticated request flow, with an inline error message if the export fails

## Design tokens

### Typography

- Primary: Inter
- Fallback: `system-ui, sans-serif`
- Supported weights: 400, 500, 600, 700, 800
- Scale: H1 36px, H2 30px, H3 24px, H4 20px, body 16px, caption 14px, small 12px

### Color palette

| Token                | Value     |
| -------------------- | --------- |
| Primary background   | `#0F172A` |
| Secondary background | `#111827` |
| Sidebar              | `#0B1220` |
| Card                 | `#1E293B` |
| Hover/border         | `#334155` |
| Primary text         | `#F8FAFC` |
| Secondary text       | `#CBD5E1` |
| Muted text           | `#94A3B8` |
| Disabled text        | `#64748B` |
| Primary blue         | `#2563EB` |
| Blue hover           | `#1D4ED8` |
| Accent blue          | `#60A5FA` |
| Success              | `#22C55E` |
| Warning              | `#F59E0B` |
| Critical             | `#DC2626` |
| Information          | `#06B6D4` |

Risk colors always accompany textual LOW, MEDIUM, HIGH, or CRITICAL labels. Unknown inputs,
running/failed assessment states, and component reasons are also presented as text.

### Shape, spacing, and motion

- Cards: 16px radius, 20px standard padding, subtle shadow
- Buttons: 12px radius and at least 44px practical interactive height
- Page spacing: consistent 20px mobile and 32px desktop content padding
- Transitions: subtle 150–200ms hover/focus changes
- Icons: Lucide React

## Reusable UI patterns

- `AppShell` and `ProtectedRoute`
- Cards and KPI/stat summaries
- Primary, secondary, and danger buttons
- Labeled form fields and validation messages
- Status badges with text labels
- Loading, empty, and error panels
- Tables and bounded pagination controls
- Confirmation dialogs
- Trust/permission policy code viewers
- Escaped JSON metadata viewer

## Interaction states

- **Loading:** visible status or skeleton without blocking keyboard access
- **Empty:** explains why content is absent and offers an appropriate next action
- **Error:** safe user-facing message without raw provider details
- **Success:** textual confirmation in addition to color
- **Partial completion:** warning with sanitized per-service results
- **Stale asset:** explicit active/stale text, not color alone

## Confirmation dialogs

Discovery confirmation identifies the AWS account name and account ID and explains that CloudOps
reads inventory metadata only. Cancel performs no API call. Confirm submits once and prevents
duplicate clicks. Dialogs have a role/name, initial focus, Escape behavior where safe, and return
focus to the trigger.

## Responsive behavior

Layouts collapse to a single column on narrow screens. Forms use the available width, tables
remain usable through responsive overflow or stacked information, and actions do not depend on
hover. Desktop layouts use a 240px sidebar and a bounded content region.

## Accessibility

- WCAG AA contrast target
- Visible keyboard focus indicators
- Semantic landmarks and headings
- Labels for form controls
- Accessible names for icon buttons
- Keyboard-operable dialogs and navigation
- Minimum practical 44px touch targets
- Status and error meaning conveyed with text, not color alone
- Untrusted metadata rendered as escaped text; no unsafe HTML

## Future UI

The Stage 6 risk dashboard, Stage 7 AI assistant workflow, Stage 8 security dashboard, Stage 9
notifications page, Stage 10 remediation workflow, Stage 11 schedules page, and Stage 12 audit
explorer are implemented. The local Version 1 demo runbook (`demo_v1.md`) now documents browser
profile setup, role demonstrations, Mailpit invitation/notification checks, remediation,
scheduling, and audit-export presentation flow. The design system reserves future space for
Stage 13 security-hardening UI (if any) and production Stage 14 operations tooling; those views
must not be presented as implemented.

## Stage 7 response design

All six AI tasks return the same strict envelope: title, bounded summary,
bounded details, caveats, immutable source references, and `draft_only=true`.
The UI renders these values as escaped text, always shows the human-review
warning, exposes history, loading/empty/error states, and hides generation
controls from Auditor and Viewer roles. Jira and email results are drafts only;
there is no delivery integration.
