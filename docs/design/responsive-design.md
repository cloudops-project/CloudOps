# Responsive Design

## Purpose and audience

Designers and frontend engineers use this proposal to keep CloudOps usable across desktop, tablet, and constrained mobile contexts.

## Principles

Start with content priority and reflow, not device detection. Proposed grid is 4 columns on narrow screens, 8 on tablet, and 12 on desktop, with breakpoints finalized after prototype testing. Navigation collapses without hiding the active organization. Filters become a labeled drawer with an active-count summary. Tables retain essential resource, severity/status, and action context through stacked rows/cards; users can reach complete detail.

Security-sensitive approval is supported on narrow screens only when target, evidence freshness, scope, consequences, and confirmation remain visible and usable; otherwise offer a clear read-only state and safe handoff, not a silent omission. Charts provide summaries and scroll/reflow without clipped labels.

## States and testing

Test long ARNs, rule names, translations, zoom, landscape/portrait, on-screen keyboards, reduced motion, slow networks, partial data, and error recovery. Do not use hover-only disclosure or fixed viewport heights that trap content.

## Open questions

Minimum supported width, mobile approval policy, navigation breakpoint, and density presets require stakeholder and accessibility review.
