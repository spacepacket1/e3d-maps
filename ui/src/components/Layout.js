import { html } from "../vendor.js";
import { navigationItems, shouldHandleNavigation } from "../router.js";

export function Layout({ children, currentPath, navigate }) {
  return html`
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">maps.e3d.ai</p>
          <h1>E3D Maps</h1>
          <p className="app-subtitle">
            Navigation intelligence for capital flows, hazards, and congestion.
          </p>
        </div>
        <nav className="app-nav" aria-label="Primary">
          ${navigationItems.map(
            (item) => html`
              <a
                key=${item.href}
                href=${item.href}
                className=${isCurrentPath(currentPath, item.href) ? "nav-link is-active" : "nav-link"}
                onClick=${(event) => handleNavigate(event, item.href, navigate)}
              >
                ${item.label}
              </a>
            `
          )}
        </nav>
      </header>
      <main className="page-content">${children}</main>
    </div>
  `;
}

function handleNavigate(event, href, navigate) {
  if (!shouldHandleNavigation(event, href)) {
    return;
  }
  event.preventDefault();
  navigate(href);
}

function isCurrentPath(currentPath, href) {
  if (href === "/") {
    return currentPath === "/" || currentPath === "/maps";
  }
  return currentPath === href;
}
