-- Phase 12: add dual-witness scoring columns to PredictionOutcomes.
-- Existing rows default to NULL for per-scorer accuracy (scorer did not run)
-- and to the safe defaults for scoring_method / consumer_exposure.

ALTER TABLE PredictionOutcomes
    ADD COLUMN IF NOT EXISTS heuristic_accuracy     Nullable(Float32) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS quantitative_accuracy  Nullable(Float32) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS scorer_agreement       Nullable(Float32) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS scoring_method         LowCardinality(String) DEFAULT 'heuristic',
    ADD COLUMN IF NOT EXISTS consumer_exposure      UInt32 DEFAULT 0,
    ADD COLUMN IF NOT EXISTS exogenous_accuracy     Nullable(Float32) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS induced_accuracy       Nullable(Float32) DEFAULT NULL;
