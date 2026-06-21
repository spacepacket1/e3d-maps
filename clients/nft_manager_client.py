"""On-chain reads from E3DNFTManager via raw JSON-RPC (no web3 dependency)."""
from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

# Mainnet contract addresses (from memory/project_e3dnftmanager_onchain.md)
NFT_MANAGER_PROXY = "0xeED4620ff525101Ffcf7327378232CA9EF778D47"

# keccak256("hasActiveSubscription(address)")[:4] = 0xbebe4a57
# keccak256("getSubscriptionDetails(address)")[:4]  = 0xd474f84f
_SEL_HAS_ACTIVE_SUB = "bebe4a57"
_SEL_GET_SUB_DETAILS = "d474f84f"

_CACHE_TTL = 300.0  # 5-minute on-chain read cache


class NFTManagerClientError(RuntimeError):
    """Raised when an on-chain read fails."""


def _calldata(selector: str, address: str) -> str:
    """Encode eth_call data for a single-address-parameter function."""
    addr_padded = address.lower().removeprefix("0x").zfill(64)
    return f"0x{selector}{addr_padded}"


class NFTManagerClient:
    """Reads subscription and agent-tier state from the live E3DNFTManager proxy."""

    def __init__(
        self,
        rpc_url: str,
        contract: str = NFT_MANAGER_PROXY,
        timeout: float = 5.0,
    ) -> None:
        self.rpc_url = rpc_url
        self.contract = contract
        self.timeout = timeout
        self._cache: dict[str, tuple[Any, float]] = {}

    # ── Public ────────────────────────────────────────────────────────────────

    def has_active_subscription(self, address: str) -> bool:
        """Return True if *address* holds a non-expired subscription."""
        return bool(self._cached(f"sub:{address.lower()}", lambda: self._fetch_has_sub(address)))

    def get_subscription_tier(self, address: str) -> int:
        """Return 0 (none), 1 (monthly), or 2 (annual) for *address*."""
        return int(self._cached(f"tier:{address.lower()}", lambda: self._fetch_tier(address)))

    def invalidate(self, address: str) -> None:
        """Evict cached entries for *address* (call after a new subscription is recorded)."""
        key_lower = address.lower()
        self._cache.pop(f"sub:{key_lower}", None)
        self._cache.pop(f"tier:{key_lower}", None)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _fetch_has_sub(self, address: str) -> bool:
        result = self._eth_call(_calldata(_SEL_HAS_ACTIVE_SUB, address))
        if not result or result in ("0x", "0x" + "0" * 64):
            return False
        return int(result, 16) != 0

    def _fetch_tier(self, address: str) -> int:
        result = self._eth_call(_calldata(_SEL_GET_SUB_DETAILS, address))
        if not result or result == "0x" or len(result) < 2 + 64 * 4:
            return 0
        # Returns (SubscriptionTier tier, uint256 expiration, uint256 remainingMints, bool isActive)
        # Each value occupies 32 bytes (64 hex chars); strip leading "0x"
        raw = result[2:]
        words = [raw[i * 64:(i + 1) * 64] for i in range(4)]
        tier = int(words[0], 16)       # 0=None, 1=Monthly, 2=Annual
        is_active = int(words[3], 16) != 0
        return tier if is_active else 0

    def _eth_call(self, data: str) -> str:
        payload = json.dumps({
            "jsonrpc": "2.0",
            "method": "eth_call",
            "params": [{"to": self.contract, "data": data}, "latest"],
            "id": 1,
        }).encode()
        req = Request(
            self.rpc_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read())
        except (URLError, OSError) as exc:
            raise NFTManagerClientError(f"JSON-RPC request failed: {exc}") from exc

        if "error" in body:
            raise NFTManagerClientError(f"eth_call error: {body['error']}")
        return body.get("result") or "0x"

    def _cached(self, key: str, fetch):
        now = time.monotonic()
        if key in self._cache:
            value, ts = self._cache[key]
            if now - ts < _CACHE_TTL:
                return value
        value = fetch()
        self._cache[key] = (value, now)
        return value
