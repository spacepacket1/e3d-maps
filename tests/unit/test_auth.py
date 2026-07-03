"""Unit tests for API key auth and registration."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from api.auth import RATE_LIMITS, ApiKeyStore, AuthError, EntitlementResolverError, RateLimitError, _hash_key
from api.registration import post_register


def _default_resolver_payload(tier: int) -> dict:
    if tier <= 0:
        return {"capabilities": {"mapsApiKeyEligible": False}}
    return {
        "capabilities": {
            "mapsApiKeyEligible": True,
            "mapsHourlyLimit": RATE_LIMITS.get(tier, 0),
            "mapsX402DiscountBps": 0,
            "discountSource": "active_subscription",
        },
        "discountSource": "active_subscription",
        "capabilitiesExpiresAt": "2026-09-26T00:00:00.000Z",
        "evidence": {"subscription": {"tier": tier}},
    }


def _make_store(*, tier: int = 1, resolver_payload=None, resolver_error=None, now=None):
    ch = MagicMock()
    ch.select_rows.return_value = []

    resolver = MagicMock()
    if resolver_error is not None:
        resolver.resolve.side_effect = resolver_error
    else:
        resolver.resolve.return_value = (
            resolver_payload if resolver_payload is not None else _default_resolver_payload(tier)
        )

    store = ApiKeyStore(
        clickhouse=ch,
        entitlements=resolver,
        now=now or (lambda: datetime(2026, 6, 28, tzinfo=UTC)),
    )
    return store, ch, resolver


class TestRegister:
    def test_issues_key_for_active_monthly_subscription(self):
        store, ch, resolver = _make_store(tier=1)
        result = store.register("0xAbCd" + "0" * 36)
        assert len(result.raw_key) == 64  # 32 hex bytes
        assert result.subscription_tier == 1
        assert result.capabilities["mapsHourlyLimit"] == 200
        ch._request_executor.assert_called_once()

    def test_issues_key_for_annual_subscription(self):
        store, ch, resolver = _make_store(tier=2)
        result = store.register("0x" + "a" * 40)
        assert result.subscription_tier == 2
        assert result.capabilities["mapsHourlyLimit"] == 1000

    def test_raises_when_no_subscription(self):
        store, ch, resolver = _make_store(tier=0)
        with pytest.raises(AuthError) as exc_info:
            store.register("0x" + "a" * 40)
        assert exc_info.value.status_code == 402

    def test_verified_promotional_agent_can_register_via_entitlements(self):
        store, ch, resolver = _make_store(
            resolver_payload={
                "capabilities": {
                    "mapsApiKeyEligible": True,
                    "mapsHourlyLimit": 1000,
                    "mapsX402DiscountBps": 9000,
                    "discountSource": "FIRST_100_AGENTS",
                },
                "discountSource": "FIRST_100_AGENTS",
                "capabilitiesExpiresAt": "2026-09-26T00:00:00.000Z",
                "evidence": {
                    "subscription": {"tier": 0},
                },
            },
        )
        result = store.register("0x" + "c" * 40)
        assert result.subscription_tier == 0
        assert result.discount_source == "FIRST_100_AGENTS"
        assert result.capabilities["mapsX402DiscountBps"] == 9000
        resolver.resolve.assert_called_once_with("0x" + "c" * 40)

    def test_registration_fails_when_entitlements_unavailable(self):
        store, ch, resolver = _make_store(
            resolver_error=EntitlementResolverError("resolver offline"),
        )
        with pytest.raises(AuthError) as exc_info:
            store.register("0x" + "e" * 40)
        assert exc_info.value.status_code == 503
        assert exc_info.value.error_code == "ENTITLEMENTS_UNAVAILABLE"

    def test_post_register_bad_address(self):
        store, _, _ = _make_store()
        resp = post_register(store, {"wallet_address": "not-an-address"})
        assert resp.status_code == 400

    def test_post_register_success(self):
        store, _, _ = _make_store(tier=1)
        resp = post_register(store, {"wallet_address": "0x" + "a" * 40})
        assert resp.status_code == 201
        assert "api_key" in resp.body
        assert resp.body["tier"] == "monthly"
        assert resp.body["capabilities"]["mapsApiKeyEligible"] is True

    def test_post_register_no_subscription(self):
        store, _, _ = _make_store(tier=0)
        resp = post_register(store, {"wallet_address": "0x" + "a" * 40})
        assert resp.status_code == 402


class TestVerify:
    def _store_with_key(
        self,
        *,
        tier: int = 1,
        resolver_payload=None,
        key_active: int = 1,
        capabilities_expires_at: str = "2026-09-26T00:00:00.000Z",
    ):
        store, ch, resolver = _make_store(tier=tier, resolver_payload=resolver_payload)
        result = store.register("0x" + "b" * 40)
        raw_key = result.raw_key
        key_hash = _hash_key(raw_key)
        # Simulate DB lookup returning the stored row
        ch.select_rows.return_value = [
            {
                "wallet_address": "0x" + "b" * 40,
                "subscription_tier": result.subscription_tier,
                "is_active": key_active,
                "capabilities_json": result.capabilities,
                "discount_source": result.discount_source,
                "capabilities_refreshed_at": "2026-06-28T00:00:00.000Z",
                "capabilities_expires_at": capabilities_expires_at,
            }
        ]
        return store, raw_key, resolver

    def test_valid_key_returns_caller(self):
        store, raw_key, resolver = self._store_with_key()
        caller = store.verify(raw_key)
        assert caller.subscription_tier == 1
        assert caller.capabilities["mapsHourlyLimit"] == 200
        resolver.resolve.assert_called_once()

    def test_invalid_key_raises_401(self):
        store, ch, resolver = _make_store()
        ch.select_rows.return_value = []
        with pytest.raises(AuthError) as exc_info:
            store.verify("deadbeef" * 8)
        assert exc_info.value.status_code == 401
        assert exc_info.value.error_code == "KEY_NOT_FOUND"

    def test_revoked_key_raises_401(self):
        store, raw_key, resolver = self._store_with_key(key_active=0)
        with pytest.raises(AuthError) as exc_info:
            store.verify(raw_key)
        assert exc_info.value.status_code == 401
        assert exc_info.value.error_code == "KEY_REVOKED"

    def test_expired_capabilities_raise_401(self):
        store, raw_key, resolver = self._store_with_key(
            capabilities_expires_at="2026-06-27T00:00:00.000Z"
        )
        with pytest.raises(AuthError) as exc_info:
            store.verify(raw_key)
        assert exc_info.value.status_code == 401
        assert exc_info.value.error_code == "CAPABILITIES_EXPIRED"
        assert "Re-issue your Maps API key" in str(exc_info.value)

    def test_rate_limit_monthly(self):
        store, raw_key, resolver = self._store_with_key(tier=1)
        # First 200 calls succeed
        for _ in range(200):
            store.verify(raw_key)
        with pytest.raises(RateLimitError):
            store.verify(raw_key)

    def test_rate_limit_annual_higher(self):
        store, raw_key, resolver = self._store_with_key(tier=2)
        for _ in range(1000):
            store.verify(raw_key)
        with pytest.raises(RateLimitError):
            store.verify(raw_key)

    def test_reissuing_key_picks_up_updated_entitlements(self):
        resolver = MagicMock()
        resolver.resolve.side_effect = [
            {
                "capabilities": {
                    "mapsApiKeyEligible": True,
                    "mapsHourlyLimit": 200,
                    "mapsX402DiscountBps": 0,
                    "discountSource": "active_subscription",
                },
                "discountSource": "active_subscription",
                "capabilitiesExpiresAt": "2026-07-01T00:00:00.000Z",
                "evidence": {"subscription": {"tier": 1}},
            },
            {
                "capabilities": {
                    "mapsApiKeyEligible": True,
                    "mapsHourlyLimit": 1000,
                    "mapsX402DiscountBps": 9000,
                    "discountSource": "FIRST_100_AGENTS",
                },
                "discountSource": "FIRST_100_AGENTS",
                "capabilitiesExpiresAt": "2026-09-26T00:00:00.000Z",
                "evidence": {"subscription": {"tier": 1}},
            },
        ]
        ch = MagicMock()
        store = ApiKeyStore(
            clickhouse=ch,
            entitlements=resolver,
            now=lambda: datetime(2026, 6, 28, tzinfo=UTC),
        )

        first = store.register("0x" + "d" * 40)
        second = store.register("0x" + "d" * 40)

        assert first.capabilities["mapsHourlyLimit"] == 200
        assert second.capabilities["mapsHourlyLimit"] == 1000
        assert second.discount_source == "FIRST_100_AGENTS"
        assert resolver.resolve.call_count == 2

    def test_revoke_persists_existing_capabilities_snapshot(self):
        store, raw_key, resolver = self._store_with_key(tier=1)
        store.revoke(raw_key)
        assert store.ch._request_executor.call_count == 2
