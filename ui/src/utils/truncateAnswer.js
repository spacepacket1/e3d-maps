export function truncateAnswer(text) {
  if (!text) return "—";
  return text.length > 120 ? text.slice(0, 120) + "…" : text;
}
