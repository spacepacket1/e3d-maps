import { html, useEffect, useState } from "../vendor.js";
import { formatConfidence, formatDateTime, titleCaseLabel, toArray } from "../formatters.js";
import { FlowGraph } from "../components/FlowGraph.js";
import { RECOMMENDATION_ACTION_CLASSES } from "../utils/recommendationActionClasses.js";

const AUTO_REFRESH_MS = 60_000;

export function MapsHomePage({ api, navigate }) {
  const [state, setState] = useState({
    loading: true,
    refreshing: false,
    error: "",
    trafficState: null,
    allSignals: [],
    topRec: null,
  });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function loadDashboard(isRefresh) {
      setState((current) => ({
        ...current,
        loading: current.loading && !isRefresh,
        refreshing: isRefresh,
        error: "",
      }));

      try {
        const [trafficState, signalsForGraphResponse, recsResponse] =
          await Promise.all([
            api.getState(),
            api.listSignals({ limit: 200 }),
            api.getRecommendations({ maxResults: 1 }).catch(() => null),
          ]);

        if (cancelled) {
          return;
        }

        setState({
          loading: false,
          refreshing: false,
          error: "",
          trafficState,
          allSignals: toArray(signalsForGraphResponse?.signals),
          topRec: recsResponse?.recommendations?.[0] || null,
        });
      } catch (error) {
        if (cancelled) {
          return;
        }
        setState((current) => ({
          ...current,
          loading: false,
          refreshing: false,
          error: error instanceof Error ? error.message : String(error),
        }));
      }
    }

    loadDashboard(reloadToken > 0);
    const timer = window.setInterval(() => loadDashboard(true), AUTO_REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [api, reloadToken]);

  const trafficState = state.trafficState;
  const hasData = Boolean(trafficState || state.allSignals.length);

  function handleNodeClick(_nodeId) {
    navigate("/signals");
  }

  return html`
    <section className="page-header">
      <div>
        <p className="eyebrow">Maps Home</p>
        <h2>Current Traffic State</h2>
      </div>
      <button className="action-button" type="button" onClick=${() => setReloadToken((value) => value + 1)}>
        ${state.refreshing ? "Refreshing..." : "Refresh"}
      </button>
    </section>

    ${state.error ? html`<p className="error-banner">${state.error}</p>` : null}
    ${state.loading
      ? html`<p className="empty-copy">Loading current map state...</p>`
      : html`
            ${!hasData ? html`<p className="empty-copy">No map state has been published yet.</p>` : null}
            <section className="panel" style=${{ padding: 0, overflow: "hidden", marginBottom: "1.5rem" }}>
              <div style=${{ padding: "1rem 1.25rem 0.5rem" }}>
                <p className="panel-label">Live Capital Flow Map</p>
                <p style=${{ fontSize: "0.8rem", color: "var(--muted)", margin: "0 0 0.5rem" }}>
                  Edge thickness = confidence · Color = risk level · Hover an edge for detail
                </p>
              </div>
              <${FlowGraph}
                signals=${state.allSignals}
                onNodeClick=${handleNodeClick}
              />
            </section>
            ${hasData
              ? html`<section className="panel-grid">
              ${state.topRec
                ? html`
                    <article className="panel rec-preview-panel">
                      <p className="panel-label">Top Recommendation</p>
                      <div className="rec-preview-header">
                        <span className="rec-preview-rank">#${state.topRec.rank}</span>
                        <h3 className="rec-preview-title">${state.topRec.title}</h3>
                        <span
                          className=${"badge " + (RECOMMENDATION_ACTION_CLASSES[state.topRec.action] || "badge-neutral")}
                        >
                          ${titleCaseLabel(state.topRec.action)}
                        </span>
                      </div>
                      ${state.topRec.reasoning?.[0]
                        ? html`<p className="rec-preview-reason">${state.topRec.reasoning[0]}</p>`
                        : null}
                      <div className="rec-preview-meta">
                        <span className="score-chip">Score <strong>${state.topRec.score}</strong></span>
                        <span className="score-chip">Confidence <strong>${state.topRec.confidence}%</strong></span>
                      </div>
                      <a
                        href="/recommendations"
                        className="rec-preview-link"
                        onClick=${(event) => {
                          event.preventDefault();
                          navigate("/recommendations");
                        }}
                      >
                        View all recommendations →
                      </a>
                    </article>
                  `
                : null}
              <article className="panel">
                <p className="panel-label">Market State</p>
                <h3>${titleCaseLabel(trafficState?.market_state)}</h3>
                <p>Last update: ${formatDateTime(trafficState?.created_at)}</p>
              </article>
              <div className="capital-summary-row">
                <article className="panel">
                  <p className="panel-label">Top Capital Flows</p>
                  ${trafficState?.dominant_flows?.length
                    ? html`
                        <table className="summary-value-table" aria-label="Top capital flows">
                          <tbody>
                          ${trafficState.dominant_flows.map(
                            (flow, index) => html`
                              <tr key=${`${flow.origin}-${flow.destination}-${index}`}>
                                <td>
                                  <strong>${flow.origin}</strong> to <strong>${flow.destination}</strong>
                                </td>
                                <td className="summary-value">${titleCaseLabel(flow.strength)}</td>
                              </tr>
                            `
                          )}
                          </tbody>
                        </table>
                      `
                    : html`<p className="empty-copy">No dominant flows yet.</p>`}
                </article>
                <article className="panel">
                  <p className="panel-label">Top Destinations</p>
                  ${trafficState?.top_destinations?.length
                    ? html`
                        <table className="summary-value-table" aria-label="Top destinations">
                          <tbody>
                          ${trafficState.top_destinations.map(
                            (destination) => html`
                              <tr key=${destination.destination}>
                                <td><strong>${destination.destination}</strong></td>
                                <td className="summary-value">${formatConfidence(destination.confidence)}</td>
                              </tr>
                            `
                          )}
                          </tbody>
                        </table>
                      `
                    : html`<p className="empty-copy">No destinations ranked yet.</p>`}
                </article>
              </div>
            </section>`
              : null}
          `}
  `;
}
