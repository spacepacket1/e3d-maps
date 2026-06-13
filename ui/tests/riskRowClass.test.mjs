import test from "node:test";
import assert from "node:assert/strict";

import { riskRowClass } from "../src/utils/riskRowClass.js";

test("riskRowClass maps critical, high, and medium risk levels to styled rows", () => {
  assert.equal(riskRowClass("critical"), "row-risk-critical");
  assert.equal(riskRowClass("high"), "row-risk-high");
  assert.equal(riskRowClass("medium"), "row-risk-medium");
});

test("riskRowClass falls back to low styling for low or unknown risk levels", () => {
  assert.equal(riskRowClass("low"), "row-risk-low");
  assert.equal(riskRowClass("unknown"), "row-risk-low");
  assert.equal(riskRowClass(undefined), "row-risk-low");
});
