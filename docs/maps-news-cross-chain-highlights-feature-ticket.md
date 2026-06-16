# E3D Maps News + Cross-Chain Highlights — Feature Ticket

## Overview

The Maps homepage currently exposes rich machine-readable state but does not yet provide the
fast human read that a user wants when they open the app:

- a top-of-page headline that explains what the map is saying right now
- a clear read on cross-chain activity across Ethereum, Solana, Base, Arbitrum, Optimism,
  bridges, and centralized-exchange routes such as Binance

This ticket adds both.

The feature should remain true to the Maps product shape:

- Maps is a navigation intelligence layer, not a raw data dashboard
- the homepage should show derived intelligence, not low-level transaction tables
- the backend should generate stable artifacts on a schedule, not on every page load

This ticket introduces two new derived artifacts:

1. `MapsNewsBrief` — a short editorial-style market read with a headline and summary
2. `CrossChainActivityState` — a structured high-level cross-chain / bridge / venue snapshot

The frontend will render:

- a `Maps News` hero block at the top of the main Maps page
- a `Cross-Chain Activity` section summarizing major bridges, L2 routes, Solana flows,
  and CEX-linked route conditions

This ticket intentionally does **not** add raw bridge activity tables or direct low-level
database inspection UIs. The product goal is a higher-level read derived from existing Maps
signals and current Maps state.

Implementation priority for this ticket:

1. produce backend artifacts first
2. expose them through read APIs
3. render them on the homepage
4. tighten prompts and queue only after the artifacts exist

Do not start with frontend-only mockups or client-side summary generation.

**Run this spec from the `e3d-maps` root:**

```bash
codex-spec-runner docs/maps-news-cross-chain-highlights-feature-ticket.md all --provider claude
```

**Or phase-by-phase:**

```bash
codex-spec-runner docs/maps-news-cross-chain-highlights-feature-ticket.md 1 --provider claude
```

---

## Background

### What Exists Today

The repo already has the pieces needed to build a higher-level product without introducing
new raw data collectors immediately.

- Maps generates `NavigationSignal` records such as:
  - `capital_migration`
  - `destination_prediction`
  - `congestion_formation`
  - `route_hazard`
  - `route_closure`
  - `route_emergence`
- The question queue already includes cross-chain prompts such as:
  - `Are any L2 bridges or cross-chain routes forming congestion right now?`
  - `Are any cross-chain bridge routes showing elevated hazard levels over the next 24 hours?`
  - `Are any cross-chain bridges or exchange withdrawal routes closing over the next 24 hours?`
- `NavigationSignal` already includes:
  - `origin`
  - `destination`
  - `asset_scope`
  - `chain_scope`
  - `confidence`
  - `risk_level`
  - `answer`
- The current public Maps API already serves derived reads through `/api/maps/...` routes.

### Why This Feature Should Be Derived, Not Raw

For the current product stage, the most valuable UX is not:

- a list of every bridge transaction
- a venue-by-venue transfer ledger
- a raw chain metrics terminal

The valuable UX is:

- "Ethereum is active but route quality is deteriorating."
- "Binance-linked routes are cooling while Solana and Base are gaining probability."
- "Bridge risk is rising around one cross-chain corridor."

That is Maps-native output. It belongs in derived artifacts generated from the existing
signal layer.

### Product Naming

Do not label the homepage block as `AI Summary`.

Use product language:

- `Maps News`
- `Current Read`
- `Navigator Bulletin`

For this ticket, the canonical label is `Maps News`.

### Current Technical Constraints

- The public `/api/maps/...` route surface is owned by the main E3D endpoint. This repo
  owns the producer side, shared schemas, write-side integrations, and UI.
- The homepage should not trigger live LLM generation on every request.
- Feature output must remain grounded in evidence from existing Maps state and signals.
- The system must tolerate missing or thin cross-chain evidence gracefully.
- This feature must not change the existing `NavigationSignal` schema or break current
  `/api/maps/state`, `/api/maps/signals`, `/api/maps/hazards`, `/api/maps/destinations`,
  or `/api/maps/graph` behavior.

---

## Product Goals

### Goal 1 — Add a Top-of-Page Market Read

When a user opens the main Maps page, they should immediately see a strong, human-readable
 read of the market in the style of a news headline and short brief.

Example shape:

- Headline: `Ethereum is active, but route quality is deteriorating`
- Summary: `Flows remain live across ETH DeFi and major venues, but congestion and route
  closures suggest a crowded environment with rising execution risk.`

### Goal 2 — Surface Cross-Chain Activity as Intelligence

The main Maps page should expose a higher-level read on:

- Ethereum vs. Solana route activity
- L2 route emergence and congestion
- bridge-linked hazards or closures
- CEX-linked movements such as Binance inflow / outflow implications

This should be presented as:

- major routes gaining probability
- major routes becoming crowded
- major routes becoming risky or unavailable

This goal also includes an explicit read on movement in and out of Ethereum:

- where capital is leaving Ethereum
- where capital is entering Ethereum from
- whether Ethereum-linked bridge corridors are healthy, crowded, or hazardous
- whether Ethereum is feeding CEX routes, L2 routes, or competing chain routes

### Goal 3 — Keep the System Stable and Schedulable

Both the news brief and cross-chain highlights should be generated on the backend on a
schedule and stored as artifacts, not synthesized ad hoc in the browser.

---

## Scope

### In Scope

