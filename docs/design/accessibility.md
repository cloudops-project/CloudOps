# Accessibility Requirements

## Purpose and audience

Design, frontend, QA, and product teams use this standard to target WCAG 2.2 AA and inclusive security workflows.

## Requirements

Use semantic HTML, landmarks, ordered headings, skip links, accessible names/descriptions, programmatic input errors, and live regions sparingly. Every workflow works without a pointer; focus is visible, logical, preserved across updates, and restored after dialogs. Avoid keyboard traps and provide at least 44px target guidance.

Test text and non-text contrast; never encode severity, trend, status, or chart series by color alone. Support zoom/reflow to 400% where applicable, text resizing, high-contrast/system colors, reduced motion, and pause/control for any moving content. Tables expose headers and sortable state; charts include narrative and tabular equivalents. Timeouts warn and allow extension unless security policy forbids it.

## Verification

Definition of done includes automated checks plus keyboard and screen-reader manual testing on agreed browser/assistive-technology combinations. Include login, onboarding, filters, evidence, approval, errors, notifications, and organization switching. Automated tools do not replace manual review.

## Open questions

Approve supported browsers, assistive-technology matrix, localization, accessibility statement/feedback route, and exception governance before release.
