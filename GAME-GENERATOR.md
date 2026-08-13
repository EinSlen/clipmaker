# Générateur de jeux verticaux

ClipMaker produit des vidéos originales en 1080×1920 sans réutiliser de vidéo tierce. Une graine
reproduit exactement le même jeu, les mêmes impacts et la même bande-son.

## Jeux disponibles

- **Ball Escape** — vortex d’anneaux plein écran, gravité, accélération et issue tardive variable.
- **Organic Escape** — balle à traînée qui brise des contours organiques avec impacts ASMR accordés.
- **Laser Dodge** — pilote néon, lasers mobiles, collisions géométriques et échecs tardifs variables.
- **Boss Battle** — arène physique, arme articulée, Warden blindé, impacts et vainqueur déterministes.
- **Soft Body 3D** — scène Blender premium avec capsule déformable, sept familles d'obstacles physiques, matériaux métal/marbre et éclairage studio.

Les trajectoires, collisions et issues viennent des solveurs physiques. Aucun trou ne suit une balle,
aucune vitesse n'est corrigée vers une ouverture et aucun vainqueur n'est imposé après coup. Une graine
peut donc produire une réussite, un impact ou un échec naturel, désormais indiqué explicitement dans le rendu.

Les quatre moteurs 2D possèdent leur propre réglage dans l'interface : anneaux, couches, lasers ou
points de vie. Soft Body compare cinq niveaux et permet de choisir une famille d'obstacles ou une
rotation automatique reproductible par graine. Les
thèmes, graines, sons, musiques et durées restent communs lorsque le moteur les prend en charge afin
de créer beaucoup de variantes sans dupliquer le code de publication.

## Utilisation

1. Ouvrir l'onglet **Jeux** et choisir un format.
2. Régler la durée, la difficulté, la palette et l'accroche en anglais. Soft Body verrouille la durée
   à 30 secondes, compare automatiquement cinq niveaux de souplesse et propose sept parcours physiques.
3. Garder la découverte musicale automatique. **Révélation à l'impact** est sélectionnée par défaut
   pour Ball Escape, Laser Dodge et Boss Battle ; Organic Escape conserve une bande-son continue et
   Soft Body un mix Foley/ambiance synchronisé aux contacts physiques.
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

Les moteurs 2D calculent et encodent par défaut nativement en 1080×1920 à 60 FPS. Les variables
`GAME_RENDER_WIDTH`, `GAME_RENDER_HEIGHT` et `GAME_RENDER_FPS` permettent de créer des smokes plus
rapides pendant le développement.

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

Valeurs de `game` : `ball-escape`, `shape-tunnel`, `laser-dodge`, `boss-battle`, `soft-body-slide`.

Le moteur `soft-body-slide` utilise Blender Eevee en mode headless. Il rejoue cinq essais progressifs
avec une capsule à contraintes physiques et un vrai réceptacle ouvert. Le paramètre `obstacle` accepte
`auto`, `moving-slide`, `stair-cascade`, `v-stairs`, `pipe-bend`, `peg-grid`, `twin-gears` ou
`compression-ring`. La graine sélectionne une combinaison reproductible de forme, parcours, palette,
réceptacle, progression de souplesse et paramètres physiques. Son mix par défaut associe les Foley
ASMR synchronisés à une musique ambiante originale qui change avec la graine ; une piste choisie ou
sous licence peut la remplacer. Blender est inclus dans l'image Docker officielle du projet.

Le profil Soft Body par défaut privilégie désormais le réalisme sans contrainte de temps : 30 secondes,
source native 1080×1920 à 30 i/s, 128 échantillons Eevee, ombres 4K, géométrie subdivisée,
collisions exportées par Blender et encodage H.264 CRF 14. Les
variables `PREMIUM_RENDER_*` servent uniquement à créer des smokes plus rapides pendant le développement.

Le délai serveur par défaut autorise jusqu’à sept jours pour un rendu Soft Body final. Il reste
configurable avec `PREMIUM_RENDER_TIMEOUT_MS` pour les machines plus rapides ou une file externe.

Sur un VPS CPU, ajuster au besoin `PREMIUM_RENDER_WIDTH`, `PREMIUM_RENDER_HEIGHT`,
`PREMIUM_RENDER_FPS` et `PREMIUM_RENDER_SAMPLES` pour les aperçus de développement. Sans surcharge,
le rendu final reste calculé nativement en 1080×1920 ; il n'est pas agrandi depuis une petite source.

## Tests

```bash
cd web
npm test                  # types + tests déterministes des 4 moteurs rapides
npm run test:render-smoke # encode et inspecte les MP4 avec ffprobe
```

Les tests vérifient aussi que le catalogue TypeScript et les moteurs Python possèdent exactement les
mêmes identifiants de jeu.

La viralité ne peut pas être garantie. Comparer la rétention par jeu, graine, accroche, durée et compte
avant d'automatiser une cadence importante.