- A new backend-generated `MapsNewsBrief` artifact
- A new backend-generated `CrossChainActivityState` artifact
- Scheduled jobs to build both artifacts from existing Maps data
- Shared schemas for both artifacts
- ClickHouse storage for both artifacts
- Read-side service methods and route handlers for both artifacts
- Frontend rendering on the main Maps homepage
- Prompt and queue improvements to strengthen cross-chain route naming consistency
- Bridge-aware flowgraph and Ethereum-specific route summaries derived from the same
  Maps signal layer

### Out of Scope

- New raw bridge-activity crawlers
- New direct E3D database tables for low-level bridge events
- A raw cross-chain analytics dashboard
- Per-bridge historical charts
- Real-time per-request LLM generation
- A multi-article news feed
- Changes to public consumer semantics of existing Maps endpoints

---

## Canonical Vocabulary

The homepage will look sloppy if routes are labeled inconsistently. This feature requires
normalized destination and route labels when rendering cross-chain highlights.

Start with a strict canonical vocabulary:

```text
ethereum
ethereum_bridges
solana
base
arbitrum
optimism
binance
cex
cross_chain_bridges
eth_defi
solana_defi
base_defi
arbitrum_defi
optimism_defi
stablecoins
perps
```

Implementation guidance:

- Keep stored raw `origin` / `destination` values unchanged in signals.
- Add a normalization layer for derived artifacts so related labels can be grouped.
- Example grouping:
  - `BINANCE`, `Binance`, `binance_exchange` -> `binance`
  - `CEX`, `exchange`, `centralized_exchange` -> `cex`
  - `bridge`, `cross_chain_bridge`, `bridges` -> `cross_chain_bridges`
  - `ETH bridge`, `ethereum_bridge`, `ethereum_bridges` -> `ethereum_bridges`
  - `BASE`, `BASE_DEFI`, `base_chain` -> `base` or `base_defi` depending on intent

Do not attempt to solve every naming edge case in v1. The goal is a good canonical read,
not ontology perfection.

Hard rule for v1:

- normalization is only for derived artifacts and UI presentation
- raw `NavigationSignal.origin`, `NavigationSignal.destination`, and `chain_scope` values
  must remain untouched in storage

Bridge-label distinction for v1:

- `ethereum_bridges` means a route explicitly framed as entering or leaving Ethereum via a
  bridge corridor
- `cross_chain_bridges` means a generic bridge hub or bridge route that is not confidently
  attributable to Ethereum ingress/egress specifically

Normalization rule:

- if one side of the route is `ethereum` or `eth_defi` and the route is bridge-framed,
  prefer `ethereum_bridges`
- otherwise prefer `cross_chain_bridges`

Do not emit both labels for the same normalized route in a single assembled state item.

---

## Phase 1 — Shared Schemas and Storage

Add durable artifact schemas and storage so the backend can generate stable homepage reads.

### What to build

#### 1a. Add `MapsNewsBrief` schema

Create `schemas/maps_news_brief.py` with a validated model similar in style to the
existing schema layer.

Fields:

```text
id                       string
scope                    string              // "global" for v1
headline                 string              // 60-100 chars target
summary                  string              // 1 compact paragraph, 220-420 chars target
stance                   string              // "risk_on" | "risk_off" | "neutral" | "cautious" | "crowded"
supporting_signal_ids    string[]
supporting_story_ids     string[]
supporting_thesis_ids    string[]
tags                     string[]            // e.g. ["ethereum", "congestion", "hazards_active"]
created_by_agent         string              // "maps_news_agent"
model                    string
adapter                  string
schema_version           string
created_at               datetime
```

Constraints:

- `headline` must be non-empty
- `summary` must be non-empty
- `scope` defaults to `global`
- `created_by_agent` defaults to `maps_news_agent`
- `headline` max length: 120 chars
- `summary` max length: 420 chars
- `tags` max items: 6
- `supporting_signal_ids` max items: 8

#### 1b. Add `CrossChainActivityState` schema

Create `schemas/cross_chain_activity_state.py`.

Fields:

```text
id                        string
scope                     string              // "global" for v1
market_bias               string              // "risk_on" | "risk_off" | "neutral" | "transitioning"
top_routes                object[]            // ranked route summaries
active_hazards            object[]            // bridge/CEX/L2-linked hazards
active_congestion         object[]            // crowding / traffic summaries
top_destinations          object[]            // normalized chain/venue destinations
supporting_signal_ids     string[]
created_by_agent          string              // "cross_chain_activity_assembler"
schema_version            string
created_at                datetime
```

Each `top_routes` item should include:

```text
origin
destination
normalized_origin
normalized_destination
signal_type
confidence
risk_level
signal_strength        // raw confidence of the underlying NavigationSignal, unmodified
route_score            // computed ranking value: confidence * type_weight * recency_multiplier
signal_age_hours       // age of the underlying signal at assembly time, for display ("detected 2h ago")
route_class            // "bridge" | "cex" | "chain" | "defi" | "staking" | "perps" | "other"
summary
time_horizon_hours
```

Each `active_hazards` item should include:

```text
origin
destination
normalized_origin
normalized_destination
confidence
risk_level
signal_age_hours
summary
```

Each `active_congestion` item should include:

```text
origin
destination
normalized_origin
normalized_destination
confidence
risk_level
signal_age_hours
summary
```

Each `top_destinations` item should include:

```text
destination
normalized_destination
confidence
supporting_signal_count
```

Add two Ethereum-specific summary collections:

