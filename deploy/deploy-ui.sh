#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEBROOT="/var/www/maps.e3d.ai/html"
CF_ZONE_ID="48063a1832b14d80c6f38932a427a372"
CF_API_TOKEN="${CF_API_TOKEN:-cfut_Zw3Dg3rIRj4UkAbMtMcezVEXVHCgNARhz6riNWgc34aad0fe}"

echo "Building UI..."
node "$REPO_ROOT/ui/build.mjs"

echo "Deploying to $WEBROOT..."
sudo rsync -a --delete "$REPO_ROOT/ui/dist/" "$WEBROOT/"

echo "Purging Cloudflare cache..."
curl -sf -X POST "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/purge_cache" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"purge_everything":true}' | grep -q '"success":true'

echo "Done. maps.e3d.ai is live."
