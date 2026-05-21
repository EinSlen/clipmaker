# Deploy sur Render.com (gratuit)

> Pré-requis : `git push origin main` doit avoir poussé ce commit sur https://github.com/EinSlen/clipmaker

## Setup (5 min, 100% gratuit, sans carte)

1. Va sur https://render.com/register
   - clique « **GitHub** » (OAuth — obligatoire car le repo est privé)
   - sur la page GitHub d'autorisation, autorise Render à voir
     `EinSlen/clipmaker` (option « Only select repositories » → coche-le)

2. Dans le dashboard Render : **New +** → **Blueprint**
   - **Connect a repository** → choisis `EinSlen/clipmaker`
   - Render détecte le `render.yaml` à la racine
   - **Apply** → ça crée le service `clipmaker-sad`

3. **Configure les secrets** (Render demande les valeurs des envVars `sync: false`)
   - `GROQ_API_KEY` = ta clé Groq
   - `ANTHROPIC_API_KEY` = laisse vide

4. Le build démarre automatiquement (≈ 5-8 min la première fois).
   URL finale : `https://clipmaker-sad.onrender.com`

## Comportement free tier

- Le service s'endort après **15 min sans trafic**.
- Première requête après endormissement : ~30 s de cold start.
- Pas de stockage persistant — le cache musique se reconstruit auto au réveil.
- 750 h/mois de runtime (largement plus qu'un mois si tu l'utilises actif).

## Auto-redeploy

Le `autoDeploy: true` du `render.yaml` fait que tout `git push origin main`
relance un build. Pratique pour itérer.

## Limitations sur free tier Render

- Pas de mode "Publier auto" via cookies TikTok (pas de Chromium dans l'image).
  → Utilise « Partager → TikTok » depuis le tel (Web Share API), c'est conçu pour ça.
- RAM 512 MB : si une vidéo lourde fait OOM au rendu, soit tu la coupes avant
  upload, soit tu passes à un plan payant (~$7/mois pour 2 GB RAM).
