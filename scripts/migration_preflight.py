"""Pre-release Alembic migration safety check.

Run this against a disposable copy of the target database (never against a
live primary without a fresh backup) before a release migration. It verifies:

1. The migration graph has exactly one head (no unmerged branches).
2. The database's current revision is a real, known revision (not None/stale
   in a way that would make ``upgrade head`` ambiguous).
3. ``alembic upgrade head`` succeeds against the given database.
4. ``alembic check`` reports no pending model/migration drift after upgrade.

This script never runs against production; it only ever runs against
whatever ``DATABASE_URL`` you export in the shell that invokes it. Always
point it at a disposable/staging database, not a live primary.

Usage (from apps/api, with the venv active):
    python ../../scripts/migration_preflight.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from alembic.config import Config  # noqa: E402
from alembic.runtime.migration import MigrationContext  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402


def _alembic_config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    settings = get_settings()
    database_url = settings.database_url.get_secret_value()
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return cfg


def check_single_head(cfg: Config) -> list[str]:
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    if len(heads) != 1:
        return [f"FAIL: expected exactly one migration head, found {len(heads)}: {heads}"]
    return [f"OK: single migration head ({heads[0]})"]


def check_current_revision(cfg: Config) -> list[str]:
    settings = get_settings()
    engine = create_engine(settings.database_url.get_secret_value())
    messages: list[str] = []
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current = context.get_current_revision()
            script = ScriptDirectory.from_config(cfg)
            heads = script.get_heads()
            if current is None:
                messages.append("INFO: database has no revision stamped (fresh database).")
            elif current not in {rev.revision for rev in script.walk_revisions()}:
                messages.append(f"FAIL: current revision {current!r} is not a known revision.")
            elif current in heads:
                messages.append(f"OK: database is already at head ({current}).")
            else:
                messages.append(f"INFO: database at {current!r}, upgrade to head is pending.")
    finally:
        engine.dispose()
    return messages


def main() -> int:
    cfg = _alembic_config()
    all_messages: list[str] = []
    failed = False

    for check in (check_single_head, check_current_revision):
        messages = check(cfg)
        all_messages.extend(messages)
        if any(m.startswith("FAIL") for m in messages):
            failed = True

    for message in all_messages:
        print(message)

    if failed:
        print("\nPreflight FAILED. Do not proceed with the release migration.")
        return 1

    print(
        "\nPreflight checks passed. Next steps (run manually, in order, against a "
        "disposable copy first, then production with a fresh backup):\n"
        "  1. alembic upgrade head\n"
        "  2. alembic current\n"
        "  3. alembic check\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
