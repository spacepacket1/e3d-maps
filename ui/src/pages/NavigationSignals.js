import { html, useEffect, useState } from "../vendor.js";
import { SignalTable } from "../components/SignalTable.js";

export function NavigationSignalsPage({ api, navigate }) {
  const [state, setState] = useState({
    loading: true,
    error: "",
    signals: [],
  });

  useEffect(() => {
    let cancelled = false;

    async function loadSignals() {
      try {
        const response = await api.listSignals({ limit: 50 });
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
  }, [api]);

  return html`
    <section className="page-header">
      <div>
        <p className="eyebrow">Navigation Signals</p>
        <h2>Recent generated signals</h2>
      </div>
    </section>
    ${state.error ? html`<p className="error-banner">${state.error}</p>` : null}
    ${state.loading
      ? html`<p className="empty-copy">Loading signals...</p>`
      : html`<${SignalTable} signals=${state.signals} navigate=${navigate} />`}
  `;
}
