# E3D Maps: Navigation Intelligence for Autonomous Finance

## Implementation Specification With Phased Feature Tickets

**Project:** E3D Maps  
**GitHub Repository:** `e3d-maps`  
**UI URL:** `https://maps.e3d.ai`  
**Primary Public API Surface:** main `e3d.ai` endpoint, under `/api/maps/...`  
**Primary Runtime:** Qwen base model with a Maps-specific adapter  
**Primary Object:** `NavigationSignal`  
**Target Consumers:** trading agents, treasury agents, research agents, future third-party agents, and human supervisors  
**Spec Version:** v2  

---

## 0. Implementation Agent Instructions

This document is intended to be implemented by an AI coding agent.

Follow these rules:

1. Build incrementally by phase.
2. Do not create circular runtime dependencies between `e3d-maps` and `e3d-agent-trading-floor`.
3. Treat E3D Maps agents as **internal producer agents**.
4. Treat trading agents and future user agents as **consumer agents** of Maps APIs.
5. Keep the public Maps API routes in the main `e3d` endpoint for v1.
6. Keep the Maps UI, Maps runner, Maps agents, prompts, schemas, and training loop in the new `e3d-maps` repo.
7. Prefer strict JSON schemas for all Qwen outputs.
8. Validate every agent output before writing to ClickHouse.
9. Do not add security-group, firewall, or manual AWS setup tasks to this spec. Those are handled outside this implementation spec.
10. When in doubt, favor append-only database writes and explicit IDs linking signals, stories, theses, actions, outcomes, and verdicts.

---

## 1. Executive Summary

E3D Maps is a separate application and agentic intelligence layer that consumes existing E3D stories, theses, wallet intelligence, market intelligence, transaction data, and trading/action/outcome records to generate forward-looking navigation intelligence for autonomous finance.

The current E3D story pipeline detects what happened on-chain. E3D Maps predicts what is likely to happen next.

The core analogy:

```text
Ethereum = road network
Transactions = traffic
Wallets = vehicles
Smart contracts and protocols = destinations
Liquidity = fuel
Agents = autonomous vehicles
E3D Maps = navigation intelligence layer
```

E3D Maps is not primarily a dashboard. The product is machine-readable situational awareness for agents.

---

## 2. Core Product Thesis

Autonomous financial agents will operate faster than human traders and analysts. These agents need predictive, machine-readable intelligence before they act.

The primary question changes from:

```text
What happened?
```

to:

```text
Given the current on-chain scene, what is likely to happen next, and what route should an agent consider?
```

E3D Maps exists to answer that question.

---

## 3. Architectural Decision Summary

### 3.1 Repositories

Create a new repo:

```text
e3d-maps
```

The existing repos remain:

```text
e3d
e3d-agent-trading-floor
```

### 3.2 Deployment URLs

```text
maps.e3d.ai                    -> E3D Maps human UI
api.e3d.ai or e3d.ai/api/maps   -> public Maps APIs through existing E3D endpoint
```

Use the main E3D endpoint for `/api/maps/...` routes in v1.

### 3.3 Main Integration Points With `e3d`

The `e3d` repo owns:

```text
nginx/default or nginx site config
spacepacket endpoint
/api/maps/... public API routes
/api/story-types public story taxonomy routes
ClickHouse read services for Maps API responses
```

The `e3d-maps` repo owns:

```text
Maps UI
Maps runner
Maps agents
Qwen Maps adapter orchestration
Maps prompts
Maps schemas
Maps training export
Maps outcome scoring jobs
ClickHouse insert/write client for Maps-generated data
```

---

## 4. No Chicken-and-Egg Rule

There is a potential circular dependency:

```text
e3d-maps can learn from e3d-trade actions/outcomes/verdicts.
e3d-trade can consume e3d-maps NavigationSignals like any other consumer agent.
```

This is not a problem if the dependencies are layered correctly.

### 4.1 Correct Dependency Direction

Use this order:

```text
E3D Core Data
  -> Story Scripts
  -> Theses
  -> Maps Agents
  -> NavigationSignals / RoutePredictions
  -> Public Maps APIs
  -> Trading Agents and other consumer agents
  -> Actions / Outcomes / Verdicts
  -> Maps Calibration Jobs
  -> Improved Maps adapter training data
```

### 4.2 Avoid Direct Repo Coupling

Do not allow `e3d-maps` and `e3d-agent-trading-floor` to directly import each other's code.

Use shared database records and public/internal APIs as the contract.

Correct:

```text
e3d-maps reads historical trade/action/outcome/verdict records from ClickHouse or E3D APIs.
e3d-agent-trading-floor reads NavigationSignals from /api/maps/signals.
```

Incorrect:

```text
e3d-maps imports trading app modules.
e3d-agent-trading-floor imports maps runner modules.
Both apps require the other app to be running in the same process.
```

### 4.3 Bootstrapping Sequence

The system should be buildable in this order:

```text
1. Build Maps schemas and tables.
2. Build Maps runner that consumes stories/theses only.
3. Generate NavigationSignals without using trading outcomes.
4. Expose /api/maps/... from main E3D endpoint.
5. Let trading agents consume Maps APIs.
6. Link future trading actions back to NavigationSignal IDs.
7. Add Maps calibration from trading outcomes.
8. Export Maps training examples.
9. Fine-tune or update Maps adapter.
```

This removes the chicken-and-egg problem.

### 4.4 Runtime Rule

Maps does not require trading output to run.

Trading can optionally consume Maps output.

