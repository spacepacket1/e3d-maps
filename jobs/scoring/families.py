"""Signal-family classification for outcome scoring.

Different NavigationSignal types realize in different ways, so they cannot share
one scoring rubric without producing dishonest labels. This module groups the
signal types into families, each of which gets a dedicated dual-witness scorer in
``jobs/score_pending_predictions.py``:

- ``FLOW``       — directional capital-movement predictions. Realization = net
  flow moved origin→destination in the predicted direction/magnitude.
- ``HAZARD``     — route danger / closure predictions. Realization = adverse
  evidence materialized (danger stories + capital fleeing the route).
- ``CONGESTION`` — crowding / over-concentration predictions. Realization =
  activity around the zone persisted rather than dissipating.
- ``UNSCORABLE`` — second-derivative types (``narrative_acceleration``,
  ``agent_swarm_formation``) that the v1 spec (§3.6) defers to v1.1. They need a
  historical velocity baseline / wallet-cluster context the scorer does not have.
  They are intentionally left unscored rather than given a fabricated label,
  because a wrong label is worse than no label in a compounding training set.
"""

from __future__ import annotations

from enum import StrEnum


class SignalFamily(StrEnum):
    FLOW = "flow"
    HAZARD = "hazard"
    CONGESTION = "congestion"
    UNSCORABLE = "unscorable"


FLOW_SIGNAL_TYPES: frozenset[str] = frozenset(
    {
        "capital_migration",
        "destination_prediction",
        "liquidity_forecast",
        "route_emergence",
        "capital_conviction",
    }
)

HAZARD_SIGNAL_TYPES: frozenset[str] = frozenset({"route_hazard", "route_closure"})

CONGESTION_SIGNAL_TYPES: frozenset[str] = frozenset({"congestion_formation"})

# Deferred to v1.1 per spec §3.6 — require baselines the scorer cannot supply yet.
UNSCORABLE_SIGNAL_TYPES: frozenset[str] = frozenset(
    {"narrative_acceleration", "agent_swarm_formation"}
)

# Every signal type that has an honest realization measure today.
SUPPORTED_SIGNAL_TYPES: frozenset[str] = (
    FLOW_SIGNAL_TYPES | HAZARD_SIGNAL_TYPES | CONGESTION_SIGNAL_TYPES
)

_FAMILY_BY_TYPE: dict[str, SignalFamily] = {
    **{signal_type: SignalFamily.FLOW for signal_type in FLOW_SIGNAL_TYPES},
    **{signal_type: SignalFamily.HAZARD for signal_type in HAZARD_SIGNAL_TYPES},
    **{signal_type: SignalFamily.CONGESTION for signal_type in CONGESTION_SIGNAL_TYPES},
    **{signal_type: SignalFamily.UNSCORABLE for signal_type in UNSCORABLE_SIGNAL_TYPES},
}


def family_for(signal_type: str | None) -> SignalFamily:
    """Return the scoring family for a signal type.

    Unknown types default to ``UNSCORABLE`` so a new signal type can never be
    silently force-fit into an inappropriate rubric.
    """
    if not signal_type:
        return SignalFamily.UNSCORABLE
    return _FAMILY_BY_TYPE.get(signal_type, SignalFamily.UNSCORABLE)
