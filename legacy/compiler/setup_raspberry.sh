#!/bin/bash
# Script d'installation pour Raspberry Pi
# Usage: chmod +x setup_raspberry.sh && ./setup_raspberry.sh

echo "=========================================="
echo "🍓 Installation sur Raspberry Pi"
echo "=========================================="
echo ""

# Mise à jour du système
echo "[1/8] Mise à jour du système..."
sudo apt update
sudo apt upgrade -y
echo "  > Système mis à jour"
echo ""

# Installation de Node.js et npm
echo "[2/8] Installation de Node.js et npm..."
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs
echo "  > Node.js version: $(node -v)"
echo "  > npm version: $(npm -v)"
echo ""

# Installation de Python et pip
echo "[3/8] Installation de Python et pip..."
sudo apt install -y python3 python3-pip python3-venv
echo "  > Python version: $(python3 --version)"
echo ""

# Installation des dépendances système
echo "[4/8] Installation des dépendances système..."
sudo apt install -y \
    ffmpeg \
    imagemagick \
    libmagickwand-dev \
    git \
    chromium-browser \
    chromium-chromedriver
echo "  > Dépendances système installées"
echo ""

# Création du dossier projet
echo "[5/8] Création du dossier projet..."
mkdir -p ~/twitch-compiler
cd ~/twitch-compiler
echo "  > Dossier créé : ~/twitch-compiler"
echo ""

# Création de l'environnement virtuel
echo "[6/8] Création de l'environnement virtuel Python..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
echo "  > Environnement virtuel créé et activé"
echo ""

# Installation des dépendances Python du projet principal
echo "[7/8] Installation des dépendances Python du projet..."
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
    echo "  > Dépendances installées depuis requirements.txt"
else
    echo "  ⚠ requirements.txt non trouvé, installation manuelle des dépendances..."
    pip install \
        moviepy \
        streamlink \
        beautifulsoup4 \
        requests \
        tqdm \
        Pillow
    echo "  > Dépendances de base installées"
fi
echo ""

# Initialisation du submodule TiktokAutoUploader
echo "[8/8] Configuration du submodule TiktokAutoUploader..."

# Si le repo est déjà un git repo avec submodule
if [ -d .git ]; then
    echo "  > Initialisation du submodule git..."
    git submodule init
    git submodule update
else
    echo "  > Clonage manuel de TiktokAutoUploader..."
    mkdir -p vendor
    cd vendor
    if [ ! -d TiktokAutoUploader ]; then
        git clone https://github.com/makiisthenes/TiktokAutoUploader.git
    fi
    cd ..
fi

echo ""
echo "[8.1] Installation des dépendances TiktokAutoUploader..."
cd vendor/TiktokAutoUploader
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
    echo "  > Dépendances Python TiktokAutoUploader installées"
else
    echo "  > Aucun requirements.txt trouvé dans TiktokAutoUploader"
fi

echo ""
echo "[8.2] Installation des dépendances npm pour tiktok-signature..."
cd tiktok_uploader/tiktok-signature
if [ -f package.json ]; then
    npm i
    echo "  > Dépendances npm installées"
else
    echo "  > Aucun package.json trouvé"
fi
cd ~/twitch-compiler

echo ""
echo "=========================================="
echo "✅ Installation terminée avec succès !"
echo "=========================================="
echo ""
echo "📝 Prochaines étapes :"
echo ""
echo "1. Copie ton script main.py :"
echo "   cp /chemin/vers/main.py ~/twitch-compiler/"
echo ""
echo "2. Copie ton requirements.txt (si tu l'as) :"
echo "   cp /chemin/vers/requirements.txt ~/twitch-compiler/"
echo ""
echo "3. Copie tes fichiers audio (optionnel) :"
echo "   cp /chemin/vers/intro.mp3 ~/twitch-compiler/"
echo "   cp /chemin/vers/transition.mp3 ~/twitch-compiler/"
echo ""
echo "4. Active l'environnement virtuel :"
echo "   source ~/twitch-compiler/venv/bin/activate"
echo ""
echo "5. Connexion TikTok (une seule fois) :"
echo "   cd ~/twitch-compiler/vendor/TiktokAutoUploader"
echo "   python cli.py login -n TON_USERNAME_TIKTOK"
echo ""
echo "6. Test du script :"
echo "   cd ~/twitch-compiler"
echo "   python main.py"
echo ""
echo "7. Configure le cron pour l'automatisation :"
echo "   crontab -e"
echo "   Ajoute : 0 8 * * * /home/pi/twitch-compiler/run_compiler.sh"
echo ""