Maps can later learn from trading output.

Therefore:

```text
Maps is upstream at inference time.
Trading outcomes are downstream feedback at training/calibration time.
```

---

## 5. Layer Distinctions

### 5.1 Story Pipeline

The existing E3D story architecture is deterministic.

```text
Raw chain data
  -> scheduled .js story scripts
  -> pattern detection rules
  -> Story objects
  -> database / API / UI
```

Stories answer:

```text
Did a known pattern occur?
```

Stories are sensors.

### 5.2 Maps Agents

E3D Maps is agentic and predictive.

```text
Stories + theses + wallet data + market data + selected outcomes
  -> Maps agents
  -> Qwen reasoning with E3D APIs
  -> NavigationSignals / RoutePredictions / Hazards
  -> ClickHouse
  -> Maps APIs
```

Maps agents answer:

```text
Given the current scene, what is likely to happen next?
```

Maps agents are navigators.

### 5.3 Trading Agents

Trading agents are downstream consumers and actors.

```text
NavigationSignals + market data + trading thesis
  -> trading agent
  -> action
  -> outcome
  -> verdict
```

Trading agents are drivers / capital allocators.

---

## 6. High-Level Architecture

```text
                            +----------------------+
                            | Existing E3D Platform |
                            | stories / theses      |
                            | wallets / tx / tokens |
                            | actions / outcomes    |
                            +----------+-----------+
                                       |
                                       | e3d.ai API reads / DB reads
                                       v
+----------------------+     +-------------------------+
| Qwen Base Model       |<--->| e3d-maps Runner         |
| Maps Adapter          |     | scheduler + validators  |
+----------------------+     +-----------+-------------+
                                          |
                                          | validated inserts
                                          v
                             +--------------------------+
                             | ClickHouse               |
                             | NavigationSignals        |
                             | RoutePredictions         |
                             | TrafficStates            |
                             | PredictionOutcomes       |
                             | SignalUtilityScores      |
                             +------------+-------------+
                                          |
                                          | reads
                                          v
                             +--------------------------+
                             | e3d main endpoint         |
                             | /api/maps/...             |
                             | /api/story-types          |
                             +------------+-------------+
                                          |
                         +----------------+----------------+
                         |                                 |
                         v                                 v
              +---------------------+          +-------------------------+
              | maps.e3d.ai UI       |          | Consumer Agents          |
              | human supervision    |          | trading / treasury / etc |
              +---------------------+          +-------------------------+
```

---

## 7. Qwen Adapter Architecture

There is one shared Qwen base model and multiple task-specific adapters.

```text
Qwen Base Model
  -> Trading Adapter
      -> trading agents
      -> trade decisions
      -> actions / outcomes / verdicts

  -> Maps Adapter
      -> maps agents
      -> NavigationSignals
      -> RoutePredictions
      -> TrafficStates
      -> PredictionOutcomes
```

### 7.1 Coordination Rule

Do not run the trading adapter and Maps adapter at the same time on the same constrained Qwen machine/GPU unless the machine supports concurrent serving.

Use a scheduler/orchestrator.

Recommended cycle:

```text
1. Existing story scripts run.
2. Thesis updates run.
3. Qwen loads Maps adapter.
4. Maps agents generate NavigationSignals.
5. Maps output is validated and written to ClickHouse.
6. Qwen unloads Maps adapter.
7. Qwen loads Trading adapter.
8. Trading agents consume latest Maps APIs and make decisions.
9. Trading actions/outcomes/verdicts are written.
10. Outcome scoring jobs run later.
```

### 7.2 Shared Ontology Rule

Maps and trading adapters must use shared definitions for:

```text
confidence
risk_level
signal_strength
time_horizon
market_state
outcome_score
verdict
```

Do not let each adapter invent its own meaning for these fields.

---

## 8. Repository Structure For `e3d-maps`

Create:

```text
e3d-maps/
  README.md
  CLAUDE.md
  .env.example
  package.json
  pyproject.toml or requirements.txt

  ui/
    src/
      App.jsx
      pages/
        MapsHome.jsx
        NavigationSignals.jsx
        RoutePredictions.jsx
        Hazards.jsx
        TrafficState.jsx
        SignalDetail.jsx
      components/
        SignalCard.jsx
        TrafficMapPanel.jsx
        RoutePredictionTable.jsx
        HazardList.jsx
        ConfidenceBadge.jsx
        EvidenceList.jsx
      api/
        mapsApiClient.js

  agents/
    runner.py
    scheduler.py
    qwen_orchestrator.py
    adapter_manager.py
    base_agent.py
    capital_migration_agent.py
    congestion_agent.py
    route_hazard_agent.py
    destination_prediction_agent.py
    confidence_scoring_agent.py
    outcome_scoring_agent.py

  clients/
    e3d_api_client.py
    clickhouse_client.py
    qwen_client.py
    trading_outcome_client.py

  schemas/
    navigation_signal.py
    route_prediction.py
    traffic_state.py
    route_hazard.py
    prediction_outcome.py
    signal_utility_score.py
    story_type_definition.py
    shared_enums.py

  prompts/
    maps_system_prompt.md
    capital_migration_agent.md
    congestion_agent.md
    route_hazard_agent.md
    destination_prediction_agent.md
    confidence_scoring_agent.md
    outcome_scoring_agent.md

  db/
    migrations/
    seed_story_types.py

  jobs/
    generate_navigation_signals.py
    score_pending_predictions.py
    compute_signal_utility_scores.py
    export_training_examples.py
    backtest_navigation_predictions.py

  training/
    datasets/
    exports/

  tests/
    unit/
    integration/
    fixtures/
```

