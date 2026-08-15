# Application web ClipMaker

Application Next.js 16 qui regroupe le studio, les moteurs de rendu, la bibliothèque, les connexions
TikTok/YouTube et l'orchestrateur quotidien.

## Développement

```bash
cp .env.example .env.local
npm ci
npm run dev
```

L'application est disponible sur <http://127.0.0.1:3000>.

## Répertoires

```text
src/app/          pages et routes API
src/components/   composants React
src/lib/          services de rendu et publication
src/automation/   configuration, état, planification et client API
scripts/          moteurs Python, upload YouTube et CLI publisher
config/           configuration d'exemple non sensible
public/           aperçus et médias statiques
uploads/          sources locales ignorées par Git
renders/          sorties locales ignorées par Git
```

## Commandes

```bash
npm test
npm run build
npm run test:render-smoke
npm run publisher:doctor -- --config config/publisher.json
npm run publisher:status -- --config config/publisher.json
```

Voir le [README racine](../README.md) pour l'architecture et le démarrage Docker.