```text
ethereum_outbound_routes   object[]   // routes whose normalized_origin is ethereum or eth_defi
ethereum_inbound_routes    object[]   // routes whose normalized_destination is ethereum or eth_defi
```

Each item should include:

```text
origin
destination
normalized_origin
normalized_destination
confidence
risk_level
route_class
summary
signal_age_hours
```

Hard limits:

- `top_routes`: max 6 items
- `active_hazards`: max 6 items
- `active_congestion`: max 6 items
- `top_destinations`: max 6 items
- `ethereum_outbound_routes`: max 6 items
- `ethereum_inbound_routes`: max 6 items
- `supporting_signal_ids`: max 20 items

#### 1c. Export schemas

Update `schemas/__init__.py` so the new models are importable from the shared schema layer.

#### 1d. Add ClickHouse migrations

Add a new migration file under `db/migrations/` that creates:

- `MapsNewsBriefs`
- `CrossChainActivityStates`

Suggested minimal columns:

For `MapsNewsBriefs`:

```text
id String
scope String
headline String
summary String
stance String
supporting_signal_ids Array(String)
supporting_story_ids Array(String)
supporting_thesis_ids Array(String)
tags Array(String)
created_by_agent String
model String
adapter String
schema_version String
created_at DateTime
```

For `CrossChainActivityStates`:

```text
id String
scope String
market_bias String
top_routes_json String
active_hazards_json String
active_congestion_json String
top_destinations_json String
ethereum_outbound_routes_json String
ethereum_inbound_routes_json String
supporting_signal_ids Array(String)
created_by_agent String
schema_version String
created_at DateTime
```

Use the same style as the existing Maps tables: append-only, newest row wins by timestamp.

Use plain `String` JSON payload columns for nested arrays, consistent with current
`TrafficState` and `FlowGraph` storage patterns already used in this repo.

#### 1e. Extend ClickHouse client

Update `clients/clickhouse_client.py` to support:

- `insert_maps_news_brief`
- `insert_maps_news_briefs`
- `insert_cross_chain_activity_state`
- `insert_cross_chain_activity_states`

Follow the serialization style already used for `TrafficState` and `FlowGraph` records.

Do not introduce a new generic serialization framework in this ticket. Keep the changes
local and consistent with the existing `ClickHouseClient` style.

### Acceptance Criteria

- Shared models validate cleanly
- New models are exported from `schemas/__init__.py`
- Migration defines both new tables
- ClickHouse client can serialize and write both artifacts

### Verification

1. Run unit tests for schema import / validation.
2. Verify the migration file matches repo conventions.
3. Add or update tests proving serialization shape for both artifact types.

---

## Phase 2 — Cross-Chain Activity Assembler

Build a deterministic assembler that derives a high-level cross-chain state from existing
Maps signals.

### What to build

#### 2a. Add assembler module

Create `services/cross_chain_activity_assembler.py`.

Its input should be a list of recent `NavigationSignal` records plus optional `TrafficState`.

Its output should be one `CrossChainActivityState`.

Implementation shape:

- expose one pure function that builds a `CrossChainActivityState` from in-memory inputs
- keep ClickHouse reads/writes outside the assembler
- make the assembler deterministic and unit-testable without network access

#### 2b. Route filtering rules

Only include signals relevant to cross-chain / venue / chain-topology reads.

Minimum confidence threshold: skip any signal with `confidence < 0.5`. This mirrors
the gate applied at signal ingestion and prevents weak signals from appearing as featured
routes in the assembled state.

Relevant signals:

- `capital_migration`
- `destination_prediction`
- `route_emergence`
- `route_hazard`
- `route_closure`
- `congestion_formation`

Relevant labels are signals whose:

- `origin` or `destination` matches the canonical vocabulary directly, or
- `chain_scope` includes `ethereum`, `solana`, `base`, `arbitrum`, `optimism`, or
- text contains route concepts such as bridge / CEX / Binance / L2

For v1, do not parse free text aggressively. Prefer structured fields in this order:

1. `origin`
2. `destination`
3. `chain_scope`
4. `asset_scope`
5. `answer` text as a last resort only

#### 2c. Normalization rules

Add a normalization helper inside the assembler or a small utility module.

Expected behaviors:

- map route labels to canonical labels
- preserve original labels separately for UI drill-down
- handle common uppercase and underscore variants
- classify each route into one `route_class`

Route classification rules for v1:

- if normalized origin or destination is `binance` or `cex`: `cex`
- if normalized origin or destination is `cross_chain_bridges` or `ethereum_bridges`: `bridge`
- if normalized origin or destination is one of `ethereum`, `solana`, `base`, `arbitrum`, `optimism`: `chain`
- if normalized origin or destination ends with `_defi`: `defi`
- if either side is `perps`: `perps`
- otherwise: `other`

#### 2d. Ranking logic

Build the state from recent signals with pragmatic scoring, not an LLM.

Suggested approach:

- rank `top_routes` by weighted score using:
  - confidence
  - recency
  - signal type priority
  - risk severity
- prioritize hazards and closures higher when building `active_hazards`
- build `top_destinations` by grouping signals on normalized destination and counting support
- build `active_congestion` from `congestion_formation` signals touching the canonical set
- build `ethereum_outbound_routes` from routes where normalized origin is `ethereum` or `eth_defi`
- build `ethereum_inbound_routes` from routes where normalized destination is `ethereum` or `eth_defi`

Ethereum route interpretation rule:

