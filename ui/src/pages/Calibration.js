import { html, useEffect, useState } from "../vendor.js";
import { formatConfidence, titleCaseLabel } from "../formatters.js";
import { deriveTrackRecord, describeCalibration } from "../utils/calibration.js";

function formatGap(gap) {
  if (typeof gap !== "number") return "n/a";
  const points = Math.round(gap * 100);
  if (points === 0) return "±0 pts";
  return `${points > 0 ? "+" : ""}${points} pts`;
}

function gapClass(gap) {
  if (typeof gap !== "number") return "badge-neutral";
  const points = Math.abs(Math.round(gap * 100));
  if (points <= 3) return "badge-positive";
  if (points <= 10) return "badge-warning";
  return "badge-danger";
}

export function CalibrationPage({ api }) {
  const [state, setState] = useState({ loading: true, error: "", calibration: null });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const calibration = await api.getCalibration({ lookbackDays: 30 });
        if (cancelled) return;
        setState({ loading: false, error: "", calibration });
      } catch (error) {
        if (cancelled) return;
        setState({
          loading: false,
          error: error instanceof Error ? error.message : String(error),
          calibration: null,
        });
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [api]);

  const record = deriveTrackRecord(state.calibration);
  const interpretation = describeCalibration({
    calibrationError: record.calibrationError,
    meanAccuracy: record.meanAccuracy,
    meanConfidence: record.meanConfidence,
  });

  return html`
    <section className="page-header">
      <div>
        <p className="eyebrow">Track Record</p>
        <h2>How accurate is the map?</h2>
      </div>
    </section>

    <p className="empty-copy" style=${{ marginTop: 0 }}>
      Every NavigationSignal is scored against reality once its time horizon closes. This is that scorecard —
      published in full, including where the map is wrong. Calibration is the difference between a navigator and a
      fortune teller.
    </p>

    ${state.error ? html`<p className="error-banner">${state.error}</p>` : null}

    ${state.loading
      ? html`<p className="empty-copy">Loading track record...</p>`
      : !record.scored
        ? html`
            <section className="panel">
              <p className="panel-label">Scoring In Progress</p>
              <h3>No predictions have closed their evaluation window yet.</h3>
              <p className="empty-copy">
                Signals are scored only after their time horizon elapses, using two independent witnesses (a
                story-based heuristic and a quantitative flow-series scorer). Once outcomes accrue, hit rate,
                calibration error, and per-signal-type reliability will appear here.
              </p>
              ${record.totalSignals
                ? html`<p className="empty-copy"><strong>${record.totalSignals.toLocaleString()}</strong> signals generated and awaiting scoring.</p>`
                : null}
            </section>
          `
        : html`
            <section className="panel-grid">
              <article className="panel">
                <p className="panel-label">Hit Rate</p>
                <h3 style=${{ fontSize: "2.2rem", margin: "0.25rem 0" }}>${formatConfidence(record.hitRate)}</h3>
                <p className="empty-copy">Share of predictions scored correct across the last ${record.lookbackDays} days.</p>
              </article>
              <article className="panel">
                <p className="panel-label">Mean Realized Accuracy</p>
                <h3 style=${{ fontSize: "2.2rem", margin: "0.25rem 0" }}>${formatConfidence(record.meanAccuracy)}</h3>
                <p className="empty-copy">Stated confidence averaged ${formatConfidence(record.meanConfidence)}.</p>
              </article>
              <article className="panel">
                <p className="panel-label">Calibration Error</p>
                <h3 style=${{ fontSize: "2.2rem", margin: "0.25rem 0" }}>
                  <span className=${"badge " + gapClass(record.meanAccuracy - record.meanConfidence)}>
                    ${formatConfidence(record.calibrationError)}
                  </span>
                </h3>
                <p className="empty-copy">${interpretation || "Distance between confidence and realized accuracy."}</p>
              </article>
              <article className="panel">
                <p className="panel-label">Predictions Scored</p>
                <h3 style=${{ fontSize: "2.2rem", margin: "0.25rem 0" }}>${record.totalScored.toLocaleString()}</h3>
                <p className="empty-copy">Across ${record.typesCovered} signal type${record.typesCovered === 1 ? "" : "s"}.</p>
              </article>
            </section>

            <section className="panel">
              <p className="panel-label">Reliability by Signal Type</p>
              <div className="table-wrap">
                <table className="data-table" aria-label="Reliability by signal type">
                  <thead>
                    <tr>
                      <th>Signal Type</th>
                      <th>Scored</th>
                      <th>Stated Confidence</th>
                      <th>Realized Accuracy</th>
                      <th>Calibration Gap</th>
                      <th>Utility</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${record.rows.map(
                      (row) => html`
                        <tr key=${row.signalType}>
                          <td><strong>${titleCaseLabel(row.signalType)}</strong></td>
                          <td>${row.samples.toLocaleString()}</td>
                          <td>${formatConfidence(row.meanConfidence)}</td>
                          <td>${formatConfidence(row.realizedAccuracy)}</td>
                          <td><span className=${"badge " + gapClass(row.calibrationGap)}>${formatGap(row.calibrationGap)}</span></td>
                          <td>${typeof row.utility === "number" ? row.utility.toFixed(2) : "—"}</td>
                        </tr>
                      `
                    )}
                  </tbody>
                </table>
              </div>
              <p className="empty-copy">
                Calibration gap is realized accuracy minus stated confidence. Negative means overconfident. Only
                signal types whose outcomes have been scored appear here.
              </p>
            </section>
          `}
  `;
}
