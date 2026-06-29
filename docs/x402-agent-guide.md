# E3D Maps x402 Agent Guide

E3D Maps navigation intelligence is available to autonomous agents via per-call micropayments in **E3D Token** (E3D). Payments happen on **Base L2**, keeping gas costs negligible while generating real on-chain E3D activity.

---

## Overview

```
Agent → buys E3D on Uniswap (mainnet)
      → bridges wE3D to Base via Wormhole
        → requests a quote from E3D payments
          → transfers wE3D on Base to the quoted treasury address
            → registers the funding tx at POST /api/payments/credits/purchase
              → receives an e3d_maps_pay_... key
                → makes API calls with Authorization: Bearer <key>
```

Every credit purchase is an on-chain Base transaction. This creates verifiable E3D token velocity.

---

## Quick Start

### 1. Acquire E3D

Buy E3D on Uniswap (Ethereum mainnet):

- **Token address**: `0x6488861b401F427D13B6619C77C297366bCf6386`
- **Uniswap pair**: search "E3D" on Uniswap v3 (ETH/E3D)

### 2. Bridge E3D to Base

Use the Wormhole scripts in `E3DToken/wormhole-e3d-base/`:

```bash
cd E3DToken/wormhole-e3d-base
cp .env.example .env
# Fill in ETH_RPC_URL, ETH_PRIVATE_KEY, BASE_RPC_URL, BASE_RECIPIENT_ADDRESS

npm install
npm run attest    # one-time: registers E3D on Wormhole for Base (takes 5-15 min)
npm run transfer  # bridges E3D from Ethereum → Base
npm run redeem    # mints wrapped E3D on Base (pass the transfer record path)
npm run check     # verify your wrapped E3D balance
```

**Wrapped E3D on Base**: address printed by `npm run attest` and `npm run check`.

Alternatively, use any Wormhole-compatible bridge UI (e.g., Portal Bridge) to bridge E3D to Base.

### 3. Transfer wE3D to the Treasury

Request a quote from E3D payments before transferring funds:

```bash
curl -X POST https://e3d.ai/api/payments/credits/quote \
  -H "Authorization: Bearer $E3D_AGENT_SERVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "product": "maps",
    "wallet": "0xYourBaseWalletAddress",
    "requestedIssuedCredits": 1000,
    "promotionCode": "FIRST_100_AGENTS"
  }'
```

Example response:

```json
{
  "product": "maps",
  "wallet": "0xyourbasewalletaddress",
  "requestedIssuedCredits": 1000,
  "requiredBaseCredits": 100,
  "requiredWE3D": "0.1",
  "appliedDiscountBps": 9000,
  "discountSource": "FIRST_100_AGENTS",
  "payment": {
    "chain": "base",
    "chainId": 8453,
    "token": "wE3D",
    "tokenAddress": "0x<wrappedE3D>",
    "treasuryAddress": "0x<treasury>"
  }
}
```

Then send wrapped E3D from your Base wallet to the quoted treasury address on Base:

- **Treasury address**: `0x<MAPS_TREASURY_ADDRESS>` *(set after deployment)*
- **Token**: wrapped E3D on Base (`WRAPPED_E3D_BASE_ADDRESS`)
- **Minimum**: 0.5 wE3D (500 credits)

This is a standard ERC-20 transfer — use any Base-compatible wallet or your agent's ethers.js client.

```js
const provider = new ethers.providers.JsonRpcProvider(BASE_RPC_URL);
const wallet = new ethers.Wallet(PRIVATE_KEY, provider);
const token = new ethers.Contract(WRAPPED_E3D_BASE_ADDRESS, ['function transfer(address,uint256) returns (bool)'], wallet);
const tx = await token.transfer(quote.payment.treasuryAddress, ethers.utils.parseUnits(quote.requiredWE3D, 18));
await tx.wait();
// Save tx.hash for step 4
```

### 4. Register Credit Purchase

Post the Base transaction hash to E3D payments to receive your product-scoped API key:

```bash
curl -X POST https://e3d.ai/api/payments/credits/purchase \
  -H "Authorization: Bearer $E3D_AGENT_SERVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "product": "maps",
    "wallet": "0xYourBaseWalletAddress",
    "txHash": "0xYourBaseTxHash",
    "promotionCode": "FIRST_100_AGENTS"
  }'
```

Response:
```json
{
  "status": "ok",
  "product": "maps",
  "creditKey": "e3d_maps_pay_abc123...",
  "issuedCredits": 1000,
  "creditRate": "1 credit = 0.001 wE3D before discounts",
  "usage": "Send as: Authorization: Bearer <api_key>"
}
```

**Store the API key securely.** It is not recoverable.

### 5. Call the API

Include your API key on every paid request:

```bash
curl https://maps.e3d.ai/api/maps/signals \
  -H "Authorization: Bearer e3d_maps_pay_abc123..."
```

Or use the `X-Payment-Key` header:

```bash
curl https://maps.e3d.ai/api/maps/signals \
  -H "X-Payment-Key: e3d_maps_pay_abc123..."
```

