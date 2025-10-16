#!/usr/bin/env bash
# ==================================================
# launch_python.sh — Lance python dans le venv
# Usage : ./launch_python.sh
# --------------------------------------------------

set -euo pipefail

VENV_DIR="${VENV_DIR:-.venv}"

if [ -d "$VENV_DIR" ]; then
  echo "⚙️  Activation du venv: $VENV_DIR"
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
else
  echo "❌ Venv introuvable ($VENV_DIR). Lance d'abord ./setup_env.sh"
  exit 1
fi