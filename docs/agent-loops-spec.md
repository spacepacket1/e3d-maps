# Agent Loops Implementation Spec

**Status:** Draft — awaiting review before implementation  
**Source:** Analysis of E3D_ECOSYSTEM_ARCHITECTURE.md + e3d_maps_navigation_intelligence_spec.md  
**Scope:** 8 new or completed agent loops identified as missing from the current system

---

## Inventory: what already exists

Before listing gaps, these loops are **already implemented and wired into the scheduler**:

| Loop | Status |
|---|---|
| Navigation signal generation (all 10 signal types) | ✅ Complete — `agents/runner.py` + `agents/question_queue.json` |
| Prediction outcome scoring (dual-witness) | ✅ Complete — `jobs/score_pending_predictions.py` |
| FlowGraph assembly with temporal edge deltas | ✅ Complete — `jobs/assemble_flow_graph.py` |
| TrafficState assembly | ✅ Complete — `jobs/assemble_traffic_state.py` |
| CrossChainActivityState assembly | ✅ Complete — `jobs/assemble_cross_chain_activity.py` |
| Watch agent (WatchPrediction + WatchDraft) | ✅ Complete — `jobs/run_watch_agent.py` |
| Maps news brief | ✅ Complete — `jobs/generate_maps_news.py` |
| Signal utility scores | ✅ Complete — `jobs/compute_signal_utility_scores.py` |
| Training export | ✅ Complete — `jobs/export_training_examples.py` |
| `narrative_acceleration_agent` | ✅ Complete — enabled in `question_queue.json` |
| `agent_swarm_formation_agent` | ✅ Complete — enabled in `question_queue.json` |

The 8 loops below are the **genuine gaps**.

---

## Loop 1: Query Demand Intelligence

**What it does.** Logs anonymized metadata about every `/api/maps/signals` request (destination queried, time horizon requested, caller ID hash). Aggregates those logs every 15 minutes into a `SignalDemandState` that captures pre-transaction intent: which destinations are being asked about before they show up on-chain.

**Why it matters.** This is the most time-sensitive item in the v2 doc — query logs are impossible to reconstruct retroactively once traffic is real.

**What to build:**
- `schemas/signal_demand_state.py` — `QueryAccessLog` + `SignalDemandState` models
- `db/migrations/0008_…` — `QueryAccessLogs` and `SignalDemandStates` tables
- `clients/clickhouse_client.py` — add `insert_query_access_log`, `insert_signal_demand_state`
- `api/maps_routes.py` — add a `log_query_access()` call at the top of `get_maps_signals()` (and any other filterable endpoint)
- `jobs/aggregate_query_demand.py` — reads `QueryAccessLogs` for last window, writes `SignalDemandState`
- `settings.py` — `query_demand_interval_seconds` (default 900)
- `agents/scheduler.py` — wire `query_demand_fn` into `from_runner_and_jobs()`

**Design choices to confirm:**
1. What fields to log? Proposed: `endpoint`, `destination_filter`, `signal_type_filter`, `time_horizon_hours_filter`, `caller_id_hash` (SHA-256 of api_key or IP, truncated to 16 hex chars for k-anonymity). No raw API keys or IPs ever stored.
2. The `SignalDemandState` also includes a `demand_surge_destinations` list — destinations whose query rate is ≥2× the 24-hour rolling baseline. Should this emit a `NavigationSignal` of a new type, or just stay in its own table and get surfaced through a new API route?

---

## Loop 2: Reflexivity Management

**What it does.** Monitors `consumer_exposure` on recent `PredictionOutcomes`. When multiple consumers have acted on signals pointing to the same destination, emits a `map_induced_congestion` NavigationSignal warning that the route is elevated-risk *because of* Maps traffic, not despite it.

**Why it matters.** The `consumer_exposure` field is already captured (MAPS-1202). Nothing currently acts on it. Without this loop, the adapter learns to produce herd-inducing signals.

**What to build:**
- `schemas/shared_enums.py` — add `MAP_INDUCED_CONGESTION = "map_induced_congestion"` to `SignalType`
- `agents/reflexivity_agent.py` — extends `BaseAgent`, takes a context of high-exposure outcomes grouped by destination, emits a `map_induced_congestion` NavigationSignal explaining the crowding pattern
- `prompts/reflexivity_agent.md`
- `jobs/detect_reflexivity.py` — deterministic trigger: queries PredictionOutcomes with `consumer_exposure >= threshold` in last 24h, groups by destination, calls reflexivity_agent for any destination that hits the threshold, writes the resulting NavigationSignal
- `settings.py` — `reflexivity_interval_seconds` (default 1800), `reflexivity_exposure_threshold` (default 3)
- `agents/scheduler.py` — wire `reflexivity_fn`
- `agents/runner.py` — add `reflexivity_agent` to `AGENT_FACTORIES`
- `agents/question_queue.json` — add entries for `reflexivity_agent`

