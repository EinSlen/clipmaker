# Machine recommandée et installation Linux

## Choix recommandé

Pour faire tourner **toute** la chaîne sur une seule petite machine, y compris Soft Body 3D, le
meilleur compromis compact est actuellement un **MINISFORUM AtomMan G7 Ti, Core i9-14900HX,
GeForce RTX 4070 Laptop, 32 Go de RAM et SSD NVMe 1 To**. La page constructeur annonce un GPU
jusqu'à 140 W, jusqu'à 96 Go de RAM et affiche 1 279 USD au 15 août 2026 ; le prix et le stock
français peuvent différer : <https://www.minisforum.com/fr/products/atomman-g7-ti-g7-ti-se>.

Prendre l'adaptateur UE/FR et la version 32 Go + 1 To. Si ce modèle dépasse environ 1 600–1 700 €,
un petit PC tour avec une RTX 5070 de bureau, 32 Go de RAM et 1 To de SSD offre généralement un
meilleur rapport performance/prix et sera plus facile à réparer.

Alternative plus récente et plus chère : **ASUS NUC 15 Performance, RTX 5060 ou 5070, 32 Go,
1 To**. ASUS le destine explicitement à la création et au rendu 3D dans un boîtier de 3 litres :
<https://www.asus.com/fr/displays-desktops/nucs/nuc-kits/asus-nuc-15-performance/>.

## Pourquoi pas un Raspberry Pi 5

Le Raspberry Pi 5 est excellent pour un petit serveur, mais sa puce est un Cortex-A76 Arm à quatre
cœurs avec un GPU VideoCore VII et au maximum 16 Go de RAM. Il peut héberger un planificateur ou
envoyer des fichiers, mais le rendu Blender natif 1080×1920/30 i/s de Soft Body serait beaucoup trop
lent et le chemin TikTok/Chromium Arm n'est pas couvert par nos tests. Caractéristiques officielles :
<https://www.raspberrypi.com/products/raspberry-pi-5/>.

Un Raspberry Pi peut servir plus tard de contrôleur basse consommation si les rendus sont produits
sur une autre machine. Pour le déploiement tout-en-un demandé ici, choisir un mini-PC x86 avec NVIDIA.

## Installation recommandée

Installer **Ubuntu Server 24.04 LTS** sur le mini-PC, avec OpenSSH, puis connecter la machine en
Ethernet. Dans les commandes suivantes, le dépôt est installé dans `/opt/clipmaker`.

### 1. Pilote, Docker et GPU

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt install -y git curl ca-certificates ubuntu-drivers-common
sudo ubuntu-drivers install
sudo reboot
```

Après le redémarrage, `nvidia-smi` doit afficher la carte. Installer ensuite Docker Engine depuis
<https://docs.docker.com/engine/install/ubuntu/>, puis le NVIDIA Container Toolkit en suivant
<https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html>.

Configuration du runtime NVIDIA :

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
sudo docker run --rm --gpus all nvidia/cuda:12.6.2-base-ubuntu24.04 nvidia-smi
```

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

Construire et démarrer avec l'accès GPU :

```bash
docker compose -f docker-compose.yml -f infra/docker/compose.gpu.yml build clipmaker
docker compose -f docker-compose.yml -f infra/docker/compose.gpu.yml up -d clipmaker
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
docker compose -f docker-compose.yml -f infra/docker/compose.gpu.yml \
  --profile publisher up -d
```

## Exploitation 24/7

- Brancher la machine en Ethernet et activer le redémarrage après coupure dans l'UEFI.
- Ajouter un petit onduleur si les coupures sont fréquentes.
- Sauvegarder `.youtube-browser/`, `vendor/TiktokAutoUploader/CookiesDir/` et
  `web/data/publisher/` sur un support chiffré.
- Garder au moins 150 Go libres : les images intermédiaires Blender peuvent être volumineuses.
- Vérifier chaque semaine les journaux et les publications ; une automatisation ne garantit ni la
  viralité ni l'absence de changement dans les interfaces TikTok/YouTube.
