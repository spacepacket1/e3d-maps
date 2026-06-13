import { html } from "../vendor.js";
import { formatDateTime, titleCaseLabel } from "../formatters.js";
import { ConfidenceBadge } from "./ConfidenceBadge.js";
import { truncateAnswer } from "../utils/truncateAnswer.js";
import { riskRowClass } from "../utils/riskRowClass.js";

export function SignalTable({ signals, navigate, emptyLabel = "No signals available." }) {
  if (!signals.length) {
    return html`<p className="empty-copy">${emptyLabel}</p>`;
  }

  return html`
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Type</th>
            <th>Answer</th>
            <th>Confidence</th>
            <th>Horizon</th>
            <th>Origin</th>
            <th>Destination</th>
            <th>Risk</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          ${signals.map(
            (signal) => html`
              <tr key=${signal.id} className=${riskRowClass(signal.risk_level)}>
                <td>
                  <a
                    href=${`/signals/${signal.id}`}
                    onClick=${(event) => handleSignalClick(event, signal.id, navigate)}
                  >
                    ${titleCaseLabel(signal.signal_type)}
                  </a>
                </td>
                <td className="answer-preview">${truncateAnswer(signal.answer)}</td>
                <td>${html`<${ConfidenceBadge} value=${signal.confidence} />`}</td>
                <td>${signal.time_horizon_hours}h</td>
                <td>${signal.origin || "n/a"}</td>
                <td>${signal.destination || "n/a"}</td>
                <td>${titleCaseLabel(signal.risk_level)}</td>
                <td>${formatDateTime(signal.created_at)}</td>
              </tr>
            `
          )}
        </tbody>
      </table>
    </div>
  `;
}

function handleSignalClick(event, signalId, navigate) {
  event.preventDefault();
  navigate(`/signals/${signalId}`);
}
