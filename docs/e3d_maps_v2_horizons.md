# E3D Maps v2 Horizons

**Status:** Strategic backlog — not ticketed
**Source:** Fable 5 divergent analysis, June 2026
**Prerequisite:** v1.2 addendum (scoring rigor + calibration) shipped and running
with ≥30 days of calibration history before any of these are productized.

These are ordered from closest-to-build to most radical restatement of the thesis.

---

## H1. The Query Stream Is the Product

**The idea.** Every `GET /api/maps/signals` call that precedes a trade is a
pre-transaction intent signal that no on-chain data contains. An agent asking
"where is capital going in the next 4h?" with an implied size is declaring intent
before the transaction exists. The access log — aggregated and anonymized — is a
leading indicator dataset with no public equivalent. This is Waze's actual edge:
not the base map, but drivers' positions and queries feeding the map.

Concretely: build a `SignalDemandState` object that aggregates per-destination query
frequency, how quickly requested time-horizons are shrinking (urgency), and relative
volume shifts across destinations before they appear on-chain. Expose it via a new
signal type `demand_surge` or as a field on `TrafficState`.

**Why it's big.** Compounding, non-replicable data moat. Competitors can copy the
agent architecture; they cannot copy the query stream.

**Key risk.** Consumers' query patterns are their alpha — if sophisticated agents
realize their queries are being mined, they will obfuscate or leave. Requires an
explicit, documented k-anonymity / aggregation commitment from the start. Per-agent
raw queries must never be surfaced; only fleet-level aggregates.

**Near-term action.** Add query metadata logging (destination asked, requested
horizon, caller_id anonymized) to the Maps API layer *now*, before traffic is real.
The schema investment is trivial; the historical record is irreplaceable.

---

## H2. Reflexivity as a First-Class Signal Type

**The idea.** When many agents act on the same signal, the signal self-fulfills —
then self-defeats as the crowded route becomes unattractive. Today's outcome scorer
will misread crowding as accuracy: a `capital_migration → ETH_DEFI` signal looks
correct if five agents simultaneously flow into ETH_DEFI because they all read it.
The adapter gets trained to produce herd-inducing signals.

The fix — and the product — is a new signal type: `map_induced_congestion`.
"This route is elevated-risk because too many Maps consumers are already on it."
This is Maps routing agents *off* the road it created a jam on, exactly like Waze.

Longer arc: serve deliberately decorrelated route variants to different consumer
cohorts — not the same prediction to every agent — so the Maps consumer fleet does
not pile into one trade. The `consumer_exposure` field added in MAPS-1202 is the
prerequisite; once exposure is tracked, exogenous vs. induced accuracy can be
decomposed and the adapter can be trained to avoid crowding.

**Why it's big.** Every signal vendor in history dies of self-crowding (factor
decay). A map that models and manages its own market impact is categorically
different and is only buildable because Maps sees the action-linkage data.

**Key risk.** Serving different routes to different consumers is discriminatory by
design. Who gets the better route? Needs an explicit, auditable allocation policy,
or it becomes a scandal (and potentially market manipulation) machine.

**Near-term action.** The `consumer_exposure` field in MAPS-1202 is the foundational
schema decision. Make sure it ships before production volume is real.

---

## H3. Directions API: Routes on Request

**The idea.** Invert the broadcast model. Instead of `GET /api/maps/signals`
(newsletter), add `POST /api/maps/route` with `{from, to, size, risk_tolerance,
time_horizon}` → Maps returns a ranked set of concrete routes: venue sequence,
expected slippage corridor, hazard exposure per leg, estimated realization window.
Exactly like Google Maps taking your location and returning turn-by-turn directions.

Every query is itself a signal (see H1). The NavigationSignal corpus becomes the
routing graph's edge weights, re-used for personalized routing at query time.
This also becomes the natural billing surface: per-route queries, priced by
complexity or route confidence.

**Why it's big.** Turns Maps from a newspaper agents optionally consult into
infrastructure that sits in every agent's execution loop — the same transition that
made Google Maps indispensable rather than a traffic radio station.

**Key risk.** A route quote that specifies a venue sequence and expected outcome is
dangerously close to an investment recommendation. Legal exposure and blame
attribution when a quoted route loses money are much sharper than for broadcast
signals. Needs explicit "informational only, not financial advice" framing and
possibly regulatory assessment per jurisdiction before launch.

---

## H4. Hazard Signals as Insurance Primitives

**The idea.** `route_hazard` signals with calibrated probabilities and time horizons
are structurally actuarial tables for DeFi risk. The `PredictionOutcome` scoring
loop is the loss-experience data an underwriter needs.

Product surface: sell the hazard feed to lending protocols, bridge operators, and
cover protocols for automated risk-parameter updates — e.g. a protocol
auto-tightens LTV ratios when `/api/maps/hazards` fires `liquidity_drain` above a
threshold. Maps becomes a risk oracle, not just a trading intelligence feed.

This is the rare *non-reflexive* revenue line: hazard predictions get more valuable
as more consumers act on them (more protocols tighten, which actually reduces the
hazard), unlike trading alpha which decays under consumption.

