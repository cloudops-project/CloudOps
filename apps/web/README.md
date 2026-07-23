# CloudOps Web

React/TypeScript administration UI for Stage 1 identity, Stage 2 AWS onboarding, and Stage 3 asset discovery. Access JWTs remain in memory; refresh uses the API's HttpOnly cookie with `credentials: include`. A failed refresh clears client authentication and protected routes redirect to login.

```powershell
npm install
npm run dev
npm run format:check
npm run lint
npm run typecheck
npm run test
npm run build
```

The access JWT remains in module memory. The refresh token is an HttpOnly cookie and is never read by JavaScript. A failed refresh invalidates both the in-memory token and `AuthProvider` user state, causing protected routes to redirect to login.

Set `VITE_API_BASE_URL` to the API origin. The UI includes registration, login, organization creation, invitation acceptance, the Stage 1 admin dashboard, member/invitation/role management, profile/password change, unauthorized, and not-found views. It intentionally excludes later-stage cloud-security widgets.

Stage 2 adds owner/admin-only AWS account list, creation, details, generated IAM setup instructions, trust/permission policy viewers, role ARN entry, connection validation/failure results, and disconnect confirmation.

Stage 3 adds tenant-scoped assets, asset details, filters, pagination, discovery jobs, sanitized results, and an accessible inventory-read confirmation before authorized users start discovery. It does not display findings, security analysis, compliance, risk, or remediation.

## Stage 6 risk workflow

The `/risk` experience presents organization score and priority, critical-finding/account
counts, stable risk-ranked findings, priority/search filters, pagination, and an accessible
recalculation confirmation dialog. Scores are accompanied by text, provider-derived labels are
escaped by React, and assessment controls follow the backend role matrix.
