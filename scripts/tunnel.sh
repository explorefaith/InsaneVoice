#!/usr/bin/env bash
# Start a public HTTPS tunnel to the local engine and point the website at it.
# After this, insanevoice.vercel.app connects from phones/anywhere (while this
# machine stays on and this script keeps running).
#
# Requires: cloudflared on PATH, engine running on 127.0.0.1:8177, git push access.
# The trycloudflare URL changes on every restart — run this script again then.
set -euo pipefail
cd "$(dirname "$0")/.."
JSON="frontend/engine.json"

command -v cloudflared >/dev/null || { echo "install cloudflared first"; exit 1; }
curl -s -m 3 http://127.0.0.1:8177/api/system >/dev/null || { echo "engine not running on 8177"; exit 1; }

cloudflared tunnel --url http://127.0.0.1:8177 > /tmp/iv_tunnel.log 2>&1 &
TPID=$!
trap 'kill $TPID 2>/dev/null || true' EXIT

URL=""
for _ in $(seq 1 30); do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/iv_tunnel.log | head -1 || true)
  [ -n "$URL" ] && break
  sleep 1
done
[ -z "$URL" ] && { echo "tunnel failed:"; tail -5 /tmp/iv_tunnel.log; exit 1; }
echo "Tunnel:  $URL"
echo "Engine:  http://127.0.0.1:8177"

cat > "$JSON" <<EOF
{
  "engineUrl": "$URL",
  "updated": "$(date -u +%FT%TZ)"
}
EOF
git add "$JSON"
git commit -m "chore: publish engine tunnel URL -> $URL" >/dev/null
git push origin main >/dev/null
echo "Published to the website — Vercel redeploys in ~1 min."
echo "Keep this running (Ctrl+C stops the tunnel)."
wait $TPID
