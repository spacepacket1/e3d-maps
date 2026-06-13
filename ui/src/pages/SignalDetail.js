import { html, useEffect, useState } from "../vendor.js";
import { ConfidenceBadge } from "../components/ConfidenceBadge.js";
import { EvidenceList } from "../components/EvidenceList.js";
import { formatDateTime, titleCaseLabel, toArray } from "../formatters.js";

export function SignalDetailPage({ api, navigate, params }) {
  const [state, setState] = useState({
    loading: true,
    error: "",
    signal: null,
    relatedRoutes: [],
  });

  useEffect(() => {
    let cancelled = false;

    async function loadSignal() {
      try {
        const [signal, routesResponse] = await Promise.all([
          api.getSignal(params.id),
          api.listRoutes({ limit: 100 }),
        ]);

        if (cancelled) {
          return;
        }

        const relatedRoutes = toArray(routesResponse?.routes).filter(
          (route) => route.navigation_signal_id === signal?.id
        );

        setState({
          loading: false,
          error: "",
          signal,
          relatedRoutes,
        });
      } catch (error) {
        if (cancelled) {
          return;
        }
        setState({
          loading: false,
          error: error instanceof Error ? error.message : String(error),
          signal: null,
          relatedRoutes: [],
        });
      }
    }

    loadSignal();
    return () => {
      cancelled = true;
    };
  }, [api, params.id]);

  if (state.loading) {
    return html`<p className="empty-copy">Loading signal detail...</p>`;
  }

  if (state.error) {
    return html`<p className="error-banner">${state.error}</p>`;
  }

  if (!state.signal) {
    return html`
      <section className="page-header">
        <div>
          <p className="eyebrow">Signal Detail</p>
          <h2>Signal not found</h2>
        </div>
      </section>
      <p className="empty-copy">The requested signal is not available.</p>
    `;
  }

  const signal = state.signal;

  return html`
    <section className="page-header">
      <div>
        <p className="eyebrow">Signal Detail</p>
        <h2>${titleCaseLabel(signal.signal_type)}</h2>
      </div>
      <a href="/signals" className="action-button action-link" onClick=${(event) => backToSignals(event, navigate)}>
        Back to signals
      </a>
    </section>

    <section className="panel detail-panel">
      <p className="panel-label">Question</p>
      <h3>${signal.question}</h3>
      <blockquote className="signal-answer">${signal.answer}</blockquote>
      <dl className="detail-grid">
        <div>
          <dt>Confidence</dt>
          <dd>${html`<${ConfidenceBadge} value=${signal.confidence} />`}</dd>
        </div>
        <div>
          <dt>Risk Level</dt>
          <dd>${titleCaseLabel(signal.risk_level)}</dd>
        </div>
        <div>
          <dt>Signal Strength</dt>
          <dd>${titleCaseLabel(signal.signal_strength)}</dd>
        </div>
        <div>
          <dt>Time Horizon</dt>
          <dd>${signal.time_horizon_hours}h</dd>
        </div>
        <div>
          <dt>Origin</dt>
          <dd>${signal.origin || "n/a"}</dd>
        </div>
        <div>
          <dt>Destination</dt>
          <dd>${signal.destination || "n/a"}</dd>
        </div>
        <div>
          <dt>Outcome Status</dt>
          <dd>${titleCaseLabel(signal.outcome_status)}</dd>
        </div>
        <div>
          <dt>Utility Score</dt>
          <dd>Not yet scored</dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>${formatDateTime(signal.created_at)}</dd>
        </div>
      </dl>
    </section>

    <section className="panel">
      <p className="panel-label">Evidence</p>
      <h3>Attached evidence</h3>
      ${html`<${EvidenceList} evidence=${toArray(signal.evidence)} />`}
    </section>

    <section className="panel-grid">
      <article className="panel">
        <p className="panel-label">Supporting Stories</p>
        ${renderLinkedReferences(toArray(signal.supporting_story_ids))}
      </article>
      <article className="panel">
        <p className="panel-label">Supporting Theses</p>
        ${renderLinkedReferences(toArray(signal.supporting_thesis_ids))}
      </article>
      <article className="panel">
        <p className="panel-label">Related Route Predictions</p>
        ${state.relatedRoutes.length
          ? html`
              <ul className="simple-list">
                ${state.relatedRoutes.map(
                  (route) => html`
                    <li key=${route.id}>
                      <strong>${route.origin}</strong> to <strong>${route.destination}</strong>
                      <span>${titleCaseLabel(route.expected_flow_direction)}</span>
                    </li>
                  `
                )}
              </ul>
            `
          : html`<p className="empty-copy">No related route predictions were returned.</p>`}
      </article>
    </section>
  `;
}

function renderLinkedReferences(items) {
  if (!items.length) {
    return html`<p className="empty-copy">No linked references.</p>`;
  }

  return html`
    <ul className="simple-list">
      ${items.map(
        (item) => html`
          <li key=${item}>
            <a href=${`#evidence-${item}`}>${item}</a>
          </li>
        `
      )}
    </ul>
  `;
}

function backToSignals(event, navigate) {
  event.preventDefault();
  navigate("/signals");
}
