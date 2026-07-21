# Git and GitHub Workflow

## Purpose and audience

The five-member team uses this workflow to keep a private repository reviewable, stable, and traceable.

## Branches and commits

Protect `main` as stable; prohibit direct pushes, deletion, and force pushes. Use short-lived `feature/`, `fix/`, `docs/`, or `research/` branches linked to issues. Conventional Commits are proposed: `type(scope): summary`, with breaking and security implications in the body.

## Pull requests

Require at least one independent approval, resolved conversations, linked issue, completed checklist, and future automated checks. Dismiss stale approvals. Architecture/security/tenancy/IAM/remediation/audit/secrets/AI changes require the designated owner in [CODEOWNERS](../../.github/CODEOWNERS). Squash merge is proposed; tag releases `vMAJOR.MINOR.PATCH` and build a changelog from merged labels/PRs after implementation starts.

## Planning

Use milestones for stages/releases and labels documented in [task breakdown](../planning/task-breakdown.md). Proposed GitHub Project columns: Backlog, Ready, In Progress, In Review, Testing, Blocked, Done. Work-in-progress limits and issue templates improve handoffs.

## Future repository settings

Enable secret scanning immediately when the remote is created; evaluate push protection. Dependabot and code scanning are future setup after ecosystems exist. Do not create the organization or remote without explicit authorization/authentication.
