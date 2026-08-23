#!/usr/bin/env bash
set -euo pipefail

export DISPLAY="${DISPLAY:-:99}"
TIKTOK_USERNAME="${TIKTOK_USERNAME:-}"
AUTH_PUBLIC_PORT="${AUTH_PUBLIC_PORT:-6081}"
AUTH_REQUEST_FILE="${AUTH_REQUEST_FILE:-/repo/web/data/auth/tiktok-request.txt}"

cleanup() {
  jobs -pr | xargs -r kill 2>/dev/null || true
}
trap cleanup EXIT INT TERM

Xvfb "$DISPLAY" -screen 0 1365x768x24 -nolisten tcp >/tmp/clipmaker-xvfb.log 2>&1 &
sleep 1
openbox-session >/tmp/clipmaker-openbox.log 2>&1 &
x11vnc -display "$DISPLAY" -forever -shared -nopw -localhost -rfbport 5900 >/tmp/clipmaker-x11vnc.log 2>&1 &
websockify --web=/usr/share/novnc 6080 localhost:5900 >/tmp/clipmaker-websockify.log 2>&1 &

echo "Connexion TikTok prête via noVNC sur http://127.0.0.1:${AUTH_PUBLIC_PORT}/vnc.html?autoconnect=true&resize=scale"
echo "Sur un serveur distant : ssh -L ${AUTH_PUBLIC_PORT}:127.0.0.1:${AUTH_PUBLIC_PORT} utilisateur@serveur"

mkdir -p "$(dirname "$AUTH_REQUEST_FILE")"
initial_request=""
if [[ "$TIKTOK_USERNAME" =~ ^[A-Za-z0-9._]{2,32}$ ]]; then
  initial_request="startup|${TIKTOK_USERNAME}"
fi
last_request=""

while true; do
  request="$initial_request"
  if [[ -s "$AUTH_REQUEST_FILE" ]]; then
    request="$(head -n 1 "$AUTH_REQUEST_FILE" | tr -d '\r\n')"
  fi
  if [[ -n "$request" && "$request" != "$last_request" ]]; then
    last_request="$request"
    username="${request#*|}"
    if [[ "$username" =~ ^[A-Za-z0-9._]{2,32}$ ]]; then
      echo "Ouverture de la connexion TikTok pour @${username}."
      (cd /repo/vendor/TiktokAutoUploader && python3 cli.py login -n "$username") \
        || echo "Connexion TikTok interrompue pour @${username}; relance-la depuis ClipMaker." >&2
    fi
    initial_request=""
  fi
  sleep 2
done
