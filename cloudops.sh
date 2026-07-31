#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' \
    'PRECHECK_PYTHON_UNAVAILABLE: Python 3.12+ is required. Install Python and rerun.' >&2
  exit 2
fi

exec python3 "${ROOT}/scripts/selfhost/cloudops.py" "$@"