- a route belongs in `ethereum_outbound_routes` when it is best understood as capital
  leaving Ethereum or ETH DeFi, including via `ethereum_bridges`
- a route belongs in `ethereum_inbound_routes` when it is best understood as capital
  arriving into Ethereum or ETH DeFi, including from `ethereum_bridges`, `cex`, or other
  chains
- if a route is too ambiguous to classify directionally, keep it in `top_routes` only and
  do not force it into the Ethereum-specific collections

Suggested signal-type weights:

```text
route_closure         1.20
route_hazard          1.10
route_emergence       1.00
capital_migration     0.95
destination_prediction 0.90
congestion_formation  0.90
```

Use these exact weights for v1.

Scoring formula for `top_routes`:

```text
route_score = confidence * signal_type_weight * recency_multiplier
```

Recency multiplier:

- signal age <= 2h: `1.00`
- signal age <= 6h: `0.92`
- signal age <= 12h: `0.84`
- older than 12h: `0.76`

Risk does not increase `top_routes` score directly. Risk is handled separately in
`active_hazards`.

Scoring formula for `active_hazards`:

```text
hazard_score = confidence * signal_type_weight * risk_multiplier * recency_multiplier
```

Risk multiplier:

- `low`: `0.85`
- `medium`: `1.00`
- `high`: `1.12`
- `critical`: `1.25`

#### 2e. Empty-state behavior

If there are too few relevant cross-chain signals:

- still write a `CrossChainActivityState`
- set arrays to empty
- set `market_bias` from the latest `TrafficState` if available, else `neutral`
- set `supporting_signal_ids` to an empty list

The homepage must still load cleanly if cross-chain evidence is sparse.

### Acceptance Criteria

- A recent set of route signals can be transformed into one `CrossChainActivityState`
- The output groups Binance / CEX / Solana / L2-related labels coherently
- Sparse signal sets return a valid empty state, not an exception

### Verification

Add unit tests covering:

1. Binance-style labels normalize into `binance`
2. Base / Arbitrum / Optimism labels group correctly
3. Hazards outrank weak opportunity signals in the hazard list
4. Empty relevant input still returns a valid state
5. Ethereum outbound routes are separated from inbound routes correctly
6. Bridge-linked routes classify as `bridge`

---

## Phase 3 — Maps News Agent

Add a scheduled backend agent that writes one editorial-style homepage brief.

### What to build

#### 3a. Add prompt file

Create `prompts/maps_news_agent.md`.

The prompt must instruct the model to:

- produce exactly one concise JSON object
- write one strong headline and one compact summary paragraph
- sound like a serious market desk, not marketing copy
- stay grounded in provided evidence only
- avoid hype, certainty language, and unsupported macro claims
- mention congestion or hazards when materially relevant
- mention Ethereum, Solana, L2s, bridges, or Binance only when present in the evidence
- avoid mentioning assets, chains, venues, or bridges that are absent from the input
- never emit markdown, code fences, or extra commentary
- choose a `stance` that is directionally coherent with the `market_bias` field from
  `CrossChainActivityState`; if the featured signals clearly contradict `market_bias`,
  explain the divergence in the summary rather than silently picking a conflicting stance
- if a previous brief is provided, acknowledge directional change when the stance has
  shifted (e.g. "Route conditions have deteriorated since this morning's read"); do not
  reference the prior brief if the stance is unchanged

Required JSON shape:

```json
{
  "headline": "Ethereum is active, but route quality is deteriorating",
  "summary": "Flows remain live across ETH DeFi and major venues, but congestion and route-closure signals suggest a crowded environment with rising execution risk.",
  "stance": "cautious",
  "tags": ["ethereum", "congestion", "hazards_active"],
  "supporting_signal_ids": ["navsig_1", "navsig_2"],
  "supporting_story_ids": ["story_1"],
  "supporting_thesis_ids": []
}
```

Hard output rules:

- `headline`: 60-120 chars
- `summary`: 160-420 chars
- `stance`: exactly one of `risk_on`, `risk_off`, `neutral`, `cautious`, `crowded`
- `tags`: 1 to 6 items
- no newline characters in `headline`
- no more than one paragraph in `summary`

#### 3b. Add agent implementation

Create `agents/maps_news_agent.py`.

Use the existing `BaseAgent` style where practical, but this agent is producing a new
artifact type, not a `NavigationSignal`.

Do not modify `BaseAgent` just to support this feature if that can be avoided cleanly.
Prefer a small local parser/validator for the news artifact.

The agent should be initialized with:

- system prompt from `prompts/maps_system_prompt.md` if useful
- agent prompt from `prompts/maps_news_agent.md`
- same OpenAI-compatible runtime client used by the rest of the Maps agents

#### 3c. Build the news context

The input context for this agent should be derived from:

- latest `TrafficState`
- latest `CrossChainActivityState`
- previous `MapsNewsBrief` (most recent stored row, if any)
- recent highest-confidence signals across hazards, congestion, and destinations
- latest top destinations

Do not pass large raw dumps unnecessarily. Keep context small and intentional.

Suggested input shape:

```text
market_state
dominant_flows
top_destinations
active_hazards
active_congestion
top_cross_chain_routes
recent_featured_signals
previous_brief          // { headline, stance, tags } from last stored brief, or null
```

Hard cap the featured-signal context:

- at most 8 signals total
- at most 3 hazard/closure signals
- at most 2 congestion signals
- at most 3 migration/destination/emergence signals

