# E3D Maps Watch Agent v1 — Feature Ticket (phase-structured)

**Target Repository:** `e3d-maps`
**Priority:** High
**Status:** Canonical, phase-structured spec. Supersedes the original
`e3d-maps-watch-agent-v1-feature-ticket.md` (the "vacuum" draft written without codebase
knowledge).

---

## Overview

Build an autonomous **Watch Agent** that is the **first production consumer of the E3D Maps
intelligence APIs** and the **reference implementation** every future third-party AI agent
will copy. It is the spinal cord of a single self-improving loop:

1. **Sense** — consume the *public* `/api/maps/...` contract over HTTP (no internal imports).
2. **Predict** — emit falsifiable, probabilistic claims with explicit settlement conditions,
   not free-text "analysis."
3. **Settle** — resolve claims against on-chain ground truth via the existing outcome-scoring
   machinery and publish a calibrated, public track record.
4. **Distill** — feed every settled call into training-example export for the
   OpenAI → Qwen-adapter self-improvement flywheel.
5. **Route** — produce machine-readable navigation for downstream agents plus human-facing
   social drafts (X under 280 chars, LinkedIn 200–500 words).

**Version 1 is draft-only and never posts automatically.**

The feature must stay true to repo shape: small explicit modules, strict schema validation,
validate-before-write, append-only storage, and reuse of existing infrastructure rather than
parallel re-implementation.

---

## How to run

This spec is implemented with **Claude Code in a fresh session, phase by phase**, committing
after each green phase. (If instead run through `codex-spec-runner`, note it drives the Codex
CLI with GPT models and has **no** `--provider` flag; route schema/contract phases to the
high model via `MODEL_OVERRIDES`. The `--provider claude` form used in older tickets is not a
real flag.)

```bash
# List detected phases (read-only)
codex-spec-runner docs/e3d-maps-watch-agent-v1-feature-ticket-revised.md --list
```

Run Python tests from the repo root with `.venv/bin/python -m pytest tests/unit/ -q`.

---

## Background — what exists today (reuse map, do NOT reinvent)

The repo already contains every organ of the flywheel. Each phase below extends a named,
existing module. Do not build parallel versions of any of these.

| Need                         | Already in repo — extend this                                          |
|------------------------------|-----------------------------------------------------------------------|
| Scheduler, 5-min cadences    | `agents/scheduler.py` (`MapsJobScheduler.from_runner_and_jobs`)        |
| LLM client (OpenAI-compatible)| `clients/qwen_client.py`, `agents/base_agent.py` (`BaseAgent`)        |
| Public API consumer client   | `clients/e3d_api_client.py`, `clients/_base_api_client.py` (`BaseE3DReadClient._get_json`) |
| Public Maps read surface     | `api/maps_routes.py`: `get_maps_signals`, `get_maps_signal`, `get_maps_predictions`, `get_maps_calibration`, `get_maps_recommendations`, `get_maps_news` |
| Read-side service            | `services/maps_api_service.py` (`get_latest_*` patterns)               |
| Dedup primitive              | `ClickHouseClient.recent_signal_exists`                                |
| Storage client + dry-run     | `clients/clickhouse_client.py` (`insert_*`, `_serialize_*`, `_json_string`, `_format_datetime`, `_print_dry_run`) |
| Prediction + outcome schemas | `schemas/route_prediction.py`, `schemas/prediction_outcome.py`        |
| Reflexivity metrics (already modeled) | `PredictionOutcome.consumer_exposure / exogenous_accuracy / induced_accuracy` |
| Utility ranking              | `schemas/signal_utility_score.py`, `jobs/compute_signal_utility_scores.py` |
| Settlement / scoring         | `agents/outcome_scoring_agent.py`, `jobs/score_pending_predictions.py` |
| Public track record          | `api/maps_routes.py: get_maps_calibration`                            |
| Training export (distill)    | `jobs/export_training_examples.py`                                     |
| Content-gen analog (template)| `agents/maps_news_agent.py` + `jobs/generate_maps_news.py` (incl. `_DryRunFallbackQwenClient`) |
| Shared enums                 | `schemas/shared_enums.py` (`SignalType`, `FlowDirection`, `FlowMagnitude`, `OutcomeStatus`, `RiskLevel`) |
| Schema base                  | `schemas/_compat.py` (`CompatBaseModel`)                              |

---

## Design principles (binding constraints)

