import { html, useEffect, useState } from "../vendor.js";
import { formatConfidence, formatDateTime, titleCaseLabel } from "../formatters.js";

export function RoutePredictionsPage({ api }) {
  const [state, setState] = useState({
    loading: true,
    error: "",
    routes: [],
  });

  useEffect(() => {
    let cancelled = false;

    async function loadRoutes() {
      try {
        const response = await api.listRoutes({ limit: 50 });
        if (cancelled) {
          return;
        }
        setState({
          loading: false,
          error: "",
          routes: Array.isArray(response?.routes) ? response.routes : [],
        });
      } catch (error) {
        if (cancelled) {
          return;
        }
        setState({
          loading: false,
          error: error instanceof Error ? error.message : String(error),
          routes: [],
        });
      }
    }

    loadRoutes();
    return () => {
      cancelled = true;
    };
  }, [api]);

  return html`
    <section className="page-header">
      <div>
        <p className="eyebrow">Route Predictions</p>
        <h2>Predicted routes</h2>
      </div>
    </section>
    ${state.error ? html`<p className="error-banner">${state.error}</p>` : null}
    ${state.loading
      ? html`<p className="empty-copy">Loading routes...</p>`
      : !state.routes.length
        ? html`<p className="empty-copy">No route predictions are available.</p>`
        : html`
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Origin</th>
                    <th>Destination</th>
                    <th>Direction</th>
                    <th>Magnitude</th>
                    <th>Confidence</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  ${state.routes.map(
                    (route) => html`
                      <tr key=${route.id}>
                        <td>${titleCaseLabel(route.route_type)}</td>
                        <td>${route.origin}</td>
                        <td>${route.destination}</td>
                        <td>${titleCaseLabel(route.expected_flow_direction)}</td>
                        <td>${titleCaseLabel(route.expected_flow_magnitude)}</td>
                        <td>${formatConfidence(route.confidence)}</td>
                        <td>${formatDateTime(route.created_at)}</td>
                      </tr>
                    `
                  )}
                </tbody>
              </table>
            </div>
          `}
  `;
}