**Why it's big.** Protocol foundations and risk teams have real budgets, multi-year
horizons, and zero alpha-decay dynamics. It's a customer base entirely orthogonal to
the trading market.

**Key risk.** Tail-risk calibration requires far more history than 30 days. One
missed bridge exploit after the feed has been marketed as "coverage-grade" is
existential. Ship strictly as an advisory feed in v2; do not accept liability.
Consider advance-notice to the flagged protocol before public publication of
`contract_risk` or `bridge_risk` hazards (both courtesy and legal protection).

---

## H5. The Adapter's World-Model as a Queryable Artifact ("Maps SDK")

**The idea.** The fine-tuned Maps adapter is a model that has internalized
question→evidence→prediction→realized-outcome tuples across months of on-chain
history. Today it is only used to generate signals internally.

Productize the *representation*: per-protocol and per-asset embedding vectors
("position in capital-flow space"), similarity queries ("what does the current scene
most resemble historically, and what happened next?"), and scene-retrieval over the
signal archive. Downstream agents stop consuming your conclusions and start consuming
your *geometry* — building their own agents on top of it.

This is "Maps SDK" vs. "Maps app": sell the learned manifold of on-chain
regime-space as a platform primitive, not a feed.

**Why it's big.** Signals are perishable; a learned latent space of on-chain
capital-flow regimes is durable IP and the basis for a platform flywheel (others
build on it, each new consumer adds training signal back in).

**Key risk.** Embedding APIs are easy to exfiltrate via bulk queries. Also hands
customers the means to disintermediate the signal product by building their own
fine-tunes on top of the embeddings. Requires rate-limiting, authentication, and a
clear platform licensing story.

---

## H6. Road Authority Market: Protocol Operators, Treasuries, Supervisors

**The idea.** Everything in v1 aims downstream at trading agents. But the same
TrafficState / congestion / hazard machinery answers questions for the people who
*own the roads*: L2 teams ("is our route emerging or closing? where are we losing
traffic to a competitor chain?"), DAO treasuries ("is our token's liquidity route
degrading?"), market-structure researchers, and eventually regulators ("systemic
congestion early warning — on-chain FAA traffic-flow center").

Concretely: a `RouteHealthReport` product keyed by protocol or chain rather than by
trade opportunity, delivered as a recurring report to protocol foundations. Same
Maps agents, same signals, different question queue and a report schema. Marginal
build cost is low.

**Why it's big.** Protocol foundations have CFO-level budgets, multi-year
relationships, and zero alpha-decay dynamics. They are indifferent to whether
trading agents front-run the reports. It diversifies revenue away from the reflexive
trading market.

**Key risk.** Publishing hazard signals about specific protocols to paying external
audiences is defamation-adjacent and can itself trigger the bank run (liquidity
drain headline → actual drain). Publication policy needs tiers: subject protocol
gets advance notice; public publication is lagged or aggregated.

---

## H7. Air-Traffic Control: Maps as Coordination Substrate (Most Radical)

**The idea.** Once multiple agents — treasury, trading, research — all read the same
TrafficState, Maps is de facto a *blackboard* (shared world-model for a
multi-agent system). The radical move: lean into it. Add write-back primitives where
consumer agents post a `RouteIntent` ("I plan to move $X along route Y starting at
T") and Maps performs slot allocation and deconfliction — air-traffic control, not
just navigation.

Within E3D's own fleet this immediately prevents self-collision (two house agents
bidding against each other in the same pool). Externally it becomes the protocol by
which third-party agents coordinate around each other's flow. Declared intents also
massively enrich the training corpus: planned route vs. realized action vs.
outcome is the richest possible training signal.

**Why it's big.** "Navigation feed" is a feature; "the coordination layer that
agents must register with to avoid colliding" is a network-effect chokepoint — the
TCP/IP move for autonomous finance. It is the natural end-state of the entire
agentic-finance thesis.

**Key risk.** An intent registry is the world's best front-running feed if leaked
or sold. It is also potentially a cartel-coordination facility in regulators' eyes.
Requires commit-reveal mechanics (intents are hashed commitments, not plain text,
until post-execution), strict access controls, and legal review before any external
access is offered.

---

## Suggested v2 Priority Order

```text
H1 (query-stream logging)  — add schema + logging NOW, zero cost, irreplaceable later
H2 (reflexivity signals)   — consumer_exposure in MAPS-1202 is the prerequisite
H3 (Directions API)        — build after FlowGraph (v1.2 Phase 13) makes routing natural
H4 (hazard primitives)     — build after v1.2 Phase 14 calibration ships ≥30 day history
H6 (road authority market) — parallel business track, low build cost, different GTM
H5 (adapter SDK)           — after adapter v0.1 is trained and validated
H7 (ATC / coordination)    — long arc; design review required before any implementation
```

The single most important near-term action across all seven: **log query metadata
today (H1) and add `consumer_exposure` to MAPS-1202 (H2 prerequisite)**. Both are
schema decisions that cost almost nothing now and are impossible to reconstruct
retroactively once production traffic exists.
