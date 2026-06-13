import test from "node:test";
import assert from "node:assert/strict";

import {
  bezierPath,
  deriveEdges,
  edgeColor,
  NODE_LAYOUT,
  strokeWidth,
} from "../src/utils/flowGraph.js";

test("deriveEdges keeps only the highest-confidence signal per origin-destination pair", () => {
  const edges = deriveEdges([
    { id: "weak", origin: "stablecoins", destination: "ETH_DEFI", confidence: 0.42, risk_level: "low" },
    { id: "strong", origin: "stablecoins", destination: "ETH_DEFI", confidence: 0.87, risk_level: "high" },
    { id: "other", origin: "ETH", destination: "PERPS", confidence: 0.55, risk_level: "medium" },
  ]);

  assert.deepEqual(
    edges.map((edge) => edge.id),
    ["strong", "other"]
  );
});

test("deriveEdges ignores invalid and self-referential node pairs", () => {
  const edges = deriveEdges([
    { id: "self", origin: "ETH", destination: "ETH", confidence: 0.8, risk_level: "medium" },
    { id: "unknown-origin", origin: "SOL", destination: "PERPS", confidence: 0.8, risk_level: "high" },
    { id: "unknown-dest", origin: "ETH", destination: "SOL", confidence: 0.8, risk_level: "high" },
  ]);

  assert.deepEqual(edges, []);
});

test("bezierPath uses the configured SVG layout coordinates", () => {
  assert.equal(
    bezierPath(NODE_LAYOUT.stablecoins, NODE_LAYOUT.PERPS),
    "M 80 210 C 450 210, 450 180, 820 180"
  );
});

test("strokeWidth and edgeColor map confidence and risk predictably", () => {
  assert.equal(strokeWidth(0), 1.5);
  assert.equal(strokeWidth(1), 7);
  assert.equal(edgeColor("critical"), "#9c3434");
  assert.equal(edgeColor("high"), "#c0561a");
  assert.equal(edgeColor("medium"), "#8d5e12");
  assert.equal(edgeColor("low"), "#0a7f68");
});
