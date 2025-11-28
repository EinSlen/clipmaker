@echo off
echo ========================================
echo Installation des dependances
echo ========================================
echo.

echo [1/5] Installation des packages Python principaux...
pip install -r requirements.txt

echo.
echo [3/5] Installation des dependances TiktokAutoUploader...
cd vendor\TiktokAutoUploader
if exist requirements.txt (
    pip install -r requirements.txt
    echo   ^> Dependances Python TiktokAutoUploader installees
) else (
    echo   ^> Aucun requirements.txt trouve dans TiktokAutoUploader
)

echo.
echo [4/5] Installation des dependances npm pour tiktok-signature...
cd tiktok_uploader\tiktok-signature
if exist package.json (
    npm i
    echo   ^> Dependances npm installees
) else (
    echo   ^> Aucun package.json trouve
)

echo.
echo [5/5] Retour au dossier principal...
cd ..\..\..

echo.
echo ========================================
echo Installation terminee !
echo ========================================
echo.
echo IMPORTANT: undetected-chromedriver v3.5.4 est installe
echo           (version stable compatible avec Chrome)
echo.
echo Prochaines etapes :
echo   1. python setup_tiktok.py (configure ton compte TikTok)
echo   2. python twitch_clip_compiler.py (lance le script)
echo.
pause