**Design choices to confirm:**
1. Threshold: how many consumers acting on signals to the same destination before a warning fires? Proposed default: **3 consumers in 24 hours**. Env-configurable as `MAPS_REFLEXIVITY_EXPOSURE_THRESHOLD`.
2. Does the LLM add value here, or should the `map_induced_congestion` signal be emitted deterministically with a canned explanation? An LLM call lets the signal explain *which* routes are crowded and why. A deterministic emit is faster and cheaper.

---

## Loop 3: Narrative Velocity

**What it does.** Reads consecutive `FlowGraphEdges` snapshots (already computed by `assemble_flow_graph.py`) and emits `narrative_acceleration` NavigationSignals when ≥N edges to the same destination are simultaneously strengthening — a second-derivative pattern the per-cycle LLM agents can miss.

**Why it matters.** The v1 spec deferred `narrative_acceleration` because it needs a historical baseline. The FlowGraph now provides that baseline. This loop activates the deferred capability without adding a new LLM agent — it's a deterministic aggregation over existing data.

**What to build:**
- `jobs/compute_narrative_velocity.py` — reads last 2 FlowGraph snapshots from ClickHouse, compares edge strengths by (origin, destination) pair, emits a `NavigationSignal` of type `narrative_acceleration` when ≥N edges to the same destination are `STRENGTHENING` or `NEW`, or `route_closure` when ≥N edges from the same origin are `WEAKENING` or `CLOSED`
- `settings.py` — `narrative_velocity_interval_seconds` (default 3600), `narrative_velocity_min_edges` (default 2)
- `agents/scheduler.py` — wire `narrative_velocity_fn`

**Design choices to confirm:**
1. Emit a `NavigationSignal` directly from a deterministic job (no LLM), or call the existing `narrative_acceleration_agent` via the runner? Proposed: **deterministic emit** — the data is already structured, the LLM adds cost without accuracy gain at this stage.
2. Minimum edge count to trigger: **2 edges** (so stablecoins→ETH_DEFI + meme_tokens→ETH_DEFI both strengthening fires the signal). Confirm or adjust.

---

## Loop 4: Anomaly Spike Detection

**What it does.** Runs every 2 minutes, compares the rate of NavigationSignals in the last 10 minutes to the 60-minute rolling baseline. If any signal type is running at >2× baseline rate (a spike), writes a record to a lightweight audit table that the Watch Agent priority queue can incorporate.

**Why it matters.** The Watch Agent currently reacts to `notable` signals polled from the public API. It has no awareness that something unusual is happening in the signal generation pipeline itself — a sudden spike in `route_hazard` signals before the Watch Agent runs its next 5-minute cycle.

**What to build:**
- `db/migrations/0008_…` — `SignalRateAnomalies` table (lightweight: `signal_type`, `baseline_rate`, `observed_rate`, `spike_ratio`, `detected_at`)
- `clients/clickhouse_client.py` — `insert_signal_rate_anomaly`
- `jobs/monitor_anomalies.py` — reads signal counts per type for last 10 min and last 60 min, computes spike ratios, writes anomalies above threshold
- `settings.py` — `anomaly_monitor_interval_seconds` (default 120), `anomaly_spike_ratio_threshold` (default 2.0)
- `agents/scheduler.py` — wire `anomaly_monitor_fn`

**Design choices to confirm:**
1. Does detecting an anomaly immediately trigger a Watch Agent run (reactive), or does the Watch Agent just read the anomaly table on its normal cadence? Proposed: **anomaly table only** — the Watch Agent already runs every 5 minutes; feeding it an anomaly flag is sufficient without adding cross-job triggering logic.
2. Should the anomaly record include a `severity` label (`elevated`, `high`, `critical`) based on the spike ratio? Proposed: yes — simpler than a raw float for UI display.

---

## Loop 5: Route Health Reporting

**What it does.** Runs daily. For each protocol or chain with meaningful signal history (≥5 NavigationSignals in last 7 days), assembles a `RouteHealthReport` summarizing traffic trends, congestion, hazard level, and dominant flow directions. Target audience: protocol operators, DAO treasuries, L2 teams — not trading agents.

