# E3D Maps v1.2 Addendum: Trust, State, and the Market Surface

**Status:** Proposed
**Depends on:** v1 spec (`e3d_maps_navigation_intelligence_spec.md`), implementation through Phase 11
**Spec Version:** v1.2

---

## 0. Why this addendum exists

The v1 build is feature-complete against its ticket list, but three parts of the
original *thesis* are under-built relative to their strategic weight. v1 produces
signals and consumes them internally. The thesis (§1, §21 of the v1 spec) is that
Maps becomes a compounding, machine-readable, **trustworthy** intelligence layer
that many agents depend on.

This addendum closes the gap between the ticket list and the thesis. It is ordered
by leverage, not by build convenience:

1. **Phase 12 — Outcome Scoring Rigor.** The entire training flywheel is bounded by
   the quality of prediction scoring. Today that is a single hand-tuned heuristic
   (v1 spec §3.5, implemented in `jobs/score_pending_predictions.py:_score_accuracy`).
   If the ground-truth label is biased, the adapter learns the bias. This is the
   highest-leverage and highest-risk surface in the system.
2. **Phase 13 — TrafficState as a Flow Graph.** The product metaphor is spatial
   (roads, traffic, congestion, destinations) but the data model is flat rows.
   `TrafficState` is a point-in-time summary, not a navigable state. Making it a
   persistent flow-graph is what turns "a feed of signals" into "a map."
3. **Phase 14 — Calibration & Utility as a Public Trust Surface.** Maps already
   computes `confidence_calibration_error` and `final_signal_utility_score` but never
   exposes them. Publishing calibration is the single strongest trust differentiator
   in a market full of unfalsifiable claims, and it is the precondition for any
   future third-party / marketplace consumption.

These phases do not change the v1 architecture, dependency direction (v1 §4), or the
producer/consumer boundary. They deepen existing objects.

---

## Phase 12: Outcome Scoring Rigor

**Problem.** `_score_accuracy` applies fixed additive weights (+0.4 matching stories,
+0.3 exchange flow, +0.2 stablecoin, +0.1 no-contradiction, −0.3 per contradiction)
and thresholds correctness at `prediction_accuracy >= 0.6`. The v1 spec itself calls
this "approximate." Risks:

- **Unfalsifiable scoring.** The signal generator and the outcome scorer can share
  the same priors (both reason over the same stories), so a signal can be scored
  "correct" because the same evidence that motivated it persisted — not because the
  prediction realized. This inflates accuracy and poisons training data.
- **No held-out validation.** Weights were chosen by intuition and never tested
  against historical realized outcomes.
- **Single method.** There is no independent cross-check, so systematic bias is
  invisible.

### Ticket MAPS-1201: Quantitative realized-outcome scorer

**Goal:** Add a scoring path that measures whether the prediction *realized* in
measurable on-chain/market terms, independent of whether confirming stories fired.

**Tasks:**

- Implement `jobs/scoring/quantitative_scorer.py`.
- For `capital_migration` / `destination_prediction` signals, compute realized
  directional flow magnitude over the evaluation window from raw exchange-flow and
  stablecoin series (not from story presence): did net flow move origin→destination
  in the predicted direction, and by a magnitude consistent with the predicted
  `expected_flow_magnitude`?
- Return a `realized_score ∈ [0,1]` plus the raw measured deltas in `notes`.
- This scorer must not read `stories` as evidence — only quantitative series — so it
  is statistically independent of the story-based heuristic.

**Acceptance Criteria:**

- Scorer produces a `realized_score` from quantitative series alone.
- Scorer never references story IDs in its computation path.
- Raw measured deltas are recorded for audit.

### Ticket MAPS-1202: Dual-scorer agreement and divergence logging

**Goal:** Run the v1 heuristic scorer and the MAPS-1201 quantitative scorer in
parallel and treat disagreement as signal, not noise.

**Tasks:**

- Extend `PredictionOutcome` with: `heuristic_accuracy`, `quantitative_accuracy`,
  `scorer_agreement` (abs difference), `scoring_method` (`heuristic` |
  `quantitative` | `blended`), and **`consumer_exposure`** (count of downstream
  agents/actions that acted on this signal before the evaluation window closed).
