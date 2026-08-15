#!/bin/bash
# Wrapper script pour exécution automatique
# Ce script active l'environnement virtuel et lance le script Python

# Chemin vers le projet
PROJECT_DIR="$HOME/twitch-compiler"
VENV_DIR="$PROJECT_DIR/venv"
SCRIPT="$PROJECT_DIR/main.py"
LOG_FILE="$PROJECT_DIR/logs/execution_$(date +%Y%m%d_%H%M%S).log"

# Créer le dossier de logs s'il n'existe pas
mkdir -p "$PROJECT_DIR/logs"

echo "========================================" | tee -a "$LOG_FILE"
echo "🚀 Démarrage du script - $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# Se déplacer dans le dossier du projet
cd "$PROJECT_DIR" || exit 1

# Activer l'environnement virtuel
source "$VENV_DIR/bin/activate" || {
    echo "❌ Erreur : Impossible d'activer l'environnement virtuel" | tee -a "$LOG_FILE"
    exit 1
}

# Lancer le script Python
python "$SCRIPT" 2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Script terminé avec succès - $(date)" | tee -a "$LOG_FILE"
else
    echo "❌ Script terminé avec erreur (code: $EXIT_CODE) - $(date)" | tee -a "$LOG_FILE"
fi

echo "========================================" | tee -a "$LOG_FILE"

# Nettoyer les vieux logs (garder seulement les 30 derniers jours)
find "$PROJECT_DIR/logs" -name "execution_*.log" -mtime +30 -delete

exit $EXIT_CODE