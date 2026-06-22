from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass(frozen=True)
class MapsRuntimeSettings:
    # LLM_BASE_URL is the canonical env var, shared with the trading floor.
    # QWEN_BASE_URL is accepted as a fallback for backward compatibility.
    qwen_base_url: str = "http://127.0.0.1:5050"
    qwen_completions_path: str = "/v1/chat/completions"
    qwen_api_key: str | None = None
    # LLM_MODEL is the canonical env var, shared with the trading floor.
    qwen_model: str = "mlx-community/Qwen2.5-14B-Instruct-4bit"
    maps_adapter_name: str = "base-v0"
    # MAPS_ADAPTER_PATH is sent as X-Adapter-Path header per request, matching trading floor.
    maps_adapter_path: str = "./adapters_maps_v1"
    maps_enable_adapter_loading: bool = False
    qwen_timeout: float = 60.0

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "MapsRuntimeSettings":
        env = environ if environ is not None else os.environ
        adapter_name = env.get("MAPS_ADAPTER_NAME") or env.get("MAPS_DEFAULT_ADAPTER") or "base-v0"
        _adapter_path_env = env.get("MAPS_ADAPTER_PATH")
        adapter_path = _adapter_path_env if _adapter_path_env is not None else "./adapters_maps_v1"
        api_key = env.get("QWEN_API_KEY") or None
        base_url = env.get("LLM_BASE_URL") or env.get("QWEN_BASE_URL") or "http://127.0.0.1:5050"
        model = env.get("LLM_MODEL") or env.get("MAPS_DEFAULT_MODEL") or "mlx-community/Qwen2.5-14B-Instruct-4bit"

        return cls(
            qwen_base_url=base_url.rstrip("/"),
            qwen_completions_path=env.get("QWEN_COMPLETIONS_PATH") or "/v1/chat/completions",
            qwen_api_key=api_key,
            qwen_model=model,
            maps_adapter_name=adapter_name,
            maps_adapter_path=adapter_path,
            maps_enable_adapter_loading=_parse_bool(env.get("MAPS_ENABLE_ADAPTER_LOADING")),
            qwen_timeout=float(env.get("QWEN_TIMEOUT") or 60.0),
        )


