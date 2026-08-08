# Générateur de jeux verticaux

ClipMaker produit des vidéos originales en 1080×1920 sans réutiliser de vidéo tierce. Une graine
reproduit exactement le même jeu, les mêmes impacts et la même bande-son.

## Jeux disponibles

- **Ball Escape** — balle soumise à la gravité, anneaux rotatifs et accélération progressive.
- **Shape Tunnel** — comète qui traverse des couches géométriques ondulantes et musicales.
- **Boss Battle** — duel procédural avec barres de vie, impacts critiques et vainqueur variable.
- **Melody Drop** — balle gravitationnelle dont chaque rebond débloque une note.

Chaque jeu possède son propre réglage de difficulté dans l'interface : anneaux, couches, points de
vie ou notes. Les thèmes, graines, sons, musiques et durées restent communs afin de créer beaucoup
de variantes sans dupliquer le code de publication.

## Utilisation

1. Ouvrir l'onglet **Auto Game** et choisir un format.
2. Régler la durée, la difficulté, la palette et l'accroche en anglais.
3. Garder **Auto Viral Mix** et **Hit Reveal** pour synchroniser les impacts avec la musique.
4. Générer, regarder la vidéo entière, puis choisir un ou plusieurs comptes TikTok et un profil YouTube.
5. Publier d'abord YouTube en privé et vérifier le résultat avant d'augmenter la cadence.

Les cibles TikTok sont traitées une par une avec un résultat séparé par compte. Les profils YouTube
sont isolés dans `.youtube-browser/accounts/<profil>/` ; le profil historique reste `default`.

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

Pour connecter plusieurs chaînes YouTube :

```bash
YOUTUBE_ACCOUNT=gaming docker compose --profile youtube-auth up --force-recreate youtube-auth
```

Puis ouvrir noVNC, terminer la connexion et sélectionner `Gaming` dans le panneau de publication.

## API

```bash
curl -X POST http://127.0.0.1:3000/api/game/render \
  -H 'Content-Type: application/json' \
  -d '{"game":"boss-battle","duration":45,"difficulty":300,"theme":"neon","soundPack":"auto","musicFile":"__discover__","musicMode":"hit-reveal"}'
```

Valeurs de `game` : `ball-escape`, `shape-tunnel`, `boss-battle`, `melody-drop`.

La viralité ne peut pas être garantie. Comparer la rétention par jeu, graine, accroche, durée et compte
avant d'automatiser une cadence importante.
