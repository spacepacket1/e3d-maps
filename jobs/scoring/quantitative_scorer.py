"""Quantitative scorer for NavigationSignal predictions (MAPS-1201).

This scorer measures whether a prediction realized in *quantitative* terms —
net flow magnitude and direction derived from raw exchange-flow and stablecoin
series — without reading story objects.  It is statistically independent of the
heuristic scorer in score_pending_predictions.py, which uses story presence as
its primary evidence.  The independence is intentional: both scorers sharing the
same evidence source would defeat the purpose of dual-scoring.

Inputs
------
exchange_flows : list of exchange-flow dicts with at minimum:
    - "net_flow"   : float  (positive = inflow to the destination, negative = outflow)
    - "direction"  : str    ("inflow" | "outflow" | "neutral" | "mixed")
    - "magnitude"  : str    ("low" | "moderate" | "high") — optional, derived if absent

stablecoin_series : list of stablecoin-activity dicts with at minimum:
    - "net_flow"   : float
    - "direction"  : str

Both lists must contain only records that fall *within* the evaluation window
(after signal.created_at, before created_at + time_horizon_hours).  The caller
is responsible for time-filtering; this module does not touch timestamps.

Returns
-------
QuantitativeScore dataclass:
    realized_score  : float in [0, 1]
    measured_deltas : dict  — raw evidence for audit / notes
    method          : "quantitative"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class QuantitativeScore:
    realized_score: float  # [0, 1]
    measured_deltas: dict[str, Any] = field(default_factory=dict)
    method: str = "quantitative"


def score(
    *,
    predicted_direction: str,  # "inflow" | "outflow" | "neutral" | "mixed"
    exchange_flows: list[dict[str, Any]],
    stablecoin_series: list[dict[str, Any]],
    min_flow_threshold: float = 0.0,
) -> QuantitativeScore:
    """Compute a realized_score in [0, 1] from quantitative series alone.

    Scoring logic
    -------------
    Each series (exchange flows, stablecoin) is assessed independently:
      +0.45  if net flow direction matches predicted_direction
      +0.0   if direction is neutral or no data
      -0.20  if net flow direction contradicts predicted_direction

    The two series are weighted 0.6 / 0.4 (exchange flows carry more weight
    as they directly reflect movement at venues).  The result is clamped to
    [0, 1].  A score of 0.5 means neither confirmation nor contradiction.
    """
    exchange_result = _assess_series(
        predicted_direction=predicted_direction,
        series=exchange_flows,
        series_name="exchange_flows",
        min_threshold=min_flow_threshold,
    )
    stablecoin_result = _assess_series(
        predicted_direction=predicted_direction,
        series=stablecoin_series,
        series_name="stablecoin_series",
        min_threshold=min_flow_threshold,
    )

    # Weighted blend: 0.6 exchange, 0.4 stablecoin.
    # Base score is 0.5 (no-signal neutral) scaled by each component.
    raw = (
        0.5
        + 0.6 * exchange_result["adjustment"]
        + 0.4 * stablecoin_result["adjustment"]
    )
    realized_score = max(0.0, min(1.0, raw))

    deltas: dict[str, Any] = {
        "exchange_flows": exchange_result,
        "stablecoin_series": stablecoin_result,
        "predicted_direction": predicted_direction,
        "realized_score": realized_score,
    }
    return QuantitativeScore(realized_score=realized_score, measured_deltas=deltas)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _assess_series(
    *,
    predicted_direction: str,
    series: list[dict[str, Any]],
    series_name: str,
    min_threshold: float,
) -> dict[str, Any]:
    """Aggregate a series and return an adjustment in [-0.5, +0.5]."""
    if not series:
        return {
            "series": series_name,
            "record_count": 0,
            "net_flow_sum": 0.0,
            "dominant_direction": "neutral",
            "matches_prediction": None,
            "adjustment": 0.0,
        }

    net_sum = sum(float(r.get("net_flow", 0.0)) for r in series)
    direction_counts: dict[str, int] = {}
    for r in series:
        d = str(r.get("direction", "neutral")).lower()
        direction_counts[d] = direction_counts.get(d, 0) + 1

    dominant = max(direction_counts, key=lambda k: direction_counts[k])

    # Ignore sub-threshold net flows — treat as neutral.
    if abs(net_sum) <= min_threshold:
        dominant = "neutral"

    matches = _direction_matches(predicted=predicted_direction, observed=dominant)
    adjustment = 0.45 if matches is True else (-0.20 if matches is False else 0.0)

    return {
        "series": series_name,
        "record_count": len(series),
        "net_flow_sum": net_sum,
        "dominant_direction": dominant,
        "direction_counts": direction_counts,
        "matches_prediction": matches,
        "adjustment": adjustment,
    }


def _direction_matches(*, predicted: str, observed: str) -> bool | None:
    """True = match, False = contradiction, None = ambiguous/neutral."""
    if observed in ("neutral", "mixed"):
        return None
    if predicted in ("neutral", "mixed"):
        return None
    return observed == predicted
