CREATE TABLE IF NOT EXISTS MapsNewsBriefs
(
    id                     String,
    scope                  String,
    headline               String,
    summary                String,
    stance                 LowCardinality(String),
    supporting_signal_ids  Array(String),
    supporting_story_ids   Array(String),
    supporting_thesis_ids  Array(String),
    tags                   Array(String),
    created_by_agent       LowCardinality(String),
    model                  LowCardinality(String),
    adapter                LowCardinality(String),
    schema_version         LowCardinality(String),
    created_at             DateTime,
    inserted_at            DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (created_at, id);

CREATE TABLE IF NOT EXISTS CrossChainActivityStates
(
    id                             String,
    scope                          String,
    market_bias                    LowCardinality(String),
    top_routes_json                String,
    active_hazards_json            String,
    active_congestion_json         String,
    top_destinations_json          String,
    ethereum_outbound_routes_json  String,
    ethereum_inbound_routes_json   String,
    supporting_signal_ids          Array(String),
    created_by_agent               LowCardinality(String),
    schema_version                 LowCardinality(String),
    created_at                     DateTime,
    inserted_at                    DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (created_at, id);