1. **One LLM seam, switchable by config.** Do NOT add the `openai` SDK or a standalone
   `openai_analysis.py`. `clients/qwen_client.py` already speaks the OpenAI-compatible
   `/v1/chat/completions` protocol (`Authorization: Bearer`, `LLM_BASE_URL`, `LLM_MODEL`).
   Run on OpenAI today via those env vars; swap to a local Qwen adapter later via
   `X-Adapter-Path` — config only, no code change. All model calls go through
   `BaseAgent`/`QwenClient`.
2. **Reference consumer = public contract only.** The Watch Agent reads E3D Maps through the
   public `/api/maps/...` HTTP surface via a `WatchFeedClient` (mirroring
   `clients/e3d_api_client.py`). The Watch Agent and its job MUST NOT import producer modules
   (`agents/*_agent.py` producers, `jobs/generate_*`, `services/*assembler*`). This is
   enforced by a test (Phase 6). Its own outputs are its own data and may be stored directly.
3. **Schema-first, validate before write.** Every output is a strict `CompatBaseModel` with
   confidence/probability constrained `0.0 ≤ x ≤ 1.0` and types from `shared_enums.py`.
   Validate before any ClickHouse write.
4. **Predictions, not assertions.** The LLM produces the *claim text* and *expected
   direction/magnitude* only. The numeric `probability` is **derived deterministically** from
   the source signal's confidence and `SignalUtilityScore` (formula in Phase 3), never
   self-reported by the model.
5. **Graceful degradation.** A model outage must degrade to a deterministic fallback (mirror
   `_DryRunFallbackQwenClient`), never crash the scheduler tick.

### Resolved decisions (do not re-litigate)

- **Notable selection:** a dedicated `/api/maps/notable` endpoint with a **server-side**
  notability score derived from `SignalUtilityScore` (Phase 2). Clients only threshold-filter.
- **Consumer write-back:** v1 builds the producer-side schema, storage, and ingestion that
  feeds `consumer_exposure` (Phase 5). The public `POST /api/maps/outcomes` endpoint is a
  documented cross-repo step (main `e3d` repo) and may be deferred; the ingestion path is
  built now.
- **Cost cascade:** v1 records the model tier (`model`, `adapter`) on every prediction but
  runs a single model by default. Escalation is a documented hook, not required for v1.

### Cross-repo note (CLAUDE.md §8)

The public `/api/maps/...` and `/api/agents/...` HTTP surface is owned by the main `e3d`
server repository. In this repo, build the service methods + route handlers in
`api/maps_routes.py` / `services/maps_api_service.py` (defining the contract + shapes + tests).
Wiring the matching public Express routes in the main `e3d` server (`server/...`) is a
**cross-repo manual step**, flagged per phase, and out of scope for automated runs here.

---

## Scope

### In scope
- New schemas: `WatchPrediction`, `WatchDraft`, `ConsumerAttestation`; `DraftStatus` enum.
- ClickHouse tables + client serializers/inserts for the new artifacts.
- `WatchFeedClient` (public-contract consumer).
- `/api/maps/notable` service method + route handler (server-side notability).
- `WatchAgent` + prompt; `watch_draft_generator`.
- Settlement integration + `consumer_exposure` population; attestation ingestion.
- `jobs/run_watch_agent.py` + scheduler/settings wiring; no-internal-imports test.
- Training-export extension for settled watch predictions.
- Read API service methods + route handlers for drafts/predictions.
- Tests for every phase under `tests/unit/`.

### Out of scope
- Automatic posting (V3), human approval UI (V2), specialized sub-agents (V4).
- New raw on-chain crawlers or a parallel event taxonomy.
- Live main-`e3d` Express wiring (documented as cross-repo manual steps).
- Per-request LLM generation on read endpoints.

---

## Phase 1 — Shared Schemas and Storage

Add durable, validated artifact schemas and append-only storage.

### What to build

#### 1a. Add `DraftStatus` enum
In `schemas/shared_enums.py`, add (StrEnum, matching existing style):
```text
DraftStatus: DRAFT = "draft", APPROVED = "approved", REJECTED = "rejected"
```

