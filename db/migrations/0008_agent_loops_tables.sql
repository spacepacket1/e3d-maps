-- Agent loops tables (Loop 1-8 implementation)
-- Adds storage for: query demand intelligence, signal rate anomalies,
-- route health reports, adapter health reports, and story hypotheses.

-- Loop 1: Query Demand Intelligence
CREATE TABLE IF NOT EXISTS QueryAccessLogs
(
    id                          String,
    endpoint                    LowCardinality(String),
    destination_filter          String    DEFAULT '',
    signal_type_filter          LowCardinality(String) DEFAULT '',
    time_horizon_hours_filter   Nullable(UInt32),
    -- SHA-256 of api_key or IP, truncated to 16 hex chars for k-anonymity.
    caller_id_hash              String,
    requested_at                DateTime,
    inserted_at                 DateTime  DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (requested_at, id)
TTL requested_at + INTERVAL 90 DAY;

CREATE TABLE IF NOT EXISTS SignalDemandStates
(
    id                              String,
    window_start                    DateTime,
    window_end                      DateTime,
    total_queries                   UInt32    DEFAULT 0,
    queries_by_destination_json     String    DEFAULT '[]',
    queries_by_signal_type_json     String    DEFAULT '[]',
    avg_requested_time_horizon_hours Nullable(Float32),
    urgency_trend                   LowCardinality(String) DEFAULT 'stable',
    top_destinations_json           String    DEFAULT '[]',
    demand_surge_destinations_json  String    DEFAULT '[]',
    created_at                      DateTime,
    inserted_at                     DateTime  DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (created_at, id);

-- Loop 4: Signal Rate Anomaly Detection
CREATE TABLE IF NOT EXISTS SignalRateAnomalies
(
    id                          String,
    signal_type                 LowCardinality(String),
    baseline_rate_per_hour      Float32,
    observed_rate_per_hour      Float32,
    spike_ratio                 Float32,
    severity                    LowCardinality(String),
    detected_at                 DateTime,
    inserted_at                 DateTime  DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (detected_at, id)
TTL detected_at + INTERVAL 30 DAY;

-- Loop 5: Route Health Reports
CREATE TABLE IF NOT EXISTS RouteHealthReports
(
    id                              String,
    protocol_or_chain               String,
    report_scope                    LowCardinality(String),
    health_score                    Float32,
    traffic_trend                   LowCardinality(String),
    congestion_level                LowCardinality(String),
    hazard_level                    LowCardinality(String),
    route_emergence_count           UInt32   DEFAULT 0,
    route_closure_count             UInt32   DEFAULT 0,
    dominant_inflow_source          String   DEFAULT '',
    dominant_outflow_destination    String   DEFAULT '',
    supporting_signal_ids           Array(String),
    summary                         String,
    created_by_agent                LowCardinality(String),
    created_at                      DateTime,
    inserted_at                     DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (created_at, protocol_or_chain);

-- Loop 6: Adapter Health Reports
CREATE TABLE IF NOT EXISTS AdapterHealthReports
(
    id                          String,
    adapter_name                LowCardinality(String),
    evaluation_window_days      UInt32,
    total_scored_signals        UInt32   DEFAULT 0,
    overall_calibration_error   Nullable(Float32),
    accuracy_by_signal_type_json String  DEFAULT '{}',
    confidence_buckets_json     String   DEFAULT '[]',
    drift_detected              UInt8    DEFAULT 0,
    drift_severity              LowCardinality(String) DEFAULT 'none',
    retraining_recommended      UInt8    DEFAULT 0,
    notes                       String   DEFAULT '',
    created_at                  DateTime,
    inserted_at                 DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (created_at, adapter_name);

-- Loop 7: Story Hypotheses
CREATE TABLE IF NOT EXISTS StoryHypotheses
(
    id                                  String,
    proposed_story_type                 String,
    description                         String,
    detection_rationale                 String,
    supporting_on_chain_patterns_json   String   DEFAULT '[]',
    related_existing_story_types_json   String   DEFAULT '[]',
    example_evidence_json               String   DEFAULT '[]',
    supporting_signal_ids               Array(String),
    confidence                          Float32,
    status                              LowCardinality(String) DEFAULT 'proposed',
    created_by_agent                    LowCardinality(String),
    created_at                          DateTime,
    inserted_at                         DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (created_at, id);
