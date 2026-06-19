from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from api.serialization import model_to_dict
from services.maps_api_service import MapsAPIService, PaginatedResult


@dataclass(frozen=True)
class RouteResponse:
    status_code: int
    body: dict[str, Any]


def get_maps_state(service: MapsAPIService) -> RouteResponse:
    state = service.get_latest_state()
    if state is None:
        return RouteResponse(status_code=404, body={"status": "not_found", "error": "state_not_found"})

    return RouteResponse(
        status_code=200,
        body={
            "status": "ok",
            "state": model_to_dict(state),
        },
    )


def get_maps_news(service: MapsAPIService) -> RouteResponse:
    news = service.get_latest_maps_news_brief()
    if news is None:
        return RouteResponse(status_code=404, body={"status": "not_found", "error": "news_not_found"})

    payload = model_to_dict(news)
    return RouteResponse(
        status_code=200,
        body={
            "status": "ok",
            "news": {
                "headline": payload["headline"],
                "summary": payload["summary"],
                "stance": payload["stance"],
                "tags": payload["tags"],
                "generated_at": payload["created_at"],
            },
        },
    )


def get_maps_cross_chain(service: MapsAPIService) -> RouteResponse:
    cross_chain = service.get_latest_cross_chain_activity_state()
    if cross_chain is None:
        return RouteResponse(
            status_code=404,
            body={"status": "not_found", "error": "cross_chain_not_found"},
        )

    payload = model_to_dict(cross_chain)
    return RouteResponse(
        status_code=200,
        body={
            "status": "ok",
            "cross_chain": {
                "market_bias": payload["market_bias"],
                "top_routes": payload["top_routes"],
                "active_hazards": payload["active_hazards"],
                "active_congestion": payload["active_congestion"],
                "top_destinations": payload["top_destinations"],
                "ethereum_outbound_routes": payload["ethereum_outbound_routes"],
                "ethereum_inbound_routes": payload["ethereum_inbound_routes"],
                "created_at": payload["created_at"],
            },
        },
    )


def get_maps_signals(
    service: MapsAPIService,
    *,
    signal_type: str | None = None,
    asset: str | None = None,
    chain: str | None = None,
    time_horizon_hours: int | None = None,
    min_confidence: float | None = None,
    limit: int = 50,
    offset: int = 0,
) -> RouteResponse:
    result = service.list_signals(
        signal_type=signal_type,
        asset=asset,
        chain=chain,
        time_horizon_hours=time_horizon_hours,
        min_confidence=min_confidence,
        limit=limit,
        offset=offset,
    )
    return RouteResponse(status_code=200, body=_paginated_body(key="signals", result=result))


def get_maps_signal(service: MapsAPIService, signal_id: str) -> RouteResponse:
    signal = service.get_signal(signal_id)
    if signal is None:
        return RouteResponse(status_code=404, body={"status": "not_found", "error": "signal_not_found"})

    return RouteResponse(
        status_code=200,
        body={
            "status": "ok",
            "signal": model_to_dict(signal),
        },
    )


def get_maps_routes(
    service: MapsAPIService,
    *,
    limit: int = 50,
    offset: int = 0,
) -> RouteResponse:
    result = service.list_routes(limit=limit, offset=offset)
    return RouteResponse(status_code=200, body=_paginated_body(key="routes", result=result))


def get_maps_hazards(
    service: MapsAPIService,
    *,
    limit: int = 50,
    offset: int = 0,
) -> RouteResponse:
    result = service.list_hazards(limit=limit, offset=offset)
    return RouteResponse(status_code=200, body=_paginated_body(key="hazards", result=result))


def get_maps_recommendations(
    service: MapsAPIService,
    *,
    objective: str | None = None,
    asset: str | None = None,
    address: str | None = None,
    story_type: str | None = None,
    max_results: int = 10,
) -> RouteResponse:
    recommendations = service.get_recommendations(
        objective=objective,
        asset=asset,
        address=address,
        story_type=story_type,
        max_results=max_results,
    )
    return RouteResponse(
        status_code=200,
        body={
            "generatedAt": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "objective": objective,
            "recommendations": [model_to_dict(r) for r in recommendations],
        },
    )


def get_maps_graph(service: MapsAPIService) -> RouteResponse:
    data = service.get_latest_flow_graph()
    if data is None:
        return RouteResponse(
            status_code=404,
            body={"status": "not_found", "error": "no_flow_graph_snapshot"},
        )
    return RouteResponse(status_code=200, body={"status": "ok", "graph": data})


def get_maps_graph_around(service: MapsAPIService, node: str) -> RouteResponse:
    data = service.get_flow_graph_around(node)
    return RouteResponse(status_code=200, body={"status": "ok", **data})


def get_maps_predictions(
    service: MapsAPIService,
    *,
    limit: int = 50,
    offset: int = 0,
) -> RouteResponse:
    result = service.list_predictions(limit=limit, offset=offset)
    return RouteResponse(status_code=200, body=_paginated_body(key="predictions", result=result))


def get_maps_notable(
    service: MapsAPIService,
    *,
    min_score: int = 0,
    since: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> RouteResponse:
    result = service.get_notable_signals(
        min_score=min_score,
        since=since,
        limit=limit,
        offset=offset,
    )
    return RouteResponse(status_code=200, body=_paginated_body(key="notable", result=result))


def get_maps_destinations(
    service: MapsAPIService,
    *,
    limit: int = 50,
    offset: int = 0,
) -> RouteResponse:
    result = service.list_destinations(limit=limit, offset=offset)
    return RouteResponse(status_code=200, body=_paginated_body(key="destinations", result=result))


def get_maps_congestion(
    service: MapsAPIService,
    *,
    limit: int = 50,
    offset: int = 0,
) -> RouteResponse:
    result = service.list_congestion(limit=limit, offset=offset)
    return RouteResponse(status_code=200, body=_paginated_body(key="congestion", result=result))


def get_maps_calibration(
    service: MapsAPIService,
    *,
    lookback_days: int = 30,
) -> RouteResponse:
    data = service.get_calibration(lookback_days=lookback_days)
    return RouteResponse(
        status_code=200,
        body={"status": "ok", "calibration": data},
    )


def post_maps_outcome(service: MapsAPIService, payload: dict[str, Any]) -> RouteResponse:
    """Ingest a consumer attestation (downstream agent's action report).

    Defines the contract for the public POST /api/maps/outcomes endpoint; the
    matching Express route in the main e3d server is a deferred cross-repo step.
    """
    try:
        attestation = service.ingest_consumer_attestation(payload)
    except ValidationError as exc:
        return RouteResponse(
            status_code=400,
            body={"status": "invalid", "error": "invalid_attestation", "detail": exc.errors()},
        )
    return RouteResponse(
        status_code=201,
        body={"status": "ok", "attestation": model_to_dict(attestation)},
    )


def _paginated_body(*, key: str, result: PaginatedResult[Any]) -> dict[str, Any]:
    return {
        "status": "ok",
        key: [item if isinstance(item, dict) else model_to_dict(item) for item in result.items],
        "pagination": {
            "limit": result.limit,
            "offset": result.offset,
            "count": len(result.items),
            "has_more": result.has_more,
        },
    }
