# CloudOps Threat Model (Index)

> Root-canonical pointer per the documentation consistency pass. The full, authoritative threat
> model — assets/adversaries, the threat/control register, per-stage threats, and residual risks —
> lives at [docs/architecture/threat-model.md](docs/architecture/threat-model.md). This file adds
> only what that document does not cover: the additional trust boundary introduced for the local
> two-day demo.

See also [SECURITY_MODEL.md](SECURITY_MODEL.md) (controls as implemented, including demo
exceptions) and `DECISIONS.md` `ADR-D06` (the forwarded-host same-origin allowance).

## Summary of the full-product threat model

`docs/architecture/threat-model.md` covers, in detail: multi-tenant leakage/IDOR, compromised
org/platform administrators, session theft/CSRF, injection/XSS/SSRF, API abuse and queue flooding,
confused-deputy/IAM exposure, compromised workers, AI prompt injection and secret leakage, webhook
forgery, audit/backup tampering, and dependency/CI compromise. None of these threats or their
planned controls change for the demo; the demo narrows *scope* (synthetic data, dry-run execution)
rather than changing the threat register.

## Demo-specific addition: the forwarded-host same-origin trust boundary

The local demo introduces one new trust boundary not present in the general threat model: Nginx,
not the browser, is trusted to report the browser-facing `Host`/scheme via `X-Forwarded-Host` /
`X-Forwarded-Proto`.

- **Why it exists.** The demo's Cloudflare Quick Tunnel hostname is random and changes on restart,
  so it cannot be enumerated into `CORS_ALLOWED_ORIGINS` ahead of time. See `ADR-D01`, `ADR-D06`.
- **What is trusted.** Only the `api` service's `TRUSTED_HOSTS`-validated ingress path through the
  Compose-network Nginx container. Nginx overwrites (does not merely append) `X-Forwarded-Host` and
  `X-Forwarded-Proto` on every proxied request, so a client cannot inject its own values that
  survive the hop.
- **What is compared.** `CookieOriginMiddleware` accepts a non-allowlisted `Origin` only when it
  **exactly equals** `scheme://forwarded_host` reconstructed from those two headers — full origin
  equality, not a substring or suffix match.
- **What is refused.** Missing forwarded host, malformed scheme, mismatched scheme, mismatched
  host, and any origin that is neither allowlisted nor forwarded-same-origin all return `403`. See
  the reject-path tests enumerated in `apps/api/app/tests/test_demo_tunnel_access.py` (not executed
  this session — see `KNOWN_ISSUES.md` VAL-01).
- **Blast radius if the boundary were wrong.** A CSRF bypass on `/auth/refresh` or `/auth/logout` —
  the two cookie-authenticated routes this middleware guards. This is why the setting defaults off
  and `Settings.model_post_init` refuses it outright when `APP_ENV` is `staging` or `production`.
- **Residual risk.** The demo publishes API port 8000 directly in addition to the proxied path
  (`compose.demo.yml`), so a request can still reach the API without going through Nginx. Such a
  request would carry no `X-Forwarded-Host`, so `_forwarded_origin()` returns `None` and the
  same-origin check cannot be satisfied — the allowlist-only behavior applies unchanged. This is a
  reason to prefer the proxied path in a production-shaped deployment, not a defect in the demo.

## Not addressed here

Live AWS onboarding threats, real remediation execution threats, and production secret-management
threats are out of scope for the demo entirely (no live AWS calls, no live remediation, no
production secrets) — see `SECURITY_MODEL.md` "Production security requirements" for what remains
unimplemented and unvalidated.
