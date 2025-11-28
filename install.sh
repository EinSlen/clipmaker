#!/bin/bash

echo "========================================"
echo "Installation des dépendances"
echo "========================================"
echo ""

echo "[1/3] Installation des packages depuis requirements.txt..."
pip install -r requirements.txt

echo ""
echo "[2/3] Installation de pytube depuis GitHub..."
pip install git+https://github.com/pytube/pytube

echo ""
echo "[3/3] Installation de undetected-chromedriver depuis GitHub..."
# pip install git+https://github.com/ultrafunkamsterdam/undetected-chromedriver.git

echo ""
echo "========================================"
echo "Installation terminée !"
echo "========================================"
echo ""
echo "Vous pouvez maintenant lancer le script :"
echo "  python twitch_clip_compiler.py"
echo ""
