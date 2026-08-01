# Publication automatique sur YouTube Shorts

ClipMaker utilise le fork épinglé [`EinSlen/youtube-shorts-agent`](https://github.com/EinSlen/youtube-shorts-agent) et l'API officielle YouTube Data v3.

Par défaut, tout fonctionne en simulation : le fichier, la durée, le format et les métadonnées sont validés, mais aucune requête d'upload n'est envoyée à YouTube. Les vidéos carrées ou verticales de 1 à 180 secondes sont acceptées.

## 1. Préparer Google Cloud

1. Créer ou sélectionner un projet dans [Google Cloud Console](https://console.cloud.google.com/).
2. Activer **YouTube Data API v3**.
3. Configurer l'écran de consentement OAuth.
4. Créer un client OAuth de type **Application de bureau**.
5. Utiliser `http://localhost:8788/callback` comme URI de redirection locale lorsqu'elle est demandée.

Un projet API non vérifié peut être limité aux uploads privés jusqu'à son audit de conformité YouTube. Commencer systématiquement en `private`.

## 2. Créer la configuration locale

Depuis la racine de ClipMaker, sous PowerShell :

```powershell
New-Item -ItemType Directory -Force .youtube-agent
Copy-Item youtube-agent.env.example .youtube-agent\.env
```

Renseigner seulement `YOUTUBE_CLIENT_ID` et `YOUTUBE_CLIENT_SECRET` dans `.youtube-agent/.env`. Ce dossier est ignoré par Git.

## 3. Autoriser la chaîne YouTube

```powershell
Set-Location web
npm install
npm run youtube:doctor
npm run youtube:auth
```

La commande affiche une URL Google. L'ouvrir, choisir la chaîne et accepter l'autorisation. Le callback local enregistre les tokens dans `.youtube-agent/.env` sans les afficher dans l'interface ClipMaker.

Relancer ensuite :

```powershell
npm run youtube:doctor
```

## 4. Premier upload réel et privé

Dans `.youtube-agent/.env` :

```dotenv
YOUTUBE_DRY_RUN=false
YOUTUBE_PRIVACY_STATUS=private
```

Créer un jeton d'administration aléatoire et placer la même valeur dans `web/.env.local` :

```powershell
$bytes = [byte[]]::new(32)
[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$token = [Convert]::ToHexString($bytes).ToLowerInvariant()
Add-Content .env.local "CLIPMAKER_UPLOAD_TOKEN=$token"
```

Redémarrer ClipMaker, générer la vidéo, ouvrir le panneau **YouTube Shorts**, saisir ce jeton puis envoyer la vidéo en **Privée**. Vérifier le résultat dans YouTube Studio avant toute publication.

`YOUTUBE_ALLOW_PUBLIC_UPLOAD=false` doit rester dans `web/.env.local`. L'interface ne propose volontairement que `private` et `unlisted`.

## Docker

Le conteneur existant suffit. Le dépôt est monté dans `/repo`, donc `/repo/.youtube-agent` conserve la configuration OAuth. Effectuer l'autorisation OAuth sur l'hôte avant de démarrer le conteneur :

```powershell
docker compose up --build
```

## Commandes de contrôle

```powershell
Set-Location web
npm run lint
npm run build
npm audit --omit=dev
npm run youtube:doctor
```