#### 1b. Add `WatchPrediction` schema
Create `schemas/watch_prediction.py` (extend `CompatBaseModel`):
```text
id: str | None = None
source_signal_id: str                       # provenance to consumed NavigationSignal
source_prediction_id: str | None = None
signal_type: SignalType                      # validated; from shared_enums
asset_scope: list[str] = []
chain_scope: list[str] = []
claim: str                                   # falsifiable, human-readable (non-empty)
probability: float = Field(ge=0.0, le=1.0)   # derived (Phase 3), not self-reported
realized_direction_expected: FlowDirection
magnitude_expected: FlowMagnitude
evaluation_window_hours: int = Field(gt=0)
status: OutcomeStatus = OutcomeStatus.PENDING
created_by_agent: str = "watch_agent"
model: str
adapter: str
schema_version: str
idempotency_key: str                         # see Phase 3 for formula
created_at: datetime
```

#### 1c. Add `WatchDraft` schema
Create `schemas/watch_draft.py` (extend `CompatBaseModel`):
```text
id: str | None = None
watch_prediction_id: str
headline: str                                # non-empty
analysis: str
significance: str
x_post: str = Field(max_length=280)
linkedin_draft: str                          # 200-500 words target (validate word count >= 150)
track_record_snapshot: dict = {}             # calibration shown in the post (Phase 4)
routing: dict = {}                            # machine-readable nav object (Phase 4)
status: DraftStatus = DraftStatus.DRAFT
created_by_agent: str = "watch_draft_generator"
model: str
adapter: str
schema_version: str
created_at: datetime
```

#### 1d. Add `ConsumerAttestation` schema
Create `schemas/consumer_attestation.py` (extend `CompatBaseModel`):
```text
id: str | None = None
watch_prediction_id: str
consumer_id: str                             # which downstream agent acted
acted: bool                                  # did the consumer act on the prediction
observed_direction: FlowDirection | None = None
observed_magnitude: FlowMagnitude | None = None
notes: str = ""
created_at: datetime
```

#### 1e. Export schemas
Update `schemas/__init__.py` so `WatchPrediction`, `WatchDraft`, `ConsumerAttestation`, and
`DraftStatus` are importable from the shared schema layer.

#### 1f. ClickHouse tables
Add a migration under `db/migrations/` (match existing style: append-only, newest row wins by
timestamp; use `String` for JSON payload columns as `TrafficState`/`FlowGraph` do):

```sql
CREATE TABLE WatchPredictions (
    id String, source_signal_id String, source_prediction_id String,
    signal_type LowCardinality(String), asset_scope Array(String), chain_scope Array(String),
    claim String, probability Float64,
    realized_direction_expected LowCardinality(String), magnitude_expected LowCardinality(String),
    evaluation_window_hours UInt32, status LowCardinality(String),
    created_by_agent String, model String, adapter String, schema_version String,
    idempotency_key String, created_at DateTime
) ENGINE = MergeTree ORDER BY (created_at, id);

CREATE TABLE WatchDrafts (
    id String, watch_prediction_id String, headline String, analysis String, significance String,
    x_post String, linkedin_draft String, track_record_snapshot String, routing String,
    status LowCardinality(String), created_by_agent String, model String, adapter String,
    schema_version String, created_at DateTime
) ENGINE = MergeTree ORDER BY (created_at, id);

CREATE TABLE ConsumerAttestations (
    id String, watch_prediction_id String, consumer_id String, acted UInt8,
    observed_direction LowCardinality(String), observed_magnitude LowCardinality(String),
    notes String, created_at DateTime
) ENGINE = MergeTree ORDER BY (created_at, id);
```

#### 1g. Extend ClickHouse client
In `clients/clickhouse_client.py`, add (mirroring `insert_maps_news_brief` + `_serialize_*`,
`_json_string`, `_format_datetime`, `_sql_string`, dry-run support):
`insert_watch_prediction(s)`, `insert_watch_draft(s)`, `insert_consumer_attestation(s)` and
matching `_serialize_*` helpers. Do not introduce a generic serialization framework.

### Acceptance Criteria
- New models validate cleanly; confidence/probability constrained to [0,1]; unknown
  `signal_type` rejected (reuse `is_known_signal_type` behavior).
- Models exported from `schemas/__init__.py`.
- Migration defines all three tables.
- ClickHouse client serializes and writes all three artifacts (dry-run shows valid rows).

### Verification
1. `tests/unit/test_watch_schemas.py`: validation + rejection of bad confidence/signal_type.
2. `tests/unit/test_watch_clickhouse_serialize.py`: serialization shape for all three.

---

## Phase 2 — Sense: Notable endpoint + public-contract consumer

### What to build

