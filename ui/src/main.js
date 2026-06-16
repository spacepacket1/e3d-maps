import { React, createRoot, html } from "./vendor.js";
import { App } from "./App.js";

// Catch errors from effects and async code — error boundaries miss these
function showOverlay(text) {
  const el = document.createElement("pre");
  el.style.cssText = "color:#9c3434;background:#fff;padding:1rem;position:fixed;top:0;left:0;right:0;z-index:9999;font-size:0.8rem;white-space:pre-wrap;max-height:60vh;overflow:auto;border-bottom:2px solid #9c3434";
  el.textContent = text;
  document.body.appendChild(el);
}

window.addEventListener("error", (e) => {
  showOverlay("JS Error: " + (e.message || "(no message)") + "\n" + (e.error?.stack || ""));
});

window.addEventListener("unhandledrejection", (e) => {
  showOverlay("Unhandled rejection: " + (e.reason?.message || String(e.reason) || "(no message)") + "\n" + (e.reason?.stack || ""));
});

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, message: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, message: error?.message || String(error) || "(no message)" };
  }

  render() {
    if (this.state.hasError) {
      return React.createElement(
        "pre",
        { style: { color: "#9c3434", background: "#fff8f8", padding: "1.5rem", whiteSpace: "pre-wrap", fontSize: "0.85rem", border: "2px solid #9c3434", margin: "1rem", borderRadius: "6px" } },
        "Render error: " + (this.state.message || "(unknown)")
      );
    }
    return this.props.children;
  }
}

const container = document.getElementById("root");
const root = createRoot(container);
root.render(html`<${ErrorBoundary}><${App} /></${ErrorBoundary}>`);
