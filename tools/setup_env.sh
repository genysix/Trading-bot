#!/usr/bin/env bash
# ================================================
# setup_env.sh — Crée le venv et installe les deps
# Usage : ./setup_env.sh
# -----------------------------------------------
set -euo pipefail

PROJECT_ROOT="$(pwd)"
VENV_DIR="${VENV_DIR:-.venv}"
PYBIN="${PYBIN:-python3}"

echo "🔍 Vérification Python..."
"$PYBIN" - <<'PY'
import sys
maj, minor = sys.version_info[:2]
req = (3,10)
ok = (maj, minor) >= req
print(f"Python détecté: {sys.version.split()[0]}  (requis >= {req[0]}.{req[1]})")
sys.exit(0 if ok else 1)
PY

if [ ! -d "$VENV_DIR" ]; then
  echo "🧪 Création du venv: $VENV_DIR"
  "$PYBIN" -m venv "$VENV_DIR"
else
  echo "ℹ️  Venv déjà présent: $VENV_DIR"
fi

echo "⚙️  Activation du venv"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "⬆️  Upgrade pip/setuptools/wheel"
python -m pip install --upgrade pip setuptools wheel

REQ_MAIN="requirements.txt"

if [ -f "$REQ_MAIN" ]; then
  echo "📦 Installation deps (requirements.txt)"
  pip install -r "$REQ_MAIN"
else
  echo "❌ Fichier $REQ_MAIN introuvable."
  exit 1
fi

# .env à partir de .env.example si absent
if [ -f ".env.example" ] && [ ! -f ".env" ]; then
  echo "🗝️  Création .env (copie de .env.example)"
  cp .env.example .env
else
  echo "ℹ️  .env déjà présent ou .env.example manquant — OK"
fi

echo "🧾 Congélation de l'état des packages -> requirements.lock.txt"
pip freeze > requirements.lock.txt

echo "✅ Environnement prêt."
echo "👉 Pour activer: source $VENV_DIR/bin/activate"