---

## 9. Integration Points In `e3d` Repo

Update the existing `e3d` repo with:

```text
e3d/
  nginx/
    default

  endpoint/spacepacket/
    routes/
      maps.js
      storyTypes.js

    services/
      mapsService.js
      storyTypeService.js

    schemas/
      mapsSchemas.js
      storyTypeSchemas.js
```

The exact folder names may differ. Use existing endpoint conventions in the `e3d` repo.

### 9.1 Nginx Requirement

Add `maps.e3d.ai` server block that serves the built `e3d-maps` UI.

Also proxy public Maps API routes to the existing `spacepacket` endpoint.

Public routes:

```text
GET /api/maps/state
GET /api/maps/signals
GET /api/maps/signals/:id
GET /api/maps/routes
GET /api/maps/hazards
GET /api/maps/predictions
GET /api/maps/destinations
GET /api/maps/congestion
GET /api/story-types
GET /api/story-types/:type
```

---

## 10. Core Data Models

### 10.1 NavigationSignal

Primary atomic object produced by Maps agents.

```json
{
  "id": "navsig_01J...",
  "signal_type": "capital_migration",
  "question": "Where is capital likely moving over the next 24 hours?",
  "answer": "Stablecoin inflows and whale outflows suggest capital rotation toward ETH DeFi.",
  "origin": "stablecoins",
  "destination": "ETH_DEFI",
  "asset_scope": ["ETH", "AAVE"],
  "chain_scope": ["ethereum"],
  "time_horizon_hours": 24,
  "confidence": 0.78,
  "risk_level": "medium",
  "signal_strength": "strong",
  "market_state": "risk_on",
  "supporting_story_ids": ["story_123", "story_456"],
  "supporting_thesis_ids": ["thesis_789"],
  "supporting_action_ids": [],
  "supporting_outcome_ids": [],
  "evidence": [
    {
      "type": "story",
      "id": "story_123",
      "summary": "Stablecoin inflows increased across tracked wallets."
    }
  ],
  "recommended_route": {
    "origin": "stablecoins",
    "destination": "ETH_DEFI",
    "route_type": "risk_adjusted_capital_rotation"
  },
  "recommended_action": "monitor_or_increase_eth_defi_exposure",
  "created_by_agent": "capital_migration_agent",
  "model": "qwen",
  "adapter": "maps-v0.1",
  "schema_version": "1.0",
  "outcome_status": "pending",
  "created_at": "2026-06-08T00:00:00Z"
}
```

Required fields:

```text
id
signal_type
question
answer
time_horizon_hours
confidence
risk_level
supporting_story_ids
created_by_agent
model
adapter
schema_version
outcome_status
created_at
```

### 10.2 RoutePrediction

Represents a predicted destination or path for capital.

```json
{
  "id": "route_01J...",
  "navigation_signal_id": "navsig_01J...",
  "route_type": "destination_prediction",
  "origin": "stablecoins",
  "destination": "ETH_DEFI",
  "expected_flow_direction": "inflow",
  "expected_flow_magnitude": "moderate",
  "time_horizon_hours": 24,
  "confidence": 0.74,
  "hazards": ["leverage_elevated"],
  "supporting_story_ids": ["story_123"],
  "created_at": "2026-06-08T00:00:00Z"
}
```

### 10.3 TrafficState

A point-in-time summary of on-chain traffic conditions.

```json
{
  "id": "traffic_01J...",
  "scope": "ethereum",
  "market_state": "risk_on",
  "dominant_flows": [
    {
      "origin": "stablecoins",
      "destination": "ETH_DEFI",
      "strength": "strong"
    }
  ],
  "congestion_zones": ["MEME_TOKENS"],
  "hazards": ["exchange_inflow_rising"],
  "top_destinations": [
    {
      "destination": "ETH_DEFI",
      "confidence": 0.78
    }
  ],
  "created_by_agent": "traffic_state_agent",
  "created_at": "2026-06-08T00:00:00Z"
}
```

### 10.4 PredictionOutcome

Scores whether a prior prediction became true.

```json
{
  "id": "outcome_01J...",
  "navigation_signal_id": "navsig_01J...",
  "route_prediction_id": "route_01J...",
  "evaluation_window_hours": 24,
  "prediction_accuracy": 0.81,
  "realized_direction": "inflow",
  "realized_magnitude": "moderate",
  "map_prediction_correct": true,
  "notes": "ETH DeFi inflows increased after signal creation.",
  "created_by_agent": "outcome_scoring_agent",
  "created_at": "2026-06-09T00:00:00Z"
}
```

### 10.5 SignalUtilityScore

Connects Maps signals to downstream trading usefulness without confusing bad execution with bad navigation.

```json
{
  "id": "utility_01J...",
  "navigation_signal_id": "navsig_01J...",
  "sample_size": 12,
  "prediction_accuracy": 0.82,
  "economic_utility": 0.74,
  "risk_reduction_utility": 0.66,
  "confidence_calibration_error": 0.08,
  "execution_adjusted_utility": 0.71,
  "final_signal_utility_score": 0.76,
  "linked_action_ids": ["action_123", "action_456"],
  "linked_outcome_ids": ["trade_outcome_123"],
  "created_at": "2026-06-09T00:00:00Z"
}
```

Important rule:

```text
A losing trade does not automatically mean the Maps signal was wrong.
```

Evaluate separately:

