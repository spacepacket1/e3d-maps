from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.navigation_signal import NavigationSignal
from schemas.route_prediction import RoutePrediction
from schemas.story_type_definition import StoryTypeDefinition
from tests.unit.payloads import (
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
