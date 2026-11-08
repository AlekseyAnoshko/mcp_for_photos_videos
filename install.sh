#!/usr/bin/env sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if ! command -v python3 >/dev/null 2>&1; then
    echo 'Нужен Python 3.11+. См. README.md → Требования.' >&2
    exit 1
fi
exec python3 "$PROJECT_DIR/scripts/deploy.py" "$@"
