# Générateur Ball Escape

ClipMaker peut produire des vidéos verticales originales sans source tierce : une balle tente de
s'échapper d'anneaux rotatifs, avec accroche, compteur, particules et audio synchronisé.

## Utilisation

1. Ouvrir ClipMaker puis l'onglet **Jeu auto**.
2. Choisir la durée, le nombre d'anneaux et la palette.
3. Garder **Auto Buzz** pour varier automatiquement les effets selon la graine.
4. Générer, regarder la vidéo entière, puis publier d'abord en privé.

Chaque graine reproduit exactement la même simulation. Une graine vide crée une nouvelle variante.
Le rendu final est un MP4 H.264/AAC en 1080×1920, compatible TikTok et YouTube Shorts.

## Stratégie audio

Le mode Auto Buzz crée une accroche sonore pendant les 300 premières millisecondes, une boucle
originale à 118 BPM, des impacts liés aux collisions et une fanfare si la balle sort. Il choisit
automatiquement entre les familles drôle, arcade et impact.

Une piste de fond peut aussi être importée. Le choix **Auto — rotation de ma bibliothèque** sélectionne
une piste de façon déterministe pour chaque graine. Pour YouTube, n'utiliser que de la musique originale,
libre ou correctement licenciée. Pour TikTok, le champ **Son officiel TikTok** accepte l'URL ou
l'identifiant d'un son de la plateforme et le transmet à l'uploader. Les tendances peuvent être
contrôlées dans le [TikTok Creative Center](https://ads.tiktok.com/business/creativecenter/inspiration/popular/music/pc/en?countryCode=FR&period=7).

## Docker / VPS

```bash
docker compose build clipmaker
docker compose up -d clipmaker
docker compose exec clipmaker npm run youtube:doctor
```

Les rendus persistent dans `web/renders/`. Un seul rendu de jeu est accepté à la fois afin de ne pas
saturer un petit VPS.

## API

```bash
curl -X POST http://127.0.0.1:3000/api/game/render \
  -H 'Content-Type: application/json' \
  -d '{"duration":45,"rings":240,"theme":"neon","soundPack":"auto","musicFile":"__discover__","musicMode":"hit-reveal"}'
```

Le mode `hit-reveal` découpe le morceau dans l'ordre et débloque le fragment
suivant à chaque collision. `__discover__` recherche un nouveau morceau CC BY
instrumental via Jamendo lorsque `JAMENDO_CLIENT_ID` est configuré, puis se
replie sur les pistes licenciées importées ou sur la bande-son originale.

La viralité ne peut pas être garantie. Tester plusieurs graines, questions et durées permet de
mesurer la rétention réelle avant d'automatiser une cadence plus importante.
