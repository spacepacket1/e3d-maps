from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.navigation_signal import NavigationSignal
from schemas.route_prediction import RoutePrediction
from schemas.story_type_definition import StoryTypeDefinition
from schemas import CrossChainActivityState, MapsNewsBrief
from tests.unit.payloads import (
    cross_chain_activity_state_payload,
    maps_news_brief_payload,
    navigation_signal_payload,
    route_prediction_payload,
    story_type_definition_payload,
)


def test_navigation_signal_accepts_valid_payload():
    signal = NavigationSignal.model_validate(navigation_signal_payload())
    assert signal.signal_type == "capital_migration"


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_navigation_signal_rejects_invalid_confidence(confidence):
    with pytest.raises(ValidationError):
        NavigationSignal.model_validate(navigation_signal_payload(confidence=confidence))


def test_navigation_signal_rejects_missing_required_fields():
    payload = navigation_signal_payload()
    payload.pop("question")

    with pytest.raises(ValidationError):
        NavigationSignal.model_validate(payload)


def test_navigation_signal_rejects_unknown_signal_type_by_default():
    with pytest.raises(ValidationError):
        NavigationSignal.model_validate(
            navigation_signal_payload(signal_type="experimental_signal")
        )


def test_navigation_signal_can_allow_unknown_signal_type_when_explicitly_configured():
    signal = NavigationSignal.model_validate(
        navigation_signal_payload(signal_type="experimental_signal"),
        context={"allow_unknown_signal_types": True},
    )

    assert signal.signal_type == "experimental_signal"


def test_route_prediction_rejects_unknown_route_type_by_default():
    with pytest.raises(ValidationError):
        RoutePrediction.model_validate(route_prediction_payload(route_type="unknown_route"))


def test_route_prediction_can_allow_unknown_route_type_when_explicitly_configured():
    route = RoutePrediction.model_validate(
        route_prediction_payload(route_type="unknown_route"),
        context={"allow_unknown_signal_types": True},
    )

    assert route.route_type == "unknown_route"


def test_story_type_definition_accepts_valid_payload():
    definition = StoryTypeDefinition.model_validate(story_type_definition_payload())
    assert definition.story_type == "capital_migration"


def test_story_type_definition_rejects_unknown_related_signal_type_by_default():
    with pytest.raises(ValidationError):
        StoryTypeDefinition.model_validate(
            story_type_definition_payload(
                related_navigation_signal_types=["capital_migration", "experimental_signal"]
            )
        )


def test_story_type_definition_can_allow_unknown_related_signal_types():
    definition = StoryTypeDefinition.model_validate(
        story_type_definition_payload(
            related_navigation_signal_types=["capital_migration", "experimental_signal"]
        ),
        context={"allow_unknown_signal_types": True},
    )

    assert definition.related_navigation_signal_types == [
        "capital_migration",
        "experimental_signal",
    ]


def test_maps_news_brief_accepts_valid_payload_and_defaults_scope():
    brief = MapsNewsBrief.model_validate(maps_news_brief_payload(scope="global"))
    assert brief.scope == "global"
    assert brief.created_by_agent == "maps_news_agent"


def test_maps_news_brief_rejects_empty_headline():
    with pytest.raises(ValidationError):
        MapsNewsBrief.model_validate(maps_news_brief_payload(headline="   "))


def test_maps_news_brief_rejects_short_headline_and_multi_paragraph_summary():
    with pytest.raises(ValidationError):
        MapsNewsBrief.model_validate(
            maps_news_brief_payload(
                summary=(
                    "Flows remain active across the strongest routes and the read is still coherent enough "
                    "to pass the minimum length requirement for a single summary paragraph.\n\n"
                    "A second paragraph should fail validation."
                )
            )
        )


def test_cross_chain_activity_state_accepts_valid_payload_and_defaults_scope():
    state = CrossChainActivityState.model_validate(cross_chain_activity_state_payload())
    assert state.scope == "global"
    assert state.created_by_agent == "cross_chain_activity_assembler"


def test_cross_chain_activity_state_rejects_too_many_top_routes():
    payload = cross_chain_activity_state_payload(
        top_routes=[cross_chain_activity_state_payload()["top_routes"][0] for _ in range(7)]
    )

    with pytest.raises(ValidationError):
        CrossChainActivityState.model_validate(payload)
