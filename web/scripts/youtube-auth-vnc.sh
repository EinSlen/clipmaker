#!/usr/bin/env bash
set -euo pipefail

export DISPLAY="${DISPLAY:-:99}"
export YOUTUBE_BROWSER_PATH="${YOUTUBE_BROWSER_PATH:-/usr/bin/chromium}"
export YOUTUBE_BROWSER_DATA_DIR="${YOUTUBE_BROWSER_DATA_DIR:-/repo/.youtube-browser}"
YOUTUBE_ACCOUNT="${YOUTUBE_ACCOUNT:-default}"
AUTH_REQUEST_FILE="${AUTH_REQUEST_FILE:-/repo/web/data/auth/youtube-request.txt}"

mkdir -p "$YOUTUBE_BROWSER_DATA_DIR"

cleanup() {
  jobs -pr | xargs -r kill 2>/dev/null || true
}
trap cleanup EXIT INT TERM

Xvfb "$DISPLAY" -screen 0 1365x768x24 -nolisten tcp >/tmp/clipmaker-xvfb.log 2>&1 &
sleep 1
openbox-session >/tmp/clipmaker-openbox.log 2>&1 &
x11vnc -display "$DISPLAY" -forever -shared -nopw -localhost -rfbport 5900 >/tmp/clipmaker-x11vnc.log 2>&1 &
websockify --web=/usr/share/novnc 6080 localhost:5900 >/tmp/clipmaker-websockify.log 2>&1 &

echo "Connexion YouTube prête via noVNC sur http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale"
echo "Sur un VPS, ouvre d'abord un tunnel SSH : ssh -L 6080:127.0.0.1:6080 utilisateur@vps"

mkdir -p "$(dirname "$AUTH_REQUEST_FILE")"
initial_request="startup|${YOUTUBE_ACCOUNT}"
last_request=""

while true; do
  request="$initial_request"
  if [[ -s "$AUTH_REQUEST_FILE" ]]; then
    request="$(head -n 1 "$AUTH_REQUEST_FILE" | tr -d '\r\n')"
  fi
  if [[ -n "$request" && "$request" != "$last_request" ]]; then
    last_request="$request"
    account="${request#*|}"
    if [[ "$account" =~ ^[a-z0-9][a-z0-9_-]{0,31}$ ]]; then
      account_root="$YOUTUBE_BROWSER_DATA_DIR"
      if [[ "$account" != "default" ]]; then
        account_root="$YOUTUBE_BROWSER_DATA_DIR/accounts/$account"
      fi
      rm -f -- \
        "$account_root/auth-profile-linux/SingletonCookie" \
        "$account_root/auth-profile-linux/SingletonLock" \
        "$account_root/auth-profile-linux/SingletonSocket"
      echo "Ouverture de la connexion YouTube pour le profil ${account}."
      YOUTUBE_ACCOUNT="$account" node scripts/youtube-agent.mjs auth \
        || echo "Connexion YouTube interrompue pour ${account}; relance-la depuis ClipMaker." >&2
    fi
    initial_request=""
  fi
  sleep 2
done
