#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f web/.env.local ]; then
  cp web/.env.example web/.env.local
  token="$(openssl rand -hex 32)"
  sed -i "s/^CLIPMAKER_UPLOAD_TOKEN=.*/CLIPMAKER_UPLOAD_TOKEN=$token/" web/.env.local
fi

admin_token="$(sed -n 's/^CLIPMAKER_UPLOAD_TOKEN=//p' web/.env.local | head -n 1)"
if [ -z "$admin_token" ]; then
  admin_token="$(openssl rand -hex 32)"
  sed -i "s/^CLIPMAKER_UPLOAD_TOKEN=.*/CLIPMAKER_UPLOAD_TOKEN=$admin_token/" web/.env.local
fi

docker compose --profile tiktok-auth up -d --build clipmaker tiktok-auth

echo "ClipMaker est disponible sur le port privé 3000."
echo "Clé admin à coller dans Studio de jeux > Automatisation > Clé admin : $admin_token"
