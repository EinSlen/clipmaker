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

## Canal « histoire pilotée par les commentaires »

Le moteur `story-comments` publie chaque jour un épisode français d'environ une minute, dans le
genre du short drama généré par IA : un casting fixe de personnages non humains très
reconnaissables, un huis clos, une trahison par épisode et un cliffhanger final. Le pipeline lit les
commentaires laissés sous l'épisode de la veille, retient le meilleur, crédite son auteur à l'écran,
puis écrit et monte l'épisode suivant. Sans commentaire exploitable, l'histoire continue seule ; la
série ne s'arrête donc jamais.

La cohérence visuelle du casting est le point décisif du format. La bible de série fige quatre
personnages avec une description purement visuelle de huit à quinze mots, et cette description est
réinjectée mot pour mot dans le prompt de chaque plan où le personnage apparaît. Le scénariste ne
redécrit jamais un personnage, il l'appelle par son nom.

Toute la chaîne tient dans des offres gratuites :

| Étage | Service | Consommation d'un épisode |
| --- | --- | --- |
| Commentaires YouTube | YouTube Data API v3 | 1 unité sur 10 000 par jour |
| Commentaires TikTok | session Chromium existante du dossier `vendor/` | aucune |
| Scénario et choix du commentaire | Groq | aucune sur l'offre gratuite |
| Images des plans | Workers AI `flux-1-schnell` | environ 700 neurones |
| Voix off française | Workers AI `melotts` en `fr` | environ 20 neurones |
| Montage | ffmpeg | aucune |

Workers AI offre 10 000 neurones par jour : un épisode quotidien en consomme moins de 8 %.
`aura-2-en` sonne mieux mais ne parle pas français et coûte 2 727 neurones pour mille caractères,
contre 18,63 par minute audio pour MeloTTS ; il n'est utilisé que si une série est passée en
anglais.

### Mise en service

1. créer les secrets GitHub `GROQ_API_KEY`, `YOUTUBE_API_KEY`, `CF_ACCOUNT_ID` et `CF_AI_TOKEN` ;
   le jeton Cloudflare ne demande que la permission **Workers AI: Read** ;
2. dans le tableau de bord, ajouter un compte, choisir le moteur **Histoire pilotée**, renseigner
   l'identifiant de série et le thème de départ, puis sauvegarder ;
3. la lecture des commentaires suppose que les épisodes précédents soient publics : un épisode privé
   n'a pas de commentaires et la série continuera toute seule.

Trois contraintes découvertes en lisant réellement une page TikTok, toutes gérées par le scraper :

- `/api/comment/list` ne répond qu'à une vraie fenêtre. En mode headless la requête part, renvoie
  un HTTP 200, mais avec un corps vide. Chromium est donc lancé en fenêtré, sous Xvfb sur un runner
  Linux.
- la requête n'est émise qu'après un clic sur l'icône commentaires ; le défilement seul ne
  déclenche rien.
- TikTok affiche de lui-même une bannière cookies et un captcha à curseur dès le chargement, et
  l'overlay du captcha absorbe tous les clics réels. Les deux sont refermables : le scraper les
  ferme avant d'agir. Si le captcha résiste, la sortie vaut `tiktok-captcha` au lieu d'une liste
  vide, pour ne pas confondre « lecture impossible » et « aucun commentaire ».

La session utilisée est celle du dossier `vendor/TiktokAutoUploader/CookiesDir`, la même que pour
l'envoi des vidéos. Compter une trentaine de secondes par lecture.

La mémoire de la série vit dans `web/data/story/<série>.json` : bible, résumé de chaque épisode et
commentaire retenu. Elle est incluse dans l'état chiffré du publisher, donc elle survit d'un run
GitHub Actions au suivant. Le thème de départ n'est lu qu'au tout premier épisode.

### Générer les clips automatiquement

Le canal peut monter l'épisode sur de vrais clips vidéo au lieu des images fixes. Les trois étages
s'enchaînent avec une seule commande :

```bash
cd web
npm run minimax:login
npm run story:make -- --series tentafruit --seconds 60
```