#### 3d. Validation and fallback

If model output is invalid or empty:

- do not fail the scheduler tick
- fall back to a deterministic template-generated brief

The fallback must be built from available `TrafficState` and `CrossChainActivityState`
data rather than a fixed string. A fixed string that repeats verbatim across multiple
failures will read as broken to users.

Fallback construction rules (in order, use the first that applies):

1. If `CrossChainActivityState` has active hazards:
   - headline: `Routes are active with elevated risk on [top normalized_destination]`
   - summary: short template incorporating `market_bias` and the top hazard summary
2. If `CrossChainActivityState` has top routes but no hazards:
   - headline: `[Top normalized_destination] leads route activity`
   - summary: short template incorporating `market_bias` and top route summary
3. If `TrafficState` is available:
   - headline: `Maps is tracking [market_bias] conditions`
   - summary: one sentence from `TrafficState` dominant flow
4. Last resort (no data):
   - headline: `Maps is warming up`
   - summary: `Signal data is accumulating. Check back shortly.`

Fallback must be deterministic and must not call the model again.

### Acceptance Criteria

- The backend can generate a valid `MapsNewsBrief`
- The prompt is constrained enough to produce short, product-grade output
- Invalid model output falls back to a deterministic brief

### Verification

Add unit tests covering:

1. valid model response -> parsed `MapsNewsBrief`
2. invalid JSON -> fallback brief
3. unsupported claims are structurally prevented by prompt + schema shape

---

## Phase 4 — Scheduled Jobs and Write Path

Wire both new artifacts into the existing job/scheduler flow.

### What to build

#### 4a. Add cross-chain assembly job

Create `jobs/assemble_cross_chain_activity.py`.

The job should:

1. query recent relevant `NavigationSignal` rows from ClickHouse
2. fetch the latest `TrafficState`
3. build a `CrossChainActivityState`
4. write it to ClickHouse

Use a bounded lookback window:

- only consider signals from the last 24 hours
- cap the input set at 200 rows ordered by newest first

#### 4b. Add Maps News generation job

Create `jobs/generate_maps_news.py`.

The job should:

1. load latest `TrafficState`
2. load latest `CrossChainActivityState`
3. load the most recent stored `MapsNewsBrief` (for directional comparison context)
4. load recent strongest signals
5. call the `maps_news_agent`
6. validate or fall back
7. write a `MapsNewsBrief`

Use a bounded lookback window for featured signals:

- only consider signals from the last 12 hours
- cap the candidate set at 50 rows before selecting featured signals

#### 4c. Extend scheduler

Update `agents/scheduler.py` so both jobs can run on a cadence.

Suggested defaults:

- `assemble_cross_chain_activity`: every 5 minutes
- `generate_maps_news`: every 5 minutes, after cross-chain activity is assembled

It is acceptable if both run in the same scheduler tick as long as ordering is stable.

Hard requirement:

- `assemble_cross_chain_activity` must run before `generate_maps_news` inside the same tick
  when both are due

#### 4d. Add runtime settings

Extend `MapsRunnerSettings` in `settings.py` with:

- `maps_news_interval_seconds`
- `cross_chain_activity_interval_seconds`

Set sensible defaults and expose them via env vars.

### Acceptance Criteria

- Scheduler can build both artifacts continuously
- Cross-chain state is assembled before the news brief in a normal cycle
- Failures in one job do not crash the scheduler loop

### Verification

1. Add unit tests for scheduler wiring if appropriate.
2. Run scheduler in `--once --dry-run` mode and confirm both jobs execute.
3. Confirm dry-run output shows valid row shapes for both tables.

---

## Phase 5 — Read API Surface

Expose both artifacts through the Maps read-side service and route layer.

### What to build

#### 5a. Extend `MapsAPIService`

In `services/maps_api_service.py`, add:

- `get_latest_maps_news_brief()`
- `get_latest_cross_chain_activity_state()`

Both should read the newest row by `created_at DESC, id DESC`, mirroring existing patterns
such as `get_latest_state()`.

#### 5b. Add route handlers

In `api/maps_routes.py`, add:

- `get_maps_news(service)`
- `get_maps_cross_chain(service)`

Suggested response shapes:

For `/api/maps/news`:

```json
{
  "status": "ok",
  "news": {
    "headline": "...",
    "summary": "...",
    "stance": "cautious",
    "tags": ["ethereum", "congestion"],
    "generated_at": "2026-06-16T13:52:17Z"
  }
}
```

For `/api/maps/cross-chain`:

```json
{
  "status": "ok",
  "cross_chain": {
    "market_bias": "neutral",
    "top_routes": [...],
    "active_hazards": [...],
    "active_congestion": [...],
    "top_destinations": [...],
    "ethereum_outbound_routes": [...],
    "ethereum_inbound_routes": [...],
    "created_at": "2026-06-16T13:52:17Z"
  }
}
```

These route names are exact:

- `GET /api/maps/news`
- `GET /api/maps/cross-chain`

Response caching should be set to 300 seconds to match the generation cadence. However,
`RouteResponse` in `api/maps_routes.py` only carries `status_code` and `body` — it has
no header field, so caching cannot be expressed at the route layer without changing that
abstraction.

Do not change `RouteResponse` in this ticket. Instead, delegate caching to the outer
HTTP layer: configure `Cache-Control: max-age=300` in the runner/WSGI/ASGI middleware or
reverse proxy that serves these routes. Document this as a deployment configuration
requirement, not a route-handler requirement.

