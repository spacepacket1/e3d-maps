import { React } from "../vendor.js";

const el = React.createElement;

export function Logo({ size = 48, className = "" }) {
  return el("svg", {
    width: size,
    height: size,
    viewBox: "0 0 64 64",
    fill: "none",
    xmlns: "http://www.w3.org/2000/svg",
    className,
    "aria-label": "E3D",
  },
    el("rect", { width: 64, height: 64, rx: 16, fill: "#0A0A0F" }),
    el("path", { d: "M15 44L22 20H28L23 44H15Z", fill: "#4D79FF" }),
    el("path", { d: "M28 44L35 20H41L36 44H28Z", fill: "#A5B4FC" }),
    el("path", { d: "M41 44L48 20H54L49 44H41Z", fill: "#6366F1" }),
    el("circle", { cx: 20, cy: 48, r: 3, fill: "#22D3EE" }),
    el("circle", { cx: 32, cy: 48, r: 3, fill: "#22D3EE" }),
    el("circle", { cx: 44, cy: 48, r: 3, fill: "#22D3EE" })
  );
}
