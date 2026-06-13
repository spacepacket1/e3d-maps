import { html, useState } from "../vendor.js";
import { formatConfidence, titleCaseLabel } from "../formatters.js";
import {
  bezierPath,
  deriveEdges,
  edgeColor,
  FLOW_GRAPH_NODE_RADIUS,
  FLOW_GRAPH_VIEWBOX_HEIGHT,
  FLOW_GRAPH_VIEWBOX_WIDTH,
  NODE_LAYOUT,
  strokeWidth,
} from "../utils/flowGraph.js";

export function FlowGraph({ signals = [], onNodeClick }) {
  const [hovered, setHovered] = useState(null);
  const edges = deriveEdges(Array.isArray(signals) ? signals : []);
  const activeNodeIds = new Set(edges.flatMap((edge) => [edge.origin, edge.destination]));

  return html`
    <div className="flow-graph-wrap">
      <svg
        viewBox=${"0 0 " + FLOW_GRAPH_VIEWBOX_WIDTH + " " + FLOW_GRAPH_VIEWBOX_HEIGHT}
        className="flow-graph-svg"
        aria-label="Capital flow graph"
      >
        <defs>
          <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#aaa" />
          </marker>
        </defs>

        ${edges.map((edge) => {
          const from = NODE_LAYOUT[edge.origin];
          const to = NODE_LAYOUT[edge.destination];
          if (!from || !to) return null;

          const edgeId = `${edge.origin}→${edge.destination}`;
          const isHovered = hovered === edgeId;

          return html`
            <g key=${edgeId}>
              <path
                d=${bezierPath(from, to)}
                fill="none"
                stroke="transparent"
                strokeWidth="20"
                style="cursor:pointer"
                onMouseEnter=${() => setHovered(edgeId)}
                onMouseLeave=${() => setHovered(null)}
              />
              <path
                d=${bezierPath(from, to)}
                fill="none"
                stroke=${edgeColor(edge.risk_level)}
                strokeWidth=${isHovered ? strokeWidth(edge.confidence) + 2 : strokeWidth(edge.confidence)}
                strokeOpacity=${isHovered ? 0.9 : 0.55}
                style="pointer-events:none;transition:stroke-opacity 0.15s"
                markerEnd="url(#arrowhead)"
              />
              ${isHovered
                ? html`
                    <text
                      x=${((from.x + to.x) / 2) * FLOW_GRAPH_VIEWBOX_WIDTH}
                      y=${((from.y + to.y) / 2) * FLOW_GRAPH_VIEWBOX_HEIGHT - 10}
                      textAnchor="middle"
                      fontSize="11"
                      fill=${edgeColor(edge.risk_level)}
                      fontWeight="600"
                    >
                      ${formatConfidence(edge.confidence)} · ${titleCaseLabel(edge.risk_level)} risk
                    </text>
                  `
                : null}
            </g>
          `;
        })}

        ${Object.entries(NODE_LAYOUT).map(([id, pos]) => {
          const isActive = activeNodeIds.has(id);
          const cx = pos.x * FLOW_GRAPH_VIEWBOX_WIDTH;
          const cy = pos.y * FLOW_GRAPH_VIEWBOX_HEIGHT;
          return html`
            <g
              key=${id}
              style=${`cursor:${isActive && onNodeClick ? "pointer" : "default"};opacity:${isActive ? 1 : 0.3}`}
              onClick=${isActive && onNodeClick ? () => onNodeClick(id) : undefined}
            >
              <circle
                cx=${cx}
                cy=${cy}
                r=${FLOW_GRAPH_NODE_RADIUS}
                fill="rgba(255,252,245,0.92)"
                stroke=${isActive ? "#0a7f68" : "#ccc"}
                strokeWidth=${isActive ? 2 : 1}
              />
              <text
                x=${cx}
                y=${cy + 4}
                textAnchor="middle"
                fontSize="10"
                fontWeight=${isActive ? "600" : "400"}
                fill=${isActive ? "#201813" : "#aaa"}
              >
                ${pos.label}
              </text>
            </g>
          `;
        })}
      </svg>
      ${edges.length === 0
        ? html`<p className="flow-graph-empty">No flow data yet. Signal generation in progress.</p>`
        : null}
    </div>
  `;
}
