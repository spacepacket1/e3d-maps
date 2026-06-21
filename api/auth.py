"""API key authentication and rate limiting for the Maps public API.

Flow:
  1. Caller POSTs wallet_address to /api/maps/register.
  2. Server verifies on-chain subscription via NFTManagerClient.
  3. Server issues a 256-bit bearer token, stores its SHA-256 hash in ClickHouse.
  4. Caller sends Authorization: Bearer <token> on all subsequent requests.
  5. verify() resolves the token → ApiCaller and enforces per-tier rate limits.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clients.clickhouse_client import ClickHouseClient
    from clients.nft_manager_client import NFTManagerClient

# Hourly request limits by subscription tier (0=none, 1=monthly, 2=annual)
RATE_LIMITS: dict[int, int] = {
    0: 0,
    1: 200,
    2: 1000,
}

TIER_NAMES = {1: "monthly", 2: "annual"}


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(AuthError):
    def __init__(self) -> None:
        super().__init__("Rate limit exceeded — upgrade to annual for 1000 req/hr", 429)


class SubscriptionExpiredError(AuthError):
    def __init__(self) -> None:
        super().__init__(
            "E3D subscription has expired — renew on-chain at maps.e3d.ai/#subscribe",
            402,
        )


@dataclass(frozen=True)
class ApiCaller:
    wallet_address: str
    subscription_tier: int


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _generate_key() -> str:
    return secrets.token_hex(32)  # 256-bit


class ApiKeyStore:
    """Thin layer over ClickHouse + NFTManagerClient for API key lifecycle."""

    def __init__(self, clickhouse: ClickHouseClient, nft: NFTManagerClient) -> None:
        self.ch = clickhouse
        self.nft = nft
        # In-memory sliding-window rate tracker: key_hash → sorted list of request timestamps
        self._rate_windows: dict[str, list[float]] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, wallet_address: str) -> tuple[str, int]:
        """Issue a new API key for a wallet with an active on-chain subscription.

        Returns (raw_key, subscription_tier).  Raises AuthError if no subscription.
        """
        tier = self.nft.get_subscription_tier(wallet_address)
        if tier == 0:
            raise AuthError(
                "No active E3D subscription found for this wallet. "
                "Subscribe at maps.e3d.ai/#subscribe (E3D token accepted).",
                402,
            )

        raw_key = _generate_key()
        key_hash = _hash_key(raw_key)

        query = "INSERT INTO maps_api_keys FORMAT JSONEachRow"
        row_json = (
            f'{{"key_hash":"{key_hash}",'
            f'"wallet_address":"{wallet_address.lower()}",'
            f'"subscription_tier":{tier},'
            f'"is_active":1}}'
        )
        self.ch._request_executor(f"{query}\n{row_json}\n".encode())
        return raw_key, tier

    # ── Verification ──────────────────────────────────────────────────────────

    def verify(self, raw_key: str) -> ApiCaller:
        """Resolve a raw bearer token to an ApiCaller.

        Raises AuthError (401/402/429) on any failure.
        """
        key_hash = _hash_key(raw_key)

        wallet, tier, is_active = self._lookup_key(key_hash)
        if not is_active:
            raise AuthError("API key has been revoked")

        # On-chain check (cached 5 min inside NFTManagerClient)
        if not self.nft.has_active_subscription(wallet):
            raise SubscriptionExpiredError()

        limit = RATE_LIMITS.get(tier, 0)
        if limit > 0:
            self._check_rate_limit(key_hash, limit)

        return ApiCaller(wallet_address=wallet, subscription_tier=tier)

    def revoke(self, raw_key: str) -> None:
        """Revoke an API key by inserting a deactivated row (ReplacingMergeTree pattern)."""
        key_hash = _hash_key(raw_key)
        wallet, tier, _ = self._lookup_key(key_hash)

        query = "INSERT INTO maps_api_keys FORMAT JSONEachRow"
        row_json = (
            f'{{"key_hash":"{key_hash}",'
            f'"wallet_address":"{wallet}",'
            f'"subscription_tier":{tier},'
            f'"is_active":0}}'
        )
        self.ch._request_executor(f"{query}\n{row_json}\n".encode())

    # ── Internals ─────────────────────────────────────────────────────────────

    def _lookup_key(self, key_hash: str) -> tuple[str, int, bool]:
        escaped = key_hash.replace("'", "\\'")
        rows = self.ch.select_rows(
            f"SELECT wallet_address, subscription_tier, is_active "
            f"FROM maps_api_keys FINAL "
            f"WHERE key_hash = '{escaped}' LIMIT 1"
        )
        if not rows:
            raise AuthError("Invalid API key")
        row = rows[0]
        return row["wallet_address"], int(row["subscription_tier"]), bool(row["is_active"])

    def _check_rate_limit(self, key_hash: str, limit: int) -> None:
        now = time.monotonic()
        window = self._rate_windows.setdefault(key_hash, [])
        cutoff = now - 3600.0
        # Trim the expired entries from the front
        idx = 0
        while idx < len(window) and window[idx] < cutoff:
            idx += 1
        if idx:
            del window[:idx]
        if len(window) >= limit:
            raise RateLimitError()
        window.append(now)