404 behavior:

- return `not_found` only if no artifact exists yet
- frontend should treat that as an empty state, not an error banner

#### 5c. Update OpenAPI and docs

Update `ui/openapi.json` and any API docs page inputs as needed so the new endpoints are
represented.

Do not rename existing API client methods or alter existing response shapes while adding
these endpoints.

### Acceptance Criteria

- Service can read latest rows for both artifact types
- Route handlers return stable JSON responses
- OpenAPI reflects both endpoints

### Verification

Add tests similar to the current route / service tests:

1. latest news brief returns 200
2. latest cross-chain state returns 200
3. missing artifact returns 404 `not_found`

---

## Phase 6 — Frontend Homepage UX

Render the new artifacts at the top of the main Maps page.

### What to build

#### 6a. Extend API client

In `ui/src/api/mapsApiClient.js`, add:

- `getNews()`
- `getCrossChainActivity()`

Both should support `allowNotFound: true`, matching existing tolerant patterns like
`getState()`.

#### 6b. Update homepage data loading

In `ui/src/pages/MapsHome.js`, load in parallel using `Promise.allSettled`:

- `getState()`
- `getNews()`
- `getCrossChainActivity()`
- existing data already used by the page

All four fetches must fire concurrently and degrade independently. Do not await them
sequentially — a slow cross-chain response should not delay the news hero, and vice versa.

Use `Promise.allSettled` (not `Promise.all`). The `request()` helper in
`ui/src/api/mapsApiClient.js` throws on non-404 errors, so `Promise.all` would reject
the entire batch if any single fetch fails, violating the independent-degradation
requirement. With `Promise.allSettled`, a failed news fetch leaves the cross-chain
section unaffected and vice versa. Check each result's `status` field before using
its `value`.

Do not add a second page for this feature in v1. The feature belongs on the existing main
Maps homepage.

#### 6c. Add `Maps News` hero block

At the top of the page, render:

- eyebrow label: `Maps News`
- large headline
- compact summary paragraph
- relative timestamp (e.g. "Updated 3 minutes ago")
- small tags/chips

If the brief is older than 15 minutes, render the timestamp in a muted or warning color
to signal that data may be stale. Do not hide the brief — just flag the age.

This should visually read like a front-page market bulletin.

#### 6d. Add `Cross-Chain Activity` section

Below the news block, render a panel with:

- top routes
- active hazards
- congestion watch
- top destinations
- Ethereum outbound routes
- Ethereum inbound routes

The goal is scanability, not exhaustiveness.

Suggested subsections:

- `Routes Opening`
- `Risky Corridors`
- `Crowding`
- `Top Destinations`
- `Out of Ethereum`
- `Into Ethereum`

Render at most:

- 3 `Routes Opening` items
- 3 `Risky Corridors` items
- 3 `Crowding` items
- 4 `Top Destinations` items
- 3 `Out of Ethereum` items
- 3 `Into Ethereum` items

#### 6e. Empty states

If `/api/maps/news` is missing:

- show a compact placeholder such as `Maps News is warming up.`

If `/api/maps/cross-chain` is missing or sparse:

- show `Cross-chain activity is quiet or not yet classified.`

#### 6f. Presentation guidelines

The design should feel intentional, editorial, and higher-signal than the existing table UI.

Recommended characteristics:

- strong headline typography
- compact but readable summary block
- meaningful accent color tied to `stance`
- no generic “AI summary” framing

Exact labels for v1:

- hero eyebrow: `Maps News`
- cross-chain panel title: `Cross-Chain Activity`
- subsection titles:
  - `Routes Opening`
  - `Risky Corridors`
  - `Crowding`
  - `Top Destinations`
  - `Out of Ethereum`
  - `Into Ethereum`

#### 6g. Extend the flow graph to show bridge and cross-chain routes

The existing `FlowGraph` component derives edges from raw `NavigationSignal` records and
only renders nodes present in `NODE_LAYOUT`. To make bridge activity legible, the graph
must be extended to show canonical bridge and chain routes explicitly.

Required v1 changes:

- add bridge- and chain-specific nodes to the graph layout:
  - `cross_chain_bridges`
  - `solana`
  - `binance`
  - `arbitrum`
  - `optimism`
  - lowercase aliases for any existing uppercase nodes that are needed by the canonical
    cross-chain vocabulary
- extend `FlowGraph` so it can render edges from `CrossChainActivityState.top_routes`,
  not just raw signals
- use `normalized_origin` and `normalized_destination` from assembled cross-chain routes
  when building those graph edges
- preserve existing confidence-based stroke width and hazard-based edge color behavior
- visually distinguish cross-chain/bridge routes from generic routes if possible without
  making the graph noisy

Graph data-source rule for v1:

- treat the graph as a deliberate hybrid view
- raw `NavigationSignal` edges remain valid input
- `CrossChainActivityState.top_routes` is also valid input
- when both describe the same `(origin, destination)` pair, prefer the assembled
  cross-chain route because it carries normalized labels and route classification
- do not silently merge fields from the two sources into a malformed edge object; choose
  one winning representation per pair

Implementation guidance:

- add an explicit internal edge shape for the graph layer rather than passing raw signal
  objects and assembled route objects interchangeably
- normalize both sources into that internal edge shape before deduplication and rendering

The goal is that a user can see whether Ethereum is routing capital:

- into L2s
- out to Solana
- into bridges
- into or out of Binance/CEX

