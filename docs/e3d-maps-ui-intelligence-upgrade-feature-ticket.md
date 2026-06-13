# E3D Maps UI Intelligence Upgrade — Feature Ticket

## Overview

The E3D Maps UI currently surfaces navigation intelligence as plain data tables. The most
valuable content — the LLM-generated `answer` text, the urgency hierarchy of hazards vs.
weak signals, the directional flow between capital locations — is either hidden or absent.
This ticket upgrades the UI in five phases so that agents and humans can read the map at a
glance, the same way Google Maps communicates traffic, hazards, and routes visually.

All UI files are vanilla JS / htm / preact with no build step. The entry point is
`ui/index.html`. Source files live in `ui/src/`. Styles are in `ui/src/styles.css`.
The API client is `ui/src/api/mapsApiClient.js`.

**Run this spec from the `e3d-maps` root:**

```bash
codex-spec-runner docs/e3d-maps-ui-intelligence-upgrade-feature-ticket.md all --provider claude
```

**Or phase-by-phase:**

```bash
codex-spec-runner docs/e3d-maps-ui-intelligence-upgrade-feature-ticket.md 1 --provider claude
```

---

## Background

### Tech stack

- `ui/vendor.js` — re-exports `html`, `useState`, `useEffect`, `useRef` from a preact CDN
  import. No build step. All components use tagged template literals (`html\`...\``).
- `ui/src/styles.css` — custom properties defined in `:root`:
  `--bg`, `--panel`, `--panel-border`, `--text`, `--muted`, `--accent`, `--accent-soft`,
  `--warning` (`#8d5e12`), `--danger` (`#9c3434`), `--shadow`.
- Existing badge classes: `.badge`, `.badge-accent`, `.badge-positive`, `.badge-warning`,
  `.badge-danger`, `.badge-neutral`.
- Existing layout classes: `.panel`, `.panel-grid`, `.panel-label`, `.table-wrap`,
  `.data-table`, `.simple-list`, `.page-header`, `.eyebrow`, `.empty-copy`,
  `.error-banner`, `.action-button`, `.filter-bar`.
- `mapsApiClient.js` exports `createMapsApiClient()`. Relevant methods:
  `listSignals(filters)`, `getSignal(id)`, `getState()`, `listHazards()`,
  `listRoutes()`, `getRecommendations(filters)`.
- `listSignals` accepts `{ signalType, asset, chain, timeHorizonHours, minConfidence, limit, offset }`.
- Formatters: `formatConfidence(v)` → `"72%"`, `formatDateTime(v)`, `titleCaseLabel(v)`,
  `toArray(v)`.

### Signal fields relevant to this ticket

```
signal_type         — e.g. "capital_migration", "route_hazard", "congestion_formation"
answer              — 2–4 sentence LLM narrative (the core intelligence)
origin              — capital source node
destination         — capital target node
confidence          — float 0.0–1.0
risk_level          — "low" | "medium" | "high" | "critical"
signal_strength     — "weak" | "moderate" | "strong"
time_horizon_hours  — 6, 12, or 24
asset_scope         — string[]
chain_scope         — string[]
market_state        — "risk_on" | "risk_off" | "neutral" | "transitioning"
recommended_action  — plain-English action hint
created_at          — ISO timestamp
```

### Capital location vocabulary

Nodes used in `origin` and `destination`:
`stablecoins`, `ETH`, `BTC`, `ETH_DEFI`, `BASE_DEFI`, `MEME_TOKENS`, `PERPS`,
`REAL_WORLD_ASSETS`, `L2_NETWORKS`, `CEX`, `NFT_MARKETS`, `LIQUID_STAKING`.

---

## Phase 1 — Answer Preview in Signal Tables and Detail

The `answer` field is the core output of every Maps agent — the 2–4 sentence LLM narrative
that explains *why* a signal was generated. It currently only appears on the SignalDetail
page. This phase surfaces it in the signal list and makes it the visual hero on the detail
page.

