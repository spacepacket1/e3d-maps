CREATE TABLE IF NOT EXISTS NavigationSignals
(
    id String,
    signal_type LowCardinality(String),
    question String,
    answer String,
    origin String,
    destination String,
    asset_scope Array(String),
    chain_scope Array(String),
    time_horizon_hours UInt32,
    confidence Float32,
    risk_level LowCardinality(String),
    signal_strength LowCardinality(String),
    market_state LowCardinality(String),
    supporting_story_ids Array(String),
    supporting_thesis_ids Array(String),
    supporting_action_ids Array(String),
    supporting_outcome_ids Array(String),
    evidence_json String,
    recommended_route_json String,
    recommended_action String,
    created_by_agent LowCardinality(String),
    model LowCardinality(String),
    adapter LowCardinality(String),
    schema_version LowCardinality(String),
    outcome_status LowCardinality(String),
    created_at DateTime,
    inserted_at DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (created_at, id);

CREATE TABLE IF NOT EXISTS RoutePredictions
(
    id String,
    navigation_signal_id String,
    route_type LowCardinality(String),
    origin String,
    destination String,
    expected_flow_direction LowCardinality(String),
    expected_flow_magnitude LowCardinality(String),
    time_horizon_hours UInt32,
    confidence Float32,
    hazards Array(String),
    supporting_story_ids Array(String),
    created_by_agent LowCardinality(String),
    model LowCardinality(String),
    adapter LowCardinality(String),
    schema_version LowCardinality(String),
    created_at DateTime,
    inserted_at DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (created_at, id);

CREATE TABLE IF NOT EXISTS TrafficStates
(
    id String,
    scope String,
    market_state LowCardinality(String),
    dominant_flows_json String,
    congestion_zones Array(String),
    hazards Array(String),
    top_destinations_json String,
    created_by_agent LowCardinality(String),
    model LowCardinality(String),
    adapter LowCardinality(String),
    schema_version LowCardinality(String),
    created_at DateTime,
    inserted_at DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (created_at, id);

CREATE TABLE IF NOT EXISTS PredictionOutcomes
(
    id String,
    navigation_signal_id String,
    route_prediction_id String,
    evaluation_window_hours UInt32,
    prediction_accuracy Float32,
    realized_direction LowCardinality(String),
    realized_magnitude LowCardinality(String),
    map_prediction_correct UInt8,
    notes String,
    created_by_agent LowCardinality(String),
    model LowCardinality(String),
    adapter LowCardinality(String),
    schema_version LowCardinality(String),
    created_at DateTime,
    inserted_at DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (created_at, id);

CREATE TABLE IF NOT EXISTS SignalUtilityScores
(
    id String,
    navigation_signal_id String,
    sample_size UInt32,
    prediction_accuracy Float32,
    economic_utility Float32,
    risk_reduction_utility Float32,
    confidence_calibration_error Float32,
    execution_adjusted_utility Float32,
    final_signal_utility_score Float32,
    linked_action_ids Array(String),
    linked_outcome_ids Array(String),
    created_at DateTime,
    inserted_at DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (created_at, id);

CREATE TABLE IF NOT EXISTS StoryTypeDefinitions
(
    story_type String,
    display_name String,
    category LowCardinality(String),
    human_meaning String,
    agent_meaning String,
    inputs Array(String),
    outputs Array(String),
    example_questions Array(String),
    related_navigation_signal_types Array(String),
    schema_version LowCardinality(String),
    created_at DateTime,
    updated_at DateTime
)
ENGINE = MergeTree
ORDER BY story_type;
