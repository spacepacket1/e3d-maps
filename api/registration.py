"""Registration endpoint handler — issue API keys from local entitlement snapshots."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from api.auth import ApiKeyStore, AuthError, TIER_NAMES

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


@dataclass(frozen=True)
class RegisterResponse:
    status_code: int
    body: dict[str, Any]


def post_register(store: ApiKeyStore, payload: dict[str, Any]) -> RegisterResponse:
    """Handle POST /api/maps/register.

    Expected payload: { "wallet_address": "0x..." }

    Returns a RegisterResponse containing the raw API key on success.  The
    caller must store it — it will not be retrievable again.
    """
    wallet_address: str = (payload.get("wallet_address") or "").strip()
    if not _ADDRESS_RE.match(wallet_address):
        return RegisterResponse(
            status_code=400,
            body={
                "status": "invalid",
                "error": "wallet_address must be a valid 20-byte Ethereum address (0x...)",
            },
        )

    try:
        result = store.register(wallet_address)
    except AuthError as exc:
        error_body = {"status": "error", "error": str(exc)}
        if exc.error_code:
            error_body["code"] = exc.error_code
        return RegisterResponse(
            status_code=exc.status_code,
            body=error_body,
        )

    return RegisterResponse(
        status_code=201,
        body={
            "status": "ok",
            "api_key": result.raw_key,
            "tier": TIER_NAMES.get(result.subscription_tier, "entitled"),
            "capabilities": result.capabilities,
            "discount_source": result.discount_source,
            "capabilities_expires_at": (
                result.capabilities_expires_at.isoformat().replace("+00:00", "Z")
                if result.capabilities_expires_at
                else None
            ),
            "note": (
                "Store this key securely — it will not be shown again. "
                "Send it as: Authorization: Bearer <api_key>"
            ),
        },
    )
