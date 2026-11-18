#!/usr/bin/env bash
# systemd entrypoint: start a trycloudflare tunnel to the local engine and
# publish its URL to frontend/engine.json (git commit + push) so the hosted
# website auto-connects from phones/anywhere. URL changes on every restart;
# the service reruns this script, so the site follows automatically.
set -euo pipefail
cd "$(dirname "$0")/.."
JSON="frontend/engine.json"
CF=/home/explorearafat/.local/bin/cloudflared

curl -s -m 3 http://127.0.0.1:8177/api/system >/dev/null || { echo "engine not up yet"; exit 1; }

"$CF" tunnel --url http://127.0.0.1:8177 > /tmp/iv_tunnel.log 2>&1 &
TPID=$!
trap 'kill $TPID 2>/dev/null || true' EXIT

URL=""
for _ in $(seq 1 45); do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/iv_tunnel.log | head -1 || true)
  [ -n "$URL" ] && break
  sleep 1
done
[ -z "$URL" ] && { echo "tunnel failed:"; tail -5 /tmp/iv_tunnel.log; exit 1; }
echo "[iv-tunnel] public URL: $URL"

OLD=$(python3 -c "import json;print(json.load(open('$JSON')).get('engineUrl',''))" 2>/dev/null || echo "")
if [ "$URL" != "$OLD" ]; then
  cat > "$JSON" <<EOF
{
  "engineUrl": "$URL",
  "updated": "$(date -u +%FT%TZ)"
}
EOF
  git add "$JSON"
  git -c user.name="InsaneVoice Tunnel" -c user.email="tunnel@faith-pc.local" \
    commit -m "chore: publish engine tunnel URL -> $URL" >/dev/null || true
  git push origin main >/dev/null 2>&1 || echo "[iv-tunnel] warning: git push failed (site keeps old URL)"
  echo "[iv-tunnel] published to website (Vercel redeploys ~1 min)"
else
  echo "[iv-tunnel] URL unchanged, site already up to date"
fi

wait $TPID
