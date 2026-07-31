# Self-host control plane

`cloudops.ps1` and `cloudops.sh` are thin wrappers around `cloudops.py`. The Python modules use only
the standard library and own configuration, secret generation, preflight, Compose orchestration,
health verification, backup/restore, update, redaction, and stable diagnostics.

Generated runtime material lives under `.cloudops/runtime/`; backups live under
`.cloudops/backups/`. Both are Git-ignored. Tests are under
`tests/features/one_command_selfhost/`.
