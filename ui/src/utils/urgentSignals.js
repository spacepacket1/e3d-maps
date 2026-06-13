export function dedupeUrgentSignals(signalGroups) {
  const urgentSignals = signalGroups.flat().filter(
    (signal) =>
      signal &&
      (signal.risk_level === "critical" || signal.risk_level === "high") &&
      signal.confidence >= 0.65
  );

  const seen = new Set();
  return urgentSignals.filter((signal) => {
    if (seen.has(signal.id)) {
      return false;
    }
    seen.add(signal.id);
    return true;
  });
}
