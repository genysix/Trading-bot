#!/bin/zsh
# =====================================================
# Script de mise à jour GitHub pour ton projet Trading-bot
# Version : sécurisée (.env protégé)
# =====================================================

# Détermination de la branche cible
if [[ "$1" == "--dev" ]]; then
  target_branch="dev"
else
  target_branch="main"
fi

echo "📦 Branche cible : $target_branch"

# Vérifie que le dossier est bien un dépôt Git
if [ ! -d ".git" ]; then
  echo "❌ Ce dossier n'est pas un dépôt Git. Lance ce script depuis la racine du projet."
  exit 1
fi

# Vérifie qu'un remote 'origin' existe
if ! git remote get-url origin >/dev/null 2>&1; then
  echo "❌ Aucun dépôt distant configuré."
  echo "👉 Ajoute-le avec : git remote add origin https://github.com/genysix/Trading-bot.git"
  exit 1
fi

# Vérifie que la branche existe localement, sinon la crée
if ! git show-ref --verify --quiet refs/heads/$target_branch; then
  echo "🆕 Création de la branche $target_branch..."
  git checkout -b $target_branch
else
  git checkout $target_branch
fi

# Synchronisation avec le distant
echo "🔄 Synchronisation avec GitHub..."
git pull origin $target_branch --rebase --autostash 2>/dev/null || echo "⚠️ Aucun changement distant ou branche non encore créée."

# Affiche l’état du dépôt
echo "🔍 Fichiers modifiés :"
git status -s

# Demande du message de commit
echo ""
read "?📝 Message du commit : " commit_msg

if [ -z "$commit_msg" ]; then
  echo "❌ Aucun message saisi. Abandon."
  exit 1
fi

# Étapes Git principales (sans toucher aux fichiers ignorés)
echo "📁 Ajout des fichiers..."
git add --all -- ':!*.env' ':!*.key' ':!*.secret'

echo "💬 Création du commit..."
git commit -m "$commit_msg" || echo "⚠️ Aucun changement à valider."

echo "⬆️ Envoi vers GitHub sur la branche $target_branch..."
git push -u origin $target_branch || echo "❌ Erreur lors du push."

echo "✅ Dépôt mis à jour avec succès sur '$target_branch' !"
# Fin du script
# =====================================================