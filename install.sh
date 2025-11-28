#!/bin/bash

echo "========================================"
echo "Installation des dépendances"
echo "========================================"
echo ""

echo "[1/5] Installation des packages Python principaux..."
pip install -r requirements.txt

echo ""
echo "[3/5] Installation des dépendances TiktokAutoUploader..."
cd vendor/TiktokAutoUploader
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
    echo "  > Dépendances Python TiktokAutoUploader installées"
else
    echo "  > Aucun requirements.txt trouvé dans TiktokAutoUploader"
fi

echo ""
echo "[4/5] Installation des dépendances npm pour tiktok-signature..."
cd tiktok_uploader/tiktok-signature
if [ -f package.json ]; then
    npm i
    echo "  > Dépendances npm installées"
else
    echo "  > Aucun package.json trouvé"
fi

echo ""
echo "[5/5] Retour au dossier principal..."
cd ../../..

echo ""
echo "========================================"
echo "Installation terminée !"
echo "========================================"
echo ""
echo "IMPORTANT: undetected-chromedriver v3.5.4 est installé"
echo "           (version stable compatible avec Chrome)"
echo ""
echo "Prochaines étapes :"
echo "  1. python setup_tiktok.py (configure ton compte TikTok)"
echo "  2. python twitch_clip_compiler.py (lance le script)"
echo ""