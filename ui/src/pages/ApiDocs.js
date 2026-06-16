import { React, useState } from "../vendor.js";

const el = React.createElement;
const BASE = "https://maps.e3d.ai";

const SIGNAL_TYPE_ENUM = [
  "capital_migration",
  "destination_prediction",
  "route_hazard",
  "route_closure",
  "congestion_formation",
  "liquidity_forecast",
  "capital_conviction",
];

const OBJECTIVE_ENUM = [
  "grow_capital",
  "preserve_capital",
  "reduce_risk",
  "seek_opportunity",
  "monitor_market",
];

const ENDPOINTS = [
  {
    path: "/api/maps/recommendations",
    description: "Returns a ranked list of recommended actions synthesized from all available navigation intelligence — signals, routes, hazards, congestion, and predictions. The primary decision-support endpoint for autonomous agents.",
    pathParams: [],
    queryParams: [
      { name: "objective", type: "string", enum: OBJECTIVE_ENUM, desc: "Agent objective — shapes action recommendations" },
      { name: "asset", type: "string", placeholder: "ETH", desc: "Focus on a specific asset (e.g. ETH, BTC, LINK)" },
      { name: "address", type: "string", placeholder: "0x1234...", desc: "Focus on a wallet or contract address" },
      { name: "storyType", type: "string", placeholder: "capital_migration", desc: "Limit to signals from a specific story category" },
      { name: "maxResults", type: "integer", placeholder: "10", desc: "Max recommendations (default 10, max 100)" },
    ],
    exampleResponse: `{
  "generatedAt": "2026-06-12T03:00:00Z",
  "objective": "seek_opportunity",
  "recommendations": [
    {
      "rank": 1,
      "title": "Capital Rotating to ETH_DEFI",
      "action": "increase_attention",
      "confidence": 92,
      "risk": 35,
      "score": 81,
      "reasoning": [
        "Capital appears to be moving toward ETH DeFi.",
        "2 supporting signals"
      ],
      "supportingSignals": ["navsig_01J", "navsig_02J"],
      "storyType": "CapitalRotation"
    }
  ]
}`,
  },
  {
    path: "/api/maps/state",
    description: "Returns the latest TrafficState — the current map of the market: dominant flows, congestion zones, active hazards, and top capital destinations. The primary situational-awareness endpoint for agents before making a decision.",
    pathParams: [],
    queryParams: [],
    exampleResponse: `{
  "status": "ok",
  "state": {
    "id": "ts_01j...",
    "scope": "global",
    "market_state": "risk_on",
    "dominant_flows": [
      { "origin": "stablecoins", "destination": "ETH", "strength": "strong" }
    ],
    "congestion_zones": ["DEX aggregators", "L2 bridges"],
    "hazards": ["exchange_outflow_spike"],
    "top_destinations": [
      { "destination": "ETH", "confidence": 0.84 }
    ],
    "created_at": "2026-06-09T16:00:00Z"
  }
}`,
  },
  {
    path: "/api/maps/news",
    description: "Returns the latest MapsNewsBrief — a short editorial read of current market conditions derived from the stored Maps artifact. A 404 not_found means the artifact has not been generated yet and should be treated as an empty state.",
    pathParams: [],
    queryParams: [],
    exampleResponse: `{
  "status": "ok",
  "news": {
    "headline": "Ethereum is active, but route quality is deteriorating",
    "summary": "Flows remain live across ETH DeFi and major venues, but congestion and route closures suggest a crowded environment with rising execution risk.",
    "stance": "cautious",
    "tags": ["ethereum", "congestion"],
    "generated_at": "2026-06-16T13:52:17Z"
  }
}`,
  },
  {
    path: "/api/maps/cross-chain",
    description: "Returns the latest CrossChainActivityState — the structured cross-chain, bridge, L2, and venue snapshot. A 404 not_found means the artifact has not been generated yet and should be treated as an empty state.",
    pathParams: [],
    queryParams: [],
    exampleResponse: `{
  "status": "ok",
  "cross_chain": {
    "market_bias": "neutral",
    "top_routes": [],
    "active_hazards": [],
    "active_congestion": [],
    "top_destinations": [],
    "ethereum_outbound_routes": [],
    "ethereum_inbound_routes": [],
    "created_at": "2026-06-16T13:52:17Z"
  }
}`,
  },
  {
    path: "/api/maps/signals",
    description: "List NavigationSignals with optional filters. Signals are the core output of Maps agents — each answers a navigation question with confidence, risk level, and a recommended action.",
    pathParams: [],
    queryParams: [
      { name: "signal_type", type: "string", enum: SIGNAL_TYPE_ENUM, desc: "Filter by signal type" },
      { name: "asset", type: "string", placeholder: "ETH", desc: "Filter by asset (e.g. ETH, BTC, USDC)" },
      { name: "chain", type: "string", placeholder: "ethereum", desc: "Filter by chain (e.g. ethereum, base, arbitrum)" },
      { name: "min_confidence", type: "float", placeholder: "0.8", desc: "Minimum confidence 0.0–1.0" },
      { name: "time_horizon_hours", type: "integer", placeholder: "24", desc: "Exact match on time horizon in hours" },
      { name: "limit", type: "integer", placeholder: "50", desc: "Max results per page (default 50, max 500)" },
      { name: "offset", type: "integer", placeholder: "0", desc: "Pagination offset" },
    ],
    exampleResponse: `{
  "status": "ok",
  "signals": [
    {
      "id": "ns_01j...",
      "signal_type": "capital_migration",
      "question": "Is capital rotating from stablecoins into ETH?",
      "answer": "Yes — stablecoin netflows suggest a high-probability rotation into ETH over 24h.",
      "origin": "stablecoins",
      "destination": "ETH",
      "confidence": 0.87,
      "risk_level": "medium",
      "signal_strength": "strong",
      "recommended_action": "increase_exposure",
      "outcome_status": "pending",
      "created_at": "2026-06-09T15:30:00Z"
    }
  ],
  "pagination": { "limit": 50, "offset": 0, "count": 1, "has_more": false }
}`,
  },
  {
    path: "/api/maps/signals/:id",
    description: "Fetch a single NavigationSignal by ID, including full evidence and recommended route details.",
    pathParams: [
      { name: "id", placeholder: "ns_01j...", desc: "NavigationSignal ID" },
    ],
    queryParams: [],
    exampleResponse: `{
  "status": "ok",
  "signal": {
    "evidence": [
      { "id": "ev_01", "type": "wallet_flow", "summary": "3 tracked wallets moved $12M from USDT to ETH." }
    ],
    "recommended_route": { "origin": "stablecoins", "destination": "ETH", "via": "spot" }
  }
}`,
  },
  {
    path: "/api/maps/predictions",
    description: "Returns capital_migration and destination_prediction signals — the forward-looking layer. Agents use these to position before a move, not after.",
    pathParams: [],
    queryParams: [
      { name: "limit", type: "integer", placeholder: "50", desc: "Max results (default 50, max 500)" },
      { name: "offset", type: "integer", placeholder: "0", desc: "Pagination offset" },
    ],
    exampleResponse: `{
  "status": "ok",
  "predictions": [ ... ],
  "pagination": { "limit": 10, "offset": 0, "count": 10, "has_more": true }
}`,
  },
  {
    path: "/api/maps/destinations",
    description: "Returns destination_prediction signals ranked by confidence descending. Use this to find the highest-probability capital destinations right now.",
    pathParams: [],
    queryParams: [
      { name: "limit", type: "integer", placeholder: "50", desc: "Max results (default 50, max 500)" },
      { name: "offset", type: "integer", placeholder: "0", desc: "Pagination offset" },
    ],
    exampleResponse: `{
  "status": "ok",
  "destinations": [
    { "destination": "ETH", "confidence": 0.91 },
    { "destination": "BTC", "confidence": 0.78 }
  ]
}`,
  },
  {
    path: "/api/maps/hazards",
    description: "Returns route_hazard and route_closure signals. Check hazards before executing a route to avoid exchange halts, bridge congestion, or liquidity gaps.",
    pathParams: [],
    queryParams: [
      { name: "limit", type: "integer", placeholder: "50", desc: "Max results (default 50, max 500)" },
      { name: "offset", type: "integer", placeholder: "0", desc: "Pagination offset" },
    ],
    exampleResponse: `{
  "status": "ok",
  "hazards": [
    {
      "signal_type": "route_hazard",
      "answer": "Elevated congestion on Arbitrum bridge. Expected delay: 20-40 min.",
      "confidence": 0.82,
      "risk_level": "high"
    }
  ]
}`,
  },
  {
    path: "/api/maps/congestion",
    description: "Returns congestion_formation signals — zones where capital is accumulating faster than it can clear. Useful for timing entries and exits.",
    pathParams: [],
    queryParams: [
      { name: "limit", type: "integer", placeholder: "50", desc: "Max results (default 50, max 500)" },
      { name: "offset", type: "integer", placeholder: "0", desc: "Pagination offset" },
    ],
    exampleResponse: `{
  "status": "ok",
  "congestion": [
    {
      "signal_type": "congestion_formation",
      "answer": "High slippage detected across DEX aggregators for ETH pairs over $500k.",
      "confidence": 0.79
    }
  ]
}`,
  },
  {
    path: "/api/maps/routes",
    description: "Returns RoutePrediction records — structured predictions about specific capital routes including expected flow direction, magnitude, and time horizon.",
    pathParams: [],
    queryParams: [
      { name: "limit", type: "integer", placeholder: "50", desc: "Max results (default 50, max 500)" },
      { name: "offset", type: "integer", placeholder: "0", desc: "Pagination offset" },
    ],
    exampleResponse: `{
  "status": "ok",
  "routes": [
    {
      "route_type": "capital_rotation",
      "origin": "stablecoins",
      "destination": "ETH",
      "expected_flow_direction": "inflow",
      "expected_flow_magnitude": "large",
      "time_horizon_hours": 24,
      "confidence": 0.85
    }
  ]
}`,
  },
  {
    path: "/api/story-types",
    description: "Returns all StoryTypeDefinitions — the taxonomy of on-chain story types that Maps agents interpret as navigation evidence.",
    pathParams: [],
    queryParams: [
      { name: "limit", type: "integer", placeholder: "50", desc: "Max results (default 50, max 500)" },
      { name: "offset", type: "integer", placeholder: "0", desc: "Pagination offset" },
    ],
    exampleResponse: `{
  "status": "ok",
  "story_types": [
    {
      "story_type": "capital_migration",
      "display_name": "Capital Migration",
      "category": "traffic",
      "human_meaning": "Capital appears to be moving from one sector, asset, or protocol to another.",
      "agent_meaning": "Use as evidence of changing capital routes and destination probabilities.",
      "inputs": ["wallet_flows", "token_transfers"],
      "related_navigation_signal_types": ["capital_migration", "destination_prediction"]
    }
  ]
}`,
  },
  {
    path: "/api/story-types/:type",
    description: "Fetch a single StoryTypeDefinition by its story_type slug.",
    pathParams: [
      { name: "type", placeholder: "capital_migration", desc: "Story type slug" },
    ],
    queryParams: [],
    exampleResponse: `{ "status": "ok", "story_type": { ... } }`,
  },
];

