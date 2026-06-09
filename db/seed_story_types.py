from __future__ import annotations

import json
from base64 import b64encode
from datetime import UTC, datetime
from urllib.request import Request, urlopen


STORY_TYPE_DEFINITIONS = (
    {
        "story_type": "capital_migration",
        "display_name": "Capital Migration",
        "category": "traffic",
        "human_meaning": "Capital appears to be moving from one sector, asset, protocol, or behavior cluster to another.",
        "agent_meaning": "Use this story type as evidence of changing capital routes and potential destination probabilities.",
        "inputs": ["wallet_flows", "token_transfers", "stablecoin_activity", "exchange_flows"],
        "outputs": ["origin", "destination", "flow_direction", "flow_strength"],
        "example_questions": [
            "Where is capital migrating?",
            "Which destination is gaining probability?",
        ],
        "related_navigation_signal_types": ["capital_migration", "destination_prediction"],
    },
    {
        "story_type": "exchange_flow",
        "display_name": "Exchange Flow",
        "category": "flows",
        "human_meaning": "Exchange inflows or outflows are changing in a way that may signal accumulation, selling pressure, or rotation.",
        "agent_meaning": "Treat this as directional evidence for risk-on or risk-off routes and for hazard detection around centralized exchange activity.",
        "inputs": ["exchange_wallets", "token_transfers", "netflow_summaries"],
        "outputs": ["asset", "venue_type", "flow_direction", "flow_strength"],
        "example_questions": [
            "Are exchange inflows suggesting distribution?",
            "Is exchange outflow consistent with accumulation?",
        ],
        "related_navigation_signal_types": ["capital_migration", "route_hazard", "liquidity_forecast"],
    },
    {
        "story_type": "stablecoin_activity",
        "display_name": "Stablecoin Activity",
        "category": "liquidity",
        "human_meaning": "Stablecoin minting, burning, or netflows are shifting and may indicate deployable capital entering or leaving the market.",
        "agent_meaning": "Use this as a funding and liquidity precursor for capital migration and destination probability signals.",
        "inputs": ["stablecoin_transfers", "mint_burn_events", "netflow_summaries"],
        "outputs": ["asset", "flow_direction", "liquidity_bias", "flow_strength"],
        "example_questions": [
            "Is fresh stablecoin liquidity entering the market?",
            "Are stables being deployed into higher-risk destinations?",
        ],
        "related_navigation_signal_types": ["capital_migration", "destination_prediction", "liquidity_forecast"],
    },
    {
        "story_type": "wallet_accumulation",
        "display_name": "Wallet Accumulation",
        "category": "wallets",
        "human_meaning": "Tracked wallets or clusters are accumulating assets, positions, or protocol exposure.",
        "agent_meaning": "Use this as evidence of conviction and route formation, especially when multiple tracked wallets converge on the same destination.",
        "inputs": ["wallet_balances", "wallet_clusters", "token_transfers"],
        "outputs": ["wallet_cluster", "asset_scope", "destination", "conviction"],
        "example_questions": [
            "Which wallets are accumulating exposure?",
            "Is smart money converging on one destination?",
        ],
        "related_navigation_signal_types": ["capital_migration", "destination_prediction", "capital_conviction"],
    },
    {
        "story_type": "whale_movement",
        "display_name": "Whale Movement",
        "category": "wallets",
        "human_meaning": "Large holders moved meaningful size across venues, assets, chains, or protocols.",
        "agent_meaning": "Use this as high-signal directional evidence when the movement is large enough to influence route probability or hazard levels.",
        "inputs": ["large_wallet_transfers", "bridge_activity", "exchange_flows"],
        "outputs": ["origin", "destination", "asset_scope", "movement_size"],
        "example_questions": [
            "Did a large holder rotate into a new destination?",
            "Is whale distribution creating a route hazard?",
        ],
        "related_navigation_signal_types": ["capital_migration", "route_hazard", "destination_prediction"],
    },
)


class StoryTypeSeeder:
    def __init__(
        self,
        *,
        host: str = "localhost",
        port: int = 8123,
        database: str = "default",
        username: str = "default",
        password: str = "",
        secure: bool = False,
        timeout: float = 10.0,
        request_executor=None,
    ) -> None:
        self.host = host
        self.port = port
        self.database = database
        self.username = username
        self.password = password
        self.secure = secure
        self.timeout = timeout
        self._request_executor = request_executor or self._default_request_executor

    def seed(self, *, now: datetime | None = None) -> int:
        current_time = (now or datetime.now(tz=UTC)).astimezone(UTC).replace(microsecond=0)
        story_types = [item["story_type"] for item in STORY_TYPE_DEFINITIONS]
        delete_sql = (
            "ALTER TABLE StoryTypeDefinitions DELETE WHERE story_type IN "
            f"({', '.join(self._sql_string(value) for value in story_types)}) SETTINGS mutations_sync = 1"
        )
        self._request_executor(delete_sql.encode("utf-8"))

        rows = []
        for definition in STORY_TYPE_DEFINITIONS:
            row = {
                **definition,
                "schema_version": "1.0",
                "created_at": self._format_datetime(current_time),
                "updated_at": self._format_datetime(current_time),
            }
            rows.append(json.dumps(row, separators=(",", ":"), sort_keys=True))

        insert_sql = "INSERT INTO StoryTypeDefinitions FORMAT JSONEachRow\n" + "\n".join(rows) + "\n"
        self._request_executor(insert_sql.encode("utf-8"))
        return len(STORY_TYPE_DEFINITIONS)

    def _default_request_executor(self, body: bytes) -> bytes:
        scheme = "https" if self.secure else "http"
        url = f"{scheme}://{self.host}:{self.port}/?database={self.database}"
        headers = {"Content-Type": "text/plain; charset=utf-8"}
        if self.username or self.password:
            token = b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {token}"

        request = Request(url=url, data=body, headers=headers, method="POST")
        with urlopen(request, timeout=self.timeout) as response:
            return response.read()

    @staticmethod
    def _format_datetime(value: datetime) -> str:
        return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _sql_string(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"


if __name__ == "__main__":
    inserted = StoryTypeSeeder().seed()
    print(f"Seeded {inserted} story type definitions.")