```text
map_prediction_correct
trade_execution_correct
thesis_correct
timing_correct
risk_management_correct
economic_utility
```

### 10.6 StoryTypeDefinition

Used by `/api/story-types` to explain E3D's vocabulary to humans and agents.

```json
{
  "story_type": "capital_migration",
  "display_name": "Capital Migration",
  "category": "traffic",
  "human_meaning": "Capital appears to be moving from one sector, asset, protocol, or behavior cluster to another.",
  "agent_meaning": "Use this story type as evidence of changing capital routes and potential destination probabilities.",
  "inputs": ["wallet_flows", "token_transfers", "stablecoin_activity", "exchange_flows"],
  "outputs": ["origin", "destination", "flow_direction", "flow_strength"],
  "example_questions": [
    "Where is capital migrating?",
    "Which destination is gaining probability?"
  ],
  "related_navigation_signal_types": ["capital_migration", "destination_prediction"],
  "schema_version": "1.0"
}
```

---

## 11. Maps Signal Types

Implement these v1 signal types:

```text
capital_migration
congestion_formation
route_emergence
route_closure
route_hazard
destination_prediction
liquidity_forecast
narrative_acceleration
agent_swarm_formation
capital_conviction
```

### 11.1 capital_migration

Purpose:

```text
Detect where capital appears to be moving from and to.
```

Example:

```text
Stablecoins -> ETH DeFi
Meme tokens -> stablecoins
Ethereum L1 -> Base
```

### 11.2 congestion_formation

Purpose:

```text
Detect crowding, over-concentration, or traffic jams before they become dangerous.
```

### 11.3 route_emergence

Purpose:

```text
Detect a new path for capital, such as a new protocol, bridge, L2, token utility, or liquidity venue.
```

### 11.4 route_closure

Purpose:

```text
Detect a path becoming unsafe, illiquid, unavailable, or unattractive.
```

### 11.5 route_hazard

Purpose:

```text
Detect risk forming along a capital route.
```

Hazard examples:

```text
exchange_inflow_rising
bridge_risk
liquidity_drain
leverage_elevated
whale_distribution
wash_activity
contract_risk
```

### 11.6 destination_prediction

Purpose:

```text
Predict where capital is likely to arrive next.
```

### 11.7 liquidity_forecast

Purpose:

```text
Forecast inflows, outflows, or liquidity scarcity over a defined time horizon.
```

### 11.8 narrative_acceleration

Purpose:

```text
Detect second-derivative narrative changes, not just static narratives.
```

### 11.9 agent_swarm_formation

Purpose:

```text
Detect many unrelated or semi-related wallets/agents converging on similar routes, assets, or protocols.
```

### 11.10 capital_conviction

Purpose:

```text
Distinguish between testing, staging, partial commitment, and full commitment.
```

---

## 12. Maps Agent Design

Each Maps agent must:

1. Receive a specific question.
2. Pull evidence through E3D APIs or database clients.
3. Reason using Qwen Maps adapter.
4. Return strict JSON matching a schema.
5. Include confidence, evidence references, and time horizon.
6. Avoid unsupported claims.
7. Output no markdown in machine responses.

### 12.1 Capital Migration Agent

Question:

```text
Where is capital likely moving over the next time horizon?
```

Inputs:

```text
recent stories
recent theses
stablecoin activity
exchange flows
wallet cluster activity
prior capital migration signals
selected trading outcomes for calibration
```

Output:

```text
NavigationSignal with signal_type = capital_migration
optional RoutePrediction
```

### 12.2 Congestion Agent

Question:

```text
Where is capital, attention, leverage, or wallet activity becoming crowded?
```

Output:

```text
NavigationSignal with signal_type = congestion_formation
```

### 12.3 Route Hazard Agent

Question:

```text
Which routes are becoming dangerous or lower quality?
```

Output:

```text
NavigationSignal with signal_type = route_hazard or route_closure
```

### 12.4 Destination Prediction Agent

Question:

```text
Which destinations are gaining probability over the selected time horizon?
```

Output:

```text
NavigationSignal with signal_type = destination_prediction
RoutePrediction rows
```

### 12.5 Confidence Scoring Agent

Question:

```text
How confident should the system be in this signal, given the evidence and prior calibration?
```

Output:

```text
confidence between 0.0 and 1.0
confidence explanation
calibration notes
```

### 12.6 Outcome Scoring Agent

Question:

```text
Did this prior NavigationSignal or RoutePrediction become true within its evaluation window?
```

Output:

```text
PredictionOutcome
```

---

## 13. Runner / Scheduler Behavior

The runner is the main process in `e3d-maps`.

It should coordinate questions, agents, Qwen adapter usage, validation, and ClickHouse writes.

### 13.1 Main Loop

Pseudo-flow:

```text
while true:
  load config
  check whether Maps cycle should run
  load Qwen Maps adapter
  fetch recent E3D context
  run configured Maps agents
  parse strict JSON outputs
  validate schemas
  write NavigationSignals / RoutePredictions / TrafficStates to ClickHouse
  unload or release Maps adapter
  sleep until next cycle
```

### 13.2 Suggested v1 Cadence

```text
generate_navigation_signals: every 5 minutes
score_pending_predictions: every 15 to 60 minutes
compute_signal_utility_scores: hourly or daily
export_training_examples: daily
```

Make cadence configurable through `.env`.

### 13.3 Question Queue

The runner should run questions, not just agents.

Example queue:

