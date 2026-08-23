# ClipMaker

[![Publication quotidienne](https://github.com/EinSlen/clipmaker/actions/workflows/daily-publisher.yml/badge.svg?branch=main)](https://github.com/EinSlen/clipmaker/actions/workflows/daily-publisher.yml)
[![Rendu 3D](https://github.com/EinSlen/clipmaker/actions/workflows/soft-body-artifact.yml/badge.svg?branch=main)](https://github.com/EinSlen/clipmaker/actions/workflows/soft-body-artifact.yml)
[![Interface Cloud](https://github.com/EinSlen/clipmaker/actions/workflows/cloud-dashboard.yml/badge.svg?branch=main)](https://github.com/EinSlen/clipmaker/actions/workflows/cloud-dashboard.yml)

**[Tableau de bord Cloud](https://einslen.github.io/clipmaker/)** ·
**[Ouvrir le studio privé](https://codespaces.new/EinSlen/clipmaker?quickstart=1)** ·
**[Suivre les publications](https://github.com/EinSlen/clipmaker/issues/36)** ·
**[Voir les workflows](https://github.com/EinSlen/clipmaker/actions)**

ClipMaker est un studio automatisé pour générer des vidéos verticales originales, affecter un jeu à
chaque compte, puis publier quotidiennement sur TikTok et YouTube Shorts. L'interface web est en
français ; les accroches et les métadonnées envoyées aux plateformes restent en anglais.

## À quoi sert ce dépôt ?

Ce dépôt regroupe tout le produit, de la simulation jusqu'à la publication :

- création de vidéos de jeux en 1080×1920 avec physique déterministe, musique et Foley synchronisé ;
- configuration **un compte = un jeu**, avec cadence, seed et plateformes indépendantes ;
- génération automatique quotidienne et publication programmée à 18 h 07, heure de Paris ;
- envoi vers TikTok au moyen d'une session de navigateur et vers YouTube Shorts ;
- conservation chiffrée des sessions, de l'état et de la vidéo en attente dans GitHub Actions ;
- notification du résultat de chaque opération dans le [ticket de suivi](https://github.com/EinSlen/clipmaker/issues/36).

Le projet contient cinq moteurs : Ball Escape, Organic Escape, Laser Dodge, Boss Battle et Soft
Body 3D. Les quatre premiers rendent en 1080×1920 à 60 i/s. Soft Body utilise Blender et propose
plusieurs familles d'obstacles avec cinq niveaux de souplesse.

## Utilisation dans le Cloud

| Service GitHub | Rôle |
| --- | --- |
| [GitHub Pages](https://einslen.github.io/clipmaker/) | Tableau de bord permanent : état, commandes manuelles et lancement des rendus 3D. |
| [GitHub Actions](https://github.com/EinSlen/clipmaker/actions) | Cron, génération, rendu, publication et notification. |
| [GitHub Codespaces](https://codespaces.new/EinSlen/clipmaker?quickstart=1) | Studio complet et privé pour connecter les comptes et modifier la configuration. |
| GitHub Secrets | Sessions, cookies et configuration chiffrée ; aucune donnée privée n'est incluse dans Pages. |

Le tableau de bord public fonctionne en lecture seule. Les commandes nécessitent un jeton GitHub
finement limité à ce dépôt avec la permission `Actions: write`. Après la première connexion, le
jeton est mémorisé dans le stockage local de ce navigateur, jamais dans le dépôt. Utiliser cette
fonction uniquement sur un appareil personnel ; le bouton **Déconnecter** efface immédiatement le
jeton de l'appareil.

## Démarrage local

Prérequis : Docker Engine avec le plugin Compose.

```bash
git clone https://github.com/EinSlen/clipmaker.git
cd clipmaker
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

Les affectations compte → jeu sont définies dans `web/config/publisher.json`. Le dry-run reste
activé par défaut afin d'éviter toute publication accidentelle.

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
├── vendor/                  fork TikTok Auto Uploader
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

Le workflow manuel **Cloud render capability** construit réellement les sept obstacles 3D,
chronomètre des images natives 1080×1920/128 samples et génère les quatre candidats 2D en qualité
publication si la 3D dépasse le budget du runner. Il ne contient aucun secret et ne publie rien.

Les sessions de navigateur, cookies, rendus, secrets et états de publication sont exclus de Git.
Ne jamais exposer directement le port 3000 sur Internet sans authentification.
