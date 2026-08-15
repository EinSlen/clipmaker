# Test de rendu sur GitHub Actions

Le workflow **Cloud render capability** répond à une seule question : un runner GitHub hébergé
peut-il produire le Soft Body 3D en vraie qualité finale avant sa limite d'exécution ? Si la réponse
est non, il rend immédiatement les quatre moteurs 2D en qualité publication afin de conserver une
solution exploitable.

Il ne publie aucune vidéo et ne lit aucun cookie. Aucun secret YouTube ou TikTok n'est nécessaire.

## Lancer le test

1. Ouvrir l'onglet **Actions** du dépôt GitHub.
2. Choisir **Cloud render capability**.
3. Cliquer sur **Run workflow**.
4. Garder `moving-slide`, la seed `910104` et le test 2D activé pour le premier passage.

Le workflow utilise l'image Docker `ci`, qui contient les mêmes versions Debian de Blender,
FFmpeg et Python que l'application. Il exécute d'abord toute la suite déterministe.

## Ce qui est réellement testé

### 3D

- construction et simulation Blender des sept familles d'obstacles ;
- fichier de télémétrie valide pour chaque scène ;
- trois PNG réellement rendus en 1080×1920 avec 128 samples Eevee ;
- mesure du temps moyen par image ;
- projection vers les 900 images uniques d'une vidéo de 30 secondes à 30 i/s.

Le seuil de compatibilité est fixé à 5 h 15, ce qui laisse une marge avant la limite d'un job GitHub
hébergé. Les images natives et le rapport JSON sont téléchargeables dans l'artefact
`3d-native-capability-*`. Une vignette basse définition n'est jamais utilisée pour conclure que la
3D finale est viable.

### Repli 2D

Le workflow rend quatre vrais MP4 1080×1920 à 60 i/s :

- Ball Escape, seed gagnante 9 ;
- Organic Escape, seed gagnante 8 ;
- Boss Battle, seed joueur gagnante 10 ;
- Laser Dodge, seed survivante 0.

Chaque fichier doit avoir une issue physique attendue, des événements réels, de la musique, une
piste AAC 48 kHz, un niveau sonore compris entre -18 et -12 LUFS et aucune plage silencieuse de
trois secondes. Les vidéos et le rapport sont dans `2d-production-candidates`.

Ball Escape est le premier candidat éditorial pour un compte de test et Organic Escape le second.
Ce classement ne prétend pas prédire les vues : la performance réelle se mesure ensuite avec des
publications privées puis un A/B test public, en comparant rétention, relecture et abonnements.

## Pourquoi ce workflow ne publie pas

Les runners GitHub sont éphémères et leur adresse IP change. C'est adapté au calcul et à la QA,
mais fragile pour des sessions de navigateur TikTok/YouTube. La publication quotidienne reste dans
l'orchestrateur Docker documenté dans [AUTOMATION.md](AUTOMATION.md), sur une machine ou un VPS
qui conserve ses sessions et son adresse IP.

## Coût et conservation

Le dépôt étant public, le test utilise les runners standards du dépôt. La concurrence est verrouillée
à un seul test pour éviter deux rendus Blender simultanés. Les artefacts sont supprimés automatiquement
au bout de trois jours.