### What to build

#### 1a. `ui/src/components/SignalTable.js` — add answer preview column

Add an `Answer` column between `Type` and `Confidence`. Render the answer as truncated text
(120 characters maximum, appended with `…` if longer). The cell should wrap; don't force
it to a single line.

```js
// In the <thead> <tr>, after the Type <th>:
html`<th>Answer</th>`

// In each <tbody> <tr>, after the Type <td> link:
html`<td className="answer-preview">${truncateAnswer(signal.answer)}</td>`
```

Add a helper at the bottom of the file:

```js
function truncateAnswer(text) {
  if (!text) return "—";
  return text.length > 120 ? text.slice(0, 120) + "…" : text;
}
```

#### 1b. `ui/src/styles.css` — answer preview cell

Add after the `.data-table` rules:

```css
.answer-preview {
  max-width: 340px;
  color: var(--muted);
  font-size: 0.82rem;
  line-height: 1.45;
  white-space: normal;
}
```

#### 1c. `ui/src/pages/SignalDetail.js` — make answer the hero

Currently the `answer` is rendered as a plain `<p>` inside the detail panel below the
`<h3>` question. Replace it with a styled blockquote so it reads as the primary finding:

Find:
```js
<h3>${signal.question}</h3>
<p>${signal.answer}</p>
```

Replace with:
```js
html`<h3>${signal.question}</h3>
<blockquote className="signal-answer">${signal.answer}</blockquote>`
```

Add to `ui/src/styles.css`:

```css
.signal-answer {
  margin: 0.75rem 0 1.25rem;
  padding: 0.9rem 1.1rem;
  border-left: 3px solid var(--accent);
  background: var(--accent-soft);
  border-radius: 0 6px 6px 0;
  font-size: 1rem;
  line-height: 1.6;
  color: var(--text);
}
```

#### 1d. `ui/src/pages/SignalDetail.js` — fix stale utility score label

The Utility Score `<dd>` currently reads `"Not available in Phase 7"`. Replace it with
`"Not yet scored"` — the implementation reference is meaningless to users.

### Verification

1. Open `ui/index.html` in a browser (serve from `e3d-maps` root with any static file
   server, e.g. `python3 -m http.server 8080 --directory ui`).
2. Navigate to `/signals`. Confirm the `Answer` column appears and answer text is truncated
   at ~120 characters with a trailing `…` on longer entries.
3. Click any signal row. Confirm the answer appears as a tinted blockquote with a left
   accent border, immediately below the question heading.
4. Confirm the Utility Score field reads `"Not yet scored"`.

---

## Phase 2 — Filter Bar on Navigation Signals Page

The `/signals` page loads 50 signals with no controls. Users and agents need to filter by
signal type, minimum confidence, asset, and chain.

### What to build

#### 2a. `ui/src/pages/NavigationSignals.js` — add filter state and UI

Replace the current static `useEffect` load with a filter-aware version.

Add filter state above the existing `state` declaration:

```js
const SIGNAL_TYPES = [
  { value: "", label: "All signal types" },
  { value: "capital_migration", label: "Capital Migration" },
  { value: "destination_prediction", label: "Destination Prediction" },
  { value: "congestion_formation", label: "Congestion" },
  { value: "route_hazard", label: "Route Hazard" },
  { value: "route_closure", label: "Route Closure" },
  { value: "route_emergence", label: "Route Emergence" },
  { value: "liquidity_forecast", label: "Liquidity Forecast" },
  { value: "capital_conviction", label: "Capital Conviction" },
  { value: "narrative_acceleration", label: "Narrative Acceleration" },
  { value: "agent_swarm_formation", label: "Agent Swarm Formation" },
];

const CONFIDENCE_LEVELS = [
  { value: "", label: "Any confidence" },
  { value: "0.75", label: "Strong (≥ 75%)" },
  { value: "0.50", label: "Moderate (≥ 50%)" },
  { value: "0.30", label: "Weak (≥ 30%)" },
];

const [filters, setFilters] = useState({ signalType: "", minConfidence: "", asset: "", chain: "" });
const [pending, setPending] = useState({ signalType: "", minConfidence: "", asset: "", chain: "" });
```

