import { React } from "../vendor.js";

const el = React.createElement;

function Section({ eyebrow, title, children }) {
  const kids = Array.isArray(children) ? children : [children];
  return el("section", { className: "wp-section panel" },
    el("div", { className: "wp-section-header" },
      eyebrow ? el("p", { className: "eyebrow" }, eyebrow) : null,
      el("h2", null, title)
    ),
    el("div", { className: "wp-body" }, ...kids)
  );
}

function Quote({ text, attribution }) {
  return el("blockquote", { className: "wp-quote" },
    el("p", null, "“", text, "”"),
    attribution ? el("cite", null, "— ", attribution) : null
  );
}

function Callout({ children }) {
  const kids = Array.isArray(children) ? children : [children];
  return el("div", { className: "wp-callout" }, ...kids);
}

export function WhitepaperPage() {
  return el("div", { className: "wp-root" },

    el("section", { className: "wp-hero" },
      el("p", { className: "eyebrow" }, "Whitepaper · June 2026"),
      el("h1", null, "E3D Maps: Navigation Intelligence for the Autonomous Capital Age"),
      el("p", { className: "wp-lead" },
        "How a navigation layer for on-chain agents transforms autonomous capital deployment from a blind guess into a GPS-guided certainty — and why the next generation of financial autonomy runs on real-time maps, not intuition."
      ),
      el("div", { className: "wp-meta" },
        el("span", null, "maps.e3d.ai"),
        el("span", { className: "wp-meta-sep" }, "·"),
        el("span", null, "E3D Ecosystem"),
        el("span", { className: "wp-meta-sep" }, "·"),
        el("span", null, "Confidential — For Authorized Agents and Operators")
      )
    ),

    el(Section, { eyebrow: "Executive Summary", title: "The Map Has Arrived" },
      el("p", null, "For most of human financial history, capital moved blind. Traders stared at charts and hoped. Algorithms fired at shadows. Even the most sophisticated quantitative funds were essentially driving cross-country at night with their headlights off — reacting to what they could see one second at a time, with no view of what lay around the next curve."),
      el("p", null, "On-chain capital is different in every way that matters — except that one. Ethereum and its expanding multichain universe constitute the most transparent financial road network ever built. Every transaction is a vehicle. Every protocol is an intersection. Every wallet is a driver. The roads are lit, the traffic is real, and the data is public. What was missing was the map."),
      el("p", null, "E3D Maps is the map."),
      el("p", null, "Built as the navigation intelligence layer for autonomous agents operating across the E3D ecosystem, E3D Maps transforms raw on-chain data into structured, machine-readable navigation signals — real-time answers to the questions every agent needs answered before moving capital: Where is money flowing? Which routes are congested? Which destinations are gaining probability? What hazards lie ahead? And above all: what should I do next?"),
      el(Quote, {
        text: "You wouldn't drive from New York to Los Angeles without GPS. Why would you deploy capital across a $3 trillion on-chain ecosystem without a navigation layer?",
        attribution: "E3D Ecosystem"
      })
    ),

    el(Section, { eyebrow: "The Problem", title: "Driving Blind at Highway Speed" },
      el("p", null, "Cast your mind back to the year 2006. You're in an unfamiliar city, it's raining, and you're late. You have a printout from MapQuest that takes you to the wrong exit, and by the time you find a gas station to ask for directions, you've missed your turn twice. Your frustration is not a personal failing. It is the result of operating a complex spatial navigation task without real-time intelligence. The roads were there. The destination was there. What was missing was the layer between them."),
      el("p", null, "That was driving before Google Maps. That is on-chain capital deployment today."),
      el("p", null, "A trading agent wakes up. Ethereum's L2 ecosystem has generated 40 million transactions in the last 24 hours. Whale wallets have moved $800 million across protocols. Stablecoin mint and burn events have spiked. Three major liquidity pools have rebalanced. Exchange netflows have shifted direction four times. Bridge volumes on Arbitrum are at a 30-day high."),
      el("p", null, "What does any of it mean? Where is the signal in the noise? Which data points are leading indicators, and which are noise from bots? Is capital rotating into ETH, or is the whale wallet movement a false positive from an OTC desk? Should the agent increase exposure or hedge?"),
      el("p", null, "Without a navigation layer, the agent is doing what every pre-GPS driver did: triangulating from incomplete landmarks, making costly wrong turns, and arriving late to moves that happened while it was still trying to figure out which way was north."),
      el(Callout, null,
        el("p", null, "The on-chain world is not short on data. It is short on navigation. The difference between data and navigation is the difference between a satellite photo of a city and a turn-by-turn route to your destination.")
      )
    ),

    el(Section, { eyebrow: "The Core Analogy", title: "Tesla Full Self-Driving Meets Google Maps for On-Chain Capital" },
      el("p", null, "To understand what E3D Maps does, you first need to understand what it is like to be an autonomous agent operating across a multi-chain financial ecosystem."),
      el("p", null, "Imagine Tesla's Full Self-Driving system. It is a machine — extraordinarily capable, continuously learning, operating at speeds and reaction times no human can match. But FSD does not navigate by instinct. It navigates by perception fused with intelligence. The car has sensors: cameras, radar, LIDAR. Those sensors see the road. But seeing the road is not the same as understanding the road. FSD needs to know not just what is directly in front of it, but what traffic looks like three miles ahead, whether the highway on-ramp it is targeting is congested, whether there is a construction closure on its planned route, and which alternate route delivers the fastest arrival time given current conditions."),
      el("p", null, "That intelligence comes from a navigation system. Without it, FSD is powerful but directionless — capable of executing a drive, but unable to plan one."),
      el("p", null, "Now substitute the FSD vehicle with an autonomous trading agent. The roads are Ethereum, Base, Arbitrum, and every other chain in the multichain universe. The traffic is the $3 trillion in on-chain capital that flows across protocols, DEXes, bridges, wallets, and exchanges every day. The destinations are assets, protocols, liquidity positions, yield opportunities. And the congestion, the hazards, the closures — those are the liquidity crunches, exchange outflow spikes, bridge delays, and smart money rotations that can turn a high-conviction trade into a catastrophic wrong-way drive."),
      el(Quote, {
        text: "An autonomous agent without a navigation layer is like a Tesla with FSD but no GPS — technically capable of driving, but operationally lost.",
        attribution: "E3D Maps Architecture Principles"
      }),
      el("p", null, "E3D Maps is the navigation system that turns capable agents into directed agents. It does not drive the car. It tells the car where to go, what to avoid, and how confident it should be in every decision — in real time, at machine speed, with verifiable evidence."),
      el("p", null, "Before Google Maps, getting somewhere unfamiliar required mental overhead that was exhausting and error-prone. You had to hold the map in your head, estimate distances, remember turns, recalculate after every wrong exit. You arrived stressed, late, and half-certain you'd missed something. After Google Maps, navigation became effortless. You followed the signal. You arrived on time. You never thought about routing at all — you just drove."),
      el("p", null, "That is the transformation E3D Maps delivers for autonomous capital. Not incremental improvement. Not slightly better data. A categorical leap from manual triangulation to real-time guided intelligence. From driving blind to turn-by-turn certainty.")
    ),

    el(Section, { eyebrow: "The Infrastructure", title: "The Roads Are Already Built — They Just Needed a Map" },
      el("p", null, "One of the most remarkable facts about the on-chain financial universe is that its infrastructure already exists at a scale that dwarfs anything human financial markets have previously attempted. Ethereum alone settles more transactions per day than many traditional financial systems process in a month. Layer 2 networks like Arbitrum, Base, and Optimism have added orders of magnitude more throughput. Bridge protocols shuttle billions of dollars between ecosystems. DEXes execute trades 24 hours a day, 365 days a year, without a single human market maker in the loop."),
      el("p", null, "The roads are built. The vehicles — autonomous agents — are multiplying. What the ecosystem has lacked is the navigation layer that sits between them and makes the entire system intelligent rather than merely fast."),
      el("p", null, "Think of Ethereum as the interstate highway system. It is vast, well-maintained, and carries enormous volume. Layer 2s are the local road networks — faster in some conditions, more specialized, lower cost for certain routes. Bridges are the tunnels and interchanges that connect them. DEXes are the intersections. Liquidity pools are the parking lots — sometimes full, sometimes empty, always worth checking before you try to pull in."),
      el("p", null, "On this road network, capital is the vehicle. Transactions are the act of driving. And the patterns of where capital moves, how fast, through which protocols, in what volume, and in what sequence — those are the traffic patterns that, properly read, tell you everything you need to know about where the smart money is going and where the jams are forming."),
      el("p", null, "E3D Maps reads those patterns. It watches the traffic in real time, synthesizes it into structured intelligence, and delivers it to agents as actionable navigation signals — so every agent on the road is driving with a full map, updated by the second.")
    ),

    el(Section, { eyebrow: "The Architecture", title: "How E3D Maps Works" },
      el("p", null, "E3D Maps is a purpose-built intelligence layer, not a data pipe. The distinction matters enormously. Data pipes deliver raw information. Intelligence layers deliver answers."),
      el("p", null, "At the input layer, E3D Maps consumes stories from the E3D platform — structured narratives derived from on-chain events, wallet behaviors, exchange flows, stablecoin activity, and whale movements. These stories arrive classified by type: capital migrations, exchange flows, stablecoin activity, wallet accumulation patterns, and large-position whale movements. Each story type carries a different navigation implication, and E3D Maps agents are trained to understand exactly what each one means."),
      el("p", null, "At the processing layer, Maps agents interpret incoming stories as navigation evidence. A surge in stablecoin minting on a particular chain is not just a data point — it is a potential leading indicator of capital ready to deploy. Three whale wallets accumulating the same asset across separate CEXes is not just a coincidence — it is a confidence-weighted signal that a destination is gaining conviction among sophisticated capital. Exchange outflows from a specific asset are not just a flow statistic — they are a potential hazard on the route to that asset."),
      el("p", null, "Agents synthesize this evidence into NavigationSignals: machine-readable, schema-validated objects that answer specific navigation questions with a confidence score, a risk level, a recommended action, and a time horizon. These signals are the output layer — written to ClickHouse, served over a read-only REST API, and consumed by downstream agents in real time."),
      el("p", null, "The TrafficState is the aggregated view — the map itself. It represents the current state of the entire on-chain capital landscape: dominant flows, congestion zones, active hazards, and top destinations by confidence. An agent that calls /api/maps/state gets a complete situational picture in a single API response."),
      el(Callout, null,
        el("p", null, "Every signal that leaves E3D Maps is schema-validated, confidence-scored, and evidence-backed. Agents do not guess. They navigate."),
        el("p", null, "NavigationSignals include: capital_migration, destination_prediction, route_hazard, route_closure, congestion_formation, liquidity_forecast, and capital_conviction — each a distinct type of navigation intelligence, each carrying everything a downstream agent needs to act.")
      )
    ),

    el(Section, { eyebrow: "What This Unlocks", title: "From Reactive to Predictive: The Autonomous Capital Frontier" },
      el("p", null, "The implications of real-time navigation intelligence for autonomous agents extend far beyond faster execution. They represent a categorical change in what autonomous capital can accomplish."),
      el("p", null, "A trading agent without navigation is reactive — it sees price move and responds. A trading agent with E3D Maps is predictive — it sees capital rotating before the price moves and positions ahead of the trade. The difference in performance is not linear. It is exponential, because the agent is not competing with other reactive agents on execution speed. It is operating in a different information space entirely."),
      el("p", null, "A treasury agent without navigation is conservative — it holds positions it cannot read and hedges against uncertainty it cannot quantify. A treasury agent with E3D Maps is decisive — it can identify specific protocol risks in real time, route capital away from congested or hazardous zones, and concentrate exposure in destinations where conviction is building across multiple signals simultaneously."),
      el("p", null, "A research agent without navigation generates analysis that may already be stale by the time it is read. A research agent with E3D Maps generates analysis grounded in the current state of capital flow — real-time, evidence-weighted, and continuously updated as the map evolves."),
      el("p", null, "This is the autonomous capital frontier: a future where agents do not just execute transactions faster than humans — they navigate more intelligently, with better information, at lower risk, continuously, without fatigue, and with full transparency into every decision they make."),
      el(Quote, {
        text: "The question is not whether agents will navigate on-chain capital. They already do. The question is whether they do it blind or with a map.",
        attribution: "E3D Maps"
      })
    ),

    el(Section, { eyebrow: "The API", title: "Built for Agents First" },
      el("p", null, "E3D Maps is not a human dashboard with an API bolted on. It is an agent-native intelligence system with a human-readable interface layered over it. The primary consumers are machines. The primary data format is structured JSON. The primary interaction pattern is polling — agents query the state, consume the signals, act, and poll again."),
      el("p", null, "The API surface is deliberately minimal and composable. /api/maps/state returns the full current map in one call. /api/maps/signals with filters returns precision intelligence for any asset, chain, signal type, confidence threshold, or time horizon combination. /api/maps/predictions surfaces forward-looking destination probability. /api/maps/hazards surfaces everything an agent needs to know to avoid bad routes. /api/maps/congestion identifies zones where capital is building faster than it can clear."),
      el("p", null, "No authentication. No rate limits for authorized agents. No pagination overhead for standard queries. The API is designed to be fast, reliable, and invisible — something the agent calls without thinking, the same way you tap the navigation icon before every drive without thinking about how GPS works."),
      el("p", null, "Because that is the point. Navigation should be infrastructure, not overhead.")
    ),

    el(Section, { eyebrow: "The Vision", title: "A Navigation Layer for Every Agent in the Ecosystem" },
      el("p", null, "E3D Maps is the first piece of infrastructure built specifically for the autonomous capital age — an age in which trillions of dollars of on-chain capital is managed, deployed, rebalanced, and protected by machines operating at speeds and scales that make human oversight impractical as the primary control mechanism."),
      el("p", null, "In this age, the quality of navigation intelligence is the primary determinant of agent performance. Not execution speed — execution is already a solved problem. Not data access — data is already public and abundant. Navigation. The capacity to synthesize data into structured intelligence, to answer navigation questions with confidence and evidence, and to update those answers continuously as conditions change."),
      el("p", null, "The vision for E3D Maps is to become the navigation standard for every autonomous agent operating across the on-chain financial ecosystem. The same way Google Maps became the default navigation layer for every human driver — regardless of vehicle, regardless of destination, regardless of time — E3D Maps aims to become the default navigation layer for every autonomous agent."),
      el("p", null, "Not because there is no other option. Because it is simply the best map available, and agents, like drivers, will always choose the best map."),
      el(Quote, {
        text: "We didn't replace the roads. We mapped them. And once you have the map, everything changes.",
        attribution: "E3D Maps"
      }),
      el("p", null, "The roads are Ethereum. The vehicles are your agents. The map is E3D Maps."),
      el("p", { className: "wp-closing" }, "Drive with confidence.")
    ),

    el("section", { className: "wp-footer panel" },
      el("p", { className: "eyebrow" }, "Access"),
      el("h2", null, "Get Started"),
      el("div", { className: "wp-cta-grid" },
        el("div", { className: "wp-cta" },
          el("p", { className: "wp-cta-label" }, "Live API"),
          el("code", { className: "wp-cta-url" }, "https://maps.e3d.ai/api/maps/state"),
          el("p", { className: "wp-cta-desc" }, "No authentication required. Query the current traffic state right now.")
        ),
        el("div", { className: "wp-cta" },
          el("p", { className: "wp-cta-label" }, "API Reference"),
          el("code", { className: "wp-cta-url" }, "maps.e3d.ai/api-docs"),
          el("p", { className: "wp-cta-desc" }, "Full endpoint documentation with request and response examples.")
        ),
        el("div", { className: "wp-cta" },
          el("p", { className: "wp-cta-label" }, "Story Taxonomy"),
          el("code", { className: "wp-cta-url" }, "maps.e3d.ai/docs"),
          el("p", { className: "wp-cta-desc" }, "The full story type taxonomy: what each type means, how agents use it, and which signals it supports.")
        )
      )
    )
  );
}
