#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Virtualenv nao encontrada. Execute scripts/bootstrap.sh primeiro." >&2
  exit 1
fi

"$PYTHON_BIN" "$PROJECT_ROOT/manage.py" runserver 127.0.0.1:8000
