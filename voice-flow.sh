#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$DIR/.venv/bin/python"

if [[ ! -f "$VENV_PYTHON" ]]; then
    echo "Virtualenv not found at $VENV_PYTHON. Please run uv sync."
    exit 1
fi

export PYTHONPATH="$DIR:$PYTHONPATH"
exec "$VENV_PYTHON" -m voice_flow.main "$@"
