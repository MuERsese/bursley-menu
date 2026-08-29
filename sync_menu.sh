#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "ERROR: Python virtual environment not found at $ROOT/.venv"
  echo "Run ./install.sh first."
  exit 1
fi

if [[ ! -d "$ROOT/.git" ]]; then
  echo "ERROR: $ROOT is not a git repository."
  exit 1
fi

"$PYTHON" "$ROOT/fetch_bursley.py"

cd "$ROOT"
git add menu.json

if git diff --cached --quiet; then
  echo "No menu changes to commit."
  exit 0
fi

git commit -m "Update Bursley menu $(date '+%Y-%m-%d %H:%M:%S %Z')" >/dev/null
git push origin HEAD

echo "Bursley menu synced successfully."
