CREATE TABLE IF NOT EXISTS FlowGraphSnapshots
(
    id           String,
    signal_count UInt32,
    node_count   UInt32,
    edge_count   UInt32,
    created_at   DateTime,
    inserted_at  DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (created_at, id);

CREATE TABLE IF NOT EXISTS FlowGraphEdges
(
    id                String,
    snapshot_id       String,
    origin            String,
    destination       String,
    strength          LowCardinality(String),
    confidence        Float32,
    hazard_level      LowCardinality(String),
    source_signal_ids Array(String),
    edge_status       LowCardinality(String),
    created_at        DateTime,
    inserted_at       DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (created_at, snapshot_id, id);
