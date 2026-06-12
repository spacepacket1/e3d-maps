import { html, useEffect, useState } from "../vendor.js";
import { formatDateTime, titleCaseLabel } from "../formatters.js";

const OBJECTIVES = [
  { value: "", label: "Any objective" },
  { value: "seek_opportunity", label: "Seek Opportunity" },
  { value: "grow_capital", label: "Grow Capital" },
  { value: "preserve_capital", label: "Preserve Capital" },
  { value: "reduce_risk", label: "Reduce Risk" },
  { value: "monitor_market", label: "Monitor Market" },
];

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

export function RecommendationsPage({ api, navigate }) {
  const [filters, setFilters] = useState({ objective: "", asset: "" });
  const [pending, setPending] = useState({ objective: "", asset: "" });
  const [state, setState] = useState({
    loading: true,
    error: "",
    generatedAt: null,
    recommendations: [],
  });

  useEffect(() => {
    let cancelled = false;
    setState((current) => ({ ...current, loading: true, error: "" }));

    api.getRecommendations({
      objective: filters.objective || undefined,
      asset: filters.asset || undefined,
      maxResults: 20,
    }).then((body) => {
      if (cancelled) return;
      setState({
        loading: false,
        error: "",
        generatedAt: body.generatedAt,
        recommendations: Array.isArray(body.recommendations) ? body.recommendations : [],
      });
    }).catch((error) => {
      if (cancelled) return;
      setState({ loading: false, error: error instanceof Error ? error.message : String(error), generatedAt: null, recommendations: [] });
    });

    return () => { cancelled = true; };
  }, [api, filters]);

  function applyFilters(event) {
    event.preventDefault();
    setFilters({ ...pending });
  }

  return html`
    <section className="page-header">
      <div>
        <p className="eyebrow">Recommendations</p>
        <h2>What should I do next?</h2>
      </div>
    </section>

    <section className="panel">
      <form onSubmit=${applyFilters} className="filter-bar">
        <select
          value=${pending.objective}
          onChange=${(e) => setPending((current) => ({ ...current, objective: e.target.value }))}
        >
          ${OBJECTIVES.map((opt) => html`
            <option key=${opt.value} value=${opt.value}>${opt.label}</option>
          `)}
        </select>
        <input
          type="text"
          placeholder="Asset (e.g. ETH)"
          value=${pending.asset}
          onInput=${(e) => setPending((current) => ({ ...current, asset: e.target.value }))}
        />
        <button className="action-button" type="submit">Refresh</button>
      </form>
    </section>

    ${state.error ? html`<p className="error-banner">${state.error}</p>` : null}

    ${state.loading
      ? html`<p className="empty-copy">Loading recommendations...</p>`
      : state.recommendations.length === 0
        ? html`<p className="empty-copy">No recommendations available. Generate navigation signals first.</p>`
        : html`
            <p className="muted-meta">
              Generated ${formatDateTime(state.generatedAt)}
              ${filters.objective ? html` · Objective: <strong>${titleCaseLabel(filters.objective)}</strong>` : null}
              ${filters.asset ? html` · Asset: <strong>${filters.asset.toUpperCase()}</strong>` : null}
            </p>
            <ol className="recommendation-list">
              ${state.recommendations.map((rec) => html`
                <li key=${rec.rank} className="recommendation-card">
                  <div className="rec-header">
                    <span className="rec-rank">#${rec.rank}</span>
                    <h3 className="rec-title">${rec.title}</h3>
                    <span className=${"badge " + (ACTION_CLASSES[rec.action] || "badge-neutral")}>
                      ${titleCaseLabel(rec.action)}
                    </span>
                  </div>
                  <div className="rec-scores">
                    <span className="score-chip">Score <strong>${rec.score}</strong></span>
                    <span className="score-chip">Confidence <strong>${rec.confidence}%</strong></span>
                    <span className="score-chip">Risk <strong>${rec.risk}</strong></span>
                    ${rec.story_type ? html`<span className="score-chip story-chip">${rec.story_type}</span>` : null}
                  </div>
                  ${rec.reasoning?.length ? html`
                    <ul className="rec-reasoning">
                      ${rec.reasoning.map((line, idx) => html`<li key=${idx}>${line}</li>`)}
                    </ul>
                  ` : null}
                  ${rec.supporting_signals?.length ? html`
                    <p className="rec-signals-label">
                      ${rec.supporting_signals.length} signal${rec.supporting_signals.length === 1 ? "" : "s"}
                      ${rec.supporting_routes?.length ? html` · ${rec.supporting_routes.length} route${rec.supporting_routes.length === 1 ? "" : "s"}` : null}
                    </p>
                  ` : null}
                </li>
              `)}
            </ol>
          `}
  `;
}
