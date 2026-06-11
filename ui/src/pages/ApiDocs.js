import { React } from "../vendor.js";

const el = React.createElement;
const BASE = "https://maps.e3d.ai";

const ENDPOINTS = [
  {
    path: "/api/maps/state",
    description: "Returns the latest TrafficState — the current map of the market: dominant flows, congestion zones, active hazards, and top capital destinations. The primary situational-awareness endpoint for agents before making a decision.",
    params: [],
    example: `curl ${BASE}/api/maps/state`,
    response: `{\n  "status": "ok",\n  "state": {\n    "id": "ts_01j...",\n    "scope": "global",\n    "market_state": "risk_on",\n    "dominant_flows": [\n      { "origin": "stablecoins", "destination": "ETH", "strength": "strong" }\n    ],\n    "congestion_zones": ["DEX aggregators", "L2 bridges"],\n    "hazards": ["exchange_outflow_spike"],\n    "top_destinations": [\n      { "destination": "ETH", "confidence": 0.84 }\n    ],\n    "created_at": "2026-06-09T16:00:00Z"\n  }\n}`,
  },
  {
    path: "/api/maps/signals",
    description: "List NavigationSignals with optional filters. Signals are the core output of Maps agents — each answers a navigation question with confidence, risk level, and a recommended action.",
    params: [
      { name: "signal_type", type: "string", desc: "capital_migration, destination_prediction, route_hazard, route_closure, congestion_formation, liquidity_forecast, capital_conviction" },
      { name: "asset", type: "string", desc: "Filter to signals including this asset in asset_scope (e.g. ETH, BTC, USDC)" },
      { name: "chain", type: "string", desc: "Filter to signals including this chain in chain_scope (e.g. ethereum, base, arbitrum)" },
      { name: "min_confidence", type: "float", desc: "Minimum confidence 0.0-1.0. Use 0.8 for high-confidence signals only." },
      { name: "time_horizon_hours", type: "integer", desc: "Exact match on signal time horizon (e.g. 4, 12, 24, 72)" },
      { name: "limit", type: "integer", desc: "Max results per page (default 50, max 500)" },
      { name: "offset", type: "integer", desc: "Pagination offset" },
    ],
    example: `curl "${BASE}/api/maps/signals?asset=ETH&min_confidence=0.8"\ncurl "${BASE}/api/maps/signals?signal_type=capital_migration"`,
    response: `{\n  "status": "ok",\n  "signals": [\n    {\n      "id": "ns_01j...",\n      "signal_type": "capital_migration",\n      "question": "Is capital rotating from stablecoins into ETH?",\n      "answer": "Yes — stablecoin netflows suggest a high-probability rotation into ETH over 24h.",\n      "origin": "stablecoins",\n      "destination": "ETH",\n      "confidence": 0.87,\n      "risk_level": "medium",\n      "signal_strength": "strong",\n      "recommended_action": "increase_exposure",\n      "outcome_status": "pending",\n      "created_at": "2026-06-09T15:30:00Z"\n    }\n  ],\n  "pagination": { "limit": 50, "offset": 0, "count": 1, "has_more": false }\n}`,
  },
  {
    path: "/api/maps/signals/:id",
    description: "Fetch a single NavigationSignal by ID, including full evidence and recommended route details.",
    params: [],
    example: `curl ${BASE}/api/maps/signals/ns_01j...`,
    response: `{\n  "status": "ok",\n  "signal": {\n    "evidence": [\n      { "id": "ev_01", "type": "wallet_flow", "summary": "3 tracked wallets moved $12M from USDT to ETH." }\n    ],\n    "recommended_route": { "origin": "stablecoins", "destination": "ETH", "via": "spot" }\n  }\n}`,
  },
  {
    path: "/api/maps/predictions",
    description: "Returns capital_migration and destination_prediction signals — the forward-looking layer. Agents use these to position before a move, not after.",
    params: [
      { name: "limit", type: "integer", desc: "Max results (default 50, max 500)" },
      { name: "offset", type: "integer", desc: "Pagination offset" },
    ],
    example: `curl "${BASE}/api/maps/predictions?limit=10"`,
    response: `{\n  "status": "ok",\n  "predictions": [ ... ],\n  "pagination": { "limit": 10, "offset": 0, "count": 10, "has_more": true }\n}`,
  },
  {
    path: "/api/maps/destinations",
    description: "Returns destination_prediction signals ranked by confidence descending. Use this to find the highest-probability capital destinations right now.",
    params: [
      { name: "limit", type: "integer", desc: "Max results (default 50, max 500)" },
      { name: "offset", type: "integer", desc: "Pagination offset" },
    ],
    example: `curl "${BASE}/api/maps/destinations?limit=5"`,
    response: `{\n  "status": "ok",\n  "destinations": [\n    { "destination": "ETH", "confidence": 0.91 },\n    { "destination": "BTC", "confidence": 0.78 }\n  ]\n}`,
  },
  {
    path: "/api/maps/hazards",
    description: "Returns route_hazard and route_closure signals. Check hazards before executing a route to avoid exchange halts, bridge congestion, or liquidity gaps.",
    params: [
      { name: "limit", type: "integer", desc: "Max results (default 50, max 500)" },
      { name: "offset", type: "integer", desc: "Pagination offset" },
    ],
    example: `curl ${BASE}/api/maps/hazards`,
    response: `{\n  "status": "ok",\n  "hazards": [\n    {\n      "signal_type": "route_hazard",\n      "answer": "Elevated congestion on Arbitrum bridge. Expected delay: 20-40 min.",\n      "confidence": 0.82,\n      "risk_level": "high"\n    }\n  ]\n}`,
  },
  {
    path: "/api/maps/congestion",
    description: "Returns congestion_formation signals — zones where capital is accumulating faster than it can clear. Useful for timing entries and exits.",
    params: [
      { name: "limit", type: "integer", desc: "Max results (default 50, max 500)" },
      { name: "offset", type: "integer", desc: "Pagination offset" },
    ],
    example: `curl ${BASE}/api/maps/congestion`,
    response: `{\n  "status": "ok",\n  "congestion": [\n    {\n      "signal_type": "congestion_formation",\n      "answer": "High slippage detected across DEX aggregators for ETH pairs over $500k.",\n      "confidence": 0.79\n    }\n  ]\n}`,
  },
  {
    path: "/api/maps/routes",
    description: "Returns RoutePrediction records — structured predictions about specific capital routes including expected flow direction, magnitude, and time horizon.",
    params: [
      { name: "limit", type: "integer", desc: "Max results (default 50, max 500)" },
      { name: "offset", type: "integer", desc: "Pagination offset" },
    ],
    example: `curl "${BASE}/api/maps/routes?limit=20"`,
    response: `{\n  "status": "ok",\n  "routes": [\n    {\n      "route_type": "capital_rotation",\n      "origin": "stablecoins",\n      "destination": "ETH",\n      "expected_flow_direction": "inflow",\n      "expected_flow_magnitude": "large",\n      "time_horizon_hours": 24,\n      "confidence": 0.85\n    }\n  ]\n}`,
  },
  {
    path: "/api/story-types",
    description: "Returns all StoryTypeDefinitions — the taxonomy of on-chain story types that Maps agents interpret as navigation evidence.",
    params: [],
    example: `curl ${BASE}/api/story-types`,
    response: `{\n  "status": "ok",\n  "story_types": [\n    {\n      "story_type": "capital_migration",\n      "display_name": "Capital Migration",\n      "category": "traffic",\n      "human_meaning": "Capital appears to be moving from one sector, asset, or protocol to another.",\n      "agent_meaning": "Use as evidence of changing capital routes and destination probabilities.",\n      "inputs": ["wallet_flows", "token_transfers"],\n      "related_navigation_signal_types": ["capital_migration", "destination_prediction"]\n    }\n  ]\n}`,
  },
  {
    path: "/api/story-types/:type",
    description: "Fetch a single StoryTypeDefinition by its story_type slug.",
    params: [],
    example: `curl ${BASE}/api/story-types/capital_migration`,
    response: `{ "status": "ok", "story_type": { ... } }`,
  },
];