La connexion n'est demandée qu'une fois : elle ouvre une fenêtre pour se connecter à Hailuo et garde
la session dans le profil persistant `.minimax-browser/`, exclu de Git. Ensuite `plan-episode.mjs`
lit les commentaires et écrit `prompts.txt`, `minimax-agent.cjs` remplit `clips/`, puis
`assemble-episode.mjs` recadre en 9:16, incruste les sous-titres et met à jour la mémoire de série.
Un clip déjà téléchargé n'est jamais regénéré, donc une interruption ne coûte que les clips
manquants et `--from-plan` reprend un plan existant.

Le mode fenêtré est obligatoire, comme pour TikTok. Deux commandes servent au diagnostic :

| Commande | Rôle |
| --- | --- |
| `npm run minimax:doctor` | vérifie la session, la zone de prompt et le bouton de génération |
| `npm run minimax:probe` | vide le DOM réel dans `renders/minimax-probe/` pour réparer un sélecteur |

Si le site change, `MINIMAX_PROMPT_SELECTOR` et `MINIMAX_SUBMIT_SELECTOR` forcent les deux
sélecteurs sans toucher au code, et `MINIMAX_RESULT_PATTERN` restreint les URL acceptées.

#### Emmener la session dans la pipeline

Un profil Chromium est bien trop volumineux pour un secret, donc seuls les cookies voyagent, comme
pour la session TikTok. `npm run minimax:login` les exporte tout seul dans
`web/data/auth/minimax-session.json`, en mode 600 et hors de Git. Rien n'est exporté tant que le
profil n'est pas connecté : une session anonyme casserait silencieusement chaque run.

Deux routes mènent au runner, au choix :

| Route | Mise en place |
| --- | --- |
| Synchronisation Cloudflare | le fichier part dans le bundle de sessions existant, ajouté dès qu'un compte utilise le moteur `story-comments`. Aucun nouveau secret. |
| Secret GitHub | `npm run minimax:session -- --github-secret` écrit `MINIMAX_COOKIES_B64`, lu directement par le workflow. |

Le runner n'a pas de profil : l'agent en fabrique un jetable, y injecte les cookies, puis le
supprime. `npm run minimax:doctor` affiche la source réellement utilisée, secret, fichier ou profil.

Le cookie qui porte l'authentification est `_token`, et il vaut trente jours. Une session est donc à
renouveler tous les mois avec `minimax:login` puis `minimax:session`. L'agent refuse de démarrer sur
une session qui ne le contient pas, plutôt que d'ouvrir un navigateur anonyme et de consommer le
délai d'attente complet de chaque clip avant d'échouer.
Sur un runner Linux le navigateur reste fenêtré sous Xvfb, déjà présent dans l'image, comme pour la
lecture des commentaires TikTok.

La variable de dépôt `STORY_CLIP_MODE` arbitre le format : `auto` par défaut tente les clips puis
retombe sur les images fixes si la génération échoue, ce qui évite de sauter une publication
quotidienne à cause d'une interface tierce ; `only` interdit ce repli et `off` reste sur les images.
Le reçu de rendu indique toujours lequel des deux a produit l'épisode.

