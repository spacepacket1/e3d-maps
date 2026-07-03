# Wallet Payments Dedup — Feature Ticket (phase-structured)

**Project:** E3D wallet payments unification
**Feature:** Remove duplicate on-chain entitlement/payment-verification code from
`e3d-maps` and `spacepacket/server` so both rely on a single shared implementation
**Target repos:** `/home/ubuntu/e3d-maps`, `/home/ubuntu/spacepacket/server`
**Status:** Draft for team review
**Priority:** Medium
**Implementation mode:** Phased, suitable for `codex-spec-runner`

---

## Codex-Spec-Runner Instructions

Each phase in this spec targets exactly one repo. **Launch `codex-spec-runner` from
the repo listed under `Repo:` for that phase.** Sandbox write access is determined at
launch time — `cd` inside the session does not grant additional write access.

Launch directory by repo:

| Repo | Launch from |
|---|---|
| `/home/ubuntu/e3d-maps` | `cd /home/ubuntu/e3d-maps` |
| `/home/ubuntu/spacepacket/server` | `cd /home/ubuntu/spacepacket/server` |

Always pass the spec as an absolute path:

```bash
cd <repo listed in the target phase>
codex-spec-runner /home/ubuntu/e3d-maps/docs/wallet-payments-dedup-feature-ticket.md <number>
```

Each phase may assume all preceding phases in this spec are complete and committed.
Phase 2 does not depend on Phase 1 being deployed (they touch unrelated code paths)
but is numbered second because it carries slightly more behavioral risk.

---

## 1. Background

An audit of the E3D Token payment integration across `e3d-agent`, `e3d-cast`,
`e3d-maps`, and `spacepacket/server` (the main `e3d` repo) found that the shared
payment rails (`productRegistry.js`, `productPaymentsRoutes.js`,
`productPaymentsService.js`, `entitlementsService.js` in `spacepacket/server`) are
already correctly used by `maps` and `cast` as registered products. That larger
finding is tracked separately and is **not** part of this ticket (see §3 Out of
Scope).

This ticket covers one narrow, low-risk finding from that audit: **two places where
the same on-chain check or the same transaction-verification logic is implemented
twice, independently, instead of once and shared.** Both are safe to consolidate
without any product or billing-model decisions — they are pure engineering dedup.

### 1.1 Duplicate #1 — subscription-tier on-chain read (cross-repo, cross-language)

`spacepacket/server` already has a single, correct implementation:
`fetchOnChainSubscriptionDetails` (`spacepacket.js:2020-2028`) calls
`E3DNFTManager.getSubscriptionDetails` / `hasActiveSubscription` once, and is reused
both by the direct `/subscription/syncOnChain` endpoint and — passed in as a
dependency — by `entitlementsService.js`'s `readOnChainState()`
(`entitlementsService.js:529-545`), which backs the public `/api/entitlements/resolve`
endpoint.

`e3d-maps` does not call that endpoint exclusively. `clients/nft_manager_client.py`
independently re-implements the same two contract calls via raw `eth_call` JSON-RPC
(selectors `bebe4a57` / `d474f84f`, matching `hasActiveSubscription` /
`getSubscriptionDetails`), and `api/auth.py`'s `_resolve_snapshot()`
(`api/auth.py:271-310`) falls back to it whenever the call to
`/api/entitlements/resolve` fails or is unavailable. This is a second,
independently-maintained reader of the same contract, in a different language, that
can silently diverge from the Node implementation and that no other E3D repo
(`e3d-agent`, `e3d-cast`) has an equivalent of.

`NFTManagerClient` has exactly two callers in `e3d-maps`: `api/auth.py` and its own
test file (`tests/unit/test_auth.py`). Nothing else depends on it.

### 1.2 Duplicate #2 — ERC-20 transfer verification (single repo, two implementations)

`spacepacket/server` has two independent implementations of "parse `Transfer` events
out of a transaction receipt and confirm tokens landed at a target address":

- `verifyTransferForProduct` (`productPaymentsService.js:185-229`) — used by the
  shared credit-purchase flow (`maps`, `cast`). Requires the sender (`fromWallet`) to
  match exactly, resolves the target address and token from `PRODUCT_REGISTRY`, and
  **rejects reverted transactions** (`receipt.status !== 1`).