#### 2a. Notable selection (producer side, server-side notability)
In `services/maps_api_service.py`, add `get_notable_signals(*, min_score: int, since=None,
limit: int, offset: int)` that returns recent navigation signals joined to their latest
`SignalUtilityScore`, with a derived `notability`:
```text
notability = round(100 * final_signal_utility_score)   # when a utility score exists
notability = round(100 * confidence)                   # fallback when none yet
```
Filter `notability >= min_score`, sort by `notability DESC, created_at DESC`, support
`since`/pagination.

In `api/maps_routes.py`, add `get_maps_notable(service, *, min_score, since, limit, offset)`
returning `RouteResponse` with `_paginated_body(key="notable", ...)`. Each item includes:
`signal_id, signal_type, asset_scope, chain_scope, confidence, notability, created_at,
summary`. Exact route: `GET /api/maps/notable`.

> **Cross-repo:** add the matching public Express route in the main `e3d` server. Documented,
> not built here.

#### 2b. Watch feed client (consumer side, HTTP only)
Create `clients/watch_feed_client.py` mirroring `clients/e3d_api_client.py` /
`BaseE3DReadClient._get_json`. Base URL from `MAPS_PUBLIC_API_BASE`. Methods:
`get_notable(min_score, since, limit)`, `get_signal(signal_id)`, `get_predictions(...)`,
`get_calibration(source="watch_agent")`. Demonstrate ecosystem-grade hygiene:
`Authorization: Bearer` auth, retry/backoff (reuse base client behavior), and **cursor/since
incremental fetch** so events are never reprocessed or skipped. This makes a separate dedup
engine unnecessary; for belt-and-suspenders, callers may consult
`ClickHouseClient.recent_signal_exists`.

This client MUST NOT import producer modules.

### Acceptance Criteria
- `get_maps_notable` returns notability-sorted, threshold-filtered, paginated results;
  empty/sparse input returns a valid empty page, not an error.
- `WatchFeedClient` fetches over HTTP with a fake transport in tests; `since` advances the
  cursor correctly.

### Verification
1. `tests/unit/test_maps_notable_endpoint.py`: ranking, threshold, pagination, empty state.
2. `tests/unit/test_watch_feed_client.py`: parsing + cursor behavior against a fake transport.

---

## Phase 3 — Predict: the Watch Agent

### What to build

#### 3a. Prompt
Create `prompts/watch_agent.md` (match existing agent-prompt convention; reuse
`prompts/maps_system_prompt.md` as system prompt where useful). Instruct the model to emit
exactly one JSON object: a falsifiable `claim`, `realized_direction_expected`
(inflow/outflow/neutral/mixed), `magnitude_expected` (low/moderate/high), and
`evaluation_window_hours`. The model MUST NOT output a probability. No markdown/code fences.
Grounded only in provided evidence.

#### 3b. Agent
Create `agents/watch_agent.py`: `class WatchAgent(BaseAgent)`. Use `BaseAgent` for prompt
build + `call_qwen` + `parse_json`, but implement a **local validator** producing a
`WatchPrediction` (do not force the `NavigationSignal`-shaped `BaseAgent.validate_output`).
For each notable signal:
- **Derive probability deterministically** (never from the model):
  ```text
  u = source utility (final_signal_utility_score) if available else None
  probability = clamp(0.0, 1.0, source_confidence * (0.5 + 0.5*u)) if u is not None
              else source_confidence
  ```
- Set provenance (`source_signal_id`, `source_prediction_id`, `model`, `adapter`,
  `schema_version`, `created_by_agent="watch_agent"`).
- **Idempotency key:**
  ```text
  idempotency_key = sha256(f"{source_signal_id}|{evaluation_window_hours}|{magnitude_expected}|{realized_direction_expected}")
  ```
- LLM access only via `self.call_qwen(...)` (the configured OpenAI-compatible seam).