const CODE_TABS = [
  { id: "curl", label: "curl" },
  { id: "node", label: "Node.js" },
  { id: "python", label: "Python" },
  { id: "c", label: "C" },
];

function buildResolvedPath(path, pathValues) {
  return Object.entries(pathValues).reduce(
    (p, [k, v]) => p.replace(`:${k}`, v ? encodeURIComponent(v) : `:${k}`),
    path
  );
}

function buildQueryString(queryValues) {
  const pairs = Object.entries(queryValues).filter(([, v]) => v !== "");
  return pairs.length
    ? "?" + pairs.map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&")
    : "";
}

function buildFullUrl(path, pathValues, queryValues) {
  return buildResolvedPath(path, pathValues) + buildQueryString(queryValues);
}

function genCode(tab, fullUrl) {
  const fullHref = `${BASE}${fullUrl}`;
  switch (tab) {
    case "curl":
      return `curl "${fullHref}"`;
    case "node":
      return `const res = await fetch("${fullHref}", {
  headers: { "Accept": "application/json" },
});
const data = await res.json();
console.log(JSON.stringify(data, null, 2));`;
    case "python":
      return `import requests

r = requests.get("${fullHref}")
r.raise_for_status()
print(r.json())`;
    case "c":
      return `#include <stdio.h>
#include <curl/curl.h>

static size_t write_cb(void *ptr, size_t size, size_t nmemb, void *s) {
    fwrite(ptr, size, nmemb, (FILE *)s);
    return size * nmemb;
}

int main(void) {
    CURL *curl = curl_easy_init();
    if (!curl) return 1;

    struct curl_slist *hdrs =
        curl_slist_append(NULL, "Accept: application/json");

    curl_easy_setopt(curl, CURLOPT_URL, "${fullHref}");
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, hdrs);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, stdout);

    curl_easy_perform(curl);
    curl_slist_free_all(hdrs);
    curl_easy_cleanup(curl);
    return 0;
}
/* gcc example.c -lcurl -o example */`;
    default:
      return "";
  }
}

