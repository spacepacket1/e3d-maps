import { html } from "../vendor.js";

export function NotFoundPage() {
  return html`
    <section className="page-header">
      <div>
        <p className="eyebrow">Not Found</p>
        <h2>Page not found</h2>
      </div>
    </section>
    <p className="empty-copy">The requested Maps page does not exist.</p>
  `;
}