**Why it matters.** Every loop in the current system serves trading agents. Route health reporting is the same agents, different question queue, different schema, different customer.

**What to build:**
- `schemas/route_health_report.py` — `RouteHealthReport` model: `protocol_or_chain`, `health_score [0,1]`, `traffic_trend` (growing/stable/declining), `congestion_level`, `hazard_level`, `route_emergence_count`, `route_closure_count`, `dominant_inflow_source`, `dominant_outflow_destination`, `supporting_signal_ids`, `summary`
- `db/migrations/0008_…` — `RouteHealthReports` table
- `clients/clickhouse_client.py` — `insert_route_health_report`
- `agents/route_health_agent.py` — extends `BaseAgent`, consumes recent NavigationSignals for a specific protocol/chain, emits a `RouteHealthReport`
- `prompts/route_health_agent.md`
- `jobs/generate_route_health_reports.py` — queries top N protocols/chains by signal volume in last 7 days, calls `route_health_agent` for each, writes results
- `settings.py` — `route_health_interval_seconds` (default 86400), `route_health_min_signals` (default 5), `route_health_top_n` (default 10)
- `agents/scheduler.py` — wire `route_health_fn`

**Design choices to confirm:**
1. Is there an API route for `RouteHealthReports`? Proposed: **not in this pass** — write to ClickHouse, make it queryable, add the API route when there's a consumer. Keeps the scope contained.
2. The `health_score` field: computed deterministically from signal ratios (hazard signals / total signals, congestion signals / total signals), or from LLM output? Proposed: **LLM outputs the summary and traffic_trend; health_score is deterministically computed** from the ratio of hazard+closure signals to total signals for that route.

---

## Loop 6: Adapter Health Monitoring

**What it does.** Runs daily. Reads the last N days of `PredictionOutcomes` with known accuracy scores, buckets them by predicted confidence, computes realized hit rate per bucket, detects calibration drift vs. the previous report, and writes an `AdapterHealthReport`. Sets `retraining_recommended = True` when drift exceeds a configurable threshold.

**Why it matters.** The training export runs daily but there's nothing that watches whether the deployed adapter is drifting. Without this loop, the "closed learning loop" is open at its most critical joint.

**What to build:**
- `schemas/adapter_health_report.py` — `AdapterHealthReport`: `adapter_name`, `evaluation_window_days`, `total_scored_signals`, `overall_calibration_error`, `accuracy_by_signal_type`, `confidence_buckets` (list of `{bucket, predicted_confidence, realized_accuracy, sample_size}`), `drift_detected`, `drift_severity` (none/mild/moderate/severe), `retraining_recommended`, `notes`
- `db/migrations/0008_…` — `AdapterHealthReports` table
- `clients/clickhouse_client.py` — `insert_adapter_health_report`
- `jobs/monitor_adapter_health.py` — no LLM; purely deterministic calibration math
- `settings.py` — `adapter_health_interval_seconds` (default 86400), `adapter_health_window_days` (default 14), `adapter_health_drift_threshold` (default 0.15)
- `agents/scheduler.py` — wire `adapter_health_fn`

**Design choices to confirm:**
1. Drift is computed as: `|current_calibration_error - previous_calibration_error| > threshold`. Does that capture what you want, or should drift be per-signal-type?
2. When `retraining_recommended = True`, does anything happen automatically, or is it purely advisory (human reads the report and decides)? Proposed: **purely advisory** in this pass — the report is written to ClickHouse, a future step adds alerting.

---

## Loop 7: Story Hypothesis

**What it does.** Runs weekly. Reads NavigationSignals where the LLM returned low confidence (< 0.4) or where answer patterns don't map cleanly to existing signal types. Calls a `story_hypothesis_agent` that proposes a new candidate story type based on recurring patterns. Writes `StoryHypothesis` records with `status = "proposed"` for human review before anything goes live.

**Why it matters.** The deterministic story scripts in `spacepacket` encode known patterns. This loop creates a channel for the LLM to propose new patterns the story pipeline doesn't yet cover.

