-- x402 credit ledger for maps.e3d.ai per-call payments
--
-- Each row is either a credit purchase (positive credit_balance) or an updated
-- balance after spending. The ReplacingMergeTree deduplicates by key_hash,
-- keeping the row with the latest last_updated timestamp.
--
-- Credit rate: 1 credit = 0.001 wE3D (wrapped E3D on Base L2)
-- Minimum purchase: 500 credits = 0.5 wE3D

CREATE TABLE IF NOT EXISTS maps_x402_credits (
    key_hash         String,
    wallet_address   String,
    credit_balance   Int64     DEFAULT 0,
    agent_tier       UInt8     DEFAULT 0,
    base_tx_hash     String    DEFAULT '',
    last_endpoint    String    DEFAULT '',
    last_updated     DateTime64(3, 'UTC') DEFAULT now64()
) ENGINE = ReplacingMergeTree(last_updated)
  ORDER BY key_hash;
