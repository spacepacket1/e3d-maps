import { html, useEffect, useState } from "../vendor.js";
import { titleCaseLabel, toArray } from "../formatters.js";
import { SignalTable } from "../components/SignalTable.js";

export function CongestionPage({ api, navigate }) {
  const [state, setState] = useState({
    loading: true,
    error: "",
    trafficState: null,
    signals: [],
  });

  useEffect(() => {
    let cancelled = false;

    async function loadCongestion() {
      try {
        const [trafficState, signalsResponse] = await Promise.all([
          api.getState(),
          api.listSignals({ signalType: "congestion_formation", limit: 50 }),
        ]);
        if (cancelled) {
          return;
        }
        setState({
          loading: false,
          error: "",
          trafficState,
          signals: toArray(signalsResponse?.signals),
        });
      } catch (error) {
        if (cancelled) {
          return;
        }
        setState({
          loading: false,
          error: error instanceof Error ? error.message : String(error),
          trafficState: null,
          signals: [],
        });
      }
    }

    loadCongestion();
    return () => {
      cancelled = true;
    };
  }, [api]);

  return html`
    <section className="page-header">
      <div>
        <p className="eyebrow">Congestion</p>
        <h2>Network slowdowns and crowding</h2>
      </div>
    </section>
    ${state.error ? html`<p className="error-banner">${state.error}</p>` : null}
    ${state.loading
      ? html`<p className="empty-copy">Loading congestion signals...</p>`
      : html`
          <section className="panel">
            <p className="panel-label">Active Congestion Zones</p>
            ${state.trafficState?.congestion_zones?.length
              ? html`
                  <ul className="simple-list">
                    ${state.trafficState.congestion_zones.map(
                      (zone) => html`<li key=${zone}>${titleCaseLabel(zone)}</li>`
                    )}
                  </ul>
                `
              : html`<p className="empty-copy">No congestion zones have been published.</p>`}
          </section>
          <section className="panel">
            <p className="panel-label">Congestion Signals</p>
            ${html`<${SignalTable}
              signals=${state.signals}
              navigate=${navigate}
              emptyLabel="No congestion signals are available."
            />`}
          </section>
        `}
  `;
}
