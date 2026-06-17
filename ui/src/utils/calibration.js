import { toArray } from "../formatters.js";

// Sample-weighted aggregate of a reliability curve (array of bucket points,
// each with mean_confidence, realized_accuracy, sample_count).
export function aggregateReliabilityCurve(curve) {
  const points = toArray(curve);
  let samples = 0;
  let confidenceSum = 0;
  let accuracySum = 0;
  for (const point of points) {
    const count = Number(point?.sample_count || 0);
    if (count <= 0) continue;
    samples += count;
    confidenceSum += Number(point?.mean_confidence || 0) * count;
    accuracySum += Number(point?.realized_accuracy || 0) * count;
  }
  if (samples === 0) {
    return { samples: 0, meanConfidence: null, realizedAccuracy: null, calibrationGap: null };
  }
  const meanConfidence = confidenceSum / samples;
  const realizedAccuracy = accuracySum / samples;
  return {
    samples,
    meanConfidence,
    realizedAccuracy,
    calibrationGap: realizedAccuracy - meanConfidence,
  };
}

// Flatten the by_signal_type map into sortable rows, highest sample count first.
export function buildSignalTypeRows(bySignalType) {
  const entries = Object.entries(bySignalType || {});
  const rows = entries.map(([signalType, data]) => {
    const aggregate = aggregateReliabilityCurve(data?.reliability_curve);
    const utility = data?.utility || null;
    return {
      signalType,
      samples: aggregate.samples,
      meanConfidence: aggregate.meanConfidence,
      realizedAccuracy: aggregate.realizedAccuracy,
      calibrationGap: aggregate.calibrationGap,
      utility: utility ? Number(utility.mean) : null,
      utilitySamples: utility ? Number(utility.sample_count || 0) : 0,
      reliabilityCurve: toArray(data?.reliability_curve),
    };
  });
  rows.sort((a, b) => b.samples - a.samples || a.signalType.localeCompare(b.signalType));
  return rows;
}

// One-line plain-English read of how well-calibrated the system is. The gap is
// realized_accuracy - mean_confidence: negative means overconfident.
export function describeCalibration({ calibrationError, meanAccuracy, meanConfidence } = {}) {
  if (typeof meanAccuracy !== "number" || typeof meanConfidence !== "number") {
    return null;
  }
  const gap = meanAccuracy - meanConfidence;
  const points = Math.round(Math.abs(gap) * 100);
  if (points <= 3) {
    return "Well calibrated — realized accuracy tracks stated confidence within 3 points.";
  }
  if (gap < 0) {
    return `Overconfident — predictions realize about ${points} points below their stated confidence.`;
  }
  return `Underconfident — predictions realize about ${points} points above their stated confidence.`;
}

// Normalize either the rich calibration shape (overall/by_signal_type) or the
// legacy volume-only shape into a single view model the page can render.
export function deriveTrackRecord(calibration) {
  const overall = calibration?.overall || {};
  const bySignalType = calibration?.by_signal_type || {};
  const totalScored = Number(overall.total_scored || 0);
  const rows = buildSignalTypeRows(bySignalType);
  return {
    scored: totalScored > 0,
    totalScored,
    hitRate: typeof overall.hit_rate === "number" ? overall.hit_rate : null,
    meanAccuracy: typeof overall.mean_accuracy === "number" ? overall.mean_accuracy : null,
    meanConfidence: typeof overall.mean_confidence === "number" ? overall.mean_confidence : null,
    calibrationError: typeof overall.calibration_error === "number" ? overall.calibration_error : null,
    lookbackDays: calibration?.lookback_days ?? null,
    typesCovered: rows.length,
    rows,
    // Legacy volume context, used only for the empty-state copy.
    totalSignals: Number(calibration?.total_signals || 0),
  };
}
