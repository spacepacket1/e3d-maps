"""API key authentication and rate limiting for the Maps public API.

Flow:
  1. Caller POSTs wallet_address to /api/maps/register.
  2. Server resolves Maps capabilities from e3d, falling back to active subscription checks.
  3. Server issues a 256-bit bearer token and stores its SHA-256 hash in ClickHouse.
  4. Caller sends Authorization: Bearer <token> on all subsequent requests.
  5. verify() resolves the token locally and enforces the stored capability snapshot.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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
LEGACY_CAPABILITIES_TTL = timedelta(days=1)


class AuthError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 401,
        *,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class RateLimitError(AuthError):
    def __init__(self) -> None:
        super().__init__(
            "Rate limit exceeded — upgrade to annual for 1000 req/hr",
            429,
            error_code="RATE_LIMIT_EXCEEDED",
        )


@dataclass(frozen=True)
class ApiCaller:
    wallet_address: str
    subscription_tier: int
    capabilities: dict[str, Any]
    discount_source: str


@dataclass(frozen=True)
class ApiKeyRecord:
    wallet_address: str
    subscription_tier: int
    is_active: bool
    capabilities: dict[str, Any]
    discount_source: str
    capabilities_refreshed_at: datetime | None
    capabilities_expires_at: datetime | None


@dataclass(frozen=True)
class RegistrationResult:
    raw_key: str
    subscription_tier: int
    capabilities: dict[str, Any]
    discount_source: str
    capabilities_expires_at: datetime | None


@dataclass(frozen=True)
class CapabilitySnapshot:
    subscription_tier: int
    capabilities: dict[str, Any]
    discount_source: str
    capabilities_expires_at: datetime | None


class EntitlementResolverError(RuntimeError):
    """Raised when the e3d entitlement resolver request fails."""


class EntitlementResolverClient:
    def __init__(
        self,
        *,
        base_url: str = "https://e3d.ai",
        internal_service_key: str,
        resolve_path: str = "/api/entitlements/resolve",
        timeout: float = 10.0,
        request_executor=None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.internal_service_key = str(internal_service_key or "").strip()
        self.resolve_path = resolve_path if resolve_path.startswith("/") else f"/{resolve_path}"
        self.timeout = timeout
        self._request_executor = request_executor or self._default_request_executor

    def resolve(self, wallet_address: str) -> dict[str, Any]:
        if not self.internal_service_key:
            raise EntitlementResolverError("Missing e3d internal service key")

        body = json.dumps({"wallet": wallet_address.lower()}).encode("utf-8")
        request = Request(
            url=f"{self.base_url}{self.resolve_path}",
            data=body,
            headers={
                "Authorization": f"Internal {self.internal_service_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            raw = self._request_executor(request, self.timeout)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise EntitlementResolverError(
                f"Entitlement resolver request failed with status {exc.code}: {detail}"
            ) from exc
        except URLError as exc:
            raise EntitlementResolverError(
                f"Entitlement resolver request failed: {exc.reason}"
            ) from exc
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError as exc:
            raise EntitlementResolverError("Entitlement resolver returned invalid JSON") from exc

    @staticmethod
    def _default_request_executor(request: Request, timeout: float) -> bytes:
        with urlopen(request, timeout=timeout) as response:
            return response.read()


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _generate_key() -> str:
    return secrets.token_hex(32)  # 256-bit


class ApiKeyStore:
    """Thin layer over ClickHouse + NFTManagerClient for API key lifecycle."""

    def __init__(
        self,
        clickhouse: ClickHouseClient,
        nft: NFTManagerClient,
        *,
        entitlements: EntitlementResolverClient | Any | None = None,
        now=None,
    ) -> None:
        self.ch = clickhouse
        self.nft = nft
        self.entitlements = entitlements
        self._now = now or (lambda: datetime.now(UTC))
        # In-memory sliding-window rate tracker: key_hash → sorted list of request timestamps
        self._rate_windows: dict[str, list[float]] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, wallet_address: str) -> RegistrationResult:
        """Issue a new API key for a wallet with Maps entitlements."""
        snapshot = self._resolve_snapshot(wallet_address)

        raw_key = _generate_key()
        key_hash = _hash_key(raw_key)
        self._write_key_row(
            key_hash=key_hash,
            wallet_address=wallet_address.lower(),
            subscription_tier=snapshot.subscription_tier,
            is_active=True,
            capabilities=snapshot.capabilities,
            discount_source=snapshot.discount_source,
            capabilities_refreshed_at=self._now(),
            capabilities_expires_at=snapshot.capabilities_expires_at,
        )
        return RegistrationResult(
            raw_key=raw_key,
            subscription_tier=snapshot.subscription_tier,
            capabilities=snapshot.capabilities,
            discount_source=snapshot.discount_source,
            capabilities_expires_at=snapshot.capabilities_expires_at,
        )

    # ── Verification ──────────────────────────────────────────────────────────

    def verify(self, raw_key: str) -> ApiCaller:
        """Resolve a raw bearer token to an ApiCaller.

        Raises AuthError (401/402/429) on any failure.
        """
        key_hash = _hash_key(raw_key)

        record = self._lookup_key(key_hash)
        if not record.is_active:
            raise AuthError("API key has been revoked", error_code="KEY_REVOKED")
        if record.capabilities_expires_at and record.capabilities_expires_at <= self._now():
            raise AuthError(
                "Re-issue your Maps API key to refresh entitlements.",
                error_code="CAPABILITIES_EXPIRED",
            )

        limit = self._rate_limit_for(record)
        if limit > 0:
            self._check_rate_limit(key_hash, limit)

        return ApiCaller(
            wallet_address=record.wallet_address,
            subscription_tier=record.subscription_tier,
            capabilities=record.capabilities,
            discount_source=record.discount_source,
        )

    def revoke(self, raw_key: str) -> None:
        """Revoke an API key by inserting a deactivated row (ReplacingMergeTree pattern)."""
        key_hash = _hash_key(raw_key)
        record = self._lookup_key(key_hash)
        self._write_key_row(
            key_hash=key_hash,
            wallet_address=record.wallet_address,
            subscription_tier=record.subscription_tier,
            is_active=False,
            capabilities=record.capabilities,
            discount_source=record.discount_source,
            capabilities_refreshed_at=record.capabilities_refreshed_at or self._now(),
            capabilities_expires_at=record.capabilities_expires_at,
        )

    # ── Internals ─────────────────────────────────────────────────────────────

    def _lookup_key(self, key_hash: str) -> ApiKeyRecord:
        escaped = key_hash.replace("'", "\\'")
        rows = self.ch.select_rows(
            f"SELECT wallet_address, subscription_tier, is_active, capabilities_json, "
            f"discount_source, capabilities_refreshed_at, capabilities_expires_at "
            f"FROM maps_api_keys FINAL "
            f"WHERE key_hash = '{escaped}' LIMIT 1"
        )
        if not rows:
            raise AuthError("Invalid API key", error_code="KEY_NOT_FOUND")
        row = rows[0]
        return ApiKeyRecord(
            wallet_address=str(row["wallet_address"]),
            subscription_tier=int(row.get("subscription_tier", 0)),
            is_active=bool(row.get("is_active", 0)),
            capabilities=self._decode_capabilities(row),
            discount_source=str(row.get("discount_source") or self._default_discount_source(row)),
            capabilities_refreshed_at=self._parse_datetime(row.get("capabilities_refreshed_at")),
            capabilities_expires_at=self._parse_datetime(row.get("capabilities_expires_at")),
        )

    def _resolve_snapshot(self, wallet_address: str) -> CapabilitySnapshot:
        if self.entitlements is not None:
            try:
                resolved = self.entitlements.resolve(wallet_address)
            except EntitlementResolverError:
                resolved = None
            if isinstance(resolved, dict):
                capabilities = resolved.get("capabilities")
                if isinstance(capabilities, dict) and capabilities.get("mapsApiKeyEligible"):
                    evidence = resolved.get("evidence") if isinstance(resolved.get("evidence"), dict) else {}
                    subscription = evidence.get("subscription") if isinstance(evidence.get("subscription"), dict) else {}
                    return CapabilitySnapshot(
                        subscription_tier=int(subscription.get("tier", 0) or 0),
                        capabilities=dict(capabilities),
                        discount_source=str(
                            resolved.get("discountSource")
                            or capabilities.get("discountSource")
                            or "base_price"
                        ),
                        capabilities_expires_at=self._parse_datetime(resolved.get("capabilitiesExpiresAt")),
                    )

        tier = self.nft.get_subscription_tier(wallet_address)
        if tier == 0:
            raise AuthError(
                "No active E3D entitlement found for this wallet. "
                "Subscribe or claim an eligible promotion before issuing a Maps API key.",
                402,
            )
        return CapabilitySnapshot(
            subscription_tier=tier,
            capabilities={
                "mapsApiKeyEligible": True,
                "mapsHourlyLimit": RATE_LIMITS.get(tier, 0),
                "mapsX402DiscountBps": 0,
                "discountSource": "active_subscription",
            },
            discount_source="active_subscription",
            capabilities_expires_at=self._now() + LEGACY_CAPABILITIES_TTL,
        )

    def _write_key_row(
        self,
        *,
        key_hash: str,
        wallet_address: str,
        subscription_tier: int,
        is_active: bool,
        capabilities: dict[str, Any],
        discount_source: str,
        capabilities_refreshed_at: datetime | None,
        capabilities_expires_at: datetime | None,
    ) -> None:
        query = "INSERT INTO maps_api_keys FORMAT JSONEachRow"
        row = {
            "key_hash": key_hash,
            "wallet_address": wallet_address,
            "subscription_tier": int(subscription_tier),
            "is_active": 1 if is_active else 0,
            "capabilities_json": json.dumps(capabilities, separators=(",", ":"), sort_keys=True),
            "discount_source": discount_source,
            "capabilities_refreshed_at": self._format_datetime(capabilities_refreshed_at),
            "capabilities_expires_at": self._format_datetime(capabilities_expires_at),
        }
        self.ch._request_executor(f"{query}\n{json.dumps(row, separators=(',', ':'))}\n".encode())

    def _rate_limit_for(self, record: ApiKeyRecord) -> int:
        hourly_limit = record.capabilities.get("mapsHourlyLimit")
        if isinstance(hourly_limit, bool):
            return 0
        if isinstance(hourly_limit, (int, float)):
            return max(0, int(hourly_limit))
        if isinstance(hourly_limit, str) and hourly_limit.strip():
            try:
                return max(0, int(float(hourly_limit)))
            except ValueError:
                return RATE_LIMITS.get(record.subscription_tier, 0)
        return RATE_LIMITS.get(record.subscription_tier, 0)

    @staticmethod
    def _decode_capabilities(row: dict[str, Any]) -> dict[str, Any]:
        raw = row.get("capabilities_json")
        if isinstance(raw, dict):
            return dict(raw)
        if isinstance(raw, str) and raw.strip():
            try:
                decoded = json.loads(raw)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, dict):
                return decoded
        tier = int(row.get("subscription_tier", 0) or 0)
        return {
            "mapsApiKeyEligible": tier > 0,
            "mapsHourlyLimit": RATE_LIMITS.get(tier, 0),
            "mapsX402DiscountBps": 0,
            "discountSource": ApiKeyStore._default_discount_source(row),
        }

    @staticmethod
    def _default_discount_source(row: dict[str, Any]) -> str:
        return "active_subscription" if int(row.get("subscription_tier", 0) or 0) > 0 else "base_price"

    @staticmethod
    def _format_datetime(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        else:
            value = value.astimezone(UTC)
        return value.isoformat().replace("+00:00", "Z")

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=UTC)
        normalized = str(value).strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

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