Change the `useEffect` dependency to `[api, filters]` and pass filters to `listSignals`:

```js
const response = await api.listSignals({
  signalType: filters.signalType || undefined,
  minConfidence: filters.minConfidence ? Number(filters.minConfidence) : undefined,
  asset: filters.asset || undefined,
  chain: filters.chain || undefined,
  limit: 100,
});
```

Add a filter form above the signal table (inside the return), after the `page-header`:

```js
html`
  <section className="panel">
    <form onSubmit=${applyFilters} className="filter-bar">
      <select
        value=${pending.signalType}
        onChange=${(e) => setPending((f) => ({ ...f, signalType: e.target.value }))}
      >
        ${SIGNAL_TYPES.map((opt) => html`<option key=${opt.value} value=${opt.value}>${opt.label}</option>`)}
      </select>
      <select
        value=${pending.minConfidence}
        onChange=${(e) => setPending((f) => ({ ...f, minConfidence: e.target.value }))}
      >
        ${CONFIDENCE_LEVELS.map((opt) => html`<option key=${opt.value} value=${opt.value}>${opt.label}</option>`)}
      </select>
      <input
        type="text"
        placeholder="Asset (e.g. ETH)"
        value=${pending.asset}
        onInput=${(e) => setPending((f) => ({ ...f, asset: e.target.value }))}
      />
      <input
        type="text"
        placeholder="Chain (e.g. ethereum)"
        value=${pending.chain}
        onInput=${(e) => setPending((f) => ({ ...f, chain: e.target.value }))}
      />
      <button className="action-button" type="submit">Filter</button>
      <button className="action-button action-button-ghost" type="button" onClick=${clearFilters}>Clear</button>
    </form>
  </section>
`
```

Add the handler functions inside the component:

```js
function applyFilters(event) {
  event.preventDefault();
  setFilters({ ...pending });
}

function clearFilters() {
  const empty = { signalType: "", minConfidence: "", asset: "", chain: "" };
  setPending(empty);
  setFilters(empty);
}
```

#### 2b. `ui/src/styles.css` — ghost button variant

Add after the `.action-button` rule:

```css
.action-button-ghost {
  background: transparent;
  color: var(--muted);
  border-color: var(--panel-border);
}
.action-button-ghost:hover {
  background: var(--panel-border);
}
```

#### 2c. Active filter count in nav badge

In `ui/src/App.js`, the nav badge for `/signals` currently shows total signal count. Keep
that count. No changes needed to the nav badge — the filter state is local to the page.

### Verification

1. Navigate to `/signals`.
2. Confirm the filter bar renders with all four controls and two buttons.
3. Select `"Route Hazard"` from the type dropdown and click Filter. Confirm only
   `route_hazard` signals appear.
4. Enter `ETH` in the Asset field and click Filter. Confirm results narrow to ETH-scoped
   signals.
5. Click Clear. Confirm all signals reload without filters.
6. Select `"Strong (≥ 75%)"` from the confidence dropdown. Confirm all visible signals
   have `confidence ≥ 0.75`.

---

## Phase 3 — Risk Urgency Hierarchy

All signals currently look identical in the table regardless of risk level. A
`route_closure` at `critical` risk and a `liquidity_forecast` at `low` risk sit in
visually identical rows. This phase adds color-coded row tinting and a high-priority alert
strip on the dashboard for signals that need immediate attention.

### What to build

#### 3a. `ui/src/styles.css` — risk row classes

Add after `.data-table tbody tr` rules:

