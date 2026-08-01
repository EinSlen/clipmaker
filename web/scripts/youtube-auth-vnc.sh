#!/usr/bin/env bash
set -euo pipefail

export DISPLAY="${DISPLAY:-:99}"
export YOUTUBE_BROWSER_PATH="${YOUTUBE_BROWSER_PATH:-/usr/bin/chromium}"
export YOUTUBE_BROWSER_DATA_DIR="${YOUTUBE_BROWSER_DATA_DIR:-/repo/.youtube-browser}"

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

node scripts/youtube-agent.mjs auth
