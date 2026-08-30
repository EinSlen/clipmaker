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
- rendu 3D matriciel à 00 h 07, génération 2D à 00 h 37 et publication Cloudflare dès 18 h 00, heure de Paris ;
- planificateur Cloudflare toutes les cinq minutes : il déclenche la publication au créneau configuré et rattrape les générations absentes ou échouées sans doubler un run actif ou réussi ;
- cron GitHub de 18 h 07 conservé comme second filet de sécurité ; l’état chiffré du publisher empêche un second envoi ;
- rattrapage GitHub à la fin d'un rendu 3D tardif : uniquement les comptes déjà dus, les artefacts du jour et la branche de production ; jamais un aperçu de test ;
- envoi TikTok autonome par l'API web historique du fork, avec vérification et repli TikTok Studio sans doublon ; envoi YouTube Shorts avec OAuth/API ;
- conservation chiffrée des sessions, de l'état et de la vidéo en attente dans GitHub Actions ;
- notification du résultat de chaque opération dans le [ticket de suivi](https://github.com/EinSlen/clipmaker/issues/36).

Le projet contient cinq moteurs : Ball Escape, Organic Escape, Laser Dodge, Boss Battle et Soft
Body 3D. Les quatre premiers rendent en 1080×1920 à 60 i/s. Soft Body utilise Blender et propose
plusieurs familles d'obstacles avec cinq niveaux de souplesse.

## Utilisation dans le Cloud

| Service GitHub | Rôle |
| --- | --- |
| [GitHub Pages](https://einslen.github.io/clipmaker/) | Tableau de bord permanent : état, affectation compte → jeu, planning, commandes et rendu 3D. |
| [GitHub Actions](https://github.com/EinSlen/clipmaker/actions) | Calcul, génération, rendu, publication et notification. Le cron de 18 h 07 sert de secours automatique. |
| [GitHub Codespaces](https://codespaces.new/EinSlen/clipmaker?quickstart=1) | Studio complet et privé pour connecter les comptes et modifier la configuration. |
| [Cloudflare Worker](https://clipmaker-cloud-control.einslen.workers.dev) | Authentification GitHub privée, configuration en KV et planificateur principal toutes les cinq minutes. |
| GitHub Secrets | Jetons du runner et clé de chiffrement de l'état ; aucune valeur n'est incluse dans Pages. |

Le tableau de bord est public en lecture seule. Après connexion avec la GitHub App privée, il permet
de modifier le jeu, l'obstacle, l'heure et les destinations de chaque compte. Aucun PAT n'est copié
dans le navigateur. La session TikTok est créée dans le Studio privé puis synchronisée vers le
Worker. YouTube utilise un jeton OAuth renouvelable conservé dans GitHub Secrets : le runner n'a
besoin ni de navigateur connecté, ni d'adresse IP fixe, ni d'un ordinateur ou VPS allumé.

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

Si le rendu n'est pas prêt à l'heure prévue, la publication reste bloquée. Le workflow
**Catch up a late daily 3D render** la relance après un rendu réussi le même jour, avec les mêmes
contrôles et sans forcer les plateformes déjà publiées. Un horaire exact n'est donc pas garanti
en cas de retard des runners ou du rendu.

```bash
cp web/config/publisher.example.json web/config/publisher.json
docker compose exec -T clipmaker node /repo/web/scripts/publisher.mjs due \
  --config /repo/web/config/publisher.json --dry-run
```

Après avoir connecté les comptes et validé un upload privé, le daemon local peut être utilisé à la
place de GitHub Actions avec :

```bash
docker compose --profile publisher up -d --build
```

Ne lance jamais le daemon local et le cron GitHub en même temps : ils utilisent deux états distincts
et pourraient envoyer le même contenu deux fois.

Les affectations compte → jeu sont définies dans `web/config/publisher.json`. Le dry-run reste
activé par défaut afin d'éviter toute publication accidentelle.

### Connecter YouTube à GitHub Actions

Une seule autorisation locale est nécessaire par chaîne YouTube :

1. activer **YouTube Data API v3** dans Google Cloud et créer un client OAuth de type
   **Application de bureau** ;
2. télécharger son fichier JSON sans l'ajouter au dépôt ;
3. exécuter depuis `web/` :

```bash
npm run youtube:oauth:setup -- --client-json "CHEMIN/client_secret.json" --account default
```

La commande ouvre Google, demande uniquement le droit `youtube.upload`, puis crée ou actualise le
secret GitHub `YOUTUBE_OAUTH_ACCOUNTS_B64`. Pour une autre chaîne, relancer la commande avec un nom
de compte différent ; le fichier local ignoré `.youtube-oauth-accounts.json` conserve le bundle à
resynchroniser. Aucun mot de passe ou jeton OAuth n'est commité.

## Architecture

```text
clipMaker/
├── cloud-dashboard/         interface statique publiée sur GitHub Pages
├── web/
│   ├── src/app/             pages Next.js et routes API
│   ├── src/components/      interface du studio
│   ├── src/lib/             rendu, musique et intégrations
│   ├── src/automation/      planification, état et idempotence
│   ├── scripts/             moteurs Python et CLI de publication
│   └── config/              affectations fixes compte → jeu
├── infra/cloud-control-worker/ authentification GitHub App et commandes Pages
├── infra/systemd/           timer Linux optionnel
├── vendor/                  fork TikTok Auto Uploader
└── docker-compose.yml       application, publication et login TikTok
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

Le workflow **Soft Body 3D artifact** s'exécute automatiquement pendant la nuit. Il simule chaque
canal 3D, répartit ses 900 images natives 1080×1920 entre les runners, assemble le MP4 et produit un
manifeste importé par le workflow de publication. Le workflow manuel **Cloud render capability** reste
un benchmark sans publication.

Les sessions de navigateur, cookies, rendus, secrets et états de publication sont exclus de Git.
Ne jamais exposer directement le port 3000 sur Internet sans authentification.
