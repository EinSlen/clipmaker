# 🎬 Twitch Clip Compiler - Auto TikTok Uploader

Compilation automatique de clips Twitch en vidéos TikTok/Shorts avec upload automatisé.

## ✨ Fonctionnalités

- 📥 **Extraction automatique** des clips Twitch des dernières 24h
- 🎞️ **Conversion au format TikTok** (9:16, 1080x1920) avec zoom intelligent
- ✂️ **Compilation** de clips jusqu'à 60 secondes
- 🎵 **Ajout de sons** (intro + transitions)
- 📝 **Texte personnalisé** sur la vidéo
- ⬆️ **Upload automatique** sur TikTok
- ⏰ **Planification** possible (cron/systemd)

## 🛠️ Prérequis

- Python 3.8+
- Node.js 16+
- ffmpeg
- Git

## 📦 Installation

### Option 1 : Installation automatique (Raspberry Pi / Linux)

```bash
# Télécharger le script d'installation
wget https://raw.githubusercontent.com/EinSlen/clipMaker/main/setup_raspberry.sh

# Rendre exécutable
chmod +x setup_raspberry.sh

# Lancer l'installation
./setup_raspberry.sh
```

### Option 2 : Installation manuelle

```bash
# 1. Cloner le repo avec submodules
git clone --recurse-submodules https://github.com/EinSlen/clipMaker.git
cd twitch-compiler

# 2. Créer l'environnement virtuel
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows

# 3. Installer les dépendances Python du projet
pip install -r requirements.txt

# 4. Installer les dépendances de TiktokAutoUploader
cd vendor/TiktokAutoUploader
pip install -r requirements.txt

# 5. Installer les dépendances npm
cd tiktok_uploader/tiktok-signature
npm install
cd ../../..

# 6. Installer ffmpeg (si pas déjà installé)
# Ubuntu/Debian/Raspberry Pi:
sudo apt install ffmpeg imagemagick

# macOS:
brew install ffmpeg imagemagick

# Windows:
# Télécharger depuis https://ffmpeg.org/download.html
```

## ⚙️ Configuration

### 1. Modifier le script `main.py`

```python
# Configuration TikTok
TIKTOK_USERNAME = 'ton_username_tiktok'  # ← CHANGE ICI
AUTO_UPLOAD = True

# URL Twitch du streamer
twitch_url = "https://m.twitch.tv/NOM_STREAMER/clips/?featured=false&range=24hr"

# Paramètres de zoom (1.0 = pas de zoom, 1.15 = +15%)
ZOOM_FACTOR = 1.1
CROP_POSITION = 'center'  # 'center', 'top', ou 'bottom'
```

### 2. Fichiers audio (optionnel)

Place tes fichiers audio dans le dossier principal :
- `intro.mp3` - Son d'intro
- `transition.mp3` - Son de transition entre clips

### 3. Connexion TikTok (première fois uniquement)

```bash
cd vendor/TiktokAutoUploader
source ../../venv/bin/activate  # Activer le venv
python cli.py login -n ton_username_tiktok
```

Une fenêtre Chrome s'ouvrira :
1. Connecte-toi manuellement à TikTok
2. Les cookies seront sauvegardés automatiquement
3. Tu n'auras plus besoin de te reconnecter

## 🚀 Utilisation

### Exécution manuelle

```bash
cd clipMaker
source venv/bin/activate
python main.py
```

### Exécution automatique (Raspberry Pi / Linux)

```bash
# 1. Rendre le wrapper script exécutable
chmod +x run_compiler.sh

# 2. Éditer le crontab
crontab -e

# 3. Ajouter une ligne (exemple : tous les jours à 8h)
0 8 * * * /home/pi/twitch-compiler/run_compiler.sh
```

**Exemples de planification :**
```bash
0 8 * * *   # Tous les jours à 8h00
0 14 * * *  # Tous les jours à 14h00
0 */6 * * * # Toutes les 6 heures
@daily      # Une fois par jour
```

