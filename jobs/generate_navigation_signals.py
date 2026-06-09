from __future__ import annotations

import argparse
import json
from typing import Sequence

from agents.runner import MapsRunner, RunnerCycleResult
from settings import MapsRuntimeSettings, MapsRunnerSettings


def run(*, dry_run: bool = False) -> RunnerCycleResult:
    runtime_settings = MapsRuntimeSettings.from_env()
    runner_settings = MapsRunnerSettings.from_env()
    runner = MapsRunner(
        runtime_settings=runtime_settings,
        runner_settings=runner_settings,
    )
    return runner.run_once(dry_run=dry_run)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate NavigationSignals for the current cycle.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print writes without inserting.")
    args = parser.parse_args(argv)
    result = run(dry_run=args.dry_run)
    print(json.dumps(result.__dict__, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
