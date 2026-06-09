# E3D Maps Project Context

## Purpose

E3D Maps is a separate repository for navigation intelligence in the E3D ecosystem. It consumes existing E3D stories, theses, wallet intelligence, market intelligence, and outcomes to predict what is likely to happen next on-chain.

Maps agents are internal producer agents. They generate validated machine-readable objects for downstream consumers such as trading agents, treasury agents, research agents, and human supervisors.

## Core Rules

1. Build incrementally by phase from `docs/e3d_maps_navigation_intelligence_spec.md`.
2. Do not implement later phases unless the current task explicitly asks for them.
3. Do not create direct runtime imports between `e3d-maps` and `e3d-agent-trading-floor`.
4. Treat shared databases and API contracts as the integration boundary.
5. Prefer strict schema validation for all agent outputs.
6. Validate every agent output before any database write.
7. Preserve append-only data patterns and explicit record IDs where practical.
8. Keep the public `/api/maps/...` surface in the main `e3d` repository for v1.

## Current Phase Guidance

Phase 0 covers repository bootstrap and shared schema definitions only.

- Keep changes scoped to bootstrap files, folder structure, schema modules, and validation tests.
- Do not add ClickHouse migrations, clients, runner behavior, or API routes yet unless a task explicitly requests them.
- Preserve existing prompts and docs unless the task requires changes.

## Schema Guidance

- Shared enums should be centralized in `schemas/shared_enums.py`.
- Confidence values must be constrained to `0.0 <= confidence <= 1.0`.
- Required fields should fail validation when omitted.
- Unknown signal types should be rejected by default and allowed only when validation is explicitly configured to allow them.

## Repo Conventions

- Favor small, explicit modules over broad abstractions.
- Keep runtime behavior conservative until later phases define orchestration and storage.
- Add tests alongside schema behavior changes.