## 📊 Structure du projet

```
clipMaker/
├── .git/                          # Git repo principal
├── .gitignore                     # Fichiers à ignorer
├── .gitmodules                    # Configuration submodule
├── README.md                      # Ce fichier
├── requirements.txt               # Dépendances Python
├── main.py                        # Script principal
├── run_compiler.sh               # Wrapper pour exécution auto
├── setup_raspberry.sh            # Script d'installation
├── vendor/
│   └── TiktokAutoUploader/       # Submodule Git
│       ├── cli.py
│       ├── requirements.txt
│       └── tiktok_uploader/
│           └── tiktok-signature/
│               └── package.json
├── clips/                        # Clips téléchargés (temp)
├── logs/                         # Logs d'exécution
├── intro.mp3                     # Son d'intro (optionnel)
└── transition.mp3                # Son de transition (optionnel)
```

## 🎨 Personnalisation

### Changer le texte sur la vidéo

```python
text_overlay = f"{streamer_name} core >>>"  # Modifie ici
```

### Modifier le zoom

```python
ZOOM_FACTOR = 1.15  # 1.0 = aucun zoom, 1.2 = zoom 20%
```

### Changer la durée de la vidéo

```python
target_duration=60  # En secondes
```

### Modifier les transitions

```python
black_screen_duration=0.3  # Durée de l'écran noir entre clips
```

## 📝 Logs

Les logs d'exécution sont sauvegardés dans `logs/` :

```bash
# Voir le dernier log
tail -f logs/execution_*.log | tail -1

# Voir tous les logs
ls -lh logs/

# Nettoyer les vieux logs (plus de 30 jours)
find logs/ -name "*.log" -mtime +30 -delete
```

## 🐛 Dépannage

### Erreur "No module named 'xxx'"

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### Erreur lors de l'upload TikTok

```bash
# Reconnecte-toi à TikTok
cd vendor/TiktokAutoUploader
python cli.py login -n ton_username
```

### Erreur npm/node

```bash
# Vérifier les versions
node -v
npm -v

# Réinstaller les dépendances
cd vendor/TiktokAutoUploader/tiktok_uploader/tiktok-signature
rm -rf node_modules package-lock.json
npm install
```

### Le cron ne s'exécute pas

```bash
# Vérifier le service cron
sudo systemctl status cron

# Vérifier les logs système
grep CRON /var/log/syslog

# Tester le wrapper script manuellement
./run_compiler.sh
```

## 🔒 Sécurité

⚠️ **Ne JAMAIS commit :**
- Les cookies TikTok (`vendor/TiktokAutoUploader/CookiesDir/`)
- Les fichiers de configuration avec mots de passe
- Les vidéos compilées

Le `.gitignore` est configuré pour ignorer automatiquement ces fichiers.

## 📚 Documentation complète

- [Guide d'installation Raspberry Pi](CRON_GUIDE.md)
- [Alternatives (VPS, Windows, Docker)](ALTERNATIVES_GUIDE.md)
- [Configuration Git et Submodules](GIT_SUBMODULE_GUIDE.md)

## 🤝 Contribution

Les contributions sont les bienvenues ! N'hésite pas à :
- Ouvrir une issue pour signaler un bug
- Proposer des améliorations
- Soumettre une pull request

## 📄 Licence

Ce projet est sous licence MIT.

## 🙏 Remerciements

- [TiktokAutoUploader](https://github.com/makiisthenes/TiktokAutoUploader) - Upload automatique sur TikTok
- [MoviePy](https://github.com/Zulko/moviepy) - Traitement vidéo
- [Streamlink](https://github.com/streamlink/streamlink) - Téléchargement de clips Twitch

## 💬 Support

Besoin d'aide ? Ouvre une issue sur GitHub !

---

**Made with ❤️ for content creators**