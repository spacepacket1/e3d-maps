import test from "node:test";
import assert from "node:assert/strict";

import { dedupeUrgentSignals } from "../src/utils/urgentSignals.js";

test("dedupeUrgentSignals keeps only high-confidence high and critical signals", () => {
  const signals = dedupeUrgentSignals([
    [
      { id: "critical-1", risk_level: "critical", confidence: 0.9 },
      { id: "high-low-confidence", risk_level: "high", confidence: 0.5 },
    ],
    [
      { id: "high-1", risk_level: "high", confidence: 0.65 },
      { id: "medium-1", risk_level: "medium", confidence: 0.95 },
    ],
  ]);

  assert.deepEqual(
    signals.map((signal) => signal.id),
    ["critical-1", "high-1"]
  );
});

test("dedupeUrgentSignals removes duplicate ids and returns an empty list when none qualify", () => {
  const signals = dedupeUrgentSignals([
    [
      { id: "dup-1", risk_level: "critical", confidence: 0.8 },
      { id: "dup-1", risk_level: "critical", confidence: 0.8 },
    ],
    [
      { id: "low-1", risk_level: "low", confidence: 0.9 },
      { id: "high-2", risk_level: "high", confidence: 0.64 },
    ],
  ]);

  assert.deepEqual(
    signals.map((signal) => signal.id),
    ["dup-1"]
  );
  assert.deepEqual(dedupeUrgentSignals([[{ id: "low-2", risk_level: "low", confidence: 0.99 }]]), []);
});