Do not add a second graph component for this feature. Extend the existing flowgraph.

#### 6g. Extend the flow graph to show bridge and cross-chain routes

The existing `FlowGraph` component derives edges from raw `NavigationSignal` records. It
filters any signal whose `origin` or `destination` is not in `NODE_LAYOUT`. The canonical
cross-chain vocabulary introduced by this feature (lowercase keys such as
`cross_chain_bridges`, `solana`, `binance`, `arbitrum`, `optimism`) does not currently
exist in `NODE_LAYOUT`, so bridge-related signals are silently dropped from the graph.

This section fixes both gaps: missing nodes, and missing data feed from the assembled
cross-chain state.

##### Add canonical nodes to `NODE_LAYOUT` in `ui/src/utils/flowGraph.js`

Add the following new entries. Positions are suggestions — adjust for visual balance, but
keep `cross_chain_bridges` near the horizontal center of the graph so it reads as a hub
between the ETH cluster and the Solana / L2 endpoints.

```js
// New canonical bridge / cross-chain nodes
cross_chain_bridges: { x: 0.30, y: 0.50, label: "Bridges" },
solana:              { x: 0.82, y: 0.10, label: "Solana" },
binance:             { x: 0.08, y: 0.10, label: "Binance" },
arbitrum:            { x: 0.42, y: 0.88, label: "Arbitrum" },
optimism:            { x: 0.62, y: 0.88, label: "Optimism" },

// Lowercase aliases for existing nodes (canonical vocab maps to these)
ethereum:   { x: 0.30, y: 0.20, label: "ETH" },       // alias for ETH
eth_defi:   { x: 0.55, y: 0.18, label: "ETH DeFi" },  // alias for ETH_DEFI
base_defi:  { x: 0.55, y: 0.55, label: "Base DeFi" }, // alias for BASE_DEFI
cex:        { x: 0.08, y: 0.80, label: "CEX" },        // alias for CEX
perps:      { x: 0.82, y: 0.30, label: "Perps" },      // alias for PERPS (already lowercase)
```

Aliases share the same visual position as the existing uppercase node. If both the
uppercase and lowercase versions of a node are active simultaneously (e.g. signals using
`ETH` and signals using `ethereum`), they will render as two overlapping circles. That
is acceptable for v1 — resolve the duplication in a follow-up cleanup or when prompt
tightening (Phase 7) converges labels toward canonical forms.

##### Extend `FlowGraph` to accept cross-chain routes

The flow graph should also render edges from `CrossChainActivityState.top_routes`, not
just from raw signals. These assembled routes use `normalized_origin` and
`normalized_destination`, which map directly to the canonical `NODE_LAYOUT` keys.

Add a `crossChainRoutes` prop to `FlowGraph`:

```js
export function FlowGraph({ signals = [], crossChainRoutes = [], onNodeClick }) { ... }
```

##### Extend `deriveEdges()` to merge cross-chain routes

Update `deriveEdges(signals, crossChainRoutes)` to accept both inputs.

For each item in `crossChainRoutes`:
- use `normalized_origin` and `normalized_destination` as the NODE_LAYOUT lookup keys
- use `signal_strength` (raw confidence) as the edge confidence
- use the item's `risk_level` for edge color
- mark the edge source as `"cross_chain"` so it can be styled distinctly

When a cross-chain route and a raw signal describe the same `(origin, destination)` pair:
- keep whichever has higher confidence, as today
- if the cross-chain route wins, preserve its `"cross_chain"` marker

##### Visual treatment for bridge edges

Render bridge edges (those with source `"cross_chain"`) with a dashed stroke so they are
visually distinct from raw-signal edges:

```js
strokeDasharray=${edge.source === "cross_chain" ? "6 3" : null}
```

All other visual properties (color, width, arrowhead, hover tooltip) apply the same as
regular edges. The hover tooltip should show `confidence · risk · "cross-chain"` to make
the source clear.

##### Wire cross-chain routes into the homepage

In `MapsHome.js`, pass `top_routes` from the loaded cross-chain state to `FlowGraph`:

```js
<${FlowGraph}
  signals=${state.allSignals}
  crossChainRoutes=${state.crossChainActivity?.top_routes ?? []}
  onNodeClick=${handleNodeClick}
/>
```

Add `crossChainActivity` to the homepage state shape and populate it from the
`getCrossChainActivity()` call already introduced in Phase 6b.

If `getCrossChainActivity()` returns null (404 or error), pass an empty array — the graph
must render normally without cross-chain data.

### Acceptance Criteria

- Homepage renders a real news-style hero when data is present
- Homepage renders a useful empty state when data is absent
- Cross-chain section is readable on desktop and mobile
- Flow graph renders bridge and cross-chain route edges with a dashed stroke
- Flow graph does not break or go blank if `crossChainRoutes` is empty

### Verification

1. Load the homepage with mocked data and confirm the news hero appears first.
2. Confirm the cross-chain section highlights hazards and routes clearly.
3. Confirm 404 / empty responses do not break the page.
4. With mocked `top_routes` data, confirm dashed edges appear in the flow graph for
   bridge routes and that hovering shows the `cross-chain` source label.
5. With no cross-chain data, confirm the flow graph renders normally from signals alone.

---

## Phase 7 — Prompt and Queue Tightening for Cross-Chain Coverage

Improve cross-chain signal quality without introducing new raw upstream data collection yet.

### What to build

#### 7a. Tighten question queue wording

