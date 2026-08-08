# Publication de YouTube Shorts avec une session navigateur

ClipMaker utilise une révision épinglée du fork MIT
[`EinSlen/youtube-uploader`](https://github.com/EinSlen/youtube-uploader). L’envoi passe par
YouTube Studio dans Chromium, avec des cookies de session locaux : aucune clé YouTube Data API,
aucun projet Google Cloud et aucun mot de passe Google n’est enregistré dans le projet.

Cette méthode dépend de l’interface de YouTube Studio. Elle peut casser lorsque YouTube modifie la
page et peut être moins conforme aux conditions de la plateforme que l’API officielle. Commencer
avec une vidéo privée et éviter les cadences agressives.

## 1. Installer et vérifier

Depuis la racine de ClipMaker :

```powershell
Set-Location web
npm install
npm run youtube:doctor
```

Chrome, Edge ou Chromium est détecté automatiquement. Si nécessaire, définir son chemin dans
`web/.env.local` :

```dotenv
YOUTUBE_BROWSER_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
```

## 2. Enregistrer la session YouTube

```powershell
npm run youtube:auth
```

Une fenêtre de navigateur dédiée s’ouvre. Se connecter manuellement au bon compte et à la bonne
chaîne. ClipMaker attend l’arrivée dans YouTube Studio, exporte les cookies nécessaires, puis ferme
la fenêtre. Il ne lit ni l’adresse e-mail ni le mot de passe.

Les données sensibles restent dans `.youtube-browser/`, dossier ignoré par Git. Le fichier de
cookies donne accès à la session YouTube : ne jamais le partager, le publier ou le commiter. Pour
révoquer la session locale, se déconnecter du compte puis supprimer ce dossier.

### Plusieurs chaînes

Le profil historique s'appelle `default`. Pour isoler une autre chaîne, lui donner un identifiant
court puis refaire la connexion :

```powershell
node scripts/youtube-agent.mjs auth --account gaming
node scripts/youtube-agent.mjs doctor --account gaming
```

Les profils supplémentaires sont stockés dans `.youtube-browser/accounts/<identifiant>/` et
apparaissent automatiquement dans le sélecteur de l'interface.

## 3. Tester puis activer l’envoi réel

Le mode simulation est actif par défaut. Ajouter d’abord dans `web/.env.local` :

```dotenv
YOUTUBE_BROWSER_DRY_RUN=true
YOUTUBE_BROWSER_HEADLESS=true
YOUTUBE_ALLOW_PUBLIC_UPLOAD=false
CLIPMAKER_UPLOAD_TOKEN=une-longue-valeur-aleatoire
```

Générer une valeur sûre sous PowerShell :

```powershell
$bytes = New-Object byte[] 32
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$rng.Dispose()
([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
```

Redémarrer ClipMaker, générer un rendu et lancer une simulation depuis le panneau YouTube Shorts.
Quand elle passe, définir `YOUTUBE_BROWSER_DRY_RUN=false`, redémarrer, saisir le jeton dans le
panneau et envoyer la première vidéo en **Privée**. Vérifier le résultat dans YouTube Studio.

## Docker local

L’image contient Chromium et le dépôt est monté dans `/repo`, donc le fichier de cookies de
`.youtube-browser/` reste persistant. Faire la connexion initiale sur l’hôte, puis lancer :

```powershell
docker compose up --build
```

Dans le conteneur, Chromium est détecté à `/usr/bin/chromium`.

## Connexion initiale sur un VPS Linux

Les profils Chrome sont séparés par système (`auth-profile-win32` et `auth-profile-linux`) car leur
chiffrement n’est pas portable. Sur le VPS, construire l’image puis lancer le service noVNC :

```bash
docker compose build clipmaker youtube-auth
docker compose --profile youtube-auth run --rm --service-ports youtube-auth
```

Pour une chaîne supplémentaire, préfixer la commande avec son identifiant :

```bash
YOUTUBE_ACCOUNT=gaming docker compose --profile youtube-auth run --rm --service-ports youtube-auth
```

Depuis le PC local, créer un tunnel SSH vers le VPS :

```bash
ssh -L 6080:127.0.0.1:6080 utilisateur@adresse-du-vps
```

Ouvrir ensuite
`http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale`, se connecter à YouTube dans la
fenêtre Chromium, puis attendre la fermeture automatique du service. Le port noVNC est lié à
`127.0.0.1` sur le VPS et n’est donc pas exposé publiquement.

La session Linux est conservée dans le volume monté `/repo/.youtube-browser`. Démarrer enfin
l’application :

```bash
docker compose up -d clipmaker
docker compose exec clipmaker npm run youtube:doctor
```

## Contrôles

```powershell
Set-Location web
npm run youtube:doctor
npm run lint
npm run build
npm audit --omit=dev
```
