# CloudFix Design System

## Purpose and audience

Product designers and frontend engineers use this proposed accessible visual language for a professional cloud-security interface. It defines intent only; no components are implemented.

## Foundations

Use Inter with a comparable system sans-serif fallback. Type scale: 12 caption, 14 body-small, 16 body, 20 h4, 24 h3, 32 h2, 40 h1 pixels, with at least 1.4 body line height. Spacing uses a 4px base: 4, 8, 12, 16, 24, 32, 48, 64. Use a responsive 12-column desktop, 8-column tablet, and 4-column mobile grid; content width and density require prototype validation.

Primary `#2563EB`, dark surface `#0F172A`, success `#22C55E`, warning `#F59E0B`, critical `#EF4444`, and information `#0EA5E9` are starting tokens. Pair each with tested foreground/background shades to meet WCAG 2.2 AA target contrast; never communicate severity/status by color alone. Light/dark themes use semantic tokens rather than literal colors in features.

## Components and states

- Severity badges combine icon/text: Critical, High, Medium, Low, Informational. Status badges distinguish Open, Investigating, Accepted (with expiry), Remediation requested, Approved, Verifying, Resolved, and Failed.
- Buttons have primary, secondary, text, and destructive-confirmation variants with disabled, loading, hover, and visible focus states. Inputs have persistent labels, descriptions, inline error association, and no placeholder-only labeling.
- Tables support keyboard-accessible sorting, filters, pagination, responsive card fallback, and explicit empty/error/loading states. Cards summarize rather than hide required detail.
- Dialogs are reserved for bounded decisions and restore focus; drawers preserve context for details. Toasts announce non-critical outcomes through appropriate live regions and never carry the only error explanation.
- Charts include text summaries, legends, patterns/labels, accessible palettes, and underlying tabular data/export where useful.
- Skeletons match approximate layout and announce loading once. Empty states explain scope/filtering and safe next action; errors include correlation ID and recovery path without leaking detail.

## Interaction and accessibility

All actions work by keyboard with logical order, skip links, visible 2px+ focus indicators, screen-reader names, headings/landmarks, and 44px target guidance. Respect reduced motion and avoid essential timed animation. Destructive/remediation actions show target, scope, approval, and consequences. AI advice is clearly labeled and visually subordinate to deterministic evidence.

## Open questions

Validate color pairs, density, data-visualization library, localization, high-contrast mode, and exact breakpoint tokens with prototypes and accessibility testing.