function EndpointCard({ endpoint }) {
  const { path, description, pathParams, queryParams, exampleResponse } = endpoint;

  const [pathValues, setPathValues] = useState(
    Object.fromEntries(pathParams.map((p) => [p.name, ""]))
  );
  const [queryValues, setQueryValues] = useState(
    Object.fromEntries(queryParams.map((p) => [p.name, ""]))
  );
  const [codeTab, setCodeTab] = useState("curl");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [fetchError, setFetchError] = useState(null);

  const fullUrl = buildFullUrl(path, pathValues, queryValues);
  const pathParamsMissing = pathParams.some((p) => !pathValues[p.name]);

  async function run() {
    setLoading(true);
    setResult(null);
    setFetchError(null);
    try {
      const res = await fetch(`${BASE}${fullUrl}`, {
        headers: { Accept: "application/json" },
      });
      const text = await res.text();
      let data;
      try {
        data = JSON.parse(text);
      } catch {
        data = text;
      }
      setResult({ status: res.status, ok: res.ok, data });
    } catch (e) {
      setFetchError(e.message);
    } finally {
      setLoading(false);
    }
  }

  const hasParams = pathParams.length > 0 || queryParams.length > 0;

  return el(
    "article",
    { className: "panel api-endpoint" },

    // ── Header ──
    el(
      "div",
      { className: "api-route" },
      el("span", { className: "api-method" }, "GET"),
      el("code", { className: "api-path" }, path)
    ),
    el("p", { className: "api-description" }, description),

    // ── Params table ──
    hasParams &&
      el(
        "div",
        { className: "table-wrap" },
        el(
          "table",
          { className: "data-table api-params" },
          el(
            "thead",
            null,
            el(
              "tr",
              null,
              el("th", null, "Parameter"),
              el("th", null, "In"),
              el("th", null, "Type"),
              el("th", null, "Description")
            )
          ),
          el(
            "tbody",
            null,
            ...pathParams.map((p) =>
              el(
                "tr",
                { key: `path-${p.name}` },
                el("td", null, el("code", null, p.name)),
                el("td", { className: "api-type" }, "path"),
                el("td", { className: "api-type" }, "string"),
                el("td", null, p.desc)
              )
            ),
            ...queryParams.map((p) =>
              el(
                "tr",
                { key: `query-${p.name}` },
                el("td", null, el("code", null, p.name)),
                el("td", { className: "api-type" }, "query"),
                el("td", { className: "api-type" }, p.type),
                el("td", null, p.desc)
              )
            )
          )
        )
      ),

    // ── Try It ──
    el(
      "div",
      { className: "try-it-section" },
      el("p", { className: "panel-label" }, "Try It"),

      hasParams &&
        el(
          "div",
          { className: "try-it-params" },
          ...pathParams.map((p) =>
            el(
              "div",
              { key: `pi-${p.name}`, className: "try-it-param-row" },
              el(
                "div",
                { className: "try-it-label-wrap" },
                el("code", { className: "try-it-param-name" }, p.name),
                el("span", { className: "try-it-param-badge try-it-badge-path" }, "path")
              ),
              el("input", {
                className: "try-it-input",
                type: "text",
                placeholder: p.placeholder || p.name,
                value: pathValues[p.name],
                onChange: (e) =>
                  setPathValues({ ...pathValues, [p.name]: e.target.value }),
              })
            )
          ),
          ...queryParams.map((p) =>
            el(
              "div",
              { key: `qi-${p.name}`, className: "try-it-param-row" },
              el(
                "div",
                { className: "try-it-label-wrap" },
                el("code", { className: "try-it-param-name" }, p.name),
                el("span", { className: "try-it-param-badge try-it-badge-query" }, "query")
              ),
              p.enum
                ? el(
                    "select",
                    {
                      className: "try-it-input",
                      value: queryValues[p.name],
                      onChange: (e) =>
                        setQueryValues({ ...queryValues, [p.name]: e.target.value }),
                    },
                    el("option", { value: "" }, "— any —"),
                    ...p.enum.map((v) => el("option", { key: v, value: v }, v))
                  )
                : el("input", {
                    className: "try-it-input",
                    type:
                      p.type === "integer" || p.type === "float"
                        ? "number"
                        : "text",
                    placeholder: p.placeholder || "",
                    value: queryValues[p.name],
                    onChange: (e) =>
                      setQueryValues({ ...queryValues, [p.name]: e.target.value }),
                  })
            )
          )
        ),

      el(
        "div",
        { className: "try-it-run-row" },
        el("code", { className: "try-it-url" }, `GET ${BASE}${fullUrl}`),
        el(
          "button",
          {
            className: "try-it-run-btn",
            onClick: run,
            disabled: loading || pathParamsMissing,
            title: pathParamsMissing ? "Fill in required path parameters" : undefined,
          },
          loading ? "Running…" : "Run"
        )
      ),

      result &&
        el(
          "div",
          { className: "try-it-result" },
          el(
            "span",
            {
              className: `try-it-status-badge${result.ok ? " is-ok" : " is-err"}`,
            },
            `${result.status} ${result.ok ? "OK" : "Error"}`
          ),
          el(
            "pre",
            { className: "code-block try-it-output" },
            typeof result.data === "string"
              ? result.data
              : JSON.stringify(result.data, null, 2)
          )
        ),

      fetchError &&
        el(
          "div",
          { className: "try-it-fetch-error" },
          `Request failed: ${fetchError}`
        )
    ),

    // ── Code Samples ──
    el(
      "div",
      { className: "code-samples-section" },
      el("p", { className: "panel-label" }, "Code Samples"),
      el(
        "div",
        { className: "code-tab-bar" },
        CODE_TABS.map((tab) =>
          el(
            "button",
            {
              key: tab.id,
              className: `code-tab-btn${codeTab === tab.id ? " is-active" : ""}`,
              onClick: () => setCodeTab(tab.id),
            },
            tab.label
          )
        )
      ),
      el("pre", { className: "code-block" }, genCode(codeTab, fullUrl))
    ),

    // ── Example Response ──
    el(
      "div",
      { className: "api-example" },
      el("p", { className: "panel-label" }, "Example response"),
      el("pre", { className: "code-block" }, exampleResponse)
    )
  );
}

