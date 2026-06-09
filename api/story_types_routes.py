from __future__ import annotations

from api.serialization import model_to_dict
from services.maps_api_service import MapsAPIService

from api.maps_routes import RouteResponse


def get_story_types(
    service: MapsAPIService,
    *,
    limit: int = 100,
    offset: int = 0,
) -> RouteResponse:
    result = service.list_story_types(limit=limit, offset=offset)
    return RouteResponse(
        status_code=200,
        body={
            "status": "ok",
            "story_types": [model_to_dict(item) for item in result.items],
            "pagination": {
                "limit": result.limit,
                "offset": result.offset,
                "count": len(result.items),
                "has_more": result.has_more,
            },
        },
    )


def get_story_type(service: MapsAPIService, story_type: str) -> RouteResponse:
    definition = service.get_story_type(story_type)
    if definition is None:
        return RouteResponse(
            status_code=404,
            body={"status": "not_found", "error": "story_type_not_found"},
        )

    return RouteResponse(
        status_code=200,
        body={
            "status": "ok",
            "story_type": model_to_dict(definition),
        },
    )