```css
.row-risk-critical {
  background: rgba(156, 52, 52, 0.07);
  border-left: 3px solid var(--danger);
}
.row-risk-high {
  background: rgba(156, 52, 52, 0.04);
  border-left: 3px solid rgba(156, 52, 52, 0.45);
}
.row-risk-medium {
  background: rgba(141, 94, 18, 0.04);
  border-left: 3px solid rgba(141, 94, 18, 0.35);
}
.row-risk-low {
  border-left: 3px solid transparent;
}
```

#### 3b. `ui/src/components/SignalTable.js` — apply row class

In the `<tr>` element for each signal, add a `className` derived from `risk_level`:

```js
html`<tr key=${signal.id} className=${riskRowClass(signal.risk_level)}>`
```

Add the helper at the bottom of the file:

```js
function riskRowClass(riskLevel) {
  switch (riskLevel) {
    case "critical": return "row-risk-critical";
    case "high":     return "row-risk-high";
    case "medium":   return "row-risk-medium";
    default:         return "row-risk-low";
  }
}
```

#### 3c. `ui/src/pages/MapsHome.js` — urgent signals alert strip

At the top of the dashboard (before the `panel-grid`), render an alert strip when any
loaded signal has `risk_level === "critical"` or `risk_level === "high"` AND
`confidence >= 0.65`.

Compute this inside the render, after `const trafficState = state.trafficState`:

```js
const urgentSignals = [
  ...state.hazards,
  ...state.congestionSignals,
  ...state.latestSignals,
].filter(
  (s) => (s.risk_level === "critical" || s.risk_level === "high") && s.confidence >= 0.65
);
// Deduplicate by id
const seen = new Set();
const dedupedUrgent = urgentSignals.filter((s) => {
  if (seen.has(s.id)) return false;
  seen.add(s.id);
  return true;
});
```

Render the strip just before the `panel-grid` section:

```js
${dedupedUrgent.length > 0 ? html`
  <section className="alert-strip">
    <span className="alert-strip-label">⚠ ${dedupedUrgent.length} urgent signal${dedupedUrgent.length === 1 ? "" : "s"}</span>
    <ul className="alert-strip-list">
      ${dedupedUrgent.slice(0, 3).map((s) => html`
        <li key=${s.id}>
          <a href=${"/signals/" + s.id} onClick=${(e) => jumpToSignal(e, s.id, navigate)}>
            ${titleCaseLabel(s.signal_type)}${s.destination ? " → " + s.destination : ""}
          </a>
          <span className=${"badge badge-" + (s.risk_level === "critical" ? "danger" : "warning")}>
            ${titleCaseLabel(s.risk_level)}
          </span>
        </li>
      `)}
    </ul>
  </section>
` : null}
```

#### 3d. `ui/src/styles.css` — alert strip

```css
.alert-strip {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  padding: 0.75rem 1rem;
  background: rgba(156, 52, 52, 0.08);
  border: 1px solid rgba(156, 52, 52, 0.22);
  border-radius: 8px;
  margin-bottom: 1.25rem;
}
.alert-strip-label {
  font-weight: 600;
  color: var(--danger);
  white-space: nowrap;
  font-size: 0.875rem;
}
.alert-strip-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1.25rem;
}
.alert-strip-list li {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.85rem;
}
.alert-strip-list a {
  color: var(--danger);
  text-decoration: underline;
  text-decoration-color: rgba(156, 52, 52, 0.35);
}
```

### Verification

1. Navigate to `/signals`. Confirm rows with `risk_level === "critical"` have a strong red
   left border and red-tinted background. Rows with `risk_level === "high"` have a lighter
   red treatment. Medium rows have a subtle amber border. Low rows have no border color.
2. Navigate to `/` (dashboard). If any high/critical signals exist with confidence ≥ 0.65,
   confirm the alert strip appears above the panel grid. Clicking a signal name navigates
   to the detail page.
3. Confirm the alert strip does not render when no urgent signals are present — no empty
   red box.

---

## Phase 4 — Dashboard Recommendation CTA Widget

