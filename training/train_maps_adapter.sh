#!/bin/bash
set -euo pipefail

# ─── Setup ───────────────────────────────────────────────────────────────────

E3D_DIR="/Users/mini/clawd/e3d"
MAPS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TRAIN_DIR="${MAPS_DIR}/training"
APP_PYTHON="${APP_PYTHON:-/opt/homebrew/bin/python3}"

cd "${E3D_DIR}"
source .venv/bin/activate
set -a
if [[ -f "${MAPS_DIR}/deploy/ai.e3d.maps-runner.env" ]]; then
  source "${MAPS_DIR}/deploy/ai.e3d.maps-runner.env"
fi
set +a

AGENT="maps"
CONFIG="${TRAIN_DIR}/train_config_maps_v1.yaml"
ADAPTER_DIR="adapters_maps_v1"
DATA_DIR="data/maps"
RUNS_LOG="${MAPS_DIR}/training_runs.jsonl"
START_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
START_EPOCH=$(date +%s)

log() {
  printf "[%s] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

log "=== Maps Adapter Training ==="
log "Working dir: $(pwd)"
log "Maps dir: ${MAPS_DIR}"
log "Start time: ${START_TS}"

# ─── Step 1: Export training data ────────────────────────────────────────────

log "Exporting Maps training examples..."
EXPORT_PATH="${TRAIN_DIR}/exports/maps_training_examples_$(date -u +%Y%m%d).jsonl"
PYTHONPATH="${MAPS_DIR}" "${APP_PYTHON}" "${MAPS_DIR}/jobs/export_training_examples.py" --output-path "${EXPORT_PATH}" --signal-limit 5000

log "Preparing MLX LoRA dataset..."
"${APP_PYTHON}" "${TRAIN_DIR}/prepare_maps_lora_data.py" \
  --input-dir "${TRAIN_DIR}/exports" \
  --output "${DATA_DIR}" \
  --min-accuracy "${MAPS_TRAIN_MIN_ACCURACY:-0.6}"

# ─── Step 2: Validate data files ─────────────────────────────────────────────

log "Checking training data..."
if [[ ! -f "${DATA_DIR}/train.jsonl" ]]; then
  log "WARNING: ${DATA_DIR}/train.jsonl not found. Cannot train without data."
  exit 0
fi

TRAIN_LINES=$(wc -l < "${DATA_DIR}/train.jsonl" | tr -d ' ')
if [[ "${TRAIN_LINES}" -lt 10 ]]; then
  log "WARNING: ${DATA_DIR}/train.jsonl has only ${TRAIN_LINES} lines (need at least 10). Skipping."
  exit 0
fi

VALID_LINES=0
TEST_LINES=0
[[ -f "${DATA_DIR}/valid.jsonl" ]] && VALID_LINES=$(wc -l < "${DATA_DIR}/valid.jsonl" | tr -d ' ')
[[ -f "${DATA_DIR}/test.jsonl" ]]  && TEST_LINES=$(wc -l  < "${DATA_DIR}/test.jsonl"  | tr -d ' ')

log "Examples — train: ${TRAIN_LINES}, valid: ${VALID_LINES}, test: ${TEST_LINES}"

# ─── Step 3: Prepare staging dir ─────────────────────────────────────────────

STAGING_DIR="${ADAPTER_DIR}.new"
STAGING_CONFIG="${TRAIN_DIR}/train_config_maps_v1.staging.yaml"

if [[ -d "${STAGING_DIR}" ]]; then
  log "Removing leftover staging dir ${STAGING_DIR} from a prior aborted run..."
  rm -rf "${STAGING_DIR}"
fi

sed "s|^adapter_path:.*|adapter_path: ./${STAGING_DIR}|" "${CONFIG}" > "${STAGING_CONFIG}"
log "Staging config: ${STAGING_CONFIG} (adapter_path -> ./${STAGING_DIR})"

# ─── Step 4: Train ───────────────────────────────────────────────────────────

log "Starting LoRA training with config: ${STAGING_CONFIG}..."
mlx_lm.lora --config "${STAGING_CONFIG}"
log "Training finished."

# ─── Step 5: Evaluate ────────────────────────────────────────────────────────

log "Running evaluation on test set..."
EVAL_OUTPUT=$(mlx_lm.lora --config "${STAGING_CONFIG}" --test 2>&1)
log "Eval output:"
printf "%s\n" "${EVAL_OUTPUT}"

NEW_LOSS=$(printf "%s" "${EVAL_OUTPUT}" | grep -i "test loss" | grep -oE "[0-9]+\.[0-9]+" | head -1 || true)
if [[ -z "${NEW_LOSS}" ]]; then
  log "WARNING: Could not parse eval loss from output. Skipping regression check."
  NEW_LOSS="null"
fi
log "Eval loss: ${NEW_LOSS}"

# ─── Step 6: Regression check ────────────────────────────────────────────────

STATUS="ok"
PREV_LOSS=""

if [[ "${NEW_LOSS}" != "null" && -f "${RUNS_LOG}" ]]; then
  PREV_LOSS=$(grep '"agent": *"maps"' "${RUNS_LOG}" | grep '"status": *"ok"' | \
    python3 -c "
import sys, json
entries = [json.loads(l) for l in sys.stdin if l.strip()]
ok = [e for e in entries if e.get('agent') == 'maps' and e.get('status') == 'ok']
if ok:
    print(ok[-1].get('eval_loss', ''))
" 2>/dev/null || true)
fi

if [[ -n "${PREV_LOSS}" && "${NEW_LOSS}" != "null" ]]; then
  REGRESSED=$(python3 -c "
new=${NEW_LOSS}; prev=${PREV_LOSS}
print('yes' if new > prev * 1.05 else 'no')
" 2>/dev/null || echo "no")

  if [[ "${REGRESSED}" == "yes" ]]; then
    log "Regression detected: new loss ${NEW_LOSS} > prev loss ${PREV_LOSS} by more than 5%."
    log "Discarding staged adapter; live ${ADAPTER_DIR} is untouched."
    rm -rf "${STAGING_DIR}"
    rm -f "${STAGING_CONFIG}"
    STATUS="rolled_back"
  fi
fi

if [[ "${STATUS}" == "ok" ]]; then
  if [[ -d "${ADAPTER_DIR}" ]]; then
    BACKUP_DIR="${ADAPTER_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
    log "Renaming current live adapter to ${BACKUP_DIR}..."
    mv "${ADAPTER_DIR}" "${BACKUP_DIR}"
  fi
  log "Promoting ${STAGING_DIR} -> ${ADAPTER_DIR}..."
  mv "${STAGING_DIR}" "${ADAPTER_DIR}"
  rm -f "${STAGING_CONFIG}"
  log "Adapter promotion complete."
fi

# ─── Step 7: Write training run metadata ─────────────────────────────────────

END_EPOCH=$(date +%s)
DURATION=$(( END_EPOCH - START_EPOCH ))
ADAPTER_VERSION="maps_v1_$(date +%Y%m%d)"

ENTRY=$(python3 -c "
import json, sys
print(json.dumps({
  'ts': '${START_TS}',
  'agent': 'maps',
  'adapter_version': '${ADAPTER_VERSION}',
  'eval_loss': float('${NEW_LOSS}') if '${NEW_LOSS}' != 'null' else None,
  'examples_train': ${TRAIN_LINES},
  'examples_valid': ${VALID_LINES},
  'examples_test': ${TEST_LINES},
  'duration_sec': ${DURATION},
  'status': '${STATUS}'
}))
")
printf "%s\n" "${ENTRY}" >> "${RUNS_LOG}"
log "Training run metadata written to ${RUNS_LOG}."

# ─── Step 8: Final result ─────────────────────────────────────────────────────

if [[ "${STATUS}" == "rolled_back" ]]; then
  log "Maps training FAILED — adapter rolled back."
  exit 1
fi

log "Maps adapter training complete."