Update `agents/question_queue.json` to ask more specific route questions around:

- Binance-linked flows
- Solana destination probability
- Base / Arbitrum / Optimism route emergence
- bridge congestion
- bridge hazard / closure conditions

The goal is not to add dozens of prompts. The goal is to improve naming discipline and
coverage for the homepage-derived artifacts.

**Audit before adding.** The queue currently has approximately 30 entries. Before adding
new ones, review existing entries for low cross-chain yield and replace rather than
append. Candidates for replacement or removal:

- Generic `Where is capital likely moving over the next 24 hours?` — too broad, replace
  with a Binance-specific rotation question
- Generic `Which destinations are gaining probability?` — too vague, replace with a
  specific L2/Solana framing
- Any duplicate agent questions where a more specific version already exists

Replacements to make (replace the generics above, or add if queue already removed them):

- `Is capital rotating from Binance-linked exchange balances into Solana or Base over the next 24 hours?`
- `Are Base, Arbitrum, or Optimism becoming more attractive capital destinations over the next 24 hours?`
- `Are any bridge routes into Solana or major L2s becoming hazardous or congested right now?`
- `Is capital leaving Ethereum for Base, Arbitrum, Optimism, Solana, or Binance-linked routes over the next 24 hours?`
- `Is capital moving into Ethereum from CEX or cross-chain bridge routes over the next 24 hours?`

Keep the queue changes bounded:

- net change: no more than +4 entries after replacements (queue should not grow beyond
  ~34 total)
- do not expand into a large cross-chain matrix

#### 7b. Tighten relevant agent prompts

Review and update these prompts where useful:

- `prompts/capital_migration_agent.md`
- `prompts/destination_prediction_agent.md`
- `prompts/route_hazard_agent.md`
- `prompts/route_closure_agent.md`
- `prompts/route_emergence_agent.md`
- `prompts/congestion_agent.md`

Prompt goals:

- prefer canonical route names where possible
- distinguish venue / chain / DeFi destination cleanly
- treat bridge and L2 routes as first-class route concepts
- avoid vague labels like `exchange` when `Binance` or `CEX` is supported by context

Hard prompt rule:

- if the evidence does not support `Binance`, prefer `CEX`
- if the evidence does not support a specific L2 name, prefer `L2_NETWORKS` or the
  strongest supported canonical label already present in context
- when the evidence supports Ethereum inflow/outflow framing, prefer explicit route
  wording such as `Ethereum -> Base` or `CEX -> Ethereum` over vague destination-only labels

Do not overfit prompts into a rigid taxonomy that the evidence cannot support.

### Acceptance Criteria

- Queue explicitly covers Binance, Solana, and major L2 route questions
- Prompt instructions improve naming consistency for route-oriented outputs

### Verification

1. Update or add tests for queue loading if needed.
2. In dry-run or fixture tests, confirm canonical labels appear more consistently.

---

## Implementation Notes

### Why Two Artifacts Instead of One

Keep `MapsNewsBrief` and `CrossChainActivityState` separate.

Reasons:

- the news brief is editorial output
- the cross-chain state is structured and deterministic
- the news brief can cite the cross-chain state
- future UIs may want one without the other

Do not overload `TrafficState` with a giant `summary` field. That object should remain a
machine-readable helicopter view.

### Why Not A Full News Feed Yet

One headline is enough for the homepage.

A feed introduces:

- ranking
- deduplication
- decay / archival policy
- repeated generation cost
- much more UI complexity

Start with one current brief.

### Why Not A Raw Bridge Endpoint Yet

The current goal is a product-grade intelligence read, not raw telemetry.

If the derived cross-chain state proves too thin, that is the signal to add new upstream
E3D functions later. Do not pre-emptively add raw endpoint complexity before the current
derived UX is validated.

---

## Deliverables

- `schemas/maps_news_brief.py`
- `schemas/cross_chain_activity_state.py`
- new migration for `MapsNewsBriefs` and `CrossChainActivityStates`
- `services/cross_chain_activity_assembler.py`
- `agents/maps_news_agent.py`
- `prompts/maps_news_agent.md`
- `jobs/assemble_cross_chain_activity.py`
- `jobs/generate_maps_news.py`
- scheduler/settings wiring
- `MapsAPIService` read methods
- `api/maps_routes.py` route handlers
- `ui/src/api/mapsApiClient.js` additions
- homepage UI on `ui/src/pages/MapsHome.js`
- CSS updates
- tests for schemas, assembler, API service, routes, and homepage client behavior

Files that must be touched in this ticket unless a phase is explicitly skipped:

- `schemas/__init__.py`
- `clients/clickhouse_client.py`
- `services/maps_api_service.py`
- `api/maps_routes.py`
- `agents/scheduler.py`
- `settings.py`
- `ui/src/api/mapsApiClient.js`
- `ui/src/pages/MapsHome.js`
- `ui/src/utils/flowGraph.js`
- `ui/src/components/FlowGraph.js`
- `ui/src/styles.css`

---

## Final Verification

From the `e3d-maps` root:

1. Run relevant Python unit tests.
2. Run frontend tests.
3. Run a dry scheduler tick and confirm:
   - cross-chain state is produced
   - maps news brief is produced
4. Confirm the homepage can render:
   - with both artifacts present
   - with one missing
   - with both missing

The feature is complete when the homepage gives a strong top-of-page market read and a
useful cross-chain route summary without requiring raw bridge telemetry views.
