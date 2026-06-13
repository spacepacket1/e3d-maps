import { html, useEffect, useState } from "../vendor.js";
import { formatConfidence, formatDateTime, titleCaseLabel, toArray } from "../formatters.js";
import { FlowGraph } from "../components/FlowGraph.js";
import { SignalTable } from "../components/SignalTable.js";
import { RECOMMENDATION_ACTION_CLASSES } from "../utils/recommendationActionClasses.js";
import { dedupeUrgentSignals } from "../utils/urgentSignals.js";

const AUTO_REFRESH_MS = 60_000;

export function MapsHomePage({ api, navigate }) {
  const [state, setState] = useState({
    loading: true,
    refreshing: false,
    error: "",
    trafficState: null,
    latestSignals: [],
    hazards: [],
    congestionSignals: [],
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
        const [trafficState, latestSignalsResponse, hazardsResponse, congestionResponse, signalsForGraphResponse, recsResponse] =
          await Promise.all([
            api.getState(),
            api.listSignals({ minConfidence: 0.7, limit: 5 }),
            api.listHazards({ limit: 5 }),
            api.listSignals({ signalType: "congestion_formation", limit: 5 }),
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
          latestSignals: toArray(latestSignalsResponse?.signals),
          hazards: toArray(hazardsResponse?.hazards),
          congestionSignals: toArray(congestionResponse?.signals),
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
  const dedupedUrgent = dedupeUrgentSignals([
    state.hazards,
    state.congestionSignals,
    state.latestSignals,
  ]);
  const hasData = Boolean(
    trafficState ||
      state.latestSignals.length ||
      state.hazards.length ||
      state.congestionSignals.length ||
      state.allSignals.length
  );

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
            ${dedupedUrgent.length > 0
              ? html`
                  <section className="alert-strip">
                    <span className="alert-strip-label">
                      ⚠ ${dedupedUrgent.length} urgent signal${dedupedUrgent.length === 1 ? "" : "s"}
                    </span>
                    <ul className="alert-strip-list">
                      ${dedupedUrgent.slice(0, 3).map(
                        (signal) => html`
                          <li key=${signal.id}>
                            <a href=${`/signals/${signal.id}`} onClick=${(event) => jumpToSignal(event, signal.id, navigate)}>
                              ${titleCaseLabel(signal.signal_type)}${signal.destination ? ` → ${signal.destination}` : ""}
                            </a>
                            <span className=${`badge badge-${signal.risk_level === "critical" ? "danger" : "warning"}`}>
                              ${titleCaseLabel(signal.risk_level)}
                            </span>
                          </li>
                        `
                      )}
                    </ul>
                  </section>
                `
              : null}
            ${!hasData ? html`<p className="empty-copy">No map state has been published yet.</p>` : null}
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
              <article className="panel">
                <p className="panel-label">Top Capital Flows</p>
                ${trafficState?.dominant_flows?.length
                  ? html`
                      <ul className="simple-list">
                        ${trafficState.dominant_flows.map(
                          (flow, index) => html`
                            <li key=${`${flow.origin}-${flow.destination}-${index}`}>
                              <strong>${flow.origin}</strong> to <strong>${flow.destination}</strong>
                              <span>${titleCaseLabel(flow.strength)}</span>
                            </li>
                          `
                        )}
                      </ul>
                    `
                  : html`<p className="empty-copy">No dominant flows yet.</p>`}
              </article>
              <article className="panel">
                <p className="panel-label">Top Destinations</p>
                ${trafficState?.top_destinations?.length
                  ? html`
                      <ul className="simple-list">
                        ${trafficState.top_destinations.map(
                          (destination) => html`
                            <li key=${destination.destination}>
                              <strong>${destination.destination}</strong>
                              <span>${formatConfidence(destination.confidence)}</span>
                            </li>
                          `
                        )}
                      </ul>
                    `
                  : html`<p className="empty-copy">No destinations ranked yet.</p>`}
              </article>
              <article className="panel">
                <p className="panel-label">Active Hazards</p>
                ${trafficState?.hazards?.length || state.hazards.length
                  ? html`
                      <ul className="simple-list">
                        ${toArray(trafficState?.hazards).map(
                          (hazard) => html`<li key=${hazard}>${hazard}</li>`
                        )}
                        ${state.hazards.map(
                          (hazardSignal) => html`
                            <li key=${hazardSignal.id}>
                              <a href=${`/signals/${hazardSignal.id}`} onClick=${(event) => jumpToSignal(event, hazardSignal.id, navigate)}>
                                ${hazardSignal.destination
                                  ? `${titleCaseLabel(hazardSignal.signal_type)} — ${hazardSignal.destination}`
                                  : titleCaseLabel(hazardSignal.signal_type)}
                              </a>
                            </li>
                          `
                        )}
                      </ul>
                    `
                  : html`<p className="empty-copy">No hazards are active.</p>`}
              </article>
              <article className="panel">
                <p className="panel-label">Active Congestion</p>
                ${trafficState?.congestion_zones?.length || state.congestionSignals.length
                  ? html`
                      <ul className="simple-list">
                        ${toArray(trafficState?.congestion_zones).map(
                          (zone) => html`<li key=${zone}>${zone}</li>`
                        )}
                        ${state.congestionSignals.map(
                          (signal) => html`
                            <li key=${signal.id}>
                              <a href=${`/signals/${signal.id}`} onClick=${(event) => jumpToSignal(event, signal.id, navigate)}>
                                ${signal.answer}
                              </a>
                            </li>
                          `
                        )}
                      </ul>
                    `
                  : html`<p className="empty-copy">No congestion zones have been detected.</p>`}
              </article>
            </section>`
              : null}
          `}

    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="panel-label">Latest High-Confidence Navigation Signals</p>
          <h3>Human review queue</h3>
        </div>
      </div>
      ${html`<${SignalTable}
        signals=${state.latestSignals}
        navigate=${navigate}
        emptyLabel="No high-confidence signals are available."
      />`}
    </section>
  `;
}

function jumpToSignal(event, signalId, navigate) {
  event.preventDefault();
  navigate(`/signals/${signalId}`);
}
