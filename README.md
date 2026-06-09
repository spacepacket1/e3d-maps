# E3D Maps

E3D Maps is the navigation intelligence layer for the E3D platform. It turns on-chain evidence into machine-readable predictions about where capital is likely to move, where congestion is forming, and which routes are becoming risky for downstream autonomous agents.

## Scope

This repository owns the Maps-specific application surface:

- Maps UI
- Maps agents and prompts
- Shared Maps schemas
- Runner and scheduler code
- ClickHouse write-side integrations
- Training export and outcome scoring jobs

The main `e3d` repository continues to own the public `/api/maps/...` routes and the primary endpoint surface. This repo produces validated Maps objects that those APIs can later read and serve.

## Core Objects

Phase 0 establishes the shared schema layer for these primary Maps records:

- `NavigationSignal`
- `RoutePrediction`
- `TrafficState`
- `PredictionOutcome`
- `SignalUtilityScore`

These objects use shared enums and validation rules so agent outputs can be checked before any database write happens.

## Repository Layout

This repo is scaffolded for the structure described in the implementation spec:

- `agents/` for Maps producer agents and orchestration
- `clients/` for external service clients
- `schemas/` for shared validation models
- `db/` for migrations and seed scripts
- `jobs/` for scheduled workflows
- `training/` for datasets and exports
- `ui/` for the Maps frontend
- `tests/` for unit and integration coverage
- `prompts/` for system and agent prompts
- `docs/` for specs and implementation context

## Install

Python is the active runtime for the Phase 0 schema work.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Run Checks

```bash
pytest
```

```bash
npm test
```

## Build The UI

Phase 11 adds a static production build for `maps.e3d.ai`.

```bash
npm run build
```

The build output is written to `ui/dist/`. Serve that directory as the nginx web root for `maps.e3d.ai`.

The generated UI keeps browser requests on same-origin relative paths such as `/api/maps/state` and `/api/story-types`. That allows nginx on `maps.e3d.ai` to serve the static files and proxy API calls back to the main E3D endpoint without changing frontend code.

## Future Runtime

The repo also includes a minimal `package.json` so frontend work can grow into the `ui/` directory without changing the repo contract defined in the spec. No application runtime beyond schema validation is introduced in Phase 0.

Phase 3 adds a narrow Qwen runtime surface:

- `clients/qwen_client.py` for prompt execution against a Qwen-compatible chat endpoint
- `agents/adapter_manager.py` for Maps adapter identity and load/unload coordination
- `settings.py` for environment-driven Qwen and adapter configuration

Actual adapter loading remains an explicit stub until the serving infrastructure is defined. The interface is in place so later runner code can adopt real loading without changing callers.