```json
[
  {
    "agent": "capital_migration_agent",
    "question": "Where is capital likely moving over the next 24 hours?",
    "time_horizon_hours": 24
  },
  {
    "agent": "congestion_agent",
    "question": "Where is congestion forming right now?",
    "time_horizon_hours": 6
  },
  {
    "agent": "route_hazard_agent",
    "question": "Which capital routes are becoming unsafe?",
    "time_horizon_hours": 24
  },
  {
    "agent": "destination_prediction_agent",
    "question": "Which destinations are gaining probability?",
    "time_horizon_hours": 24
  }
]
```

---

## 14. ClickHouse Tables

Create tables for Maps outputs. Use exact existing E3D ClickHouse conventions where possible.

### 14.1 NavigationSignals

Suggested columns:

```text
id String
signal_type LowCardinality(String)
question String
answer String
origin String
destination String
asset_scope Array(String)
chain_scope Array(String)
time_horizon_hours UInt32
confidence Float32
risk_level LowCardinality(String)
signal_strength LowCardinality(String)
market_state LowCardinality(String)
supporting_story_ids Array(String)
supporting_thesis_ids Array(String)
supporting_action_ids Array(String)
supporting_outcome_ids Array(String)
evidence_json String
recommended_route_json String
recommended_action String
created_by_agent LowCardinality(String)
model LowCardinality(String)
adapter LowCardinality(String)
schema_version LowCardinality(String)
outcome_status LowCardinality(String)
created_at DateTime
inserted_at DateTime DEFAULT now()
```

### 14.2 RoutePredictions

```text
id String
navigation_signal_id String
route_type LowCardinality(String)
origin String
destination String
expected_flow_direction LowCardinality(String)
expected_flow_magnitude LowCardinality(String)
time_horizon_hours UInt32
confidence Float32
hazards Array(String)
supporting_story_ids Array(String)
created_by_agent LowCardinality(String)
model LowCardinality(String)
adapter LowCardinality(String)
schema_version LowCardinality(String)
created_at DateTime
inserted_at DateTime DEFAULT now()
```

### 14.3 TrafficStates

```text
id String
scope String
market_state LowCardinality(String)
dominant_flows_json String
congestion_zones Array(String)
hazards Array(String)
top_destinations_json String
created_by_agent LowCardinality(String)
model LowCardinality(String)
adapter LowCardinality(String)
schema_version LowCardinality(String)
created_at DateTime
inserted_at DateTime DEFAULT now()
```

### 14.4 PredictionOutcomes

```text
id String
navigation_signal_id String
route_prediction_id String
evaluation_window_hours UInt32
prediction_accuracy Float32
realized_direction LowCardinality(String)
realized_magnitude LowCardinality(String)
map_prediction_correct UInt8
notes String
created_by_agent LowCardinality(String)
model LowCardinality(String)
adapter LowCardinality(String)
schema_version LowCardinality(String)
created_at DateTime
inserted_at DateTime DEFAULT now()
```

### 14.5 SignalUtilityScores

```text
id String
navigation_signal_id String
sample_size UInt32
prediction_accuracy Float32
economic_utility Float32
risk_reduction_utility Float32
confidence_calibration_error Float32
execution_adjusted_utility Float32
final_signal_utility_score Float32
linked_action_ids Array(String)
linked_outcome_ids Array(String)
created_at DateTime
inserted_at DateTime DEFAULT now()
```

### 14.6 StoryTypeDefinitions

```text
story_type String
display_name String
category LowCardinality(String)
human_meaning String
agent_meaning String
inputs Array(String)
outputs Array(String)
example_questions Array(String)
related_navigation_signal_types Array(String)
schema_version LowCardinality(String)
created_at DateTime
updated_at DateTime
```

---

## 15. Public Maps APIs In Main E3D Endpoint

Implement these routes in the existing `spacepacket` endpoint.

### 15.1 GET /api/maps/state

Returns latest TrafficState.

Response:

```json
{
  "status": "ok",
  "state": {
    "id": "traffic_01J...",
    "scope": "ethereum",
    "market_state": "risk_on",
    "dominant_flows": [],
    "congestion_zones": [],
    "hazards": [],
    "top_destinations": [],
    "created_at": "2026-06-08T00:00:00Z"
  }
}
```

### 15.2 GET /api/maps/signals

Query params:

```text
signal_type
asset
chain
time_horizon_hours
min_confidence
limit
offset
```

Returns recent NavigationSignals.

### 15.3 GET /api/maps/signals/:id

Returns a single NavigationSignal with evidence references.

### 15.4 GET /api/maps/routes

Returns RoutePredictions.

### 15.5 GET /api/maps/hazards

Returns route hazards and route closures.

### 15.6 GET /api/maps/predictions

Returns active predictions and their pending/scored status.

### 15.7 GET /api/maps/destinations

Returns ranked predicted destinations.

### 15.8 GET /api/maps/congestion

Returns congestion-related signals.

### 15.9 GET /api/story-types

Returns StoryTypeDefinition list.

### 15.10 GET /api/story-types/:type

Returns one StoryTypeDefinition.

---

## 16. Maps UI Requirements

The UI at `maps.e3d.ai` is for human supervision and product demonstration.

### 16.1 Pages

Build these pages:

```text
/maps or /                 -> Maps Home / Traffic State
/signals                   -> NavigationSignals list
/signals/:id               -> Signal detail
/routes                    -> RoutePredictions
/hazards                   -> Hazards and route closures
/congestion                -> Congestion view
/story-types               -> Story taxonomy
```

### 16.2 Maps Home

