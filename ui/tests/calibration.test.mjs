import test from "node:test";
import assert from "node:assert/strict";

import {
  aggregateReliabilityCurve,
  buildSignalTypeRows,
  describeCalibration,
  deriveTrackRecord,
} from "../src/utils/calibration.js";

test("aggregateReliabilityCurve sample-weights confidence and accuracy", () => {
  const agg = aggregateReliabilityCurve([
    { mean_confidence: 0.6, realized_accuracy: 0.5, sample_count: 10 },
    { mean_confidence: 0.8, realized_accuracy: 0.9, sample_count: 30 },
  ]);
  assert.equal(agg.samples, 40);
  // weighted confidence = (0.6*10 + 0.8*30)/40 = 0.75
  assert.ok(Math.abs(agg.meanConfidence - 0.75) < 1e-9);
  // weighted accuracy = (0.5*10 + 0.9*30)/40 = 0.8
  assert.ok(Math.abs(agg.realizedAccuracy - 0.8) < 1e-9);
  assert.ok(Math.abs(agg.calibrationGap - 0.05) < 1e-9);
});

test("aggregateReliabilityCurve handles empty input", () => {
  const agg = aggregateReliabilityCurve([]);
  assert.deepEqual(agg, { samples: 0, meanConfidence: null, realizedAccuracy: null, calibrationGap: null });
});

test("buildSignalTypeRows sorts by sample count and attaches utility", () => {
  const rows = buildSignalTypeRows({
    capital_migration: {
      reliability_curve: [{ mean_confidence: 0.7, realized_accuracy: 0.7, sample_count: 5 }],
      utility: { mean: 0.5, sample_count: 5 },
    },
    destination_prediction: {
      reliability_curve: [{ mean_confidence: 0.8, realized_accuracy: 0.6, sample_count: 50 }],
      utility: null,
    },
  });
  assert.equal(rows.length, 2);
  assert.equal(rows[0].signalType, "destination_prediction"); // 50 > 5
  assert.equal(rows[0].samples, 50);
  assert.equal(rows[0].utility, null);
  assert.equal(rows[1].utility, 0.5);
});

test("describeCalibration flags overconfidence and good calibration", () => {
  assert.match(describeCalibration({ meanAccuracy: 0.6, meanConfidence: 0.8 }), /Overconfident/);
  assert.match(describeCalibration({ meanAccuracy: 0.81, meanConfidence: 0.8 }), /Well calibrated/);
  assert.match(describeCalibration({ meanAccuracy: 0.85, meanConfidence: 0.7 }), /Underconfident/);
  assert.equal(describeCalibration({ meanAccuracy: null, meanConfidence: 0.7 }), null);
});

test("deriveTrackRecord marks unscored when no outcomes exist", () => {
  const record = deriveTrackRecord({ overall: { total_scored: 0 }, by_signal_type: {} });
  assert.equal(record.scored, false);
  assert.equal(record.totalScored, 0);
  assert.deepEqual(record.rows, []);
});

test("deriveTrackRecord surfaces overall metrics and rows when scored", () => {
  const record = deriveTrackRecord({
    lookback_days: 30,
    overall: { hit_rate: 0.62, mean_accuracy: 0.66, mean_confidence: 0.7, calibration_error: 0.04, total_scored: 120 },
    by_signal_type: {
      capital_migration: { reliability_curve: [{ mean_confidence: 0.7, realized_accuracy: 0.66, sample_count: 120 }] },
    },
  });
  assert.equal(record.scored, true);
  assert.equal(record.totalScored, 120);
  assert.equal(record.hitRate, 0.62);
  assert.equal(record.typesCovered, 1);
  assert.equal(record.rows[0].samples, 120);
});

test("deriveTrackRecord tolerates the legacy volume-only shape", () => {
  const record = deriveTrackRecord({ total_signals: 6510, signals_last_24h: 370, avg_confidence: 0.63 });
  assert.equal(record.scored, false);
  assert.equal(record.totalSignals, 6510);
  assert.deepEqual(record.rows, []);
});
