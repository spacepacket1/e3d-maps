import { React } from "../vendor.js";

const el = React.createElement;

export function WhitepaperPage() {
  function handleDownload() {
    const win = window.open("/whitepaper.html", "_blank");
    if (win) {
      win.addEventListener("load", () => win.print());
    }
  }

  return el("div", { className: "whitepaper-shell" },

    el("div", { className: "whitepaper-toolbar panel" },
      el("span", { className: "whitepaper-toolbar-title" }, "E3D Maps Whitepaper"),
      el("div", { className: "whitepaper-toolbar-actions" },
        el("a", {
          href: "/whitepaper.html",
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
      src: "/whitepaper.html",
      className: "whitepaper-frame",
      title: "E3D Maps Whitepaper",
    })
  );
}
