-- Maps API key registry
-- ReplacingMergeTree(issued_at): revocation inserts a row with is_active=0 and
-- a later issued_at; FINAL on SELECT forces deduplication to the latest version.
CREATE TABLE IF NOT EXISTS maps_api_keys (
    key_hash          String,           -- SHA-256 hex of the raw bearer token
    wallet_address    String,           -- lowercase Ethereum address
    subscription_tier UInt8,            -- 0=none, 1=monthly, 2=annual (captured at registration)
    issued_at         DateTime64(3, 'UTC') DEFAULT now64(),
    is_active         UInt8 DEFAULT 1   -- 0 = revoked
) ENGINE = ReplacingMergeTree(issued_at)
ORDER BY key_hash
SETTINGS index_granularity = 8192;