function Endpoint({ path, description, params, example, response }) {
  return el("article", { className: "panel api-endpoint" },
    el("div", { className: "api-route" },
      el("span", { className: "api-method" }, "GET"),
      el("code", { className: "api-path" }, path)
    ),
    el("p", { className: "api-description" }, description),
    params.length > 0 && el("div", { className: "table-wrap" },
      el("table", { className: "data-table api-params" },
        el("thead", null,
          el("tr", null,
            el("th", null, "Parameter"),
            el("th", null, "Type"),
            el("th", null, "Description")
          )
        ),
        el("tbody", null,
          ...params.map((p) =>
            el("tr", { key: p.name },
              el("td", null, el("code", null, p.name)),
              el("td", { className: "api-type" }, p.type),
              el("td", null, p.desc)
            )
          )
        )
      )
    ),
    el("div", { className: "api-example" },
      el("p", { className: "panel-label" }, "Example request"),
      el("pre", { className: "code-block" }, example)
    ),
    el("div", { className: "api-example" },
      el("p", { className: "panel-label" }, "Example response"),
      el("pre", { className: "code-block" }, response)
    )
  );
}

export function ApiDocsPage() {
  return el("div", null,
    el("section", { className: "page-header" },
      el("div", null,
        el("p", { className: "eyebrow" }, "API Reference"),
        el("h2", null, "Agent API")
      )
    ),
    el("div", { className: "panel api-intro" },
      el("p", null,
        "The E3D Maps API is a read-only REST API designed for agents. All endpoints return JSON. Base URL: ",
        el("code", null, BASE),
        ". No authentication required."
      ),
      el("p", { style: { marginTop: "12px" } },
        "Agents should poll ",
        el("code", null, "/api/maps/state"),
        " for situational awareness and ",
        el("code", null, "/api/maps/signals"),
        " for actionable signals. High-confidence signals (min_confidence=0.8) are the primary inputs for trading and treasury decisions."
      )
    ),
    ...ENDPOINTS.map((ep) => el(Endpoint, { key: ep.path, ...ep }))
  );
}
