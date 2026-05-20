# clipMaker · studio sad/philo TikTok

App Next.js mobile-first pour fabriquer des TikTok dans le style des comptes mélancoliques type
[@u.s.e.r.0.0.46](https://www.tiktok.com/@u.s.e.r.0.0.46). Tu importes une vidéo (ou tu en piques une
sur YouTube), tu ajoutes du texte philosophique, tu choisis le **son triste tendance TikTok**, et tu
publies — directement depuis l'app TikTok via la share sheet de ton téléphone, ou en auto via les
cookies enregistrés côté serveur.

## Ce qui est inclus

- **Import** vidéo (drop + caméra mobile) → enregistrée côté serveur + bibliothèque IndexedDB.
- **Suggestions YouTube** centrées sur des personnes dans des scènes tristes/mélancoliques
  (vibes *sad / philo / rupture / solitude / anime*). Import direct → bibliothèque.
- **Textes générés par Groq** (LLM gratuit — llama 3.3 70B). Tone calqué sur le compte cible :
  1-3 lignes, intime, doux-amer, sans emoji ni morale. Fallback de 20 textes intégrés si pas de clé.
- **Hashtags** auto-régénérables, sélectionnables, copiables.
- **Musique triste tendance TikTok auto-téléchargée par vibe** : tu choisis Triste / Rupture /
  Solitude / Nostalgie / Philo / Tendance — l'app télécharge automatiquement les meilleurs sons
  TikTok trending de YouTube (via yt-dlp) dans `public/music/<vibe>/`. Bouton « re-pull » pour
  rafraîchir.
- **Publication** : deux modes
  1. **Partager → TikTok** (mobile) : ouvre la share sheet du téléphone, la vidéo file dans l'app
     TikTok, tu ajoutes le texte et tu publies. Pas de cookies, pas de Selenium, pas de blocage.
  2. **Publier auto** (desktop ou serveur) : sélecteur multi-comptes basé sur
     `vendor/TiktokAutoUploader/CookiesDir/`. Bouton pour connecter un nouveau compte.

## Prérequis (self-host)

- Node 18+ et npm
- Python 3.10+ (pour le vendor `TiktokAutoUploader`)
- `ffmpeg` et `ffprobe` dans le PATH
- `yt-dlp` dans le PATH

## Accéder depuis ton téléphone (sans Docker) — **option recommandée**

Un script tout-en-un récupère `cloudflared.exe`, build l'app, démarre le serveur, et expose
une URL HTTPS publique :

```powershell
cd web
pwsh ./start-tunnel.ps1
```

Sortie :
```
2026-05-… INF +-----------------------------------------------+
2026-05-… INF |  https://your-random-words.trycloudflare.com  |
2026-05-… INF +-----------------------------------------------+
```

Tu colles cette URL dans le navigateur de ton téléphone (où que tu sois — 4G ou Wi-Fi).
L'URL change à chaque démarrage. Ctrl+C tue Next.js + le tunnel.

## Déploiement permanent (Fly.io, gratuit)

Pour une URL stable accessible H24 sans laisser ton PC allumé :

```bash
# Une seule fois
curl -L https://fly.io/install.sh | sh
fly auth signup  # ou login

# Depuis la racine du dépôt :
fly launch --no-deploy --copy-config --name clipmaker-sad
fly volumes create clipmaker_data --size 3 --region cdg
fly secrets set GROQ_API_KEY=...  ANTHROPIC_API_KEY=...
fly deploy
```

Le `Dockerfile.fly` est déjà préparé (Node + ffmpeg + yt-dlp + python). Le volume persistant
stocke `uploads/`, `renders/`, `public/music/`. Free tier Fly.io : 3 petites VM + 3 GB de volume.

## Install local (sans Docker, sans tunnel)

```bash
cd web
npm install
cp .env.example .env.local
# colle ta clé Groq (gratuite)
npm run dev -- -H 0.0.0.0
```
Ouvre `http://<ip-de-ton-pc>:3000` depuis ton tel sur le même Wi-Fi.

