# E3D Maps — Production Deployment Guide

Target machine: `/Users/mini/clawd/` (macOS, existing E3D stack)

Prerequisites already running on this machine:
- Qwen MLX server on port 5050
- ClickHouse on port 8123
- spacepacket (e3d) Express server via PM2
- nginx with TLS termination

---

## Step 1 — Clone e3d-maps

```bash
cd /Users/mini/clawd
git clone https://github.com/spacepacket1/e3d-maps.git
cd e3d-maps
```

---

## Step 2 — Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Verify the install:

```bash
python -c "import agents, schemas, jobs; print('OK')"
```

---

## Step 3 — Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set the values for this machine:

```ini
# Qwen (already running on 5050 — leave default unless port differs)
LLM_BASE_URL=http://127.0.0.1:5050
LLM_MODEL=mlx-community/Qwen2.5-14B-Instruct-4bit
QWEN_API_KEY=

# Adapter — set the absolute path once training has produced one.
# Leave empty on first deploy to run the base model.
MAPS_ADAPTER_PATH=
MAPS_ADAPTER_NAME=base-v0
MAPS_ENABLE_ADAPTER_LOADING=false

# E3D API — use the production URL and a service key
E3D_BASE_URL=https://e3d.ai
E3D_API_KEY=<production-api-key>

# ClickHouse — defaults work for local single-node setup
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_DATABASE=default
CLICKHOUSE_USERNAME=default
CLICKHOUSE_PASSWORD=
CLICKHOUSE_SECURE=false

# Runner cadences (seconds) — keep spec defaults unless load dictates change
MAPS_RUNNER_INTERVAL_SECONDS=300

# Set to production
MAPS_ENV=production
```

---

## Step 4 — Run ClickHouse migrations

```bash
source .venv/bin/activate

# Apply all migration files in order
for f in db/migrations/*.sql; do
  echo "==> $f"
  cat "$f" | curl -s --data-binary @- \
    "http://localhost:8123/?user=default&password="
done
```

Verify the tables exist:

```bash
curl -s "http://localhost:8123/?query=SHOW+TABLES" | tr ',' '\n'
# Expected: NavigationSignals, RoutePredictions, TrafficStates,
#           PredictionOutcomes, SignalUtilityScores, StoryTypeDefinitions
```

---

## Step 5 — Seed story types

```bash
source .venv/bin/activate
python db/seed_story_types.py
```

Verify:

```bash
curl -s "http://localhost:8123/?query=SELECT+count(*)+FROM+StoryTypeDefinitions"
# Should return a positive integer
```

---

## Step 6 — Dry-run the runner

```bash
source .venv/bin/activate
python agents/runner.py --once --dry-run
```

Expected output: runner completes without errors. No DB writes in dry-run mode.

---

## Step 7 — Update and restart spacepacket

Pull the new code (the Maps API routes are already in the repo):

```bash
cd /Users/mini/clawd/e3d
git pull origin master
npm install  # only needed if package.json changed
pm2 restart spacepacket
```

Verify the new routes are live:

```bash
curl -s http://localhost:3001/api/maps/state
# {"status":"not_found","error":"state_not_found"}  — expected before first run

curl -s http://localhost:3001/api/story-types | python3 -m json.tool | head -20
# Should list story type objects
```

---

## Step 8 — Build and deploy the Maps UI

```bash
cd /Users/mini/clawd/e3d-maps

# Build (copies ui/src + index.html to ui/dist/)
node ui/build.mjs

# Deploy to nginx document root
sudo mkdir -p /var/www/maps.e3d.ai/html
sudo cp -r ui/dist/. /var/www/maps.e3d.ai/html/
sudo chown -R www-data:www-data /var/www/maps.e3d.ai/html 2>/dev/null || true
```

---

## Step 9 — nginx configuration

The nginx config change is already committed to the e3d repo (maps.e3d.ai server block). Pull it:

```bash
cd /Users/mini/clawd/e3d
git pull origin master  # (already done above — skip if fresh)
```

Copy the config into place and reload:

```bash
sudo cp nginx/default /etc/nginx/sites-enabled/default
sudo nginx -t  # must say "syntax is ok" before proceeding
sudo systemctl reload nginx
```

---

## Step 10 — TLS certificate for maps.e3d.ai

Obtain a Let's Encrypt certificate. The nginx config expects:

```
/etc/letsencrypt/live/maps.e3d.ai/fullchain.pem
/etc/letsencrypt/live/maps.e3d.ai/privkey.pem
```

Run certbot (nginx plugin handles the ACME challenge automatically):

```bash
sudo certbot --nginx -d maps.e3d.ai --non-interactive --agree-tos \
  -m spacepacket@gmail.com
```

After cert issuance, reload nginx again:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

Verify HTTPS:

```bash
curl -s https://maps.e3d.ai/api/story-types | python3 -m json.tool | head -10
```

---

## Step 11 — Start the Maps runner via launchd

A launchd plist is included at `deploy/ai.e3d.maps-runner.plist`.

The plist embeds the ClickHouse credentials and Qwen URL directly.
Update those values if they change, then install:

```bash
# Install into user LaunchAgents (runs at login, no sudo needed)
cp /Users/mini/e3d-maps/deploy/ai.e3d.maps-runner.plist \
   ~/Library/LaunchAgents/ai.e3d.maps-runner.plist

# Load and start immediately
launchctl load ~/Library/LaunchAgents/ai.e3d.maps-runner.plist
```

Check the runner is healthy:

```bash
launchctl list | grep e3d
# Should show ai.e3d.maps-runner with a PID (not just a status code)

tail -f /Users/mini/e3d-maps/deploy/logs/maps-runner.log
# Should see scheduler tick messages, no tracebacks
```

---

## Step 12 — Post-deploy verification

After the first full scheduler tick (up to 5 minutes):

```bash
# NavigationSignals should start appearing
curl -s "http://localhost:3001/api/maps/signals?limit=5" | python3 -m json.tool

# TrafficState should update
curl -s http://localhost:3001/api/maps/state | python3 -m json.tool

# Public HTTPS check
curl -s https://maps.e3d.ai/api/maps/signals?limit=1
```

PM2 process status:

```bash
pm2 status
# e3d-maps-runner should show status: online, restarts: 0
```

---

## Ongoing operations

**View runner logs:**
```bash
tail -f /Users/mini/e3d-maps/deploy/logs/maps-runner.log
tail -f /Users/mini/e3d-maps/deploy/logs/maps-runner.err
```

**Restart runner after a code update:**
```bash
cd /Users/mini/e3d-maps
git pull origin main
launchctl unload ~/Library/LaunchAgents/ai.e3d.maps-runner.plist
launchctl load  ~/Library/LaunchAgents/ai.e3d.maps-runner.plist
```

**Run backtest manually:**
```bash
source .venv/bin/activate
python jobs/backtest_navigation_predictions.py --output /tmp/backtest_report.json
cat /tmp/backtest_report.json | python3 -m json.tool
```

**Train the Maps adapter** (after enough PredictionOutcomes have accumulated):
```bash
bash training/train_maps_adapter.sh
```

Then update `.env`:
```ini
MAPS_ADAPTER_PATH=/Users/mini/clawd/e3d-maps/adapters_maps_v1
```

And restart the runner:
```bash
pm2 restart e3d-maps-runner
```
