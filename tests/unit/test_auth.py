"""Unit tests for API key auth and registration."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from api.auth import ApiKeyStore, AuthError, RateLimitError, SubscriptionExpiredError, _hash_key
from api.registration import post_register


def _make_store(*, tier: int = 1, active: bool = True):
    nft = MagicMock()
    nft.get_subscription_tier.return_value = tier
    nft.has_active_subscription.return_value = active

    ch = MagicMock()
    ch.select_rows.return_value = []

    store = ApiKeyStore(clickhouse=ch, nft=nft)
    return store, ch, nft


class TestRegister:
    def test_issues_key_for_active_monthly_subscription(self):
        store, ch, nft = _make_store(tier=1)
        raw_key, actual_tier = store.register("0xAbCd" + "0" * 36)
        assert len(raw_key) == 64  # 32 hex bytes
        assert actual_tier == 1
        ch._request_executor.assert_called_once()

    def test_issues_key_for_annual_subscription(self):
        store, ch, nft = _make_store(tier=2)
        _, tier = store.register("0x" + "a" * 40)
        assert tier == 2

    def test_raises_when_no_subscription(self):
        store, ch, nft = _make_store(tier=0)
        with pytest.raises(AuthError) as exc_info:
            store.register("0x" + "a" * 40)
        assert exc_info.value.status_code == 402

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

    def test_post_register_no_subscription(self):
        store, _, _ = _make_store(tier=0)
        resp = post_register(store, {"wallet_address": "0x" + "a" * 40})
        assert resp.status_code == 402


class TestVerify:
    def _store_with_key(self, *, tier: int = 1, active_sub: bool = True, key_active: int = 1):
        store, ch, nft = _make_store(tier=tier, active=active_sub)
        raw_key, _ = store.register("0x" + "b" * 40)
        key_hash = _hash_key(raw_key)
        # Simulate DB lookup returning the stored row
        ch.select_rows.return_value = [
            {"wallet_address": "0x" + "b" * 40, "subscription_tier": tier, "is_active": key_active}
        ]
        return store, raw_key

    def test_valid_key_returns_caller(self):
        store, raw_key = self._store_with_key()
        caller = store.verify(raw_key)
        assert caller.subscription_tier == 1

    def test_invalid_key_raises_401(self):
        store, ch, nft = _make_store()
        ch.select_rows.return_value = []
        with pytest.raises(AuthError) as exc_info:
            store.verify("deadbeef" * 8)
        assert exc_info.value.status_code == 401

    def test_revoked_key_raises_401(self):
        store, raw_key = self._store_with_key(key_active=0)
        with pytest.raises(AuthError) as exc_info:
            store.verify(raw_key)
        assert exc_info.value.status_code == 401

    def test_expired_subscription_raises_402(self):
        store, raw_key = self._store_with_key(active_sub=False)
        with pytest.raises(SubscriptionExpiredError):
            store.verify(raw_key)

    def test_rate_limit_monthly(self):
        store, raw_key = self._store_with_key(tier=1)
        # First 200 calls succeed
        for _ in range(200):
            store.verify(raw_key)
        with pytest.raises(RateLimitError):
            store.verify(raw_key)

    def test_rate_limit_annual_higher(self):
        store, raw_key = self._store_with_key(tier=2)
        for _ in range(1000):
            store.verify(raw_key)
        with pytest.raises(RateLimitError):
            store.verify(raw_key)


class TestNFTManagerClient:
    def test_decodes_has_active_subscription_true(self):
        from clients.nft_manager_client import NFTManagerClient

        client = NFTManagerClient(rpc_url="http://localhost:8545")
        true_result = "0x" + "0" * 63 + "1"
        with patch.object(client, "_eth_call", return_value=true_result):
            assert client.has_active_subscription("0x" + "a" * 40) is True

    def test_decodes_has_active_subscription_false(self):
        from clients.nft_manager_client import NFTManagerClient

        client = NFTManagerClient(rpc_url="http://localhost:8545")
        false_result = "0x" + "0" * 64
        with patch.object(client, "_eth_call", return_value=false_result):
            assert client.has_active_subscription("0x" + "a" * 40) is False

    def test_decodes_subscription_tier_monthly(self):
        from clients.nft_manager_client import NFTManagerClient

        client = NFTManagerClient(rpc_url="http://localhost:8545")
        # tier=1 (monthly), expiry, mints, is_active=1
        result = "0x" + "0" * 63 + "1" + "0" * 63 + "1" + "0" * 63 + "3" + "0" * 63 + "1"
        with patch.object(client, "_eth_call", return_value=result):
            assert client.get_subscription_tier("0x" + "a" * 40) == 1

    def test_inactive_subscription_returns_tier_0(self):
        from clients.nft_manager_client import NFTManagerClient

        client = NFTManagerClient(rpc_url="http://localhost:8545")
        # tier=2, but is_active=0
        result = "0x" + "0" * 63 + "2" + "0" * 63 + "1" + "0" * 63 + "3" + "0" * 64
        with patch.object(client, "_eth_call", return_value=result):
            assert client.get_subscription_tier("0x" + "a" * 40) == 0