- `map_prediction_correct` becomes a blend: require both scorers above threshold for
  a confident `true`; flag `disputed` when they diverge beyond a configurable delta.
- Log all `disputed` outcomes to a review queue for human/audit sampling.
- Decompose accuracy into `exogenous_accuracy` (consumer_exposure = 0) vs.
  `induced_accuracy` (consumer_exposure > 0) so the training export can filter
  self-fulfilling signal examples (see MAPS-1204).

**Why consumer_exposure must be captured now:** once many agents act on the same
signal, the outcome scorer will misread self-fulfillment as accuracy and train the
adapter toward herd-inducing outputs. The only defense is logging exposure *before*
it becomes non-zero in production. It is nearly free to add as a schema field today
and impossible to backfill reliably later.

**Acceptance Criteria:**

- Both scores persist on every outcome row.
- `consumer_exposure` is populated from Phase 8 action-linkage data when available;
  defaults to 0 (not null) so the column is always queryable.
- Divergent outcomes are flagged `disputed` and excluded from training export by
  default (see MAPS-1204).
- Agreement rate and exogenous-vs-induced accuracy split are queryable over time
  (they are system-health metrics).

### Ticket MAPS-1203: Backtest the rubric against held-out history

**Goal:** Replace intuition-chosen weights with weights validated against realized
history.

**Tasks:**

- Implement `jobs/backtest_scoring_rubric.py` (distinct from the existing
  `backtest_navigation_predictions.py`, which backtests *predictions*; this backtests
  the *scorer*).
- Take a held-out window of historical signals with known realized outcomes, sweep
  the rubric weights, and report which weighting best predicts realized outcomes.
- Output a calibration report: heuristic accuracy vs. quantitative ground truth,
  per signal_type.
- Make rubric weights configurable via `.env` / config, not hard-coded constants.

**Acceptance Criteria:**

- Weights are loaded from config, not literals in `_score_accuracy`.
- Backtest report shows heuristic-vs-quantitative agreement per signal type.
- A documented procedure exists for re-tuning weights as history accumulates.

### Ticket MAPS-1204: Training-export quality gate

**Goal:** Stop low-confidence ground truth from contaminating the adapter dataset.

**Tasks:**

- In `jobs/export_training_examples.py`, exclude `disputed` outcomes by default and
  add a `--min-scorer-agreement` filter.
- Tag each exported example with the `scoring_method` that produced its label.

**Acceptance Criteria:**

- Disputed-label examples are excluded unless explicitly included via flag.
- Each training example carries provenance of how its label was derived.

---

## Phase 13: TrafficState as a Flow Graph

**Problem.** `schemas/traffic_state.py` models state as flat lists (`dominant_flows`,
`congestion_zones`, `top_destinations`). There is no persistent graph, no notion of
edges strengthening/decaying over time, and no spatial query surface. The map cannot
be navigated — only listed.

### Ticket MAPS-1301: FlowGraph state object

**Goal:** Introduce a graph representation of capital flow as the central state object.

**Tasks:**

- Add `schemas/flow_graph.py`: nodes are capital locations (sectors, protocols,
  asset clusters, exchanges, stablecoins); edges are directed flows with
  `strength`, `direction`, `confidence`, and `last_updated`.
- Nodes carry `congestion`, `hazard`, and `inflow/outflow` attributes derived from
  active signals.
- A `FlowGraph` is assembled by the runner from current NavigationSignals +
  RoutePredictions + TrafficState each cycle and persisted (append-only snapshots,
  per v1 §4.4 / rule 10).

**Acceptance Criteria:**

- FlowGraph validates against a strict schema.
- Each snapshot links the signal IDs that produced each edge (auditability).
- Snapshots are append-only with explicit IDs.

### Ticket MAPS-1302: Temporal edge dynamics

**Goal:** Let the graph express acceleration/decay — the precondition for the
deferred `narrative_acceleration` signal type (v1 §3.6).

