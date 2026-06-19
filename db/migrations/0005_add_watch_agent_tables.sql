CREATE TABLE IF NOT EXISTS WatchPredictions
(
    id                           String,
    source_signal_id             String,
    source_prediction_id         String,
    signal_type                  LowCardinality(String),
    asset_scope                  Array(String),
    chain_scope                  Array(String),
    claim                        String,
    probability                  Float64,
    realized_direction_expected  LowCardinality(String),
    magnitude_expected           LowCardinality(String),
    evaluation_window_hours      UInt32,
    status                       LowCardinality(String),
    created_by_agent             LowCardinality(String),
    model                        LowCardinality(String),
    adapter                      LowCardinality(String),
    schema_version               LowCardinality(String),
    idempotency_key              String,
    created_at                   DateTime,
    inserted_at                  DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (created_at, id);

CREATE TABLE IF NOT EXISTS WatchDrafts
(
    id                      String,
    watch_prediction_id     String,
    headline                String,
    analysis                String,
    significance            String,
    x_post                  String,
    linkedin_draft          String,
    track_record_snapshot   String,
    routing                 String,
    status                  LowCardinality(String),
    created_by_agent        LowCardinality(String),
    model                   LowCardinality(String),
    adapter                 LowCardinality(String),
    schema_version          LowCardinality(String),
    created_at              DateTime,
    inserted_at             DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (created_at, id);

CREATE TABLE IF NOT EXISTS ConsumerAttestations
(
    id                   String,
    watch_prediction_id  String,
    consumer_id          String,
    acted                UInt8,
    observed_direction   LowCardinality(String),
    observed_magnitude   LowCardinality(String),
    notes                String,
    created_at           DateTime,
    inserted_at          DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (created_at, id);