Show:

```text
Current Traffic State
Top Capital Flows
Top Destinations
Active Hazards
Active Congestion
Latest High-Confidence NavigationSignals
```

### 16.3 Signal Detail

Show:

```text
question
answer
confidence
risk level
signal strength
time horizon
origin / destination
supporting stories
supporting theses
related route predictions
outcome status
utility score if available
```

---

## 17. Training Loop

The Maps training loop should create examples from:

```text
agent question
E3D API evidence
NavigationSignal answer
confidence score
realized chain outcome
trading action if linked
trading outcome if linked
verdict if linked
SignalUtilityScore
```

### 17.1 TrainingExample Format

```json
{
  "id": "train_01J...",
  "task": "capital_migration_prediction",
  "question": "Where is capital likely moving over the next 24 hours?",
  "context": {
    "story_ids": ["story_123"],
    "thesis_ids": ["thesis_456"],
    "market_state": "risk_on"
  },
  "agent_answer": {
    "navigation_signal_id": "navsig_01J...",
    "answer": "Stablecoin flows suggest rotation toward ETH DeFi.",
    "confidence": 0.78
  },
  "outcome": {
    "prediction_accuracy": 0.81,
    "map_prediction_correct": true,
    "economic_utility": 0.74
  },
  "label": "good_prediction_useful_signal",
  "created_at": "2026-06-09T00:00:00Z"
}
```

### 17.2 Export Job

Create:

```text
jobs/export_training_examples.py
```

It should export JSONL.

Output path:

```text
training/exports/maps_training_examples_YYYYMMDD.jsonl
```

---

## 18. Phase Tickets

## Phase 0: Repository Bootstrap

### Ticket MAPS-0001: Create `e3d-maps` repo skeleton

**Goal:** Create the repo structure for the Maps app.

**Tasks:**

- Create `README.md`.
- Create `CLAUDE.md` with project context.
- Create `.env.example`.
- Create folders listed in Section 8.
- Add basic install/run instructions.

**Acceptance Criteria:**

- Repo can be cloned.
- Folder structure exists.
- `README.md` explains E3D Maps in one page.
- `CLAUDE.md` tells an AI coding agent the project purpose and rules.

---

### Ticket MAPS-0002: Define shared schemas and enums

**Goal:** Add schema definitions for all Maps objects.

**Tasks:**

- Implement `schemas/shared_enums.py`.
- Implement `schemas/navigation_signal.py`.
- Implement `schemas/route_prediction.py`.
- Implement `schemas/traffic_state.py`.
- Implement `schemas/prediction_outcome.py`.
- Implement `schemas/signal_utility_score.py`.
- Add validation tests.

**Acceptance Criteria:**

- Invalid confidence values are rejected.
- Missing required fields are rejected.
- Unknown signal types are rejected unless explicitly configured.
- Unit tests pass.

---

## Phase 1: ClickHouse Maps Storage

### Ticket MAPS-0101: Add ClickHouse migrations for Maps tables

**Goal:** Create ClickHouse tables for Maps objects.

**Tasks:**

- Add migrations for:
  - `NavigationSignals`
  - `RoutePredictions`
  - `TrafficStates`
  - `PredictionOutcomes`
  - `SignalUtilityScores`
  - `StoryTypeDefinitions`
- Use MergeTree or the existing E3D table engine convention.
- Add created/inserted timestamps.

**Acceptance Criteria:**

- Migrations run successfully.
- Tables can accept one sample row each.
- Tables can be queried from ClickHouse client.

---

### Ticket MAPS-0102: Implement ClickHouse write client

**Goal:** Let `e3d-maps` write validated Maps records to ClickHouse.

**Tasks:**

- Implement `clients/clickhouse_client.py`.
- Add insert functions:
  - `insert_navigation_signal`
  - `insert_route_prediction`
  - `insert_traffic_state`
  - `insert_prediction_outcome`
  - `insert_signal_utility_score`
- Add batch insert support.
- Add dry-run mode.

**Acceptance Criteria:**

- Client can insert sample validated records.
- Dry-run prints the rows that would be inserted.
- Client does not accept invalid schema objects.

---

## Phase 2: E3D API Clients

### Ticket MAPS-0201: Implement E3D API read client

**Goal:** Let Maps agents consume existing E3D APIs.

**Tasks:**

- Implement `clients/e3d_api_client.py`.
- Add methods:
  - `get_recent_stories`
  - `get_recent_theses`
  - `get_wallet_activity`
  - `get_token_activity`
  - `get_exchange_flows`
  - `get_market_context`
- Use existing E3D endpoint conventions.
- Add retries and timeouts.

**Acceptance Criteria:**

- Client can fetch recent stories.
- Client can fetch recent theses.
- Missing API responses are handled gracefully.

---

### Ticket MAPS-0202: Implement trading outcome read client

**Goal:** Let Maps calibration jobs read trading action/outcome/verdict data.

**Tasks:**

- Implement `clients/trading_outcome_client.py`.
- Add methods:
  - `get_recent_actions`
  - `get_recent_outcomes`
  - `get_recent_verdicts`
  - `get_actions_linked_to_navigation_signal`
- Do not require this client for initial Maps signal generation.

**Acceptance Criteria:**

- Maps runner can run without trading outcome data.
- Calibration jobs can use trading outcome data when available.

---

## Phase 3: Qwen Maps Adapter Runtime

### Ticket MAPS-0301: Implement Qwen client and adapter manager

**Goal:** Add runtime utilities for using Qwen with the Maps adapter.

