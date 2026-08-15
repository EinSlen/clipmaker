# Publication quotidienne

ClipMaker possède un orchestrateur idempotent pour générer puis publier une vidéo par jour et par chaîne. Il peut fonctionner comme service Docker permanent ou être appelé toutes les quinze minutes par un timer systemd.

## Garanties

- Une clé de job stable `date:channel` empêche les doublons.
- La seed et la rotation des jeux sont déterministes pour chaque journée.
- L'état est écrit atomiquement dans `web/data/publisher/`.
- Un verrou inter-processus empêche deux rendus ou publications simultanés.
- Une cible déjà publiée n'est jamais renvoyée lors d'un retry.
- Les échecs YouTube et TikTok sont isolés : une publication partielle est reprise sans dupliquer la plateforme réussie.
- Le journal append-only `publisher-events.jsonl` conserve les tentatives et erreurs.
- La configuration d'exemple est en dry-run et toutes les cibles sont désactivées.

## 1. Préparer la configuration

```bash
cd /opt/clipmaker
cp web/config/publisher.example.json web/config/publisher.json
nano web/config/publisher.json
```

Un objet dans `channels` représente une paire de comptes et une rotation éditoriale. Duplique cet objet pour publier des jeux différents sur plusieurs comptes. Les heures utilisent `timeZone`, `Europe/Paris` par défaut.

Paramètres importants :

- `generateTime` : heure à partir de laquelle le rendu nocturne peut commencer.
- `publishTime` : heure à partir de laquelle la vidéo prête peut être envoyée.
- `rotation` : ordre quotidien des jeux et réglages.
- `youtube.enabled` / `tiktok.enabled` : cibles actives.
- `dryRun` : doit rester `true` pendant les tests.

Pour YouTube public, les trois protections suivantes doivent être présentes :

1. `youtube.privacy` vaut `public` ;
2. `youtube.confirmPublic` vaut `true` ;
3. `YOUTUBE_ALLOW_PUBLIC_UPLOAD=true` dans `.env.local`.

Pour TikTok public, `tiktok.visibility` doit valoir `public` et `tiktok.confirmPublic` doit valoir
`true`. Le mode privé est la valeur par défaut pour les premiers essais.

## 2. Préparer les secrets et sessions

Dans `web/.env.local` :

```dotenv
CLIPMAKER_UPLOAD_TOKEN=une-longue-valeur-aleatoire
YOUTUBE_BROWSER_DRY_RUN=true
YOUTUBE_ALLOW_PUBLIC_UPLOAD=false
PUBLISHER_DRY_RUN=true
```

Ne place jamais le token ou les cookies dans `publisher.json`. Les sessions YouTube restent dans `.youtube-browser/` et les sessions TikTok dans `vendor/TiktokAutoUploader/CookiesDir/`, tous deux exclus de Git.

Connexion YouTube sur le serveur :

```bash
docker compose --profile youtube-auth up youtube-auth
```

Puis suivre [YOUTUBE-UPLOAD.md](YOUTUBE-UPLOAD.md). Pour TikTok, connecter chaque compte avec le CLI du fork avant d'activer sa cible.

Connexion TikTok via noVNC (une exécution par compte) :

```bash
TIKTOK_USERNAME=moncompte docker compose --profile tiktok-auth run --rm --service-ports tiktok-auth
ssh -L 6081:127.0.0.1:6081 utilisateur@serveur
```

Ouvrir `http://127.0.0.1:6081/vnc.html?autoconnect=true&resize=scale`. Le jeton de publication saisi
dans l'interface est conservé uniquement en mémoire de session et doit correspondre à
`CLIPMAKER_UPLOAD_TOKEN`.

## 3. Vérifier sans publier

```bash
docker compose up -d --build clipmaker
docker compose exec -T clipmaker node /repo/web/scripts/publisher.mjs doctor \
  --config /repo/web/config/publisher.json

docker compose exec -T clipmaker node /repo/web/scripts/publisher.mjs due \
  --config /repo/web/config/publisher.json --dry-run
```

Le dry-run ne rend aucune vidéo et n'envoie rien. Il affiche la date, la seed, le jeu choisi et les cibles prévues.

Commandes utiles :

```bash
# État et historique des jobs
docker compose exec -T clipmaker node /repo/web/scripts/publisher.mjs status \
  --config /repo/web/config/publisher.json

# Génération immédiate d'une chaîne
docker compose exec -T clipmaker node /repo/web/scripts/publisher.mjs generate \
  --config /repo/web/config/publisher.json --channel main

# Reprendre uniquement les plateformes non publiées
docker compose exec -T clipmaker node /repo/web/scripts/publisher.mjs publish \
  --config /repo/web/config/publisher.json --channel main
```

## 4. Activer le service Docker

Après un upload privé/non répertorié réussi :

1. activer les cibles voulues dans `publisher.json` ;
2. régler `PUBLISHER_DRY_RUN=false` ;
3. régler `YOUTUBE_BROWSER_DRY_RUN=false` ;
4. démarrer le profil.

```bash
docker compose --profile publisher up -d --build
docker compose logs -f publisher
```

Le daemon relit la configuration à chaque cycle. Un redémarrage n'est donc pas nécessaire pour changer la rotation ou les horaires.

## 5. Alternative systemd

Si tu préfères ne pas garder un second conteneur actif, installe le timer fourni :

```bash
sudo cp infra/systemd/clipmaker-publisher.service /etc/systemd/system/
sudo cp infra/systemd/clipmaker-publisher.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now clipmaker-publisher.timer
systemctl list-timers clipmaker-publisher.timer
```

Les unités supposent le dépôt dans `/opt/clipmaker`. Modifier `WorkingDirectory` et les chemins si nécessaire. Ne pas activer simultanément le daemon Docker et le timer systemd.

## Exploitation

- Le serveur web écoute uniquement sur `127.0.0.1` par défaut. Utiliser un tunnel SSH ou un reverse proxy authentifié pour l'interface.
- Sauvegarder `web/data/publisher/`, `.youtube-browser/` et les cookies TikTok hors du dépôt.
- Surveiller `docker compose logs publisher` et la taille de `web/renders/`.
- Laisser suffisamment d'avance entre génération et publication : le rendu Soft Body 3D peut durer plusieurs heures sur CPU.
- Sur une machine NVIDIA, utiliser le fichier Compose GPU décrit dans [HARDWARE.md](HARDWARE.md).
- Si une session expire, désactiver temporairement la cible concernée, reconnecter le compte, exécuter `doctor`, puis relancer `publish`.
