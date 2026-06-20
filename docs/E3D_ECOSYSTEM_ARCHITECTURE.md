# E3D Ecosystem Architecture

### A navigation-to-execution stack for on-chain markets

> **The metaphor.** E3D is a starship. It is assembled from the bottom up and it flies from the
> bottom up. Fuel is forged on-chain, ignited into intelligence, focused into guidance, and spent at
> the command tip where decisions are made. Spent fuel is not lost — the exhaust is recaptured as
> training signal, and the vehicle climbs a little smarter on every burn. Read this document the way
> a rocket flies: from the engines up to the nose.

---

## 1. Overview

E3D turns raw on-chain evidence into autonomous, accountable action — and then learns from the
result. It is not a single application but a **layered stack of four independent repositories**, each
a stage of the same vehicle, bolted together not by shared code but by shared contracts.

The animating thesis is simple and unfashionable: **on-chain story signals fire _before_ price
moves.** Patterns in wallet behavior, token flows, and market microstructure precede the candle.
E3D is built to be a telescope pointed at the pre-pump window, not a rear-view mirror reacting to
moves already in progress.

| Stage | Repository | Role | Runtime |
|---|---|---|---|
| 🎯 Command tip | `e3d-agent-trading-floor` | Action — decisions and execution | Node.js |
| 🧭 Guidance | `e3d-maps` | Navigation intelligence — prediction | Python |
| 🛰 Core stage | `spacepacket` (E3D.ai) | Data + intelligence hub | Node.js |
| 🚀 Engines | `E3DToken` | On-chain economic substrate | Solidity / TypeScript |

One non-negotiable design law runs through every joint of the vehicle:

> **AI suggests. Code decides.** Language models produce structured proposals. Deterministic code
> validates every field, enforces every limit, and chooses whether anything happens at all. A
> hallucination, a prompt injection, or a degraded model can waste a cycle. It cannot move capital.

---

## 2. The vehicle at a glance

```
                        ▲  ( nose / command )
                       ╱ ╲
                      ╱   ╲      e3d-agent-trading-floor
                     ╱     ╲     Action — Scout · Harvest · Risk · Executor · Manager
                    ╱       ╲
                   ╱─────────╲
                  │           │  e3d-maps
                  │           │  Navigation — signals · routes · traffic · outcomes
                  │           │
                  │           │  spacepacket (E3D.ai core)
        evidence  │           │  Ingestion · stories · theses · API + MCP · 3D UI
            ▲     │           │
            │     │           │  E3DToken
            │    ╱│           │╲  ERC-20 · agent identity NFTs · x402 · Wormhole→Solana
            │   ╱ └───────────┘ ╲
            │  ╱    ███████████    ╲   ← fins
                     ╲  ╲│╱  ╱
                      ╲ ╲│╱ ╱         exhaust = outcomes recaptured
                       ╲╲│╱╱          as training feedback
                        ╲│╱
                         ▽

   Powered by shared infrastructure: ClickHouse · API + MCP contracts · Qwen + LoRA adapters
```

---

## 3. 🚀 Engines — `E3DToken` (the economic substrate)

Every rocket needs propellant with a known chemistry. E3D's propellant is a **single canonical
asset** with an unambiguous definition across chains.

- **`E3DToken.sol`** — a clean OpenZeppelin ERC-20 (`E3D`), minted on **Ethereum**, the source of
  truth for supply and liquidity. Two extensions do real work in the agent economy: `ERC20Burnable`
  powers **deflation-on-usage** (fees are burned, so genuine activity makes the token scarcer), and
  `ERC20Permit` lets an agent **authorize a spend with a signature instead of a separate
  transaction** — the gasless primitive that machine-to-machine x402 payments ride on.
- **`E3DNFTManager.sol`** — far more than a marketplace now: an **upgradeable (proxy) ERC-721 that is
  the agent identity and payment layer** for the whole ecosystem (see §3.1). It still mints tradable
  collectibles, but its center of gravity has moved to autonomous agents.
- **`wormhole-e3d-solana`** — the cross-chain rails. Rather than fragmenting supply by minting a
  second independent token, E3D uses **Wormhole Wrapped Token Transfers**: the canonical asset stays
  locked on Ethereum, and a 1:1-backed wrapped SPL representation is minted on **Solana** after
  verification. The flow is deliberate and auditable — *attest → transfer → redeem → verify
  balances on both chains.*