**Tasks:**

- Compute per-edge deltas between consecutive snapshots (strengthening, weakening,
  newly-formed, closing).
- Surface `route_emergence` / `route_closure` directly from edge births/deaths.

**Acceptance Criteria:**

- Edge deltas are computed without look-ahead (no future snapshot used to score a
  past edge).
- Newly-formed and closing edges are flagged.

### Ticket MAPS-1303: Spatial query API

**Goal:** Make the graph queryable the way an agent would actually navigate it.

**Tasks:**

- Add `GET /api/maps/graph` (current snapshot) and `GET /api/maps/graph/around/:node`
  (subgraph: what flows into/out of a node, N hops).
- Support "downstream of X" and "what is converging on Y" queries — the questions a
  consumer agent actually asks.

**Acceptance Criteria:**

- API returns a valid subgraph for a given node.
- Empty/unknown nodes are handled gracefully.
- Response shape is documented for agent consumers.

### Ticket MAPS-1304: Render the map in the UI

**Goal:** Replace the table-first home with the graph as the primary surface.

**Tasks:**

- Add a `FlowMap` component (force-directed or sankey) on Maps Home; nodes sized by
  capital, edges by flow strength, colored by hazard/congestion.
- Tables become drill-downs from the graph, not the entry point.

**Acceptance Criteria:**

- Maps Home renders the live flow graph.
- Clicking a node opens its signals/routes.
- Graceful empty state.

---

## Phase 14: Calibration & Utility as a Public Trust Surface

**Problem.** `confidence_calibration_error` (SignalUtilityScore §10.5) and
`final_signal_utility_score` are computed but never surfaced. The most credible thing
Maps can say — "when we say 0.8, we're right ~78% of the time" — is invisible.

### Ticket MAPS-1401: Calibration aggregation job

**Goal:** Compute calibration curves from scored outcomes.

**Tasks:**

- Implement `jobs/compute_calibration_curves.py`.
- Bucket scored signals by predicted confidence; compute realized hit-rate per bucket,
  per signal_type and overall.
- Persist append-only calibration snapshots with sample sizes.

**Acceptance Criteria:**

- Curves computed per signal type and overall.
- Buckets include sample size (no claims on thin data).
- Snapshots are timestamped and append-only.

### Ticket MAPS-1402: Public calibration + utility API

**Goal:** Expose trust metrics through the main E3D endpoint (v1 §15 conventions).

**Tasks:**

- Add `GET /api/maps/calibration` (current curves + history).
- Add `final_signal_utility_score` and calibration-bucket hit-rate to
  `GET /api/maps/signals` responses so consumers can weight signals by proven track
  record.

**Acceptance Criteria:**

- Calibration endpoint returns curves with sample sizes.
- Signal responses carry a track-record field consumers can filter on.

### Ticket MAPS-1403: Calibration dashboard

**Goal:** Make the track record the headline of the human UI.

**Tasks:**

- Add a `/calibration` page: reliability diagram (predicted vs. realized), hit-rate
  over time, utility-score distribution, scorer-agreement trend (from Phase 12).

**Acceptance Criteria:**

- Reliability diagram renders from `/api/maps/calibration`.
- Page surfaces sample sizes and the dual-scorer agreement metric.

---

## Sequencing

```text
Phase 12 (scoring rigor)   -> do first; everything downstream depends on label quality
Phase 14 (calibration)     -> do second; it consumes Phase 12 outputs and is the trust story
Phase 13 (flow graph)      -> parallelizable; product/demo leverage, lower data risk
```

Phases 12 and 14 are the moat (trustworthy compounding data). Phase 13 is the
product/demo surface. If resources are constrained, ship 12 + 14 before 13.

---

## Out of scope (tracked separately)

The "marketplace / rating-agency for predictions" and external paid third-party
consumers are deliberately **not** ticketed here. They are a business-model decision,
not an implementation phase, and they become possible only once Phases 12 and 14 make
the utility score and calibration credible and public. Revisit after 14 ships with
≥30 days of calibration history.
