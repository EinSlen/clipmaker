# ClipMaker

Studio auto-hébergé pour générer des vidéos verticales originales, les contrôler, puis publier
quotidiennement sur TikTok et YouTube Shorts. L'interface web est en français ; les accroches et les
métadonnées envoyées aux plateformes restent en anglais.

Le projet contient cinq moteurs : Ball Escape, Organic Escape, Laser Dodge, Boss Battle et Soft
Body 3D. Les quatre premiers rendent en 1080×1920 à 60 i/s. Soft Body utilise Blender et propose
plusieurs familles d'obstacles avec cinq niveaux de souplesse.

## Démarrage local

Prérequis : Docker Engine avec le plugin Compose.

```bash
git clone --recurse-submodules https://github.com/EinSlen/clipMaker.git
cd clipMaker
cp web/.env.example web/.env.local
docker compose up -d --build clipmaker
```

Ouvrir ensuite <http://127.0.0.1:3000>. Le port n'écoute que sur la machine locale par défaut.

Pour le développement sans Docker :

```bash
cd web
npm ci
npm run dev
```

## Publication quotidienne

L'orchestrateur intégré sépare le rendu de la publication, conserve un état atomique et évite les
doublons après un redémarrage. Sa configuration d'exemple ne publie rien : le dry-run est activé et
les deux plateformes sont désactivées.

```bash
cp web/config/publisher.example.json web/config/publisher.json
docker compose exec -T clipmaker node /repo/web/scripts/publisher.mjs due \
  --config /repo/web/config/publisher.json --dry-run
```

Après avoir connecté les comptes et validé un upload privé, le daemon peut être démarré avec :

```bash
docker compose --profile publisher up -d --build
```

La procédure complète, les protections pour la publication publique, le multi-compte et
l'alternative systemd sont décrits dans [docs/AUTOMATION.md](docs/AUTOMATION.md).

## Architecture

```text
clipMaker/
├── web/
│   ├── src/app/             pages Next.js et routes API
│   ├── src/components/      interface du studio
│   ├── src/lib/             rendu, musique et intégrations
│   ├── src/automation/      planification, état et idempotence
│   ├── scripts/             moteurs Python et CLI de publication
│   └── config/              affectations fixes compte → jeu
├── infra/systemd/           timer Linux optionnel
├── docs/                    exploitation et moteurs
├── vendor/                  fork TikTok Auto Uploader
├── legacy/                  ancien compilateur et anciens déploiements
└── docker-compose.yml       application, publication et login YouTube
```

## Vérifications

```bash
cd web
npm test
npm run build
npm run test:render-smoke
docker compose config --quiet
```

Le smoke de rendu encode de vrais MP4. Le rendu Soft Body final est volontairement beaucoup plus
long et se valide séparément à cause du coût Blender.

## Documentation

- [Générateur et variantes](docs/GAME-GENERATOR.md)
- [Automatisation quotidienne](docs/AUTOMATION.md)
- [Connexion YouTube par session](docs/YOUTUBE-UPLOAD.md)
- [Machine recommandée et installation Linux](docs/HARDWARE.md)
- [Ancien pipeline archivé](legacy/compiler/README.md)

Les sessions de navigateur, cookies, rendus, secrets et états de publication sont exclus de Git.
Ne jamais exposer directement le port 3000 sur Internet sans authentification.