### 3.1 Agent identity and payments

The 2026 upgrade turned `E3DNFTManager` into the on-chain home for agent identity and the settlement
substrate for agentic navigation:

- **Identity NFTs.** Each autonomous agent mints an on-chain identity (`mintAgentIdentity`) — a
  verifiable birth certificate carrying its controlling wallet and a registration URI. The activation
  fee is **burned in E3D**: identity costs scarcity.
- **On-chain reputation.** Reputation, validation level, funding, and task activity are recorded on
  the token and written by a low-privilege **scorer role** (the Maps scoring service), deliberately
  decoupled from the proxy-admin key.
- **Reputation-priced access.** `getAgentTier` exposes an on-chain access tier (reputation +
  validation) that off-chain **x402** metering reads to price each navigation call — you pay more for
  proven agents and proven quality, not flat-rate access.
- **Controlled handoff.** Identity tokens are non-transferable except through a deliberate
  `handoffAgent` — you can *sell a proven agent*, but it can't be casually listed or drained.
- **Living metadata.** An agent's `tokenURI` resolves to `maps.e3d.ai/agents/<id>`, serving its live
  reputation as ERC-721 metadata — identity that travels with the token, a track record that stays
  current.

Put together, this is the payment model for agentic navigation: **E3D is the unit, x402 is the rail,
the NFT is identity + reputation, and burn returns value to holders.** One token meters what an agent
consumes, prices it by what the agent has earned, and rewards what the agent honestly contributes —
with no human in the loop. *(Deployed: proxy `0xeED4…88eE`, implementation `0x4bAA…89eeD`.)*

**Why it sits at the bottom.** This layer is the substrate the rest of the stack indexes, narrates,
predicts over, and ultimately trades. Combustion happens here; everything above is what we do with
the energy.

---

## 4. 🛰 Core stage — `spacepacket` / E3D.ai (the data + intelligence hub)

This is the heavy stage — the largest tank in the vehicle and the gravitational center of the whole
ecosystem. It does three jobs: **ingest, understand, and serve.**

### 4.1 Ingestion — `buildDB`

A wide battery of builders pulls the chains into a queryable substrate: Ethereum, BSC, and Solana
transactions and swaps; price histories; pool liquidity; address names and symbols; and rolling
**timeseries** that give every later layer a sense of motion rather than a single snapshot.

### 4.2 Intelligence

Raw rows are not insight. The intelligence layer distills activity into the higher-order objects the
rest of the stack consumes:

- **Stories** — typed narratives detected in on-chain behavior (staging, clustering, accumulation,
  smart-money, stealth accumulation, breakouts, and more). These are the pre-pump signals the entire
  thesis rests on.
- **Theses** — longer-horizon, higher-conviction views.
- **Wallet and market intelligence** — counterparties, flows, microstructure.
- **Outcomes** — what actually happened, so the loop can close.

### 4.3 Serving — API, MCP, and the visualization

The core stage exposes its intelligence through an **HTTP API** and a **Model Context Protocol (MCP)
surface**, so both humans and agents can read the same ground truth. Crucially, the public
`/api/maps/...` routes live **here**, in the main E3D repository — the upper stages produce objects
that this surface later serves. On top of it all sits the original E3D promise: a **3D visualization**
that turns Ethereum data into a navigable landscape.

**Why it sits in the middle.** Everything above the core stage is a *consumer* of its intelligence,
and everything it learns flows back down into it. It is the stage that converts fuel into usable
thrust.

---

## 5. 🧭 Guidance — `e3d-maps` (navigation intelligence)

If the core stage tells you *what is happening*, Maps tells you **where things are going next.** It
is the guidance computer: it reads the evidence and forecasts the routes capital is likely to take,
where congestion is forming, and which paths are becoming hazardous for downstream agents.

Maps is, by design, a **producer of validated machine-readable objects** — never vibes, never prose
predictions. Its outputs are strictly schema-checked before any database write.

### 5.1 The agent swarm

A constellation of focused producer agents, each with a narrow mandate, orchestrated over a **Qwen**
runtime:

- capital migration & capital conviction
- congestion
- route emergence, route closure, route hazard
- destination prediction
- liquidity forecasting
- narrative acceleration & swarm formation
- a watch agent (with draft generation) for emerging situations
- confidence scoring and outcome scoring to keep the system honest

