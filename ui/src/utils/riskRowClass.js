export function riskRowClass(riskLevel) {
  switch (riskLevel) {
    case "critical":
      return "row-risk-critical";
    case "high":
      return "row-risk-high";
    case "medium":
      return "row-risk-medium";
    default:
      return "row-risk-low";
  }
}