- `verifyE3DTransferToEscrow` (`spacepacket.js:1406-1464`) — used by
  `agentRoutes.js` (`agentRoutes.js:505,672`) to verify E3D deposits into an AI-agent
  funding escrow. Discovers the funder from the transaction rather than asserting it,
  uses a fixed `ESCROW_E3D_ADDRESS` instead of a product config, and **does not check
  transaction revert status at all.**

The missing revert-status check in `verifyE3DTransferToEscrow` is a real correctness
gap, not just a style difference: a reverted funding transaction can currently pass
verification.

---

## 2. Design Principles (binding constraints)

1. **One implementation per on-chain check.** No repo should independently
   re-implement a contract read or transfer-verification routine that already exists
   in `spacepacket/server`. If a repo needs the result, it calls the existing HTTP
   endpoint (`/api/entitlements/resolve`) rather than reading the chain itself.
2. **Failure is not silently downgraded to a second implementation.** If
   `/api/entitlements/resolve` is unreachable, `e3d-maps` should surface that as an
   error, not transparently fall back to an independent on-chain read that can
   disagree with the canonical one. `e3d-agent` and `e3d-cast` already work this way;
   `e3d-maps` should match them.
3. **Extraction, not rewrite.** `verifyTransferForProduct`'s log-parsing core should
   be pulled out into a small primitive that both callers use, preserving each
   caller's existing external behavior except where §1.2 identifies an explicit bug
   fix (the revert-status check).
4. **No product or billing-model changes in this ticket.** This ticket does not touch
   `PRODUCT_REGISTRY`, does not register `e3d` as a payable product, and does not
   change how subscription tiers are purchased or priced. It only removes duplicate
   *verification* code.

---

## 3. Scope

### In scope

- Removing `e3d-maps`'s independent on-chain subscription-tier fallback.
- Extracting a shared ERC-20 transfer-verification primitive in
  `spacepacket/server` and migrating both existing callers onto it.
- Fixing the missing revert-status check surfaced by that extraction.
- Test coverage for both changes.

### Out of scope (tracked separately, not part of this ticket)

- Making `e3d`'s own premium/subscription features use the same metered,
  pay-per-action E3D credit model as `maps`/`cast` (`productRegistry.js`
  registration for an `e3d` product). This is a product/billing-model decision, not
  an engineering cleanup, and is explicitly deferred.
- Any change to how signup/login users without a connected wallet pay — that
  mechanism (account-tier subscriptions) is intentionally being kept as-is.
- The x402 prepaid-credits gap in `e3d-maps` (`maps_x402_credits` table, unused
  `docs/x402-agent-guide.md` payment flow) — a separate, larger cross-repo wiring
  effort, not a dedup.

---

## 4. Phase 1 — Remove `e3d-maps`'s redundant on-chain entitlement fallback

Repo:

```text
/home/ubuntu/e3d-maps
```

### What to build

- In `api/auth.py`, remove the `NFTManagerClient` fallback branch from
  `ApiKeyStore._resolve_snapshot()` (`api/auth.py:271-310`). The method should call
  only `EntitlementResolverClient.resolve()`; on `EntitlementResolverError`, raise
  `AuthError` (402, "No active E3D entitlement found...") instead of falling through
  to a direct chain read.
- Delete `clients/nft_manager_client.py` entirely (confirmed to have no callers
  outside `api/auth.py` and its own tests).
- Remove the now-unused `nft` constructor parameter from `ApiKeyStore.__init__`
  (`api/auth.py:163-176`) and any wiring that constructs `NFTManagerClient` for it.
- Update `tests/unit/test_auth.py`: remove or rewrite tests that exercise the
  fallback path (e.g. `test_active_subscription_still_registers_when_entitlements_unavailable`,
  and any test constructing `ApiKeyStore` with an `nft=` argument) to reflect that
  resolver failure is now a hard error.
- Update `docs/x402-agent-guide.md` / any other doc referencing the NFT-fallback
  behavior if it's described there.

### Acceptance Criteria

- `grep -rn "NFTManagerClient\|nft_manager_client" e3d-maps --include="*.py"`
  (excluding `__pycache__`) returns no matches.
- `ApiKeyStore._resolve_snapshot()` has exactly one code path for entitlement
  resolution.
- A simulated `EntitlementResolverError` during registration results in an
  `AuthError` (402) response, not a successful registration via chain fallback.
- Full existing test suite passes: `.venv/bin/python -m pytest tests/unit/ -q`.

