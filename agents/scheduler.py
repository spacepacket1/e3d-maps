from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field
from typing import Callable, Sequence


@dataclass
class JobConfig:
    """Configuration for a single scheduled job."""

    name: str
    run_fn: Callable[[], None]
    interval_seconds: int
    _last_run: float = field(default=-float("inf"), init=False, repr=False)

    def is_due(self, now: float) -> bool:
        return (now - self._last_run) >= self.interval_seconds

    def mark_ran(self, now: float) -> None:
        self._last_run = now


@dataclass(frozen=True)
class SchedulerResult:
    cycles: int
    jobs_run: int


class MapsJobScheduler:
    """Runs Maps jobs at configured intervals.

    The scheduler wakes on each tick, checks which jobs are due, and runs
    them in registration order. Intervals are configurable; the defaults
    match the spec-recommended cadences:

      - generate_navigation_signals: every 5 minutes
      - score_pending_predictions:   every 30 minutes
      - compute_signal_utility_scores: every 60 minutes
      - export_training_examples:    every 24 hours
      - assemble_cross_chain_activity: every 5 minutes
      - generate_maps_news: every 5 minutes

    Use from_runner_and_jobs() to build a scheduler from Maps runner and
    job callables, or construct directly with a custom JobConfig list.
    """

    DEFAULT_SIGNALS_INTERVAL = 300
    DEFAULT_SCORING_INTERVAL = 1800
    DEFAULT_UTILITY_INTERVAL = 3600
    DEFAULT_EXPORT_INTERVAL = 86400
    DEFAULT_FLOW_GRAPH_INTERVAL = 300
    DEFAULT_TRAFFIC_STATE_INTERVAL = 300
    DEFAULT_CROSS_CHAIN_ACTIVITY_INTERVAL = 300
    DEFAULT_MAPS_NEWS_INTERVAL = 300
    DEFAULT_WATCH_INTERVAL = 300
    DEFAULT_QUERY_DEMAND_INTERVAL = 900
    DEFAULT_REFLEXIVITY_INTERVAL = 600
    DEFAULT_NARRATIVE_VELOCITY_INTERVAL = 300
    DEFAULT_ANOMALY_MONITOR_INTERVAL = 300
    DEFAULT_ROUTE_HEALTH_INTERVAL = 3600
    DEFAULT_ADAPTER_HEALTH_INTERVAL = 86400
    DEFAULT_STORY_HYPOTHESIS_INTERVAL = 86400
    DEFAULT_BRIDGE_SYNTHESIS_INTERVAL = 360
    DEFAULT_TICK_SECONDS = 60

    def __init__(
        self,
        jobs: Sequence[JobConfig],
        *,
        tick_seconds: int = DEFAULT_TICK_SECONDS,
        sleep_fn: Callable[[float], None] = time.sleep,
        now_fn: Callable[[], float] = time.time,
    ) -> None:
        self.jobs = list(jobs)
        self.tick_seconds = tick_seconds
        self._sleep_fn = sleep_fn
        self._now_fn = now_fn

    def run_once(self) -> SchedulerResult:
        """Check all jobs and run any that are due. Returns after one tick."""
        import sys
        import traceback
        now = self._now_fn()
        ran = 0
        for job in self.jobs:
            if job.is_due(now):
                try:
                    job.run_fn()
                    job.mark_ran(now)
                    ran += 1
                except Exception:
                    print(f"[scheduler] job {job.name!r} failed:", file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)
                    job.mark_ran(now)
        return SchedulerResult(cycles=1, jobs_run=ran)

    def run_loop(self) -> None:
        """Run the scheduler indefinitely, sleeping tick_seconds between ticks."""
        while True:
            self.run_once()
            self._sleep_fn(float(self.tick_seconds))

    @classmethod
    def from_runner_and_jobs(
        cls,
        *,
        runner_fn: Callable[[], None],
        scorer_fn: Callable[[], None] | None = None,
        utility_fn: Callable[[], None] | None = None,
        export_fn: Callable[[], None] | None = None,
        flow_graph_fn: Callable[[], None] | None = None,
        traffic_state_fn: Callable[[], None] | None = None,
        cross_chain_activity_fn: Callable[[], None] | None = None,
        maps_news_fn: Callable[[], None] | None = None,
        watch_fn: Callable[[], None] | None = None,
        query_demand_fn: Callable[[], None] | None = None,
        reflexivity_fn: Callable[[], None] | None = None,
        narrative_velocity_fn: Callable[[], None] | None = None,
        anomaly_monitor_fn: Callable[[], None] | None = None,
        route_health_fn: Callable[[], None] | None = None,
        adapter_health_fn: Callable[[], None] | None = None,
        story_hypothesis_fn: Callable[[], None] | None = None,
        bridge_synthesis_fn: Callable[[], None] | None = None,
        signals_interval: int = DEFAULT_SIGNALS_INTERVAL,
        scoring_interval: int = DEFAULT_SCORING_INTERVAL,
        utility_interval: int = DEFAULT_UTILITY_INTERVAL,
        export_interval: int = DEFAULT_EXPORT_INTERVAL,
        flow_graph_interval: int = DEFAULT_FLOW_GRAPH_INTERVAL,
        traffic_state_interval: int = DEFAULT_TRAFFIC_STATE_INTERVAL,
        cross_chain_activity_interval: int = DEFAULT_CROSS_CHAIN_ACTIVITY_INTERVAL,
        maps_news_interval: int = DEFAULT_MAPS_NEWS_INTERVAL,
        watch_interval: int = DEFAULT_WATCH_INTERVAL,
        query_demand_interval: int = DEFAULT_QUERY_DEMAND_INTERVAL,
        reflexivity_interval: int = DEFAULT_REFLEXIVITY_INTERVAL,
        narrative_velocity_interval: int = DEFAULT_NARRATIVE_VELOCITY_INTERVAL,
        anomaly_monitor_interval: int = DEFAULT_ANOMALY_MONITOR_INTERVAL,
        route_health_interval: int = DEFAULT_ROUTE_HEALTH_INTERVAL,
        adapter_health_interval: int = DEFAULT_ADAPTER_HEALTH_INTERVAL,
        story_hypothesis_interval: int = DEFAULT_STORY_HYPOTHESIS_INTERVAL,
        bridge_synthesis_interval: int = DEFAULT_BRIDGE_SYNTHESIS_INTERVAL,
        tick_seconds: int = DEFAULT_TICK_SECONDS,
        sleep_fn: Callable[[float], None] = time.sleep,
        now_fn: Callable[[], float] = time.time,
    ) -> "MapsJobScheduler":
        jobs: list[JobConfig] = [
            JobConfig(
                name="generate_navigation_signals",
                run_fn=runner_fn,
                interval_seconds=signals_interval,
            )
        ]
        if scorer_fn is not None:
            jobs.append(
                JobConfig(
                    name="score_pending_predictions",
                    run_fn=scorer_fn,
                    interval_seconds=scoring_interval,
                )
            )
        if utility_fn is not None:
            jobs.append(
                JobConfig(
                    name="compute_signal_utility_scores",
                    run_fn=utility_fn,
                    interval_seconds=utility_interval,
                )
            )
        if export_fn is not None:
            jobs.append(
                JobConfig(
                    name="export_training_examples",
                    run_fn=export_fn,
                    interval_seconds=export_interval,
                )
            )
        if flow_graph_fn is not None:
            jobs.append(
                JobConfig(
                    name="assemble_flow_graph",
                    run_fn=flow_graph_fn,
                    interval_seconds=flow_graph_interval,
                )
            )
        if traffic_state_fn is not None:
            jobs.append(
                JobConfig(
                    name="assemble_traffic_state",
                    run_fn=traffic_state_fn,
                    interval_seconds=traffic_state_interval,
                )
            )
        if cross_chain_activity_fn is not None:
            jobs.append(
                JobConfig(
                    name="assemble_cross_chain_activity",
                    run_fn=cross_chain_activity_fn,
                    interval_seconds=cross_chain_activity_interval,
                )
            )
        if maps_news_fn is not None:
            jobs.append(
                JobConfig(
                    name="generate_maps_news",
                    run_fn=maps_news_fn,
                    interval_seconds=maps_news_interval,
                )
            )
        if watch_fn is not None:
            jobs.append(
                JobConfig(
                    name="run_watch_agent",
                    run_fn=watch_fn,
                    interval_seconds=watch_interval,
                )
            )
        if query_demand_fn is not None:
            jobs.append(
                JobConfig(
                    name="aggregate_query_demand",
                    run_fn=query_demand_fn,
                    interval_seconds=query_demand_interval,
                )
            )
        if reflexivity_fn is not None:
            jobs.append(
                JobConfig(
                    name="detect_reflexivity",
                    run_fn=reflexivity_fn,
                    interval_seconds=reflexivity_interval,
                )
            )
        if narrative_velocity_fn is not None:
            jobs.append(
                JobConfig(
                    name="compute_narrative_velocity",
                    run_fn=narrative_velocity_fn,
                    interval_seconds=narrative_velocity_interval,
                )
            )
        if anomaly_monitor_fn is not None:
            jobs.append(
                JobConfig(
                    name="monitor_anomalies",
                    run_fn=anomaly_monitor_fn,
                    interval_seconds=anomaly_monitor_interval,
                )
            )
        if route_health_fn is not None:
            jobs.append(
                JobConfig(
                    name="generate_route_health_reports",
                    run_fn=route_health_fn,
                    interval_seconds=route_health_interval,
                )
            )
        if adapter_health_fn is not None:
            jobs.append(
                JobConfig(
                    name="monitor_adapter_health",
                    run_fn=adapter_health_fn,
                    interval_seconds=adapter_health_interval,
                )
            )
        if story_hypothesis_fn is not None:
            jobs.append(
                JobConfig(
                    name="propose_story_hypotheses",
                    run_fn=story_hypothesis_fn,
                    interval_seconds=story_hypothesis_interval,
                )
            )
        if bridge_synthesis_fn is not None:
            jobs.append(
                JobConfig(
                    name="synthesize_bridge_signals",
                    run_fn=bridge_synthesis_fn,
                    interval_seconds=bridge_synthesis_interval,
                )
            )
        return cls(jobs=jobs, tick_seconds=tick_seconds, sleep_fn=sleep_fn, now_fn=now_fn)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the E3D Maps job scheduler.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="Run one scheduler tick.")
    mode.add_argument("--loop", action="store_true", help="Run the scheduler continuously.")
    parser.add_argument("--dry-run", action="store_true", help="Pass dry_run to all jobs.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    import jobs.score_pending_predictions as scorer_mod
    import jobs.compute_signal_utility_scores as utility_mod
    import jobs.export_training_examples as export_mod
    import jobs.assemble_flow_graph as flow_graph_mod
    import jobs.assemble_traffic_state as traffic_state_mod
    import jobs.assemble_cross_chain_activity as cross_chain_mod
    import jobs.generate_maps_news as maps_news_mod
    import jobs.run_watch_agent as watch_mod
    import jobs.aggregate_query_demand as query_demand_mod
    import jobs.detect_reflexivity as reflexivity_mod
    import jobs.compute_narrative_velocity as narrative_velocity_mod
    import jobs.monitor_anomalies as anomaly_mod
    import jobs.generate_route_health_reports as route_health_mod
    import jobs.monitor_adapter_health as adapter_health_mod
    import jobs.propose_story_hypotheses as story_hypothesis_mod
    import jobs.synthesize_bridge_signals as bridge_synthesis_mod
    from agents.runner import MapsRunner
    from agents.qwen_orchestrator import QwenOrchestrator
    from settings import MapsRuntimeSettings, MapsRunnerSettings

    dry_run: bool = args.dry_run

    runtime_settings = MapsRuntimeSettings.from_env()
    runner_settings = MapsRunnerSettings.from_env()
    runner = MapsRunner(
        runtime_settings=runtime_settings,
        runner_settings=runner_settings,
    )
    orchestrator = QwenOrchestrator.from_settings(
        runtime_settings,
        maps_runner_factory=lambda: runner,
    )

    scheduler = MapsJobScheduler.from_runner_and_jobs(
        runner_fn=lambda: orchestrator.run_maps_cycle(dry_run=dry_run),
        scorer_fn=lambda: scorer_mod.run(dry_run=dry_run),
        utility_fn=lambda: utility_mod.run(dry_run=dry_run),
        export_fn=lambda: export_mod.run(dry_run=dry_run),
        flow_graph_fn=lambda: flow_graph_mod.run(dry_run=dry_run),
        traffic_state_fn=lambda: traffic_state_mod.run(dry_run=dry_run),
        cross_chain_activity_fn=lambda: cross_chain_mod.run(dry_run=dry_run),
        maps_news_fn=lambda: maps_news_mod.run(dry_run=dry_run),
        watch_fn=lambda: watch_mod.run(dry_run=dry_run),
        query_demand_fn=lambda: query_demand_mod.run(dry_run=dry_run),
        reflexivity_fn=lambda: reflexivity_mod.run(dry_run=dry_run),
        narrative_velocity_fn=lambda: narrative_velocity_mod.run(dry_run=dry_run),
        anomaly_monitor_fn=lambda: anomaly_mod.run(dry_run=dry_run),
        route_health_fn=lambda: route_health_mod.run(dry_run=dry_run),
        adapter_health_fn=lambda: adapter_health_mod.run(dry_run=dry_run),
        story_hypothesis_fn=lambda: story_hypothesis_mod.run(dry_run=dry_run),
        bridge_synthesis_fn=lambda: bridge_synthesis_mod.run(dry_run=dry_run),
        signals_interval=runner_settings.run_interval_seconds,
        scoring_interval=runner_settings.scoring_interval_seconds,
        utility_interval=runner_settings.utility_interval_seconds,
        export_interval=runner_settings.export_interval_seconds,
        flow_graph_interval=runner_settings.flow_graph_interval_seconds,
        traffic_state_interval=runner_settings.traffic_state_interval_seconds,
        cross_chain_activity_interval=runner_settings.cross_chain_activity_interval_seconds,
        maps_news_interval=runner_settings.maps_news_interval_seconds,
        watch_interval=runner_settings.watch_interval_seconds,
        query_demand_interval=runner_settings.query_demand_interval_seconds,
        reflexivity_interval=runner_settings.reflexivity_interval_seconds,
        narrative_velocity_interval=runner_settings.narrative_velocity_interval_seconds,
        anomaly_monitor_interval=runner_settings.anomaly_monitor_interval_seconds,
        route_health_interval=runner_settings.route_health_interval_seconds,
        adapter_health_interval=runner_settings.adapter_health_interval_seconds,
        story_hypothesis_interval=runner_settings.story_hypothesis_interval_seconds,
        bridge_synthesis_interval=runner_settings.bridge_synthesis_interval_seconds,
        tick_seconds=runner_settings.scheduler_tick_seconds,
    )

    if args.once:
        result = scheduler.run_once()
        print(f"Scheduler tick complete: {result.jobs_run} job(s) ran.")
        return 0

    scheduler.run_loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
