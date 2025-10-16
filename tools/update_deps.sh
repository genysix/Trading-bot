#!/usr/bin/env bash
# ==================================================
# update_deps.sh — Upgrade de TOUTES les dépendances
# Usage : ./update_deps.sh
# --------------------------------------------------
set -euo pipefail

VENV_DIR="${VENV_DIR:-.venv}"

# Active le venv si présent, sinon essaye d'utiliser pip user
if [ -d "$VENV_DIR" ]; then
  echo "⚙️  Activation du venv: $VENV_DIR"
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
fi

echo "⬆️  Upgrade pip/setuptools/wheel"
python -m pip install --upgrade pip setuptools wheel

bump_file () {
  local req="$1"
  if [ -f "$req" ]; then
    echo "⬆️  Upgrade deps depuis $req"
    # Upgrade en respectant les noms de paquets listés
    pip install --upgrade -r "$req"
  else
    echo "ℹ️  $req non trouvé — skip"
  fi
}

bump_file "requirements.txt"


echo "📋 Packages obsolètes éventuels (vérif) :"
pip list --outdated || true

echo "✅ Dépendances mises à jour."