The Recommendations page is the most actionable page in the app but has no entry point
from the dashboard. Users land on the dashboard, see traffic state and signals, and have
to know to navigate to `/recommendations` separately. This phase adds a top-recommendation
preview card to the dashboard that drives users and agents to the full recommendations view.

### What to build

#### 4a. `ui/src/pages/MapsHome.js` — fetch top recommendation

Add `topRec: null` to the initial state shape. In the `loadDashboard` function, add a
fifth parallel request to `api.getRecommendations({ maxResults: 1 })`. Assign the first
result to `topRec`:

```js
const [trafficState, latestSignalsResponse, hazardsResponse, congestionResponse, recsResponse] =
  await Promise.all([
    api.getState(),
    api.listSignals({ minConfidence: 0.7, limit: 5 }),
    api.listHazards({ limit: 5 }),
    api.listSignals({ signalType: "congestion_formation", limit: 5 }),
    api.getRecommendations({ maxResults: 1 }).catch(() => null),
  ]);

// In setState:
topRec: recsResponse?.recommendations?.[0] || null,
```

#### 4b. `ui/src/pages/MapsHome.js` — recommendation preview card

Add the card as the first panel inside the `panel-grid` section, before `Market State`.
Only render it when `state.topRec` is non-null:

```js
${state.topRec ? html`
  <article className="panel rec-preview-panel">
    <p className="panel-label">Top Recommendation</p>
    <div className="rec-preview-header">
      <span className="rec-preview-rank">#${state.topRec.rank}</span>
      <h3 className="rec-preview-title">${state.topRec.title}</h3>
      <span className=${"badge " + (ACTION_CLASSES[state.topRec.action] || "badge-neutral")}>
        ${titleCaseLabel(state.topRec.action)}
      </span>
    </div>
    ${state.topRec.reasoning?.[0] ? html`
      <p className="rec-preview-reason">${state.topRec.reasoning[0]}</p>
    ` : null}
    <div className="rec-preview-meta">
      <span className="score-chip">Score <strong>${state.topRec.score}</strong></span>
      <span className="score-chip">Confidence <strong>${state.topRec.confidence}%</strong></span>
    </div>
    <a
      href="/recommendations"
      className="rec-preview-link"
      onClick=${(e) => { e.preventDefault(); navigate("/recommendations"); }}
    >
      View all recommendations →
    </a>
  </article>
` : null}
```

Import `ACTION_CLASSES` from Recommendations — or copy the constant into `MapsHome.js`:

```js
const ACTION_CLASSES = {
  avoid: "badge-danger",
  wait: "badge-warning",
  reduce_exposure: "badge-warning",
  monitor: "badge-neutral",
  hold: "badge-neutral",
  investigate: "badge-accent",
  increase_attention: "badge-accent",
  increase_exposure: "badge-positive",
};
```

#### 4c. `ui/src/styles.css` — recommendation preview card styles

```css
.rec-preview-panel {
  grid-column: span 2;
}
.rec-preview-header {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
  flex-wrap: wrap;
}
.rec-preview-rank {
  font-weight: 700;
  color: var(--muted);
  font-size: 0.85rem;
}
.rec-preview-title {
  margin: 0;
  font-size: 1rem;
  flex: 1;
}
.rec-preview-reason {
  color: var(--muted);
  font-size: 0.875rem;
  margin: 0 0 0.75rem;
  line-height: 1.5;
}
.rec-preview-meta {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
}
.rec-preview-link {
  display: inline-block;
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--accent);
  text-decoration: none;
}
.rec-preview-link:hover {
  text-decoration: underline;
}
```

### Verification

1. Navigate to `/` (dashboard). If recommendations data is available, confirm the top
   recommendation card appears as the first panel in the grid, spanning two columns.
2. Confirm the action badge is colored correctly (e.g. `increase_exposure` → green).
3. Confirm the first reasoning bullet appears as muted body text.
4. Click "View all recommendations →". Confirm navigation to `/recommendations`.
5. If no recommendations are available, confirm no card renders — no empty panel appears.