**Tasks:**

- Implement `clients/qwen_client.py`.
- Implement `agents/adapter_manager.py`.
- Add config for Maps adapter path/name.
- Add placeholder support for adapter loading/unloading if actual infrastructure differs.

**Acceptance Criteria:**

- Maps runner can call Qwen with a prompt.
- Adapter name/path is configurable.
- If adapter loading is not available yet, code provides a clear stub interface.

---

### Ticket MAPS-0302: Add Maps system prompt

**Goal:** Define the core behavior of Maps agents.

**Tasks:**

- Create `prompts/maps_system_prompt.md`.
- State that Maps agents are navigators, not traders.
- Require strict JSON output.
- Require evidence references.
- Require confidence values.
- Prohibit unsupported claims.

**Acceptance Criteria:**

- Prompt clearly distinguishes observations, predictions, recommendations, and confidence.
- Prompt instructs agents to return machine-parseable JSON only.

---

## Phase 4: Maps Agents

### Ticket MAPS-0401: Implement BaseAgent

**Goal:** Create reusable agent wrapper.

**Tasks:**

- Implement `agents/base_agent.py`.
- Add methods:
  - `build_context`
  - `build_prompt`
  - `call_qwen`
  - `parse_json`
  - `validate_output`
  - `run`

**Acceptance Criteria:**

- BaseAgent can run against fixture context.
- Invalid JSON is caught.
- Invalid schema output is rejected.

---

### Ticket MAPS-0402: Implement CapitalMigrationAgent

**Goal:** Generate `capital_migration` NavigationSignals.

**Tasks:**

- Create agent file.
- Create prompt file.
- Use recent stories/theses/flows as context.
- Produce `NavigationSignal` JSON.

**Acceptance Criteria:**

- Agent produces valid `NavigationSignal` objects.
- Signal includes origin, destination, confidence, evidence, and time horizon.

---

### Ticket MAPS-0403: Implement CongestionAgent

**Goal:** Generate `congestion_formation` NavigationSignals.

**Acceptance Criteria:**

- Agent detects potential crowding/congestion from context.
- Output validates against schema.

---

### Ticket MAPS-0404: Implement RouteHazardAgent

**Goal:** Generate `route_hazard` and `route_closure` NavigationSignals.

**Acceptance Criteria:**

- Agent returns hazards with risk level and evidence.
- Output validates against schema.

---

### Ticket MAPS-0405: Implement DestinationPredictionAgent

**Goal:** Generate destination predictions and RoutePrediction rows.

**Acceptance Criteria:**

- Agent returns at least one destination prediction when evidence supports it.
- RoutePrediction rows link back to NavigationSignal IDs.

---

## Phase 5: Maps Runner

### Ticket MAPS-0501: Implement question queue

**Goal:** Configure questions that Maps agents answer each cycle.

**Tasks:**

- Add JSON/YAML config for question queue.
- Include agent name, question text, and time horizon.
- Support enabling/disabling questions.

**Acceptance Criteria:**

- Runner can load question queue.
- Disabled questions are skipped.

---

### Ticket MAPS-0502: Implement runner main loop

**Goal:** Run Maps agents continuously or on demand.

**Tasks:**

- Implement `agents/runner.py`.
- Add command-line modes:
  - `--once`
  - `--loop`
  - `--dry-run`
- Coordinate adapter loading.
- Run questions.
- Validate outputs.
- Write records.

**Acceptance Criteria:**

- `python agents/runner.py --once --dry-run` completes.
- `python agents/runner.py --once` writes sample records if configured.
- Malformed agent outputs are not written.

---

## Phase 6: Public Maps APIs In `e3d`

### Ticket E3D-MAPS-API-0601: Add Maps routes to main endpoint

**Repo:** `e3d`

**Goal:** Expose Maps records through main E3D endpoint.

**Tasks:**

- Add route file for `/api/maps/...`.
- Add service file for querying ClickHouse Maps tables.
- Add schema/response normalizers.
- Add pagination.

**Acceptance Criteria:**

- `GET /api/maps/state` returns latest TrafficState.
- `GET /api/maps/signals` returns recent NavigationSignals.
- `GET /api/maps/signals/:id` returns one signal.
- `GET /api/maps/routes` returns route predictions.
- `GET /api/maps/hazards` returns hazards.

---

### Ticket E3D-MAPS-API-0602: Add Story Types API

**Repo:** `e3d`

**Goal:** Expose story type meanings to humans and agents.

**Tasks:**

- Add `GET /api/story-types`.
- Add `GET /api/story-types/:type`.
- Read from `StoryTypeDefinitions` table or static seed source.

**Acceptance Criteria:**

- Story types return human and agent meanings.
- Related NavigationSignal types are included.

---

## Phase 7: Maps UI

### Ticket MAPS-0701: Create Maps UI shell

**Goal:** Build React UI shell for `maps.e3d.ai`.

**Tasks:**

- Create UI app if not already present.
- Add routing.
- Add API client.
- Add pages listed in Section 16.

**Acceptance Criteria:**

- UI loads at local dev URL.
- UI can call `/api/maps/state`.
- UI handles empty data gracefully.

---

### Ticket MAPS-0702: Build NavigationSignals list/detail views

**Goal:** Show generated signals for human review.

**Acceptance Criteria:**

- Signals list shows type, confidence, horizon, origin, destination, risk, created_at.
- Detail page shows evidence and linked stories/theses.

---

### Ticket MAPS-0703: Build Traffic State dashboard