### Verification

- Run the updated `tests/unit/test_auth.py` and confirm no test still asserts
  fallback behavior.
- Manually confirm (or note as a follow-up if infra isn't available in this
  environment) that a live call to `/api/entitlements/resolve` against a wallet with
  an active on-chain subscription still returns a usable capability snapshot,
  matching what the deleted fallback used to compute.

---

## 5. Phase 2 — Shared ERC-20 transfer-verification primitive

Repo:

```text
/home/ubuntu/spacepacket/server
```

### What to build

- Extract the log-parsing core of `verifyTransferForProduct`
  (`productPaymentsService.js:185-229`) into a standalone function, e.g.
  `verifyErc20TransferReceipt({ provider, tokenAddress, toAddress, fromAddress })`,
  that:
  - fetches the receipt and throws if not found;
  - throws if `receipt.status !== 1` (reverted transaction);
  - sums `Transfer` events into `toAddress`, optionally filtered by `fromAddress`
    when provided (omit the filter when `fromAddress` is not passed);
  - returns the total transferred (in the smallest unit) and does not itself know
    about `PRODUCT_REGISTRY`.
- Reimplement `verifyTransferForProduct` as a thin wrapper: resolve `provider`,
  `method.tokenAddress`, `method.treasuryAddress` from `PRODUCT_REGISTRY` as today,
  then call the shared primitive with `fromAddress: fromWallet`. External behavior
  for `maps`/`cast` purchases must be unchanged.
- Reimplement `verifyE3DTransferToEscrow` (`spacepacket.js:1406-1464`) to call the
  same primitive with `toAddress: ESCROW_E3D_ADDRESS` and no `fromAddress` (funder is
  still discovered from the matched log, not asserted in advance). Keep the function
  name and call signature used by `agentRoutes.js:505,672` unchanged.
- Add the revert-status check as part of this migration — this is an intentional
  behavior change for the escrow path, not an accidental one, and should be called
  out in the PR description as a bug fix.

### Acceptance Criteria

- `productPaymentsService.test.js` continues to pass unmodified in its existing
  assertions (purchase/quote/balance behavior for `maps` and `cast` unchanged).
- New test: a transaction with `receipt.status = 0` (reverted) passed to
  `verifyE3DTransferToEscrow` is rejected, where previously it would have been
  accepted if it contained a matching `Transfer` log.
- New or updated test in `agentRoutes.orchestrator.test.js` (or a new
  `agentRoutes.escrow.test.js` if none exists) confirms successful escrow funding
  still verifies correctly for a valid, confirmed transaction.
- No behavioral change to `POST /api/payments/credits/purchase` for `maps` or `cast`.

### Verification

- Run `productPaymentsService.test.js`, `productPaymentsRoutes.test.js`, and the
  agent routes test suite; all must pass.
- Confirm via code review that `verifyTransferForProduct` and
  `verifyE3DTransferToEscrow` no longer contain independent copies of the
  `Transfer`-log-parsing loop.

---

## 6. Test Plan

- `e3d-maps`: `.venv/bin/python -m pytest tests/unit/ -q` — full suite, with
  particular attention to `test_auth.py`.
- `spacepacket/server`: existing Node test suite (`productPaymentsService.test.js`,
  `productPaymentsRoutes.test.js`, `entitlementsRoutes.test.js`, agent routes tests),
  plus the two new tests described in Phase 2 (reverted-tx rejection, successful
  escrow funding unaffected).
- No new integration/E2E environment is required — both phases are covered by
  existing unit-test infrastructure in each repo.

## 7. Open Questions

1. **Resolver downtime behavior.** Phase 1 makes `e3d-maps` registration hard-fail
   when `/api/entitlements/resolve` is unreachable, instead of degrading to a direct
   chain read. Is that acceptable, or does `e3d-maps` need retry/backoff or a short
   local cache in front of the resolver call to reduce sensitivity to transient
   resolver blips? (`e3d-agent`/`e3d-cast` have no fallback either, so hard-fail is at
   least consistent with the rest of the ecosystem.)
2. **Existing escrow-funding callers.** Confirm there are no other undiscovered
   callers of `verifyE3DTransferToEscrow` outside `agentRoutes.js` before Phase 2
   lands (a repo-wide grep was done as part of this audit and found none, but should
   be re-checked at implementation time in case of concurrent changes).
