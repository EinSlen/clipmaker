# Machine recommandée et installation Linux

## Choix recommandé : 50 à 100 €

Le meilleur choix pour ClipMaker est un **mini-PC professionnel x86-64 d'occasion**, pas une
machine gaming neuve. Chercher en priorité l'une de ces trois familles :

- **HP EliteDesk 800 G2 Mini** ;
- **Dell OptiPlex 3040/3050 Micro** ;
- **Lenovo ThinkCentre M710q Tiny**.

Configuration cible : **Core i5-6400T/6500T ou meilleur, 8 Go de RAM et SSD 256 Go**, alimentation
incluse. Un modèle SFF plus volumineux avec un i5-6500 non-T convient aussi et rendra un peu plus
vite.

Offre professionnelle vérifiée au 15 août 2026 : **Lenovo ThinkCentre M710q, Core i5-6400T, 8 Go,
SSD 512 Go à 99,99 € chez Cash Express**. La fiche indique un produit testé, une garantie de deux
ans, le paiement sécurisé, la livraison ou le retrait en magasin :
<https://www.cashexpress.fr/micro-lenovo-i5-6400t-thinkcentre-m710q-8go-512go-intel-hd-occasion%2C4817947.html>.
Le stock étant unitaire, confirmer avant paiement que le bloc d'alimentation est inclus.

Éviter les versions Celeron/Pentium, 4 Go de RAM, disque dur mécanique ou vendues sans alimentation.
Ne pas payer plus de 100 € pour un i5 de sixième génération. Si cette offre disparaît, chercher les
mêmes références chez Cash Express, Easy Cash ou un reconditionneur professionnel avec au moins un
an de garantie. Si deux offres sont au même prix,
prendre celle avec 16 Go de RAM ; sinon 8 Go suffisent pour démarrer et la mémoire pourra être
augmentée plus tard.

## Temps de rendu à accepter

Ce matériel est suffisant pour Docker, l'interface, les quatre moteurs 2D et les uploaders. Il peut
rester allumé en permanence et finir les rendus 2D sans intervention. En revanche, un Soft Body 3D
natif de 30 secondes peut occuper le CPU pendant plusieurs jours. L'orchestrateur relancera un job
interrompu, mais le rendu en cours peut recommencer ; une seule machine à moins de 100 € ne peut donc
pas garantir un nouveau Soft Body chaque jour si un rendu dépasse 24 heures.

Pour publier Soft Body quotidiennement sans réduire la qualité, préparer une réserve de vidéos sur
le PC principal puis les transférer sur le mini-PC pour publication. Avec l'automatisation actuelle,
le mini-PC peut assurer seul la chaîne complète des comptes Ball Escape, Organic Escape, Laser Dodge
et Boss Battle ; Soft Body doit être rendu en avance si son temps de calcul dépasse une journée.

## Pourquoi pas un Raspberry Pi 5

Le Raspberry Pi 5 est excellent pour un petit serveur, mais sa puce est un Cortex-A76 Arm à quatre
cœurs avec un GPU VideoCore VII. La carte, l'alimentation, le refroidissement et le stockage dépassent
souvent le budget d'un mini-PC professionnel complet. Il peut héberger un planificateur ou envoyer
des fichiers, mais le rendu Blender natif 1080×1920/30 i/s de Soft Body serait beaucoup trop lent et
le chemin TikTok/Chromium Arm n'est pas couvert par nos tests. Caractéristiques officielles :
<https://www.raspberrypi.com/products/raspberry-pi-5/>.

Un Raspberry Pi peut servir de contrôleur basse consommation si les rendus sont produits ailleurs.
À prix égal, le mini-PC x86 d'occasion est plus simple et plus compatible avec le dépôt actuel.

## Installation recommandée

Installer **Ubuntu Server 24.04 LTS** sur le mini-PC, avec OpenSSH, puis connecter la machine en
Ethernet. Dans les commandes suivantes, le dépôt est installé dans `/opt/clipmaker`.

### 1. Système et Docker

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt install -y git curl ca-certificates
sudo reboot
```

Installer ensuite Docker Engine et le plugin Compose depuis
<https://docs.docker.com/engine/install/ubuntu/>. Aucun pilote NVIDIA ni runtime GPU n'est nécessaire
pour la configuration à moins de 100 €.

### 2. Installer ClipMaker

```bash
sudo git clone --recurse-submodules https://github.com/EinSlen/clipMaker.git /opt/clipmaker
sudo chown -R "$USER":"$USER" /opt/clipmaker
cd /opt/clipmaker
cp web/.env.example web/.env.local
cp web/config/publisher.example.json web/config/publisher.json
```

Générer un token et l'inscrire dans `web/.env.local` :

```bash
openssl rand -hex 32
nano web/.env.local
```

Conserver au départ :

```dotenv
CLIPMAKER_UPLOAD_TOKEN=la-valeur-generee
YOUTUBE_BROWSER_DRY_RUN=true
YOUTUBE_ALLOW_PUBLIC_UPLOAD=false
PUBLISHER_DRY_RUN=true
```

Construire et démarrer en rendu CPU :

```bash
docker compose build clipmaker
docker compose up -d clipmaker
docker compose exec -T clipmaker node /repo/web/scripts/publisher.mjs doctor \
  --config /repo/web/config/publisher.json
```

### 3. Connecter les comptes

YouTube utilise le port local 6080 et TikTok le port 6081. Ces ports restent liés à localhost ; les
ouvrir depuis ton ordinateur avec des tunnels SSH.

```bash
# Sur le serveur : YouTube
docker compose --profile youtube-auth run --rm --service-ports youtube-auth

# Sur le serveur : TikTok
TIKTOK_USERNAME=moncompte docker compose --profile tiktok-auth run --rm --service-ports tiktok-auth
```

Depuis ton ordinateur :

```bash
ssh -L 6080:127.0.0.1:6080 utilisateur@adresse-du-serveur
ssh -L 6081:127.0.0.1:6081 utilisateur@adresse-du-serveur
```

Ouvrir respectivement `http://127.0.0.1:6080/vnc.html` et
`http://127.0.0.1:6081/vnc.html`. Les sessions restent dans les dossiers ignorés par Git.

### 4. Tester puis activer

Exécuter le plan quotidien sans rendre ni publier :

```bash
docker compose exec -T clipmaker node /repo/web/scripts/publisher.mjs due \
  --config /repo/web/config/publisher.json --dry-run
```

Faire ensuite un vrai rendu manuel, un upload YouTube privé et un upload TikTok de test. Seulement
après vérification, activer les cibles de `publisher.json`, passer les variables dry-run à `false`,
puis démarrer :

```bash
docker compose --profile publisher up -d
```

## Exploitation 24/7

- Brancher la machine en Ethernet et activer le redémarrage après coupure dans l'UEFI.
- Ajouter un petit onduleur si les coupures sont fréquentes.
- Sauvegarder `.youtube-browser/`, `vendor/TiktokAutoUploader/CookiesDir/` et
  `web/data/publisher/` sur un support chiffré.
- Choisir au minimum un SSD de 256 Go et surveiller l'espace : les images intermédiaires Blender
  peuvent être volumineuses. Ajouter plus tard un SSD USB si une grande réserve de vidéos est gardée.
- Vérifier chaque semaine les journaux et les publications ; une automatisation ne garantit ni la
  viralité ni l'absence de changement dans les interfaces TikTok/YouTube.