## LLM gratuit (Groq)

1. Crée une clé sur https://console.groq.com/keys (gratuit, pas de carte).
2. `GROQ_API_KEY=...` dans `web/.env.local` (ou `.env`).
3. Modèle par défaut : `llama-3.3-70b-versatile` (excellent en français). Modifiable via `GROQ_MODEL`.

Si tu mets aussi `ANTHROPIC_API_KEY`, il prend la priorité (Claude Haiku — qualité premium).

## Musique : tendance TikTok auto-fetch

Tu n'as **rien à uploader**. L'app utilise `data/music-sources.json` qui contient des recherches
YouTube ciblées « sad tiktok trending sound 2025 » etc. par vibe. Au premier choix d'une vibe sans
fichiers, elle télécharge les meilleurs résultats dans `public/music/<vibe>/`. Bouton « re-pull »
dans le picker pour rafraîchir une vibe (purge l'ancien lot et re-télécharge).

Tu peux toujours déposer manuellement tes propres `.mp3` dans `public/music/` ou les déclarer dans
`data/music.json` (ils prennent le pas sur les auto-fetchés).

## Comptes TikTok (mode auto-upload)

Le sélecteur lit `vendor/TiktokAutoUploader/CookiesDir/`. Pour ajouter un compte :
- soit clique « Ajouter un compte » dans l'éditeur (lance le login côté serveur),
- soit `cd vendor/TiktokAutoUploader && python cli.py login -n <username>`.

Note : ce mode requiert un Chromium côté serveur (déjà fourni dans le Dockerfile). En mobile, le
mode **Partage** est plus fiable et n'a pas besoin de ça.

## API

| Route | Méthode | Rôle |
|---|---|---|
| `/api/upload` | POST (multipart) | enregistre une vidéo dans `uploads/` |
| `/api/uploads/[file]` | GET | sert un fichier d'`uploads/` |
| `/api/render` | POST | rend la vidéo finale (texte + musique) dans `renders/` |
| `/api/renders/[file]` | GET | sert un fichier de `renders/` |
| `/api/ai/text` | POST | propositions de textes (Groq → Anthropic → fallback) |
| `/api/ai/hashtags` | POST | hashtags pertinents (Groq → Anthropic → fallback) |
| `/api/youtube/suggest` | POST | suggestions YouTube par vibe (`yt-dlp ytsearch`) |
| `/api/youtube/download` | POST | télécharge une vidéo YouTube dans `uploads/` |
| `/api/music/list` | GET `?vibe=` | liste les pistes (auto-fetch si vide pour la vibe) |
| `/api/music/fetch` | POST | (re)télécharge les sons tendance pour une vibe |
| `/api/tiktok/accounts` | GET / POST | liste les comptes / lance un login |
| `/api/tiktok/upload` | POST | publie sur TikTok via vendor (mode cookies) |

## Architecture

```
clipMaker/                         # dépôt
├─ main.py / motivation.py         # pipelines Python historiques
├─ music_helper.py                 # mix musique (partagé) avec web/public/music/
├─ vendor/TiktokAutoUploader/      # uploader cookies
├─ docker-compose.yml              # one-shot self-host (+ Cloudflare Tunnel)
└─ web/                            # app Next.js
   ├─ app/                         # pages + API routes
   ├─ components/                  # Preview, MusicPicker, AccountPicker, …
   ├─ lib/                         # llm, ffmpeg, music-fetcher, db (IndexedDB)
   ├─ data/
   │   ├─ music.json               # tracks manuels + libellés vibes
   │   └─ music-sources.json       # recherches YouTube par vibe (auto-fetch)
   ├─ public/music/                # bibliothèque locale (sous-dirs = vibe)
   ├─ uploads/                     # vidéos sources
   └─ renders/                     # vidéos rendues
```
