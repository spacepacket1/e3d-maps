"""Registration endpoint handler — issue API keys against on-chain subscriptions."""
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
        raw_key, tier = store.register(wallet_address)
    except AuthError as exc:
        return RegisterResponse(
            status_code=exc.status_code,
            body={"status": "error", "error": str(exc)},
        )

    return RegisterResponse(
        status_code=201,
        body={
            "status": "ok",
            "api_key": raw_key,
            "tier": TIER_NAMES.get(tier, "unknown"),
            "note": (
                "Store this key securely — it will not be shown again. "
                "Send it as: Authorization: Bearer <api_key>"
            ),
        },
    )
