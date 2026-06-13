import { html, useEffect, useState } from "../vendor.js";
import { SignalTable } from "../components/SignalTable.js";

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

export function NavigationSignalsPage({ api, navigate }) {
  const [filters, setFilters] = useState({ signalType: "", minConfidence: "", asset: "", chain: "" });
  const [pending, setPending] = useState({ signalType: "", minConfidence: "", asset: "", chain: "" });
  const [state, setState] = useState({
    loading: true,
    error: "",
    signals: [],
  });

  useEffect(() => {
    let cancelled = false;
    setState((current) => ({ ...current, loading: true, error: "" }));

    async function loadSignals() {
      try {
        const response = await api.listSignals({
          signalType: filters.signalType || undefined,
          minConfidence: filters.minConfidence ? Number(filters.minConfidence) : undefined,
          asset: filters.asset || undefined,
          chain: filters.chain || undefined,
          limit: 100,
        });
        if (cancelled) {
          return;
        }
        setState({
          loading: false,
          error: "",
          signals: Array.isArray(response?.signals) ? response.signals : [],
        });
      } catch (error) {
        if (cancelled) {
          return;
        }
        setState({
          loading: false,
          error: error instanceof Error ? error.message : String(error),
          signals: [],
        });
      }
    }

    loadSignals();
    return () => {
      cancelled = true;
    };
  }, [api, filters]);

  function applyFilters(event) {
    event.preventDefault();
    setFilters({ ...pending });
  }

  function clearFilters() {
    const empty = { signalType: "", minConfidence: "", asset: "", chain: "" };
    setPending(empty);
    setFilters(empty);
  }

  return html`
    <section className="page-header">
      <div>
        <p className="eyebrow">Navigation Signals</p>
        <h2>Recent generated signals</h2>
      </div>
    </section>
    <section className="panel">
      <form onSubmit=${applyFilters} className="filter-bar">
        <select
          value=${pending.signalType}
          onChange=${(e) => setPending((current) => ({ ...current, signalType: e.target.value }))}
        >
          ${SIGNAL_TYPES.map((opt) => html`<option key=${opt.value} value=${opt.value}>${opt.label}</option>`)}
        </select>
        <select
          value=${pending.minConfidence}
          onChange=${(e) => setPending((current) => ({ ...current, minConfidence: e.target.value }))}
        >
          ${CONFIDENCE_LEVELS.map((opt) => html`<option key=${opt.value} value=${opt.value}>${opt.label}</option>`)}
        </select>
        <input
          type="text"
          placeholder="Asset (e.g. ETH)"
          value=${pending.asset}
          onInput=${(e) => setPending((current) => ({ ...current, asset: e.target.value }))}
        />
        <input
          type="text"
          placeholder="Chain (e.g. ethereum)"
          value=${pending.chain}
          onInput=${(e) => setPending((current) => ({ ...current, chain: e.target.value }))}
        />
        <button className="action-button" type="submit">Filter</button>
        <button className="action-button action-button-ghost" type="button" onClick=${clearFilters}>Clear</button>
      </form>
    </section>
    ${state.error ? html`<p className="error-banner">${state.error}</p>` : null}
    ${state.loading
      ? html`<p className="empty-copy">Loading signals...</p>`
      : html`<${SignalTable} signals=${state.signals} navigate=${navigate} />`}
  `;
}
