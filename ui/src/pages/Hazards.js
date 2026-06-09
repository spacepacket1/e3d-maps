import { html, useEffect, useState } from "../vendor.js";
import { titleCaseLabel, toArray } from "../formatters.js";
import { SignalTable } from "../components/SignalTable.js";

export function HazardsPage({ api, navigate }) {
  const [state, setState] = useState({
    loading: true,
    error: "",
    trafficState: null,
    hazards: [],
  });

  useEffect(() => {
    let cancelled = false;

    async function loadHazards() {
      try {
        const [trafficState, hazardsResponse] = await Promise.all([
          api.getState(),
          api.listHazards({ limit: 50 }),
        ]);
        if (cancelled) {
          return;
        }
        setState({
          loading: false,
          error: "",
          trafficState,
          hazards: toArray(hazardsResponse?.hazards),
        });
      } catch (error) {
        if (cancelled) {
          return;
        }
        setState({
          loading: false,
          error: error instanceof Error ? error.message : String(error),
          trafficState: null,
          hazards: [],
        });
      }
    }

    loadHazards();
    return () => {
      cancelled = true;
    };
  }, [api]);

  return html`
    <section className="page-header">
      <div>
        <p className="eyebrow">Hazards</p>
        <h2>Route hazards and closures</h2>
      </div>
    </section>
    ${state.error ? html`<p className="error-banner">${state.error}</p>` : null}
    ${state.loading
      ? html`<p className="empty-copy">Loading hazards...</p>`
      : html`
          <section className="panel">
            <p className="panel-label">Traffic State Hazards</p>
            ${state.trafficState?.hazards?.length
              ? html`
                  <ul className="simple-list">
                    ${state.trafficState.hazards.map(
                      (hazard) => html`<li key=${hazard}>${titleCaseLabel(hazard)}</li>`
                    )}
                  </ul>
                `
              : html`<p className="empty-copy">No active hazards on the latest traffic state.</p>`}
          </section>
          <section className="panel">
            <p className="panel-label">Hazard Signals</p>
            ${html`<${SignalTable}
              signals=${state.hazards}
              navigate=${navigate}
              emptyLabel="No hazard or closure signals are available."
            />`}
          </section>
        `}
  `;
}
