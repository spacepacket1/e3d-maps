import { html } from "../vendor.js";
import { navigationItems, headerLinks, shouldHandleNavigation } from "../router.js";

export function Layout({ children, currentPath, navigate, counts = {} }) {
  return html`
    <div className="app-shell">
      <header className="app-header">
        <div className="app-hero">
          <div className="app-title-row">
            <div className="app-title-block">
              <img src="/e3d_logo_200.png" alt="E3D" className="app-logo" width="48" height="48" />
              <div>
                <p className="eyebrow">maps.e3d.ai</p>
                <h1>E3D Maps</h1>
              </div>
            </div>
            <div className="header-links">
              ${headerLinks.map((link) => html`
                <a
                  key=${link.href}
                  href=${link.href}
                  className=${currentPath === link.href ? "header-link is-active" : "header-link"}
                  onClick=${(e) => handleNavigate(e, link.href, navigate)}
                >
                  ${link.label}
                </a>
              `)}
            </div>
          </div>
          <p className="app-subtitle">
            Navigation intelligence for on-chain capital flows — built for agents, readable by humans.
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
                ${counts[item.href] != null ? html`<span className="nav-count">${counts[item.href]}</span>` : null}
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
  if (!shouldHandleNavigation(event, href)) return;
  event.preventDefault();
  navigate(href);
}

function isCurrentPath(currentPath, href) {
  if (href === "/") return currentPath === "/" || currentPath === "/maps";
  return currentPath === href;
}
