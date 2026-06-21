import { html, useEffect, useState } from "../vendor.js";
import { formatConfidence, formatDateTime, titleCaseLabel, toArray } from "../formatters.js";
import { FlowGraph } from "../components/FlowGraph.js";
import { RECOMMENDATION_ACTION_CLASSES } from "../utils/recommendationActionClasses.js";

const AUTO_REFRESH_MS = 60_000;
const CROSS_CHAIN_LIMITS = {
  top_routes: 3,
  active_hazards: 3,
  active_congestion: 3,
  top_destinations: 4,
  ethereum_outbound_routes: 3,
  ethereum_inbound_routes: 3,
};

function resolveSettledValue(result, fallback = null) {
  return result?.status === "fulfilled" ? (result.value ?? fallback) : fallback;
}

function collectRejectedMessages(results) {
  const messages = new Set();
  for (const result of results) {
    if (result?.status !== "rejected") continue;
    const message = result.reason instanceof Error ? result.reason.message : String(result.reason || "");
    if (message) messages.add(message);
  }
  return [...messages];
}

function riskBadgeClass(riskLevel) {
  switch (riskLevel) {
    case "critical":
    case "high":
      return "badge-danger";
    case "medium":
      return "badge-warning";
    default:
      return "badge-accent";
  }
}

function routePair(item) {
  return `${titleCaseLabel(item.origin)} → ${titleCaseLabel(item.destination)}`;
}

function hasCrossChainContent(crossChainActivity) {
  if (!crossChainActivity) return false;
  return (
    toArray(crossChainActivity.top_routes).length > 0 ||
    toArray(crossChainActivity.active_hazards).length > 0 ||
    toArray(crossChainActivity.active_congestion).length > 0 ||
    toArray(crossChainActivity.top_destinations).length > 0 ||
    toArray(crossChainActivity.ethereum_outbound_routes).length > 0 ||
    toArray(crossChainActivity.ethereum_inbound_routes).length > 0
  );
}

function CrossChainList({ items, emptyLabel, renderItem }) {
  if (!items.length) {
    return html`<p className="empty-copy">${emptyLabel}</p>`;
  }

  return html`
    <div className="cross-chain-list">
      ${items.map(renderItem)}
    </div>
  `;
}

function predictionTitle(prediction) {
  if (prediction?.question) return prediction.question;
  if (prediction?.answer) return prediction.answer;
  const origin = prediction?.origin || prediction?.source_chain || prediction?.asset || "Capital";
  const destination = prediction?.destination || prediction?.target_chain || prediction?.chain || "next destination";
  return `${titleCaseLabel(origin)} → ${titleCaseLabel(destination)}`;
}

function predictionSummary(prediction) {
  return prediction?.reasoning || prediction?.evidence_summary || prediction?.answer || prediction?.description || "";
}