---

## Phase 5 — Capital Flow Graph Visualization

The biggest gap between E3D Maps and a real map is the absence of a visual map. Capital
flows between named nodes (`stablecoins`, `ETH_DEFI`, `PERPS`, etc.) but there is no
spatial representation. This phase adds an interactive SVG flow graph to the dashboard
showing live origin→destination flows sized by confidence and colored by hazard level.

No external dependencies. The graph is rendered as inline SVG using preact/htm. Node
positions are defined in a static layout map (the vocabulary is fixed). Edges are drawn as
cubic Bézier curves. Data comes from `/api/maps/signals` (derived client-side) with an
optional richer feed from `/api/maps/graph` if the endpoint is available.

### What to build

#### 5a. `ui/src/api/mapsApiClient.js` — add `getFlowGraph`

Add to the returned client object:

```js
async getFlowGraph() {
  const body = await request("/api/maps/graph", { allowNotFound: true });
  return body || null;
},
```

#### 5b. `ui/src/components/FlowGraph.js` — new file

Create `ui/src/components/FlowGraph.js`.

**Node layout** — a two-column layout with source nodes on the left and destination nodes
on the right. Nodes that appear as both origin and destination sit in the middle column.

```js
const NODE_LAYOUT = {
  //  x and y are 0–1 fractions of the SVG viewBox (1000×600)
  stablecoins:       { x: 0.08, y: 0.35, label: "Stablecoins" },
  BTC:               { x: 0.08, y: 0.60, label: "BTC" },
  CEX:               { x: 0.08, y: 0.80, label: "CEX" },
  ETH:               { x: 0.30, y: 0.20, label: "ETH" },
  ETH_DEFI:          { x: 0.55, y: 0.18, label: "ETH DeFi" },
  LIQUID_STAKING:    { x: 0.55, y: 0.38, label: "Liquid Staking" },
  BASE_DEFI:         { x: 0.55, y: 0.55, label: "Base DeFi" },
  L2_NETWORKS:       { x: 0.55, y: 0.70, label: "L2 Networks" },
  PERPS:             { x: 0.82, y: 0.30, label: "Perps" },
  REAL_WORLD_ASSETS: { x: 0.82, y: 0.55, label: "RWA" },
  MEME_TOKENS:       { x: 0.82, y: 0.76, label: "Meme Tokens" },
  NFT_MARKETS:       { x: 0.30, y: 0.80, label: "NFT Markets" },
};

const VW = 1000;
const VH = 600;
const NODE_R = 28;
```

**Edge color by hazard/risk level:**

```js
function edgeColor(riskLevel) {
  switch (riskLevel) {
    case "critical": return "#9c3434";
    case "high":     return "#c0561a";
    case "medium":   return "#8d5e12";
    default:         return "#0a7f68";
  }
}
```

**Derive edges from signals.** Each signal with a non-empty `origin` and `destination`
that are both in `NODE_LAYOUT` contributes an edge. Group signals by
`origin + "→" + destination`, taking the highest-confidence signal per pair:

```js
export function deriveEdges(signals) {
  const map = new Map();
  for (const sig of signals) {
    const key = `${sig.origin}→${sig.destination}`;
    if (!NODE_LAYOUT[sig.origin] || !NODE_LAYOUT[sig.destination]) continue;
    if (sig.origin === sig.destination) continue;
    const existing = map.get(key);
    if (!existing || sig.confidence > existing.confidence) {
      map.set(key, sig);
    }
  }
  return [...map.values()];
}
```

**Cubic Bézier path between two nodes.** The control points are offset horizontally
toward the midpoint of the SVG to give the curves a natural flow look:

```js
function bezierPath(from, to) {
  const x1 = from.x * VW;
  const y1 = from.y * VH;
  const x2 = to.x * VW;
  const y2 = to.y * VH;
  const cx = (x1 + x2) / 2;
  return `M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`;
}
```