export function ApiDocsPage() {
  return el(
    "div",
    null,
    el(
      "section",
      { className: "page-header" },
      el(
        "div",
        null,
        el("p", { className: "eyebrow" }, "API Reference"),
        el("h2", null, "Agent API")
      ),
      el(
        "a",
        {
          href: "/openapi.json",
          target: "_blank",
          rel: "noopener noreferrer",
          className: "action-link",
        },
        "openapi.json"
      )
    ),
    el(
      "div",
      { className: "panel api-intro" },
      el(
        "p",
        null,
        "The E3D Maps API is a read-only REST API designed for agents. All endpoints return JSON. Base URL: ",
        el("code", null, BASE),
        ". No authentication required."
      ),
      el(
        "p",
        { style: { marginTop: "12px" } },
        "Agents should poll ",
        el("code", null, "/api/maps/state"),
        " for situational awareness and ",
        el("code", null, "/api/maps/signals"),
        " for actionable signals. High-confidence signals (min_confidence=0.8) are the primary inputs for trading and treasury decisions."
      ),
      el(
        "p",
        { style: { marginTop: "12px" } },
        "Deployment requirement: serve ",
        el("code", null, "/api/maps/news"),
        " and ",
        el("code", null, "/api/maps/cross-chain"),
        " with ",
        el("code", null, "Cache-Control: max-age=300"),
        " at the outer HTTP layer. These route handlers return JSON bodies only; caching is not expressed inside ",
        el("code", null, "RouteResponse"),
        "."
      )
    ),
    ...ENDPOINTS.map((ep) => el(EndpointCard, { key: ep.path, endpoint: ep }))
  );
}
