#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="/Users/mini/e3d-maps/deploy/logs"
RUN_DIR="/Users/mini/e3d-maps/deploy/run"
mkdir -p "$LOG_DIR" "$RUN_DIR"

QWEN_HEALTH_URL="${QWEN_HEALTH_URL:-http://127.0.0.1:5050/health}"
WINDOW_STATE="$RUN_DIR/qwen_adapter_window.state"
NODE_BIN="${NODE_BIN:-/opt/homebrew/bin/node}"

SCOUT_ADAPTER_PATH="${SCOUT_ADAPTER_PATH:-/Users/mini/clawd/e3d/adapters_scout_v1}"
HARVEST_ADAPTER_PATH="${HARVEST_ADAPTER_PATH:-/Users/mini/clawd/e3d/adapters_harvest_v1}"
MAPS_ADAPTER_PATH="${MAPS_ADAPTER_PATH:-/Users/mini/clawd/e3d/adapters_maps_v1}"
STORY_ADAPTER_PATH="${STORY_ADAPTER_PATH:-/Users/mini/clawd/e3d/adapters_story_v1}"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*"
}

wait_for_qwen() {
  local deadline=$(( $(date +%s) + 300 ))
  while (( $(date +%s) < deadline )); do
    if curl -sS --max-time 30 "$QWEN_HEALTH_URL" >/dev/null 2>&1; then
      return 0
    fi
    sleep 10
  done
  log "WARNING: Qwen health check did not return before deadline; continuing anyway."
}

mark_key() {
  local phase="$1"
  date '+%Y%m%d%H'"-$phase"
}

already_ran() {
  local key="$1"
  [[ -f "$WINDOW_STATE" ]] && grep -qx "$key" "$WINDOW_STATE"
}

record_ran() {
  local key="$1"
  printf '%s\n' "$key" >> "$WINDOW_STATE"
  tail -n 96 "$WINDOW_STATE" > "$WINDOW_STATE.tmp"
  mv "$WINDOW_STATE.tmp" "$WINDOW_STATE"
}

run_trading_window() {
  local key
  key="$(mark_key trading)"
  if already_ran "$key"; then
    return 0
  fi
  log "window trading start: scout adapter then harvest adapter"
  wait_for_qwen
  (
    cd /Users/mini/e3d-agent-trading-floor
    export LLM_BASE_URL="${LLM_BASE_URL:-http://127.0.0.1:5050}"
    export LLM_MODEL="${LLM_MODEL:-mlx-community/Qwen2.5-7B-Instruct-4bit}"
    export LLM_TOOL_USE_OVERRIDE="${LLM_TOOL_USE_OVERRIDE:-0}"
    export SCOUT_ADAPTER_PATH
    export HARVEST_ADAPTER_PATH
    "$NODE_BIN" pipeline.js --once
  )
  record_ran "$key"
  log "window trading end"
}

run_maps_window() {
  local key
  key="$(mark_key maps)"
  if already_ran "$key"; then
    return 0
  fi
  log "window maps start: maps adapter"
  wait_for_qwen
  (
    cd /Users/mini/e3d-maps
    set -a
    [[ -f deploy/ai.e3d.maps-runner.env ]] && source deploy/ai.e3d.maps-runner.env
    set +a
    export MAPS_ADAPTER_PATH
    export MAPS_ADAPTER_NAME="${MAPS_ADAPTER_NAME:-maps-v0.1}"
    /opt/homebrew/bin/python3 -m agents.scheduler --once
  )
  record_ran "$key"
  log "window maps end"
}

run_story_window() {
  local key
  key="$(mark_key story)"
  if already_ran "$key"; then
    return 0
  fi
  log "window story start: story adapter"
  wait_for_qwen
  (
    cd /Users/mini/e3d/buildDB
    set -a
    [[ -f .env ]] && source .env
    set +a
    export LLM_PROVIDER=local
    export LOCAL_MODEL_URL="${LOCAL_MODEL_URL:-http://127.0.0.1:5050}"
    export STORY_ADAPTER_PATH
    export STORY_ENRICH_LIMIT="${STORY_ENRICH_LIMIT:-5}"
    export INTER_STORY_DELAY_MS="${INTER_STORY_DELAY_MS:-5000}"
    "$NODE_BIN" storyEnrichAI.js --limit "$STORY_ENRICH_LIMIT"
  )
  record_ran "$key"
  log "window story end"
}

log "qwen adapter window runner started"

while true; do
  minute="$(date '+%M')"
  minute=$((10#$minute))

  if (( minute < 16 )); then
    run_trading_window || log "ERROR: trading window failed"
    sleep 60
  elif (( minute < 34 )); then
    run_maps_window || log "ERROR: maps window failed"
    sleep 60
  elif (( minute < 58 )); then
    run_story_window || log "ERROR: story window failed"
    sleep 60
  else
    log "buffer window"
    sleep 60
  fi
done