### 5.2 The objects it emits

The shared schema layer is the heart of the repo — every output validates against it:

`NavigationSignal` · `RoutePrediction` · `TrafficState` · `PredictionOutcome` ·
`SignalUtilityScore` — plus `FlowGraph`, `CrossChainActivityState`, `WatchDraft`, `WatchPrediction`,
and `MapsNewsBrief`.

### 5.3 Jobs and the closed loop

Scheduled jobs assemble traffic state and flow graphs, generate navigation signals, backtest
predictions, score pending and settled predictions, compute **signal utility scores**, and **export
training examples**. This last step is what makes Maps a learning system rather than a static
oracle: settled predictions become labeled training data.

Maps ships its own frontend to **`maps.e3d.ai`**, served as static files by nginx that proxies API
calls back to the main E3D endpoint — same-origin, zero coupling.

**Why it sits near the top.** Guidance does not act. It aims. It hands the command tip a sharp,
validated picture of the road ahead.

---

## 6. 🎯 Command tip — `e3d-agent-trading-floor` (action)

The nose of the vehicle — the only stage permitted to *act*. It is a multi-agent, AI-assisted
portfolio system that runs a continuous cycle of discovery, evaluation, risk validation, and
execution. **It is paper-mode by default;** live execution requires an explicit, deliberate switch.

### 6.1 Five specialists, one deterministic spine

No agent works alone, and no agent can unilaterally move capital. Five LLM agents collaborate inside
a pipeline whose backbone is plain, auditable code:

| Agent | Mandate |
|---|---|
| **Scout** | Discovers 0–3 buy candidates from a story-filtered universe |
| **Harvest** | Manages held positions — hold, monitor, trim, or exit |
| **Risk** | Enforces hard limits and quant gates |
| **Executor** | Records the paper trade ticket (or submits the live order) |
| **Manager** | Grades the cycle after the fact, flags issues, writes the report |

Between the agents sit the parts that actually hold the keys: a perception layer that builds a
ranked **cognitive state** from a handful of targeted API calls, hard sell checks (stop-loss, fraud
breach, target hits), and a deterministic **portfolio engine** for ranking, rotation, and
allocation.

### 6.2 Story-first, evidence-chained

The token universe shown to Scout is not a list of high-volume movers — it is dynamically assembled
from **active story coverage** and sorted by freshness of on-chain signal. Tokens with no story are
excluded regardless of momentum. Every candidate must carry an **evidence chain**: `evidence[]`,
`why_now`, `risks[]`, `conviction_score`, an entry zone, an invalidation price, and targets.
Undocumented decisions are invalid by construction.

### 6.3 External boosters

Strap-on quant feeds enrich each cycle: **DexScreener** order flow, **CoinGecko**, **Fear & Greed**,
and **Binance funding**. Every cycle is UUID-stamped and logged append-only to `pipeline.jsonl` and
optionally to ClickHouse for training retention. A live **dashboard** renders the floor in motion.

**Why it sits at the tip.** This is where intent becomes consequence — and precisely why it is
wrapped in the most deterministic guardrails in the stack.

---

## 7. Agentic loops — the unit of computation

Strip away the metaphor and E3D is not really four programs. It is **three agentic loops running at
three different tempos**, chained end to end. Each loop is the same primitive — *perceive → decide →
act → score → learn* — and one loop's output is the next one's input. The loop, not the model, is the
unit of computation.

- **The core loop (`spacepacket`, continuous).** Ingest on-chain activity → detect stories and
  theses → generate candidate actions → evaluate what actually happened → recalibrate the weights →
  ingest again. The agent runtime, skills, and outcome evaluators turn a firehose of transactions
  into scored intelligence, and never stop.
- **The navigation loop (`e3d-maps`, scheduled).** Pull evidence → the producer swarm emits
  NavigationSignals and RoutePredictions → consumers act → dual-witness scoring settles each
  prediction → calibration and utility scores update → quality-gated examples export → the adapter
  fine-tunes → sharper predictions next cycle. This is the loop that learns to be right.