**Edge stroke width** is proportional to confidence, ranging from 1.5px (confidence = 0)
to 7px (confidence = 1):

```js
function strokeWidth(confidence) {
  return 1.5 + confidence * 5.5;
}
```

**Component:**

```js
import { html, useState } from "../vendor.js";
import { formatConfidence, titleCaseLabel } from "../formatters.js";

export function FlowGraph({ signals = [], onNodeClick }) {
  const [hovered, setHovered] = useState(null);
  const edges = deriveEdges(signals);
  const activeNodeIds = new Set(edges.flatMap((e) => [e.origin, e.destination]));

  return html`
    <div className="flow-graph-wrap">
      <svg
        viewBox=${"0 0 " + VW + " " + VH}
        className="flow-graph-svg"
        aria-label="Capital flow graph"
      >
        <defs>
          <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#aaa" />
          </marker>
        </defs>

        <!-- Edges -->
        ${edges.map((edge) => {
          const from = NODE_LAYOUT[edge.origin];
          const to = NODE_LAYOUT[edge.destination];
          if (!from || !to) return null;
          const isHovered = hovered === edge.origin + "→" + edge.destination;
          return html`
            <g key=${edge.origin + edge.destination}>
              <!-- Hit area (wider invisible path for easier hover) -->
              <path
                d=${bezierPath(from, to)}
                fill="none"
                stroke="transparent"
                strokeWidth="20"
                style="cursor:pointer"
                onMouseEnter=${() => setHovered(edge.origin + "→" + edge.destination)}
                onMouseLeave=${() => setHovered(null)}
              />
              <path
                d=${bezierPath(from, to)}
                fill="none"
                stroke=${edgeColor(edge.risk_level)}
                strokeWidth=${isHovered ? strokeWidth(edge.confidence) + 2 : strokeWidth(edge.confidence)}
                strokeOpacity=${isHovered ? 0.9 : 0.55}
                style="pointer-events:none;transition:stroke-opacity 0.15s"
                markerEnd="url(#arrowhead)"
              />
              ${isHovered ? html`
                <text
                  x=${((NODE_LAYOUT[edge.origin].x + NODE_LAYOUT[edge.destination].x) / 2) * VW}
                  y=${((NODE_LAYOUT[edge.origin].y + NODE_LAYOUT[edge.destination].y) / 2) * VH - 10}
                  textAnchor="middle"
                  fontSize="11"
                  fill=${edgeColor(edge.risk_level)}
                  fontWeight="600"
                >
                  ${formatConfidence(edge.confidence)} · ${titleCaseLabel(edge.risk_level)} risk
                </text>
              ` : null}
            </g>
          `;
        })}

        <!-- Nodes -->
        ${Object.entries(NODE_LAYOUT).map(([id, pos]) => {
          const isActive = activeNodeIds.has(id);
          const cx = pos.x * VW;
          const cy = pos.y * VH;
          return html`
            <g
              key=${id}
              style=${"cursor:" + (isActive && onNodeClick ? "pointer" : "default") + ";opacity:" + (isActive ? 1 : 0.3)}
              onClick=${isActive && onNodeClick ? () => onNodeClick(id) : undefined}
            >
              <circle
                cx=${cx} cy=${cy} r=${NODE_R}
                fill="rgba(255,252,245,0.92)"
                stroke=${isActive ? "#0a7f68" : "#ccc"}
                strokeWidth=${isActive ? 2 : 1}
              />
              <text
                x=${cx} y=${cy + 4}
                textAnchor="middle"
                fontSize="10"
                fontWeight=${isActive ? "600" : "400"}
                fill=${isActive ? "#201813" : "#aaa"}
              >
                ${pos.label}
              </text>
            </g>
          `;
        })}
      </svg>
      ${edges.length === 0 ? html`
        <p className="flow-graph-empty">No flow data yet. Signal generation in progress.</p>
      ` : null}
    </div>
  `;
}
```

