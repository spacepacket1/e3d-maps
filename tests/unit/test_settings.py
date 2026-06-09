from __future__ import annotations

from settings import MapsRuntimeSettings


def test_runtime_settings_use_existing_defaults_and_env_fallbacks():
    settings = MapsRuntimeSettings.from_env(
        {
            "MAPS_DEFAULT_MODEL": "qwen2.5",
            "MAPS_DEFAULT_ADAPTER": "base-v0",
        }
    )

    assert settings.qwen_base_url == "http://127.0.0.1:5050"
    assert settings.qwen_completions_path == "/v1/chat/completions"
    assert settings.qwen_model == "qwen2.5"
    assert settings.maps_adapter_name == "base-v0"
    assert settings.maps_adapter_path == "./adapters_maps_v1"
    assert settings.maps_enable_adapter_loading is False


def test_runtime_settings_prefer_llm_env_vars_over_qwen_aliases():
    settings = MapsRuntimeSettings.from_env(
        {
            "LLM_BASE_URL": "http://llm.internal:5050",
            "LLM_MODEL": "mlx-community/Qwen2.5-14B-Instruct-4bit",
            "QWEN_BASE_URL": "http://should-be-ignored:8000",
            "MAPS_DEFAULT_MODEL": "should-be-ignored",
        }
    )

    assert settings.qwen_base_url == "http://llm.internal:5050"
    assert settings.qwen_model == "mlx-community/Qwen2.5-14B-Instruct-4bit"


def test_runtime_settings_prefer_explicit_adapter_env_values():
    settings = MapsRuntimeSettings.from_env(
        {
            "QWEN_BASE_URL": "http://qwen.internal:8080/",
            "QWEN_COMPLETIONS_PATH": "v1/chat/completions",
            "QWEN_API_KEY": "secret",
            "MAPS_DEFAULT_MODEL": "qwen-maps",
            "MAPS_DEFAULT_ADAPTER": "base-v0",
            "MAPS_ADAPTER_NAME": "maps-v0.1",
            "MAPS_ADAPTER_PATH": "/models/maps-v0.1",
            "MAPS_ENABLE_ADAPTER_LOADING": "true",
        }
    )

    assert settings.qwen_base_url == "http://qwen.internal:8080"
    assert settings.qwen_completions_path == "v1/chat/completions"
    assert settings.qwen_api_key == "secret"
    assert settings.qwen_model == "qwen-maps"
    assert settings.maps_adapter_name == "maps-v0.1"
    assert settings.maps_adapter_path == "/models/maps-v0.1"
    assert settings.maps_enable_adapter_loading is True