- **The trading loop (`e3d-agent-trading-floor`, every ~5 minutes).** Build the cognitive state →
  Scout and Harvest propose → Risk validates → the portfolio engine sizes → Executor records →
  Manager grades the cycle → log the training event → run again. A deterministic spine with five
  agents riding it, where AI suggests and code decides.

**Loops with skin in the game.** What separates E3D's loops from the demos crowding everyone's feed is
that they are *economically autonomous*. Every agent in every loop can carry an on-chain identity (an
`E3DNFTManager` NFT), earn a reputation scored by the loop's own outcomes, **pay** for the services it
consumes from other loops (x402, settled in E3D, priced by its tier), and **be paid** for the honest
signal it contributes. Perceive, decide, act, score, learn — and settle up. An agent is born with an
identity, funded with a wallet, and starts navigating with no human in the loop.

**Nested, not isolated.** The loops chain: the core's stories feed Maps' predictions; Maps'
predictions feed Trade's decisions; the settled outcomes from Trade and Maps flow back down into the
core and the shared adapters. Three tempos, one closed system — which is exactly what the exhaust is.

---

## 8. 🔥 The exhaust — outcomes as training feedback

A starship that threw its propellant away would be a poor design. E3D recaptures it.

Predictions and trades both **settle** — and settlement is the most valuable data the system
produces. Maps scores its predictions and exports training examples; the trading floor logs every
graded cycle. Those outcomes flow back **down** the stack into the core's intelligence and into the
adapters that power the agents. The vehicle does not just climb; it climbs **smarter on every
burn.** This is the closed loop that turns four repositories into one learning organism.

---

## 9. The launch infrastructure — how the stages connect

The stages are bolted together by **contracts, not imports.** This is a hard architectural rule, not
a stylistic preference:

> There are **no direct runtime imports** between `e3d-maps` and `e3d-agent-trading-floor`. Shared
> databases and API contracts *are* the integration boundary.

Three shared systems form the launch pad beneath the whole vehicle:

1. **ClickHouse** — the shared write-side store for predictions, outcomes, and append-only training
   data. The stages meet in the data, never in each other's call stack.
2. **API + MCP contracts** — the core's HTTP and MCP surfaces are the lingua franca. Upper stages
   read ground truth through them; the public `/api/maps/...` routes are served from the core.
3. **Qwen + LoRA adapters** — a shared inference substrate. A per-request adapter-path convention
   lets specialized agent identities ride a common serving layer, with real adapter loading kept
   behind an explicit interface until the serving infrastructure is fully defined.

The payoff of this discipline: each stage can be built, tested, deployed, and reasoned about on its
own. Replace a stage and the contract holds. Couple two stages directly and you have welded the
fuel tank to the nose cone — exactly what this architecture refuses to do.

---

## 10. End-to-end: one full burn

To see the whole vehicle fire in sequence, follow a single signal from the engines to the tip and
back:

1. **Ignition.** Capital moves on-chain — an E3D token, an NFT, a swap, a bridge transfer.
2. **Combustion.** `spacepacket` indexes it and detects a *story* — say, stealth accumulation in the
   pre-pump window.
3. **Guidance.** `e3d-maps` reads that story and emits a `RoutePrediction` and a `NavigationSignal`:
   capital is likely to flow toward a given destination, and the route is clear.
4. **Command.** The trading floor's Scout, shown a story-filtered universe and the Maps picture,
   proposes an evidence-chained candidate. Risk validates it against hard limits. The portfolio
   engine sizes it. Executor records the ticket.
5. **Exhaust.** The prediction and the trade both settle. Maps scores the prediction; the Manager
   grades the cycle. Both outcomes export as training data and flow back down into the core and the
   adapters.
6. **Next burn.** The vehicle climbs again — with sharper stories, better-calibrated predictions,
   and more disciplined agents.

---

## 11. Design principles, distilled

- **AI suggests, code decides.** Models propose; deterministic code disposes.
- **Story-first, not price-first.** Aim at the pre-pump window, never chase the candle.
- **Evidence chains, not guesses.** Every decision carries its receipts.
- **Validate before you write.** Strict schemas guard every database boundary.
- **Contracts, not imports.** Stages meet in shared data and APIs — never in each other's runtime.
- **Fail safely.** Paper mode by default; live execution is an explicit, deliberate act.
- **Close the loop.** Outcomes are fuel. Recapture the exhaust.

---

*Build the telescope, not the rear-view mirror.*
