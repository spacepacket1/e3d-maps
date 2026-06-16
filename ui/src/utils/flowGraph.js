export const NODE_LAYOUT = {
  stablecoins: { x: 0.08, y: 0.35, label: "Stablecoins" },
  BTC: { x: 0.08, y: 0.60, label: "BTC" },
  CEX: { x: 0.08, y: 0.80, label: "CEX" },
  cex: { x: 0.08, y: 0.80, label: "CEX" },
  binance: { x: 0.08, y: 0.10, label: "Binance" },
  ETH: { x: 0.30, y: 0.20, label: "ETH" },
  ethereum: { x: 0.30, y: 0.20, label: "ETH" },
  cross_chain_bridges: { x: 0.30, y: 0.50, label: "Bridges" },
  ETH_DEFI: { x: 0.55, y: 0.18, label: "ETH DeFi" },
  eth_defi: { x: 0.55, y: 0.18, label: "ETH DeFi" },
  LIQUID_STAKING: { x: 0.55, y: 0.38, label: "Liquid Staking" },
  BASE_DEFI: { x: 0.55, y: 0.55, label: "Base DeFi" },
  base_defi: { x: 0.55, y: 0.55, label: "Base DeFi" },
  L2_NETWORKS: { x: 0.55, y: 0.70, label: "L2 Networks" },
  PERPS: { x: 0.82, y: 0.30, label: "Perps" },
  perps: { x: 0.82, y: 0.30, label: "Perps" },
  solana: { x: 0.82, y: 0.10, label: "Solana" },
  REAL_WORLD_ASSETS: { x: 0.82, y: 0.55, label: "RWA" },
  MEME_TOKENS: { x: 0.82, y: 0.76, label: "Meme Tokens" },
  NFT_MARKETS: { x: 0.30, y: 0.80, label: "NFT Markets" },
  arbitrum: { x: 0.42, y: 0.88, label: "Arbitrum" },
  optimism: { x: 0.62, y: 0.88, label: "Optimism" },
};

export const FLOW_GRAPH_VIEWBOX_WIDTH = 1000;
export const FLOW_GRAPH_VIEWBOX_HEIGHT = 600;
export const FLOW_GRAPH_NODE_RADIUS = 28;

export function edgeColor(riskLevel) {
  switch (riskLevel) {
    case "critical":
      return "#9c3434";
    case "high":
      return "#c0561a";
    case "medium":
      return "#8d5e12";
    default:
      return "#0a7f68";
  }
}

function normalizeSignalEdge(signal) {
  return {
    origin: signal.origin,
    destination: signal.destination,
    confidence: signal.confidence,
    risk_level: signal.risk_level,
    source: "signal",
  };
}

function normalizeCrossChainEdge(route) {
  return {
    origin: route.normalized_origin,
    destination: route.normalized_destination,
    confidence: route.signal_strength,
    risk_level: route.risk_level,
    source: "cross_chain",
  };
}

export function deriveEdges(signals = [], crossChainRoutes = []) {
  const map = new Map();

  for (const edge of (Array.isArray(signals) ? signals : []).map(normalizeSignalEdge)) {
    const key = `${edge.origin}→${edge.destination}`;
    if (!NODE_LAYOUT[edge.origin] || !NODE_LAYOUT[edge.destination]) continue;
    if (edge.origin === edge.destination) continue;
    const existing = map.get(key);
    if (!existing || edge.confidence > existing.confidence) {
      map.set(key, edge);
    }
  }

  for (const edge of (Array.isArray(crossChainRoutes) ? crossChainRoutes : []).map(normalizeCrossChainEdge)) {
    const key = `${edge.origin}→${edge.destination}`;
    if (!NODE_LAYOUT[edge.origin] || !NODE_LAYOUT[edge.destination]) continue;
    if (edge.origin === edge.destination) continue;
    const existing = map.get(key);
    if (
      !existing ||
      edge.confidence > existing.confidence ||
      (edge.confidence === existing.confidence && edge.source === "cross_chain")
    ) {
      map.set(key, edge);
    }
  }
  return [...map.values()];
}

export function bezierPath(from, to) {
  const x1 = from.x * FLOW_GRAPH_VIEWBOX_WIDTH;
  const y1 = from.y * FLOW_GRAPH_VIEWBOX_HEIGHT;
  const x2 = to.x * FLOW_GRAPH_VIEWBOX_WIDTH;
  const y2 = to.y * FLOW_GRAPH_VIEWBOX_HEIGHT;
  const cx = (x1 + x2) / 2;
  return `M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`;
}

export function strokeWidth(confidence) {
  return 1.5 + confidence * 5.5;
}