#### 5c. `ui/src/styles.css` — flow graph styles

```css
.flow-graph-wrap {
  position: relative;
  width: 100%;
  background: var(--panel);
  border-radius: 10px;
  overflow: hidden;
}
.flow-graph-svg {
  width: 100%;
  height: auto;
  display: block;
}
.flow-graph-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  font-size: 0.875rem;
  pointer-events: none;
}
```

#### 5d. `ui/src/pages/MapsHome.js` — embed the graph

Import `FlowGraph` and add it as a full-width section on the dashboard, above the
`panel-grid`, below the alert strip from Phase 3.

```js
import { FlowGraph } from "../components/FlowGraph.js";
```

Add `allSignals: []` to the initial state. In `loadDashboard`, add a fifth/sixth parallel
fetch for all signals (limit 200, no confidence filter — the graph benefits from weak
signals too):

```js
const signalsForGraphResponse = await api.listSignals({ limit: 200 });
// in setState:
allSignals: toArray(signalsForGraphResponse?.signals),
```

Add `onNodeClick` handler inside the component:

```js
function handleNodeClick(nodeId) {
  navigate(`/signals?chain=&asset=&signalType=&node=${encodeURIComponent(nodeId)}`);
}
```

Render the graph section:

```js
<section className="panel" style="padding: 0; overflow: hidden; margin-bottom: 1.5rem;">
  <div style="padding: 1rem 1.25rem 0.5rem;">
    <p className="panel-label">Live Capital Flow Map</p>
    <p style="font-size:0.8rem;color:var(--muted);margin:0 0 0.5rem;">
      Edge thickness = confidence · Color = risk level · Hover an edge for detail
    </p>
  </div>
  <${FlowGraph}
    signals=${state.allSignals}
    onNodeClick=${handleNodeClick}
  />
</section>
```

### Verification

1. Navigate to `/` (dashboard). Confirm the flow graph SVG renders above the panel grid.
2. If signals exist with valid `origin`/`destination` nodes, confirm curved arrows appear
   between the corresponding SVG nodes.
3. Hover an edge. Confirm a confidence + risk level tooltip appears near the midpoint.
4. High-risk edges should be red/amber; low-risk edges should be green.
5. Inactive nodes (no edges) should be visually dimmed (opacity 0.3).
6. Confirm the graph is responsive — it scales horizontally on a narrow viewport without
   horizontal scrollbars (the SVG `viewBox` + `width: 100%` handles this).
7. Confirm no JavaScript errors when `allSignals` is empty — the empty state message
   appears inside the graph panel.

---

## Appendix: File Change Summary

| File | Phases | Change type |
|---|---|---|
| `ui/src/components/SignalTable.js` | 1, 3 | Add answer preview column; add risk row class |
| `ui/src/pages/SignalDetail.js` | 1 | Answer hero blockquote; fix utility score label |
| `ui/src/pages/NavigationSignals.js` | 2 | Filter bar with signal type, confidence, asset, chain |
| `ui/src/pages/MapsHome.js` | 3, 4, 5 | Alert strip; rec widget; flow graph embed |
| `ui/src/components/FlowGraph.js` | 5 | New file — SVG flow graph component |
| `ui/src/api/mapsApiClient.js` | 5 | Add `getFlowGraph()` method |
| `ui/src/styles.css` | 1, 2, 3, 4, 5 | Styles for each phase feature |

## Appendix: Design Tokens Reference

```
--bg:           #f3efe7       warm off-white page background
--panel:        rgba(255,252,245,0.9)  card background
--panel-border: rgba(61,45,30,0.12)   subtle border
--text:         #201813       near-black body text
--muted:        #6f6357       secondary text
--accent:       #0a7f68       teal — primary brand / safe / positive
--accent-soft:  rgba(10,127,104,0.12) teal tint
--warning:      #8d5e12       amber — medium risk
--danger:       #9c3434       red — high / critical risk
```
