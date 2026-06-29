#!/usr/bin/env bash
set -euo pipefail

E3D_DIR="/Users/mini/clawd/e3d"
CONFIG="/Users/mini/e3d-maps/training/train_config_story_v1_7b.yaml"
ADAPTER_DIR="${E3D_DIR}/adapters_story_v1"
STAGING_DIR="${E3D_DIR}/adapters_story_v1.new"
RUNS_LOG="/Users/mini/e3d-maps/training_runs.jsonl"
START_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
START_EPOCH=$(date +%s)

log() {
  printf "[%s] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

cd "${E3D_DIR}"
source .venv/bin/activate

log "=== Story Adapter 7B Training ==="
log "Config: ${CONFIG}"
log "Adapter staging dir: ${STAGING_DIR}"

if [[ -d "${STAGING_DIR}" ]]; then
  log "Removing stale staging dir..."
  rm -rf "${STAGING_DIR}"
fi

TRAIN_LINES=$(wc -l < data/train.jsonl | tr -d ' ')
VALID_LINES=$(wc -l < data/valid.jsonl | tr -d ' ')
TEST_LINES=$(wc -l < data/test.jsonl | tr -d ' ')
log "Examples - train: ${TRAIN_LINES}, valid: ${VALID_LINES}, test: ${TEST_LINES}"

mlx_lm.lora --config "${CONFIG}"

log "Running test evaluation..."
EVAL_OUTPUT=$(mlx_lm.lora --config "${CONFIG}" --test 2>&1)
printf "%s\n" "${EVAL_OUTPUT}"

NEW_LOSS=$(printf "%s" "${EVAL_OUTPUT}" | grep -i "test loss" | grep -oE "[0-9]+\.[0-9]+" | head -1 || true)
if [[ -z "${NEW_LOSS}" ]]; then
  log "WARNING: Could not parse test loss."
  NEW_LOSS="null"
fi

if [[ -d "${ADAPTER_DIR}" ]]; then
  BACKUP_DIR="${ADAPTER_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
  log "Renaming current adapter to ${BACKUP_DIR}"
  mv "${ADAPTER_DIR}" "${BACKUP_DIR}"
fi

log "Promoting ${STAGING_DIR} -> ${ADAPTER_DIR}"
mv "${STAGING_DIR}" "${ADAPTER_DIR}"

END_EPOCH=$(date +%s)
DURATION=$(( END_EPOCH - START_EPOCH ))
ENTRY=$(python3 -c "
import json
print(json.dumps({
  'ts': '${START_TS}',
  'agent': 'story',
  'adapter_version': 'story_v1_7b_$(date +%Y%m%d)',
  'eval_loss': float('${NEW_LOSS}') if '${NEW_LOSS}' != 'null' else None,
  'examples_train': ${TRAIN_LINES},
  'examples_valid': ${VALID_LINES},
  'examples_test': ${TEST_LINES},
  'duration_sec': ${DURATION},
  'status': 'ok'
}))
")
printf "%s\n" "${ENTRY}" >> "${RUNS_LOG}"
log "Training metadata written to ${RUNS_LOG}"
log "Story 7B adapter training complete."