**Goal:** Show the current map state.

**Acceptance Criteria:**

- Dashboard shows top flows, hazards, congestion, and destinations.
- Dashboard refreshes without full page reload or via manual refresh.

---

## Phase 8: Trading Feedback Calibration

### Ticket MAPS-0801: Link trading actions to NavigationSignals

**Goal:** Allow trading agents to record which Maps signals influenced an action.

**Repo:** likely `e3d-agent-trading-floor` and/or `e3d`

**Tasks:**

- Add optional `navigation_signal_ids` to trading action records.
- Add optional `route_prediction_ids` to trading action records.
- Preserve existing behavior if no Maps signal is used.

**Acceptance Criteria:**

- Trading actions can link to zero or more Maps signals.
- Existing trading app still works without Maps.

---

### Ticket MAPS-0802: Compute SignalUtilityScore

**Goal:** Score how useful Maps signals were for downstream trading agents.

**Tasks:**

- Implement `jobs/compute_signal_utility_scores.py`.
- Read NavigationSignals.
- Read linked trading actions/outcomes/verdicts.
- Compute:
  - prediction_accuracy
  - economic_utility
  - risk_reduction_utility
  - confidence_calibration_error
  - execution_adjusted_utility
  - final_signal_utility_score

**Acceptance Criteria:**

- Job creates SignalUtilityScore rows.
- Job does not treat all losing trades as bad Maps signals.
- Job separates map correctness from trade execution quality.

---

## Phase 9: Prediction Outcome Scoring

### Ticket MAPS-0901: Score pending predictions

**Goal:** Determine whether Maps predictions became true.

**Tasks:**

- Implement `jobs/score_pending_predictions.py`.
- Find pending signals whose time horizon has elapsed.
- Fetch realized on-chain/market/story context.
- Score prediction accuracy.
- Write PredictionOutcome.
- Update or append outcome status as needed.

**Acceptance Criteria:**

- Pending predictions become scored.
- Outcome score includes evidence and notes.
- No future-looking data is used before its timestamp.

---

## Phase 10: Training Data Export

### Ticket MAPS-1001: Export Maps training examples

**Goal:** Create JSONL training data for the Maps adapter.

**Tasks:**

- Implement `jobs/export_training_examples.py`.
- Join questions, evidence, NavigationSignals, PredictionOutcomes, and SignalUtilityScores.
- Output JSONL.

**Acceptance Criteria:**

- Export file is valid JSONL.
- Each example includes question, context, answer, confidence, and outcome.
- Examples can be filtered by utility score.

---

## Phase 11: Deployment

### Ticket MAPS-1101: Build Maps UI for `maps.e3d.ai`

**Goal:** Produce static build artifacts.

**Tasks:**

- Add production build script.
- Document output path.
- Ensure relative API calls work behind nginx.

**Acceptance Criteria:**

- UI build completes.
- Build can be served by nginx.

---

### Ticket E3D-MAPS-DEPLOY-1102: Update nginx config in `e3d` repo

**Repo:** `e3d`

**Goal:** Add `maps.e3d.ai` server block and proxy API calls.

**Tasks:**

- Update nginx config under `e3d/nginx`.
- Serve Maps UI build.
- Proxy `/api/maps/...` and `/api/story-types...` to main endpoint.

**Acceptance Criteria:**

- `maps.e3d.ai` serves the Maps UI.
- `maps.e3d.ai/api/maps/state` reaches the main endpoint.
- Existing `e3d.ai` behavior is not broken.

---

## 19. Suggested Build Order For AI Implementation Agent

Follow this exact order:

```text
1. Create e3d-maps repo skeleton.
2. Add schemas and tests.
3. Add ClickHouse migrations.
4. Add ClickHouse client with dry-run mode.
5. Add E3D API read client.
6. Add Qwen client and adapter manager stubs.
7. Add BaseAgent.
8. Add CapitalMigrationAgent first.
9. Add runner --once --dry-run mode.
10. Generate first valid NavigationSignal from fixture data.
11. Write first NavigationSignal to ClickHouse.
12. Add /api/maps/signals in e3d endpoint.
13. Add minimal Maps UI to display signals.
14. Add remaining agents.
15. Add prediction scoring.
16. Add trading feedback linking.
17. Add SignalUtilityScore.
18. Add training export.
```

---

## 20. Success Criteria For v1

E3D Maps v1 is successful when:

1. `e3d-maps` runs as a separate repo/app.
2. Maps agents generate valid NavigationSignals using Qwen Maps adapter.
3. NavigationSignals are written to ClickHouse.
4. `maps.e3d.ai` displays current traffic state and recent signals.
5. Main E3D endpoint exposes `/api/maps/...`.
6. Trading agents can consume Maps APIs without direct repo coupling.
7. Trading actions can optionally link back to NavigationSignals.
8. Maps can score its own predictions after the time horizon expires.
9. Maps can compute SignalUtilityScore from downstream outcomes.
10. Maps can export training examples for future Maps adapter improvement.

---

## 21. Strategic Framing

E3D Stories are the sensors.

E3D Maps is the navigation layer.

E3D Trading is the action layer.

```text
Stories -> Maps -> Trading -> Actions -> Outcomes -> Maps Calibration -> Better Maps
```

The compounding data asset is:

```text
agent question
+ E3D evidence
+ Maps prediction
+ confidence
+ realized outcome
+ downstream trading utility
+ verdict
```

That is the dataset that can make E3D Maps increasingly useful to autonomous financial agents.
