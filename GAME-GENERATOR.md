# Générateur de jeux verticaux

ClipMaker produit des vidéos originales en 1080×1920 sans réutiliser de vidéo tierce. Une graine
reproduit exactement le même jeu, les mêmes impacts et la même bande-son.

## Jeux disponibles

- **Ball Escape** — balle soumise à la gravité, anneaux rotatifs et accélération progressive.
- **Organic Escape** — balle à traînée qui brise des contours organiques avec impacts ASMR accordés.
- **Soft Body Slide 3D** — scène Blender premium avec capsule déformable, matériaux métal/marbre et éclairage studio.

Chaque jeu possède son propre réglage de difficulté dans l'interface : anneaux, couches, points de
vie ou notes. Les thèmes, graines, sons, musiques et durées restent communs afin de créer beaucoup
de variantes sans dupliquer le code de publication.

## Utilisation

1. Ouvrir l'onglet **Auto Game** et choisir un format.
2. Régler la durée, la difficulté, la palette et l'accroche en anglais.
3. Garder **Auto Viral Mix** et **Hit Reveal** pour synchroniser les impacts avec la musique.
4. Générer une vidéo ou un lot de trois variantes, regarder chaque résultat, puis choisir un ou plusieurs comptes TikTok et un profil YouTube.
5. Publier d'abord YouTube en privé et vérifier le résultat avant d'augmenter la cadence.

Les cibles TikTok sont traitées une par une avec un résultat séparé par compte. Les profils YouTube
sont isolés dans `.youtube-browser/accounts/<profil>/` ; le profil historique reste `default`. Les
routages TikTok et YouTube sont mémorisés séparément pour chaque jeu dans le navigateur.

## Audio

Le moteur crée une accroche sonore dans les 300 premières millisecondes, des impacts synchronisés et
une musique électronique originale si aucune piste licenciée n'est disponible. Le mode `hit-reveal`
débloque le morceau dans l'ordre, impact après impact.

Pour YouTube, utiliser uniquement une musique originale, libre ou correctement licenciée. Pour TikTok,
le champ **Official TikTok sound** peut attacher l'identifiant d'un son officiel au post sans l'intégrer
au fichier YouTube.

## Docker / VPS

```bash
docker compose build clipmaker
docker compose up -d clipmaker
docker compose exec clipmaker npm run youtube:doctor
```

Les rendus persistent dans `web/renders/`. Un seul rendu est encodé à la fois pour ne pas saturer un
petit VPS.

Les moteurs 2D calculent par défaut en 360×640 à 15 FPS puis encodent en 1080×1920. Les variables
`GAME_RENDER_WIDTH`, `GAME_RENDER_HEIGHT` et `GAME_RENDER_FPS` permettent d'augmenter la qualité ou
de réduire la charge d'un VPS.

Pour connecter plusieurs chaînes YouTube :

```bash
YOUTUBE_ACCOUNT=gaming docker compose --profile youtube-auth up --force-recreate youtube-auth
```

Puis ouvrir noVNC, terminer la connexion et sélectionner `Gaming` dans le panneau de publication.

## API

```bash
curl -X POST http://127.0.0.1:3000/api/game/render \
  -H 'Content-Type: application/json' \
  -d '{"game":"shape-tunnel","duration":45,"difficulty":200,"theme":"neon","soundPack":"auto","musicFile":"__discover__","musicMode":"continuous"}'
```

Valeurs de `game` : `ball-escape`, `shape-tunnel`, `soft-body-slide`.

Le moteur `soft-body-slide` utilise Blender Eevee en mode headless. Il rejoue cinq essais canoniques
avec une rampe mobile, une capsule à contraintes physiques et un vrai réceptacle ouvert. La graine
sélectionne une combinaison reproductible parmi plus de 2 000 variantes : forme, parcours, palette,
réceptacle, progression de souplesse et paramètres physiques. Son mix par défaut privilégie les Foley
ASMR synchronisés ; une musique choisie ou sous licence reste facultative. Blender est inclus dans
l'image Docker officielle du projet.

Sur un VPS CPU, ajuster au besoin `PREMIUM_RENDER_WIDTH`, `PREMIUM_RENDER_HEIGHT`,
`PREMIUM_RENDER_FPS` et `PREMIUM_RENDER_SAMPLES`. Les valeurs par défaut privilégient un rendu final
1080×1920 fluide tout en calculant les images Blender à une résolution intermédiaire plus économique.

## Tests

```bash
cd web
npm test                  # types + tests déterministes des 2 moteurs rapides
npm run test:render-smoke # encode et inspecte les 2 MP4 avec ffprobe
```

Les tests vérifient aussi que le catalogue TypeScript et les moteurs Python possèdent exactement les
mêmes identifiants de jeu.

La viralité ne peut pas être garantie. Comparer la rétention par jeu, graine, accroche, durée et compte
avant d'automatiser une cadence importante.