#### 3c. Deterministic fallback
If model output is invalid/empty, build a deterministic `WatchPrediction` from the source
signal (claim templated from `signal_type` + origin/destination + asset_scope; direction from
the signal's flow framing; magnitude from confidence band). Never call the model again; never
crash the tick.

### Acceptance Criteria
- Valid model output → validated `WatchPrediction` with derived probability and stable
  idempotency key.
- Invalid output → deterministic fallback prediction.
- `WatchAgent` imports no producer modules.

### Verification
1. `tests/unit/test_watch_agent.py`: valid parse, probability derivation, idempotency
   determinism, fallback on invalid JSON.

---

## Phase 4 — Route: draft generation

### What to build

#### 4a. Draft generator
Create `agents/watch_draft_generator.py` building a `WatchDraft` from a `WatchPrediction` plus
a track-record snapshot fetched via `WatchFeedClient.get_calibration(source="watch_agent")`.
- **X post (≤280):** lead with the record, e.g.
  `"E3D Maps flagged $34M ETH → Coinbase. 71% on inflow→price calls (n=240, Brier 0.18). Sell-side liquidity building. Every transaction is traffic. maps.e3d.ai #Ethereum #E3D"`.
  Enforce length ≤280 (truncate gracefully).
- **LinkedIn (200–500 words):** stored only, never auto-published.
- **`routing`:** a machine-readable nav object (origin/destination/route_type/expected
  direction/window) for downstream agents — reuse `services/recommendation_engine.py` shapes.
- `track_record_snapshot`: the calibration figures embedded in the post.
- `status = DraftStatus.DRAFT`.

#### 4b. Fallback
If the LLM draft is invalid, generate a deterministic draft from the prediction +
track-record snapshot (mirror the maps-news fallback pattern).

### Acceptance Criteria
- X post ≤280 and leads with the track record.
- LinkedIn within target length.
- `routing` populated; `status=draft`.

### Verification
1. `tests/unit/test_watch_draft_generator.py`: length bounds, track-record lead, fallback.

---

## Phase 5 — Settle + reflexivity

This is the subtle-correctness phase; implement carefully.

### What to build

#### 5a. Register watch predictions for settlement
Make watch predictions resolvable by the existing pipeline
(`jobs/score_pending_predictions.py` / `agents/outcome_scoring_agent.py`) so each produces a
`PredictionOutcome` against on-chain ground truth. Reuse `PredictionOutcome` as-is (do not add
a parallel outcome type); set `navigation_signal_id = source_signal_id` and
`evaluation_window_hours` from the prediction. Keep changes additive and minimal.

#### 5b. Attestation ingestion → `consumer_exposure`
Add a service method (`services/maps_api_service.py`) and storage path to ingest
`ConsumerAttestation`s, and populate `PredictionOutcome.consumer_exposure` = count of
attestations with `acted = true` for that prediction before the window closed. Let the
existing `jobs/compute_signal_utility_scores.py` derive `exogenous_accuracy` vs
`induced_accuracy` from exposure (extend minimally if needed).

> **Cross-repo:** public `POST /api/maps/outcomes` (attestation submit) in main `e3d` server —
> documented, deferred. v1 ingestion path is built and testable here.

### Acceptance Criteria
- A pending watch prediction with elapsed window produces a `PredictionOutcome`.
- `consumer_exposure` reflects attestations; exogenous/induced split populates when exposure
  data exists.

### Verification
1. `tests/unit/test_watch_settlement.py`: settlement produces an outcome; exposure counting;
   exogenous vs induced split.

---

## Phase 6 — Scheduled job + scheduler wiring + boundary test

### What to build

#### 6a. Job
Create `jobs/run_watch_agent.py` with a `run(...)` entrypoint mirroring
`jobs/generate_maps_news.py`: fetch notable via `WatchFeedClient`, run `WatchAgent`, generate
drafts, validate, write `WatchPrediction` + `WatchDraft` (idempotent on `idempotency_key`).
Bounded lookback + candidate cap. Dry-run supported.

#### 6b. Scheduler
In `agents/scheduler.py`, add `watch_fn` param + `DEFAULT_WATCH_INTERVAL = 300` to
`MapsJobScheduler.from_runner_and_jobs`, registering a `run_watch_agent` `JobConfig`. Do not
build a new scheduler.

#### 6c. Settings
Extend `settings.py` (`MapsRunnerSettings` / `MapsRuntimeSettings`): `watch_interval_seconds`,
`min_event_score` (default 60), `maps_public_api_base`. Expose via env
(`WATCH_INTERVAL_SECONDS`, `MIN_EVENT_SCORE`, `MAPS_PUBLIC_API_BASE`).

#### 6d. Boundary test (binding)
Add `tests/unit/test_watch_agent_boundary.py` asserting that `agents/watch_agent.py`,
`agents/watch_draft_generator.py`, and `jobs/run_watch_agent.py` import nothing from producer
internals (no `agents/*producer*`, `jobs/generate_*`, `services/*assembler*`,
`agents/maps_news_agent`). Allowed: `WatchFeedClient`, schemas, `QwenClient`/`BaseAgent`,
`ClickHouseClient`, `settings`.

### Acceptance Criteria
- Scheduler runs the watch job at the configured interval; failures in the job do not crash
  the loop; restart-safe via idempotency.
- Boundary test passes.

### Verification
1. Run scheduler `--once --dry-run`; confirm the watch job executes and emits valid rows.
2. `tests/unit/test_watch_agent_boundary.py` passes.

---

## Phase 7 — Distill: training-export hook

### What to build

#### 7a. Extend export
In `jobs/export_training_examples.py`, include settled watch predictions: extend the listing
and `_build_context` so each exported example pairs the prediction's claim + consumed context
+ realized `PredictionOutcome` (the label) + utility. Keep JSONL shape consistent with
existing examples.

### Acceptance Criteria
- Settled watch predictions appear in `write_examples_jsonl` output with the realized outcome
  as label.

### Verification
1. `tests/unit/test_export_training_examples_watch.py`: a settled prediction yields one
   labeled example.

---

## Phase 8 — Read API surface for drafts/predictions

### What to build

#### 8a. Service methods
In `services/maps_api_service.py`: `list_watch_drafts(limit, offset)`,
`get_watch_draft(draft_id)`, `get_watch_prediction(prediction_id)` (newest-first, mirror
`get_latest_*`).

#### 8b. Route handlers
In `api/maps_routes.py`: `get_agent_drafts`, `get_agent_draft`, `get_agent_prediction`
returning `RouteResponse` (use `_paginated_body` for the list). Exact routes:
`GET /api/agents/drafts`, `GET /api/agents/drafts/:id`, `GET /api/agents/predictions/:id`.
404 → `not_found` when absent (frontend treats as empty state).

> **Cross-repo:** matching public Express routes in main `e3d` server — documented, deferred.

### Acceptance Criteria
- Service reads newest rows; route handlers return stable JSON; missing → 404 `not_found`.

### Verification
1. `tests/unit/test_agent_routes.py`: list 200, detail 200, missing 404.

---

## Deliverables
- `schemas/watch_prediction.py`, `schemas/watch_draft.py`, `schemas/consumer_attestation.py`
- `schemas/shared_enums.py` (+`DraftStatus`), `schemas/__init__.py` (exports)
- migration under `db/migrations/` (3 tables)
- `clients/clickhouse_client.py` (inserts + serializers)
- `clients/watch_feed_client.py`
- `agents/watch_agent.py`, `prompts/watch_agent.md`, `agents/watch_draft_generator.py`
- `jobs/run_watch_agent.py`, `jobs/export_training_examples.py` (extend)
- `agents/scheduler.py`, `settings.py` (wiring)
- `services/maps_api_service.py`, `api/maps_routes.py` (notable + drafts/predictions + ingestion)
- tests under `tests/unit/` for every phase

Files that must be touched unless a phase is skipped: `schemas/__init__.py`,
`clients/clickhouse_client.py`, `agents/scheduler.py`, `settings.py`,
`services/maps_api_service.py`, `api/maps_routes.py`, `jobs/export_training_examples.py`.

---

## Final Verification
From `e3d-maps` root:
1. `.venv/bin/python -m pytest tests/unit/ -q` — all green.
2. Scheduler `--once --dry-run` produces valid `WatchPrediction` + `WatchDraft` rows.
3. Boundary test confirms the Watch Agent consumes only the public contract.
4. A settled prediction flows into training-export output.

Feature is complete when the Watch Agent, on a schedule, consumes the public Maps contract,
emits falsifiable predictions that settle into a calibrated track record, generates
record-leading drafts (never auto-posted), feeds settled calls into training export, and
imports nothing from producer internals.

---

## Roadmap
- **V2** — human approval workflow: flip `WatchDraft.status` (field already exists; no migration).
- **V3** — automatic posting of approved drafts; measure published-post reflexivity via `induced_accuracy`.
- **V3.5** — distillation cutover: train the Qwen adapter, flip `MAPS_ADAPTER_PATH`; enable the cost cascade.
- **V4** — specialized agents (Whale/Exchange/Bridge/Narrative/Opportunity/Protocol) as `WatchAgent` subclasses.
- **V5** — open prediction market: external agents stake on predictions; re-consume the market price as a higher-order signal.