export function MapsHomePage({ api, navigate }) {
  const [state, setState] = useState({
    loading: true,
    refreshing: false,
    error: "",
    trafficState: null,
    crossChainActivity: null,
    allSignals: [],
    predictions: [],
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

      const results = await Promise.allSettled([
        api.getState(),
        api.getCrossChainActivity(),
        api.listSignals({ limit: 200 }),
        api.listPredictions({ limit: 3 }),
        api.getRecommendations({ maxResults: 1 }),
      ]);

      if (cancelled) {
        return;
      }

      const [
        trafficStateResult,
        crossChainResult,
        signalsResult,
        predictionsResult,
        recommendationsResult,
      ] = results;
      const rejectedMessages = collectRejectedMessages(results);

      setState({
        loading: false,
        refreshing: false,
        error: rejectedMessages.length ? "Some homepage data is temporarily unavailable." : "",
        trafficState: resolveSettledValue(trafficStateResult),
        crossChainActivity: resolveSettledValue(crossChainResult),
        allSignals: toArray(resolveSettledValue(signalsResult)?.signals),
        predictions: toArray(resolveSettledValue(predictionsResult)?.predictions).slice(0, 3),
        topRec: resolveSettledValue(recommendationsResult)?.recommendations?.[0] || null,
      });
    }

    loadDashboard(reloadToken > 0);
    const timer = window.setInterval(() => loadDashboard(true), AUTO_REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [api, reloadToken]);

  const trafficState = state.trafficState;
  const crossChainActivity = state.crossChainActivity;
  const hasAnyHomepageData = Boolean(
    trafficState || state.allSignals.length || state.predictions.length || hasCrossChainContent(crossChainActivity)
  );
  const crossChainItems = {
    top_routes: toArray(crossChainActivity?.top_routes).slice(0, CROSS_CHAIN_LIMITS.top_routes),
    active_hazards: toArray(crossChainActivity?.active_hazards).slice(0, CROSS_CHAIN_LIMITS.active_hazards),
    active_congestion: toArray(crossChainActivity?.active_congestion).slice(0, CROSS_CHAIN_LIMITS.active_congestion),
    top_destinations: toArray(crossChainActivity?.top_destinations).slice(0, CROSS_CHAIN_LIMITS.top_destinations),
    ethereum_outbound_routes: toArray(crossChainActivity?.ethereum_outbound_routes).slice(
      0,
      CROSS_CHAIN_LIMITS.ethereum_outbound_routes
    ),
    ethereum_inbound_routes: toArray(crossChainActivity?.ethereum_inbound_routes).slice(
      0,
      CROSS_CHAIN_LIMITS.ethereum_inbound_routes
    ),
  };

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
          <section className="panel predictions-preview">
            <div className="predictions-preview-header">
              <div>
                <p className="panel-label">Predictions</p>
                <h3>Forward-looking capital moves</h3>
              </div>
              <a
                href="/signals"
                className="rec-preview-link"
                onClick=${(event) => {
                  event.preventDefault();
                  navigate("/signals");
                }}
              >
                View signals →
              </a>
            </div>
            ${state.predictions.length
              ? html`
                  <div className="prediction-card-grid">
                    ${state.predictions.map(
                      (prediction) => html`
                        <article key=${prediction.id} className="prediction-card">
                          <div className="prediction-card-topline">
                            <span className="badge badge-accent">${titleCaseLabel(prediction.signal_type || "prediction")}</span>
                            <span className="score-chip">${formatConfidence(prediction.confidence)}</span>
                          </div>
                          <h4>${predictionTitle(prediction)}</h4>
                          ${predictionSummary(prediction)
                            ? html`<p>${predictionSummary(prediction)}</p>`
                            : html`<p className="empty-copy">No summary attached to this prediction yet.</p>`}
                          <span className="prediction-card-date">${formatDateTime(prediction.created_at)}</span>
                        </article>
                      `
                    )}
                  </div>
                `
              : html`<p className="empty-copy">No forward-looking predictions are available yet.</p>`}
          </section>

          <section className="panel" style=${{ padding: 0, overflow: "hidden", marginBottom: "1.5rem" }}>
            <div style=${{ padding: "1rem 1.25rem 0.5rem" }}>
              <p className="panel-label">Live Capital Flow Map</p>
              <p style=${{ fontSize: "0.8rem", color: "var(--muted)", margin: "0 0 0.5rem" }}>
                Edge thickness = confidence · Color = risk level · Dashed = cross-chain route
              </p>
            </div>
            <${FlowGraph}
              signals=${state.allSignals}
              crossChainRoutes=${crossChainActivity?.top_routes ?? []}
              onNodeClick=${handleNodeClick}
            />
          </section>

          ${!hasAnyHomepageData ? html`<p className="empty-copy">No map state has been published yet.</p>` : null}

          ${trafficState || state.topRec
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

                ${trafficState
                  ? html`
                      <article className="panel">
                        <p className="panel-label">Market State</p>
                        <h3>${titleCaseLabel(trafficState.market_state)}</h3>
                        <p>Last update: ${formatDateTime(trafficState.created_at)}</p>
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
                    `
                  : null}
              </section>`
            : null}

          <section className="panel cross-chain-panel">
            <div className="cross-chain-panel-header">
              <div>
                <p className="panel-label">Cross-Chain Activity</p>
                <h3>Cross-Chain Activity</h3>
              </div>
              ${crossChainActivity?.market_bias
                ? html`<span className="badge badge-accent">${titleCaseLabel(crossChainActivity.market_bias)}</span>`
                : null}
            </div>

            ${hasCrossChainContent(crossChainActivity)
              ? html`
                  <div className="cross-chain-grid">
                    <article className="cross-chain-section">
                      <p className="panel-label">Routes Opening</p>
                      <${CrossChainList}
                        items=${crossChainItems.top_routes}
                        emptyLabel="Cross-chain activity is quiet or not yet classified."
                        renderItem=${(item, index) => html`
                          <div key=${`${item.normalized_origin}-${item.normalized_destination}-${index}`} className="cross-chain-item">
                            <div className="cross-chain-item-header">
                              <strong>${routePair(item)}</strong>
                              <span className=${`badge ${riskBadgeClass(item.risk_level)}`}>${titleCaseLabel(item.risk_level)}</span>
                            </div>
                            <p>${item.summary}</p>
                          </div>
                        `}
                      />
                    </article>

                    <article className="cross-chain-section">
                      <p className="panel-label">Risky Corridors</p>
                      <${CrossChainList}
                        items=${crossChainItems.active_hazards}
                        emptyLabel="Cross-chain activity is quiet or not yet classified."
                        renderItem=${(item, index) => html`
                          <div key=${`${item.normalized_origin}-${item.normalized_destination}-${index}`} className="cross-chain-item">
                            <div className="cross-chain-item-header">
                              <strong>${routePair(item)}</strong>
                              <span className=${`badge ${riskBadgeClass(item.risk_level)}`}>${titleCaseLabel(item.risk_level)}</span>
                            </div>
                            <p>${item.summary}</p>
                          </div>
                        `}
                      />
                    </article>

                    <article className="cross-chain-section">
                      <p className="panel-label">Crowding</p>
                      <${CrossChainList}
                        items=${crossChainItems.active_congestion}
                        emptyLabel="Cross-chain activity is quiet or not yet classified."
                        renderItem=${(item, index) => html`
                          <div key=${`${item.normalized_origin}-${item.normalized_destination}-${index}`} className="cross-chain-item">
                            <div className="cross-chain-item-header">
                              <strong>${routePair(item)}</strong>
                              <span className=${`badge ${riskBadgeClass(item.risk_level)}`}>${formatConfidence(item.confidence)}</span>
                            </div>
                            <p>${item.summary}</p>
                          </div>
                        `}
                      />
                    </article>

                    <article className="cross-chain-section">
                      <p className="panel-label">Top Destinations</p>
                      <${CrossChainList}
                        items=${crossChainItems.top_destinations}
                        emptyLabel="Cross-chain activity is quiet or not yet classified."
                        renderItem=${(item, index) => html`
                          <div key=${`${item.normalized_destination}-${index}`} className="cross-chain-item">
                            <div className="cross-chain-item-header">
                              <strong>${titleCaseLabel(item.destination)}</strong>
                              <span className="badge badge-accent">${formatConfidence(item.confidence)}</span>
                            </div>
                            <p>${item.supporting_signal_count} supporting signal${item.supporting_signal_count === 1 ? "" : "s"}</p>
                          </div>
                        `}
                      />
                    </article>

                    <article className="cross-chain-section">
                      <p className="panel-label">Out of Ethereum</p>
                      <${CrossChainList}
                        items=${crossChainItems.ethereum_outbound_routes}
                        emptyLabel="Cross-chain activity is quiet or not yet classified."
                        renderItem=${(item, index) => html`
                          <div key=${`${item.normalized_origin}-${item.normalized_destination}-${index}`} className="cross-chain-item">
                            <div className="cross-chain-item-header">
                              <strong>${routePair(item)}</strong>
                              <span className="badge badge-neutral">${titleCaseLabel(item.route_class)}</span>
                            </div>
                            <p>${item.summary}</p>
                          </div>
                        `}
                      />
                    </article>

                    <article className="cross-chain-section">
                      <p className="panel-label">Into Ethereum</p>
                      <${CrossChainList}
                        items=${crossChainItems.ethereum_inbound_routes}
                        emptyLabel="Cross-chain activity is quiet or not yet classified."
                        renderItem=${(item, index) => html`
                          <div key=${`${item.normalized_origin}-${item.normalized_destination}-${index}`} className="cross-chain-item">
                            <div className="cross-chain-item-header">
                              <strong>${routePair(item)}</strong>
                              <span className="badge badge-neutral">${titleCaseLabel(item.route_class)}</span>
                            </div>
                            <p>${item.summary}</p>
                          </div>
                        `}
                      />
                    </article>
                  </div>
                `
              : html`<p className="empty-copy">Cross-chain activity is quiet or not yet classified.</p>`}
          </section>
        `}
  `;
}