**What to build:**
- `schemas/story_hypothesis.py` — `StoryHypothesis`: `proposed_story_type`, `description`, `detection_rationale`, `supporting_signal_ids`, `example_evidence`, `confidence`, `status` (proposed/under_review/validated/rejected)
- `schemas/shared_enums.py` — add `HypothesisStatus` StrEnum
- `db/migrations/0008_…` — `StoryHypotheses` table
- `clients/clickhouse_client.py` — `insert_story_hypothesis`
- `agents/story_hypothesis_agent.py`
- `prompts/story_hypothesis_agent.md`
- `jobs/propose_story_hypotheses.py` — queries low-confidence signals from last 30 days, groups by answer patterns, calls agent, writes proposals
- `settings.py` — `story_hypothesis_interval_seconds` (default 604800 = 7 days)
- `agents/scheduler.py` — wire `story_hypothesis_fn`

**Design choices to confirm:**
1. "Low-confidence signals" threshold: proposed **< 0.4**. Is that the right cutoff, or should we also look at signals that were scored DISPUTED or INCORRECT?
2. The hypothesis output is purely a DB record. Is there any human-facing surface needed now (a `/hypotheses` page, an API route), or is querying ClickHouse directly sufficient for v1?

---

## Loop 8: Cross-Chain Bridge Flow Synthesis

**What it does.** Reads the latest `CrossChainActivityState` (already assembled every 5 minutes). When significant bridge flows are present — active routes above a configurable magnitude threshold — emits `NavigationSignal` records of type `capital_migration` with multi-chain `chain_scope`. This makes the cross-chain intelligence visible to consumer agents that only poll `/api/maps/signals` without calling the dedicated cross-chain endpoint.

**Why it matters.** `CrossChainActivityState` is assembled but isolated. Consumer trading agents looking at NavigationSignals never see the cross-chain picture. Bridge flows often precede on-chain inflows by minutes — the exact pre-pump window the architecture is designed to capture.

**What to build:**
- `schemas/shared_enums.py` — add `CROSS_CHAIN_BRIDGE_FLOW = "cross_chain_bridge_flow"` to `SignalType`
- `jobs/synthesize_bridge_signals.py` — deterministic (no LLM); reads latest `CrossChainActivityState`, converts each `top_routes` entry above magnitude threshold into a `NavigationSignal` with `signal_type = "cross_chain_bridge_flow"`, multi-chain `chain_scope`, and confidence derived from the route's `strength` field
- `settings.py` — `bridge_synthesis_interval_seconds` (default 300), `bridge_synthesis_min_strength` (default `"moderate"`)
- `agents/scheduler.py` — wire `bridge_synthesis_fn`

**Design choices to confirm:**
1. Deterministic vs. LLM-driven? Proposed: **deterministic** — the CrossChainActivityState already has structured route data (origin chain, destination chain, strength, top_destinations). An LLM adds cost without adding accuracy since the data is already machine-readable.
2. Confidence mapping: `weak → 0.5`, `moderate → 0.65`, `strong → 0.8`. Confirm or adjust.
3. Should this deduplicate against existing `capital_migration` signals (same route within 4 hours)? Proposed: **yes**, use the existing `clickhouse_client.recent_signal_exists()` check.

---

## Shared implementation decisions

**Migration:** All new tables go in one new migration file `db/migrations/0008_agent_loops_tables.sql`.

**Scheduler wiring:** All 8 new jobs get parameters in `MapsJobScheduler.from_runner_and_jobs()` following the existing pattern (optional `fn` + `interval`).

**Settings:** All new interval and threshold settings go in `MapsRunnerSettings` with env-var overrides following the existing naming convention.

**Tests:** Each new job gets a unit test file following the pattern of `test_generate_maps_news.py` or `test_assemble_flow_graph.py` — stub ClickHouse reader/writer, test the core logic in isolation.

**What is NOT in this spec:**
- API routes for new schemas (deferred — build when there's a consumer)
- UI pages for new data (deferred)
- Alerting / notification when `retraining_recommended = True` (deferred)

---

## Open questions (need answers before implementation)

1. **Loop 1, Q2** — Does `SignalDemandState` emit a `NavigationSignal`, or stay in its own table?
2. **Loop 2, Q2** — Reflexivity signal: LLM explanation or deterministic emit?
3. **Loop 3, Q1** — Narrative velocity: deterministic `NavigationSignal` emit, or call existing LLM agent?
4. **Loop 4, Q1** — Anomaly detection: reactive Watch trigger, or anomaly table only?
5. **Loop 5, Q1** — Route health API route: now or deferred?
6. **Loop 6, Q2** — Adapter health: advisory-only, or add alerting?
7. **Loop 7, Q2** — Story hypothesis: ClickHouse-only, or add API/UI surface?
8. **Loop 8, Q1** — Bridge synthesis: deterministic or LLM?
