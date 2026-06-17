import { html, useEffect, useState } from "../vendor.js";
import { formatConfidence, formatDateTime, titleCaseLabel, toArray } from "../formatters.js";
import { FlowGraph } from "../components/FlowGraph.js";
import { RECOMMENDATION_ACTION_CLASSES } from "../utils/recommendationActionClasses.js";
import { deriveTrackRecord } from "../utils/calibration.js";

const AUTO_REFRESH_MS = 60_000;
const NEWS_STALE_MINUTES = 15;
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

function formatRelativeUpdatedAt(value) {
  if (!value) {
    return { label: "Update time unavailable", isStale: true };
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return { label: `Updated ${value}`, isStale: true };
  }

  const deltaMs = Math.max(0, Date.now() - date.getTime());
  const deltaMinutes = Math.round(deltaMs / 60_000);
  const deltaHours = Math.round(deltaMs / 3_600_000);
  const deltaDays = Math.round(deltaMs / 86_400_000);

  let label = "Updated just now";
  if (deltaMinutes >= 1 && deltaMinutes < 60) {
    label = `Updated ${deltaMinutes} minute${deltaMinutes === 1 ? "" : "s"} ago`;
  } else if (deltaMinutes >= 60 && deltaHours < 24) {
    label = `Updated ${deltaHours} hour${deltaHours === 1 ? "" : "s"} ago`;
  } else if (deltaHours >= 24) {
    label = `Updated ${deltaDays} day${deltaDays === 1 ? "" : "s"} ago`;
  }

  return { label, isStale: deltaMs > NEWS_STALE_MINUTES * 60_000 };
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

function stanceClass(stance) {
  switch (stance) {
    case "risk_on":
      return "maps-news-hero stance-risk-on";
    case "risk_off":
      return "maps-news-hero stance-risk-off";
    case "crowded":
      return "maps-news-hero stance-crowded";
    case "cautious":
      return "maps-news-hero stance-cautious";
    default:
      return "maps-news-hero stance-neutral";
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

export function MapsHomePage({ api, navigate }) {
  const [state, setState] = useState({
    loading: true,
    refreshing: false,
    error: "",
    trafficState: null,
    mapsNews: null,
    crossChainActivity: null,
    allSignals: [],
    topRec: null,
    calibration: null,
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
        api.getNews(),
        api.getCrossChainActivity(),
        api.listSignals({ limit: 200 }),
        api.getRecommendations({ maxResults: 1 }),
        api.getCalibration({ lookbackDays: 30 }),
      ]);

      if (cancelled) {
        return;
      }

      const [
        trafficStateResult,
        mapsNewsResult,
        crossChainResult,
        signalsResult,
        recommendationsResult,
        calibrationResult,
      ] = results;
      const rejectedMessages = collectRejectedMessages(results);

      setState({
        loading: false,
        refreshing: false,
        error: rejectedMessages.length ? "Some homepage data is temporarily unavailable." : "",
        trafficState: resolveSettledValue(trafficStateResult),
        mapsNews: resolveSettledValue(mapsNewsResult),
        crossChainActivity: resolveSettledValue(crossChainResult),
        allSignals: toArray(resolveSettledValue(signalsResult)?.signals),
        topRec: resolveSettledValue(recommendationsResult)?.recommendations?.[0] || null,
        calibration: resolveSettledValue(calibrationResult),
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
  const mapsNews = state.mapsNews;
  const crossChainActivity = state.crossChainActivity;
  const hasAnyHomepageData = Boolean(
    trafficState || state.allSignals.length || mapsNews || hasCrossChainContent(crossChainActivity)
  );
  const newsTimestamp = formatRelativeUpdatedAt(mapsNews?.generated_at);
  const trackRecord = deriveTrackRecord(state.calibration);
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
          <section className=${stanceClass(mapsNews?.stance)}>
            <div className="maps-news-copy">
              <p className="eyebrow">Maps News</p>
              ${mapsNews
                ? html`
                    <h3>${mapsNews.headline}</h3>
                    <p className="maps-news-summary">${mapsNews.summary}</p>
                    <div className="maps-news-meta">
                      <span className=${newsTimestamp.isStale ? "maps-news-timestamp is-stale" : "maps-news-timestamp"}>
                        ${newsTimestamp.label}
                      </span>
                      <span className="maps-news-meta-sep">•</span>
                      <span className="maps-news-meta-value">${titleCaseLabel(mapsNews.stance)}</span>
                    </div>
                    <div className="maps-news-tags">
                      ${toArray(mapsNews.tags).map(
                        (tag) => html`<span key=${tag} className="badge badge-neutral">${titleCaseLabel(tag)}</span>`
                      )}
                    </div>
                  `
                : html`
                    <h3>Maps News is warming up.</h3>
                    <p className="maps-news-summary">
                      The homepage bulletin will appear here once the latest market brief has been published.
                    </p>
                  `}
            </div>
          </section>

          <a
            href="/calibration"
            className="track-record-strip"
            onClick=${(event) => {
              event.preventDefault();
              navigate("/calibration");
            }}
          >
            <span className="panel-label">Track Record · 30d</span>
            ${trackRecord.scored
              ? html`
                  <span className="track-record-stats">
                    <span className="score-chip">Hit rate <strong>${formatConfidence(trackRecord.hitRate)}</strong></span>
                    <span className="score-chip">Calibration error <strong>${formatConfidence(trackRecord.calibrationError)}</strong></span>
                    <span className="score-chip">${trackRecord.totalScored.toLocaleString()} scored</span>
                  </span>
                `
              : html`<span className="track-record-stats"><span className="score-chip">Scoring in progress — first outcomes pending</span></span>`}
            <span className="track-record-cta">View track record →</span>
          </a>

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
