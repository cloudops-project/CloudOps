# One-command self-host feature tests

These host-side tests cover configuration, secret stability, Compose isolation,
health diagnostics, backup path confinement, command dispatch, and destructive
confirmation without requiring AWS, Cloudflare, or other live providers.

Container integration is exercised separately by the CI self-host job so unit
failures remain fast and component-specific. Application behavior remains in
`apps/api/app/tests`.
