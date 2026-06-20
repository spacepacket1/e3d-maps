import { React } from "../vendor.js";

const el = React.createElement;

export function ArchitecturePage() {
  function handleDownload() {
    const win = window.open("/architecture.html", "_blank");
    if (win) {
      win.addEventListener("load", () => win.print());
    }
  }

  return el("div", { className: "whitepaper-shell" },

    el("div", { className: "whitepaper-toolbar panel" },
      el("span", { className: "whitepaper-toolbar-title" }, "E3D Ecosystem Architecture"),
      el("div", { className: "whitepaper-toolbar-actions" },
        el("a", {
          href: "/architecture.html",
          target: "_blank",
          rel: "noopener noreferrer",
          className: "btn-secondary",
        }, "Open in new tab"),
        el("button", {
          className: "btn-primary",
          onClick: handleDownload,
        }, "Download PDF"),
      )
    ),

    el("iframe", {
      src: "/architecture.html",
      className: "whitepaper-frame",
      title: "E3D Ecosystem Architecture",
    })
  );
}
