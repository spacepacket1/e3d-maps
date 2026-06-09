import { createRoot, html } from "./vendor.js";
import { App } from "./App.js";

const container = document.getElementById("root");
const root = createRoot(container);

root.render(html`<${App} />`);