### Subscription API keys remain separate

`POST /api/maps/register` is still the Maps subscription auth path for rate-limited access. It issues subscription API keys managed by `e3d-maps` and is unaffected by the prepaid credit migration described here.

---

## Pricing

| Endpoint category | Examples | Cost |
|---|---|---|
| **Free** | `/maps/news`, `/maps/state`, `/maps/calibration` | 0 credits |
| **Standard** | `/maps/signals`, `/maps/routes`, `/maps/hazards`, `/maps/predictions` | 10 credits (0.01 wE3D) |
| **Premium** | `/maps/recommendations`, `/maps/cross-chain`, `/maps/notable` | 50 credits (0.05 wE3D) |
| **Write** | `/maps/outcomes` | 100 credits (0.10 wE3D) |

**1 credit = 0.001 wE3D**. Minimum purchase: 500 credits = 0.5 wE3D.

### Agent NFT Tier Discounts

Activate an agent identity NFT on [E3DNFTManager](https://etherscan.io/address/0xeED4620ff525101Ffcf7327378232CA9EF778D47) to earn discounts. Pass your tier as `agent_tier` when registering credits.

| Tier | Activation | Discount |
|---|---|---|
| 0 | No NFT | No discount |
| 1 | Active NFT | 20% off |
| 2 | Validated agent | 40% off |
| 3 | Elite agent | 60% off |

---

## Credit Balance

Check remaining credits through E3D payments:

```bash
curl "https://e3d.ai/api/payments/credits/balance?product=maps" \
  -H "Authorization: Bearer e3d_maps_pay_abc123..."
```

Response:
```json
{
  "product": "maps",
  "credits": 850,
  "wallet": "0x...",
  "agentTier": 0,
  "creditRate": "1 credit = 0.001 wE3D before discounts"
}
```

Response headers on every paid call include:

```
X-Credits-Remaining: 840
X-Credits-Used: 10
```

---

## 402 Response Format

When payment is missing or credits are exhausted, the server returns HTTP 402:

```json
{
  "x402Version": 1,
  "error": "Payment required",
  "accepts": [{
    "scheme": "exact",
    "network": "base-mainnet",
    "maxAmountRequired": "10000000000000000",
    "resource": "https://maps.e3d.ai/api/maps/signals",
    "description": "E3D Maps API — 10 credits (0.01 wE3D)",
    "payTo": "0x<treasury>",
    "maxTimeoutSeconds": 300,
    "asset": "0x<wrappedE3D>",
    "extra": {
      "prepayGuide": "https://maps.e3d.ai/docs/x402-agent-guide",
      "creditRate": "1 credit = 0.001 wE3D",
      "minPurchase": "500 credits"
    }
  }],
  "purchasePath": "POST /api/payments/credits/purchase",
  "product": "maps"
}
```

---

## Integration with openclaw

openclaw agents can add E3D Maps as a paid data source by registering credits on startup. Example configuration:

```json
{
  "dataSources": {
    "e3d-maps": {
      "baseUrl": "https://maps.e3d.ai/api",
      "auth": {
        "type": "bearer",
        "keyEnvVar": "E3D_MAPS_API_KEY"
      },
      "paymentScheme": "x402-prepay",
      "creditPurchaseUrl": "https://e3d.ai/api/payments/credits/purchase",
      "creditQuoteUrl": "https://e3d.ai/api/payments/credits/quote",
      "product": "maps"
    }
  }
}
```

Set `E3D_MAPS_API_KEY` in the openclaw runtime environment after purchasing credits.

---

## Replenishing Credits

When credits run low, repeat steps 3–4: request a new quote, transfer more wE3D to the quoted treasury address, and register the new transaction with `product: "maps"`. A new API key is issued; your old key is still valid until its balance hits zero.

To automate replenishment in your agent:

```js
async function ensureCredits(minBalance = 100) {
  const res = await fetch('https://e3d.ai/api/payments/credits/balance?product=maps', {
    headers: { 'Authorization': `Bearer ${process.env.E3D_MAPS_CREDIT_KEY}` }
  });
  const { credits } = await res.json();
  if (credits < minBalance) {
    // request quote, transfer wE3D on Base, then POST /api/payments/credits/purchase
    await purchaseCredits();
  }
}
```

## Deprecation Note

Legacy `/api/maps/credits` examples referred to an older Maps-specific alias. Use the E3D payment endpoints for new integrations:

- `POST /api/payments/credits/quote`
- `POST /api/payments/credits/purchase`
- `GET /api/payments/credits/balance?product=maps`

---

## Why E3D?

- **E3D is the unit** — all maps.e3d.ai intelligence is priced in E3D
- **Base is the rail** — sub-cent gas makes micropayments viable
- **NFT is identity** — agent tier reduces cost and signals reputation on-chain
- **Burn returns value** — treasury collects wE3D, bridges back to Ethereum, and burns, reducing E3D supply

Every API call is a vote that E3D-denominated on-chain intelligence has value.
