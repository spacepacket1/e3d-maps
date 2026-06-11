from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

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


def get_maps_predictions(
    service: MapsAPIService,
    *,
    limit: int = 50,
    offset: int = 0,
) -> RouteResponse:
    result = service.list_predictions(limit=limit, offset=offset)
    return RouteResponse(status_code=200, body=_paginated_body(key="predictions", result=result))


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


def _paginated_body(*, key: str, result: PaginatedResult[Any]) -> dict[str, Any]:
    return {
        "status": "ok",
        key: [model_to_dict(item) for item in result.items],
        "pagination": {
            "limit": result.limit,
            "offset": result.offset,
            "count": len(result.items),
            "has_more": result.has_more,
        },
    }
