import { html } from "../vendor.js";
import { formatConfidence } from "../formatters.js";

export function ConfidenceBadge({ value }) {
  const tone = value >= 0.8 ? "high" : value >= 0.6 ? "medium" : "low";
  return html`<span className=${`confidence-badge confidence-${tone}`}>${formatConfidence(value)}</span>`;
}
