ALTER TABLE maps_api_keys
    ADD COLUMN IF NOT EXISTS capabilities_json String DEFAULT '{}';

ALTER TABLE maps_api_keys
    ADD COLUMN IF NOT EXISTS discount_source String DEFAULT 'active_subscription';

ALTER TABLE maps_api_keys
    ADD COLUMN IF NOT EXISTS capabilities_refreshed_at DateTime64(3, 'UTC') DEFAULT now64();

ALTER TABLE maps_api_keys
    ADD COLUMN IF NOT EXISTS capabilities_expires_at Nullable(DateTime64(3, 'UTC')) DEFAULT NULL;
