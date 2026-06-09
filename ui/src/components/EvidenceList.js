import { html } from "../vendor.js";

export function EvidenceList({ evidence }) {
  if (!evidence.length) {
    return html`<p className="empty-copy">No evidence was attached to this signal.</p>`;
  }

  return html`
    <ul className="detail-list">
      ${evidence.map(
        (item) => html`
          <li key=${item.id} id=${`evidence-${item.id}`}>
            <strong>${item.type}</strong>
            <span className="detail-id">${item.id}</span>
            <p>${item.summary}</p>
          </li>
        `
      )}
    </ul>
  `;
}
