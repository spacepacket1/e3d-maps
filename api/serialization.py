from __future__ import annotations

import json


def model_to_dict(model) -> dict:
    if hasattr(model, "model_dump"):
        return _normalize_utc_suffix(model.model_dump(mode="json"))
    return _normalize_utc_suffix(json.loads(model.json()))


def _normalize_utc_suffix(value):
    if isinstance(value, dict):
        return {key: _normalize_utc_suffix(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_utc_suffix(item) for item in value]
    if isinstance(value, str) and value.endswith("+00:00"):
        return value[:-6] + "Z"
    return value
