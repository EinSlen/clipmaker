---
title: clipMaker — Sad / Philo TikTok Studio
emoji: 🎬
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: TikTok sad/philo studio — texte + musique trending
---

# clipMaker

Mini-studio mobile pour faire des TikTok tristes/philosophiques :

- importe une vidéo ou prends-en une sur YouTube
- ajoute du texte au style @u.s.e.r.0.0.46 (généré par Groq, gratuit)
- choisis la vibe → l'app télécharge auto les sons tristes tendance TikTok
- bouton « Partager → TikTok » qui ouvre la share sheet du téléphone

## Variables d'environnement à configurer dans Settings → Variables and secrets

- `GROQ_API_KEY` (recommandé, gratuit sur https://console.groq.com/keys) — sinon fallback textes intégrés
- `ANTHROPIC_API_KEY` (optionnel, premium override)

Repo source : https://github.com/EinSlen/clipMaker
