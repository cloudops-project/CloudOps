# Notification template security

V1 templates are code-owned, versioned deterministic renderers; no Jinja or
user-supplied template code is executed. Only an allowlisted finding/account/
organization projection reaches rendering. Subjects remove control characters
and are bounded, email includes plain text, webhook JSON encoding escapes
content, and provider payloads have a byte limit.

Approval stores a fingerprint over channel, template key, destination reference,
source payload hash, and provider. The worker recomputes it immediately before
delivery; any material change requires reapproval. Delivery evidence records
template version and a SHA-256 content hash, not the body.

Tenant-editable templates, HTML email, a preview endpoint, and localization are
deferred. Before adding them, introduce a tenant-owned versioned template table,
strict variable schema, autoescaped sandboxed rendering, size limits, preview
RBAC, composite tenant foreign keys, and XSS/sandbox/cross-tenant tests.