Un repli n'est jamais silencieux : le compte rendu quotidien publié dans le
[ticket de suivi](https://github.com/EinSlen/clipmaker/issues/36) porte une ligne d'alerte avec la
raison exacte de l'échec, et signale aussi un épisode monté avec moins de clips que prévu.

Trois pièges découverts en pilotant réellement le site, tous gérés par l'agent :

- la zone de prompt est un éditeur Slate. Une saisie touche par touche y perd tout après les
  premiers caractères, parce que chaque frappe provoque un rendu React qui réinitialise la
  sélection. Un prompt de 274 caractères est ainsi arrivé au modèle sous la forme de deux lettres,
  et le clip produit était cohérent avec ces deux lettres, donc l'échec ne se voyait pas. Le texte
  est envoyé en un seul événement puis relu pour vérification.
- le format, la durée et la résolution sont des réglages d'interface, pas des consignes de prompt.
  Le site les garde par modèle dans `VIDEO_SETTINGS_BY_MODEL_V2` et part sur du 21:9 cinéma,
  inutilisable en vertical. Ils sont donc écrits avant le démarrage de l'application, plutôt que
  cliqués dans un menu. `MINIMAX_RATIO`, `MINIMAX_DURATION` et `MINIMAX_RESOLUTION` les pilotent, et
  `MINIMAX_DURATION` sert aussi à découper l'épisode en plans de la bonne longueur.
- reconnaître le clip généré est le point délicat. La page charge ses propres vidéos
  promotionnelles pendant l'attente, exactement au format d'un résultat : la première version de
  l'agent a téléchargé une publicité du site en croyant avoir son clip. Seules les créations du
  compte apparaissant dans `/api/feed/creation/my`, l'agent relève les identifiants présents avant
  l'envoi et ne retient qu'un identifiant nouveau, ce qui lève toute ambiguïté. La liste est lue en
  capturant la réponse de la galerie, car le site signe lui-même ses appels.

`npm run minimax:doctor` sert de pré-vérification complète et sans coût : il contrôle la session,
les deux sélecteurs, les réglages effectifs, le solde de crédits, et écrit un prompt de longueur
réelle qu'il relit, sans jamais lancer de génération.

#### Sous-titres calés sur la voix

Le clip parle de lui-même, et le modèle ne dit jamais la réplique écrite mot pour mot. Les
sous-titres sont donc construits à partir de ce qui est réellement entendu : la piste audio du clip
est transcrite avec des horodatages par mot, puis regroupée en trois ou quatre mots par carton. Un
sous-titre apparaît ainsi pendant que ses mots sont prononcés, et rien ne s'affiche dans un silence.

Sur un épisode en images fixes rien n'est transcrit : c'est la voix qui dit elle-même où chaque mot
tombe. edge-tts n'écrit que des sous-titres à la phrase en ligne de commande, mais le service émet
un événement par mot, et `speak_words.py` lit ce flux directement. Les timings sont donc exacts,
gratuits, et sans aucune clé.

Un clip généré parle en revanche de son propre chef, donc son audio est transcrit : par Groq Whisper
si `GROQ_API_KEY` est présente, sinon par Workers AI via le Worker, qui expose une tâche
`transcribe` bornée à un audio de 16 kHz mono. Sans transcripteur disponible, le montage retombe sur
une répartition uniforme du texte écrit et le signale dans son reçu : l'épisode reste sous-titré,
simplement moins précisément.

Le mot en train d'être prononcé est repeint sur fond rouge, le reste du groupe restant en blanc.
`drawtext` ne sait pas dire où un mot tombe dans une ligne, donc une position estimée ferait dériver
la boîte rouge à côté du mot : les avances réelles sont mesurées par `caption_metrics.py` dans la
police même que ffmpeg utilise pour dessiner, ce qui aligne la boîte exactement. Chaque carton est
donc dessiné deux fois, une passe blanche pour tout le groupe et une passe rouge pour le seul mot
actif, dans cet ordre puisque les filtres `drawtext` s'appliquent en séquence.

#### Crédits

Un clip coûte des crédits, et l'agent refuse de commencer s'il ne peut pas payer la totalité des
clips manquants. Le refus est volontairement tout ou rien : la moitié d'un épisode signifie toute la
narration entassée sur un tiers de la durée, ce qui se lit plus mal que le repli sur images fixes,
lequel produit au moins un épisode complet. Le solde, le prix unitaire et le nombre de clips
manquants partent dans le compte rendu du ticket.

Prix relevés sur l'offre gratuite : soixante crédits pour un clip de cinq secondes, cent vingt pour
dix secondes, la résolution ne changeant rien. `MINIMAX_CREDITS_PER_CLIP` sert de repli si le prix
n'est plus lisible dans l'interface.

Deux limites à connaître. L'offre gratuite tourne autour de cent crédits par connexion quotidienne,
soit deux à trois clips, alors qu'un épisode de soixante secondes en demande quatre de quinze
secondes : baisser `--seconds` réduit le nombre de clips demandés. Et le site est protégé par Akamai
Bot Manager, donc un pilotage répété peut déclencher un contrôle.

### Vérifier sans aucune clé

```bash
cd web
node scripts/story/build-episode.mjs --offline --series smoke-test --seconds 45 \
  --output-dir renders/story-smoke --no-music
```

Le mode hors ligne remplace les images et la voix par des marqueurs déterministes et n'appelle
aucune API. Il produit un vrai MP4 1080×1920 et sert à valider le montage, la mémoire de série et
les sous-titres. Rien n'est publié.

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
│   │   └── story/           épisodes pilotés par les commentaires
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
