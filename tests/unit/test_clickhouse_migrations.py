from __future__ import annotations

from pathlib import Path


def test_phase_1_migration_defines_all_required_maps_tables():
    migration_path = Path("db/migrations/0001_create_maps_tables.sql")
    migration_sql = migration_path.read_text()

    assert "CREATE TABLE IF NOT EXISTS NavigationSignals" in migration_sql
    assert "CREATE TABLE IF NOT EXISTS RoutePredictions" in migration_sql
    assert "CREATE TABLE IF NOT EXISTS TrafficStates" in migration_sql
    assert "CREATE TABLE IF NOT EXISTS PredictionOutcomes" in migration_sql
    assert "CREATE TABLE IF NOT EXISTS SignalUtilityScores" in migration_sql
    assert "CREATE TABLE IF NOT EXISTS StoryTypeDefinitions" in migration_sql


def test_phase_1_migration_uses_mergetree_and_insert_timestamps():
    migration_sql = Path("db/migrations/0001_create_maps_tables.sql").read_text()

    assert migration_sql.count("ENGINE = MergeTree") == 6
    assert migration_sql.count("inserted_at DateTime DEFAULT now()") == 5


def test_phase_1_maps_news_cross_chain_migration_matches_repo_conventions():
    migration_sql = Path("db/migrations/0004_add_maps_news_and_cross_chain_tables.sql").read_text()

    assert "CREATE TABLE IF NOT EXISTS MapsNewsBriefs" in migration_sql
    assert "CREATE TABLE IF NOT EXISTS CrossChainActivityStates" in migration_sql
    assert "top_routes_json" in migration_sql
    assert "active_hazards_json" in migration_sql
    assert migration_sql.count("ENGINE = MergeTree") == 2
    assert migration_sql.count("inserted_at") == 2