@dataclass(frozen=True)
class MapsRunnerSettings:
    e3d_base_url: str = "https://e3d.ai"
    e3d_api_prefix: str = "/api"
    e3d_api_key: str | None = None
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_database: str = "default"
    clickhouse_username: str = "default"
    clickhouse_password: str = ""
    clickhouse_secure: bool = False
    clickhouse_timeout: float = 10.0
    question_queue_path: str | None = None
    run_interval_seconds: int = 300
    scoring_interval_seconds: int = 1800
    utility_interval_seconds: int = 3600
    export_interval_seconds: int = 86400
    flow_graph_interval_seconds: int = 300
    traffic_state_interval_seconds: int = 300
    cross_chain_activity_interval_seconds: int = 300
    maps_news_interval_seconds: int = 300
    watch_interval_seconds: int = 300
    query_demand_interval_seconds: int = 900
    reflexivity_interval_seconds: int = 600
    narrative_velocity_interval_seconds: int = 300
    anomaly_monitor_interval_seconds: int = 300
    route_health_interval_seconds: int = 3600
    adapter_health_interval_seconds: int = 86400
    story_hypothesis_interval_seconds: int = 86400
    bridge_synthesis_interval_seconds: int = 360
    scheduler_tick_seconds: int = 60
    use_sample_context: bool = False
    use_sample_responses: bool = False
    min_signal_confidence: float = 0.5
    min_event_score: int = 60
    maps_public_api_base: str = "https://e3d.ai"
    # On-chain payment gating (E3DNFTManager subscription checks)
    eth_rpc_url: str = ""
    eth_nft_manager_address: str = "0xeED4620ff525101Ffcf7327378232CA9EF778D47"
    maps_api_auth_enabled: bool = False

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "MapsRunnerSettings":
        env = environ if environ is not None else os.environ

        return cls(
            e3d_base_url=(env.get("E3D_BASE_URL") or "https://e3d.ai").rstrip("/"),
            e3d_api_prefix=env.get("E3D_API_PREFIX") or "/api",
            e3d_api_key=env.get("E3D_API_KEY") or None,
            clickhouse_host=env.get("CLICKHOUSE_HOST") or env.get("CH_HOST") or "localhost",
            clickhouse_port=int(env.get("CLICKHOUSE_PORT") or env.get("CH_PORT") or 8123),
            clickhouse_database=env.get("CLICKHOUSE_DATABASE") or env.get("CH_DB") or "default",
            clickhouse_username=env.get("CLICKHOUSE_USERNAME") or env.get("CH_USER") or "default",
            clickhouse_password=env.get("CLICKHOUSE_PASSWORD") or env.get("CH_PASSWORD") or "",
            clickhouse_secure=_parse_bool(env.get("CLICKHOUSE_SECURE") or env.get("CH_SECURE")),
            clickhouse_timeout=float(env.get("CLICKHOUSE_TIMEOUT") or 10.0),
            question_queue_path=env.get("MAPS_QUESTION_QUEUE_PATH") or None,
            run_interval_seconds=int(env.get("MAPS_RUNNER_INTERVAL_SECONDS") or 300),
            scoring_interval_seconds=int(env.get("MAPS_SCORING_INTERVAL_SECONDS") or 1800),
            utility_interval_seconds=int(env.get("MAPS_UTILITY_INTERVAL_SECONDS") or 3600),
            export_interval_seconds=int(env.get("MAPS_EXPORT_INTERVAL_SECONDS") or 86400),
            flow_graph_interval_seconds=int(env.get("MAPS_FLOW_GRAPH_INTERVAL_SECONDS") or 300),
            traffic_state_interval_seconds=int(env.get("MAPS_TRAFFIC_STATE_INTERVAL_SECONDS") or 300),
            cross_chain_activity_interval_seconds=int(
                env.get("MAPS_CROSS_CHAIN_ACTIVITY_INTERVAL_SECONDS") or 300
            ),
            maps_news_interval_seconds=int(env.get("MAPS_NEWS_INTERVAL_SECONDS") or 300),
            watch_interval_seconds=int(env.get("WATCH_INTERVAL_SECONDS") or 300),
            query_demand_interval_seconds=int(env.get("MAPS_QUERY_DEMAND_INTERVAL_SECONDS") or 900),
            reflexivity_interval_seconds=int(env.get("MAPS_REFLEXIVITY_INTERVAL_SECONDS") or 600),
            narrative_velocity_interval_seconds=int(
                env.get("MAPS_NARRATIVE_VELOCITY_INTERVAL_SECONDS") or 300
            ),
            anomaly_monitor_interval_seconds=int(
                env.get("MAPS_ANOMALY_MONITOR_INTERVAL_SECONDS") or 300
            ),
            route_health_interval_seconds=int(env.get("MAPS_ROUTE_HEALTH_INTERVAL_SECONDS") or 3600),
            adapter_health_interval_seconds=int(
                env.get("MAPS_ADAPTER_HEALTH_INTERVAL_SECONDS") or 86400
            ),
            story_hypothesis_interval_seconds=int(
                env.get("MAPS_STORY_HYPOTHESIS_INTERVAL_SECONDS") or 86400
            ),
            bridge_synthesis_interval_seconds=int(
                env.get("MAPS_BRIDGE_SYNTHESIS_INTERVAL_SECONDS") or 360
            ),
            scheduler_tick_seconds=int(env.get("MAPS_SCHEDULER_TICK_SECONDS") or 60),
            use_sample_context=_parse_bool(env.get("MAPS_RUNNER_USE_SAMPLE_CONTEXT")),
            use_sample_responses=_parse_bool(env.get("MAPS_RUNNER_USE_SAMPLE_RESPONSES")),
            min_signal_confidence=float(env.get("MAPS_MIN_SIGNAL_CONFIDENCE") or 0.5),
            min_event_score=int(env.get("MIN_EVENT_SCORE") or 60),
            maps_public_api_base=(
                env.get("MAPS_PUBLIC_API_BASE") or env.get("E3D_BASE_URL") or "https://e3d.ai"
            ).rstrip("/"),
            eth_rpc_url=env.get("ETH_RPC_URL") or "",
            eth_nft_manager_address=(
                env.get("ETH_NFT_MANAGER_ADDRESS") or "0xeED4620ff525101Ffcf7327378232CA9EF778D47"
            ),
            maps_api_auth_enabled=_parse_bool(env.get("MAPS_API_AUTH_ENABLED")),
        )
