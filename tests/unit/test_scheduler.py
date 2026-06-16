from __future__ import annotations

from agents.scheduler import JobConfig, MapsJobScheduler, SchedulerResult


def test_job_is_due_when_interval_has_elapsed():
    calls: list[None] = []
    job = JobConfig(name="test_job", run_fn=calls.append, interval_seconds=300)

    assert job.is_due(now=0.0)
    job.mark_ran(0.0)
    assert not job.is_due(now=299.0)
    assert job.is_due(now=300.0)


def test_run_once_runs_due_jobs_and_skips_others():
    fast_calls: list[None] = []
    slow_calls: list[None] = []

    now_values = [500.0]

    def now_fn():
        return now_values[0]

    scheduler = MapsJobScheduler(
        jobs=[
            JobConfig(name="fast", run_fn=lambda: fast_calls.append(None), interval_seconds=100),
            JobConfig(name="slow", run_fn=lambda: slow_calls.append(None), interval_seconds=1000),
        ],
        now_fn=now_fn,
    )

    result = scheduler.run_once()

    assert result.jobs_run == 2
    assert len(fast_calls) == 1
    assert len(slow_calls) == 1

    result2 = scheduler.run_once()

    assert result2.jobs_run == 0
    assert len(fast_calls) == 1

    now_values[0] = 600.0
    result3 = scheduler.run_once()

    assert result3.jobs_run == 1
    assert len(fast_calls) == 2
    assert len(slow_calls) == 1


def test_run_once_returns_scheduler_result():
    scheduler = MapsJobScheduler(jobs=[])
    result = scheduler.run_once()

    assert isinstance(result, SchedulerResult)
    assert result.cycles == 1
    assert result.jobs_run == 0


def test_run_loop_sleeps_between_ticks():
    sleep_calls: list[float] = []
    tick_count = [0]

    def now_fn():
        return float(tick_count[0] * 1000)

    def sleep_fn(seconds: float) -> None:
        sleep_calls.append(seconds)
        tick_count[0] += 1
        if tick_count[0] >= 3:
            raise StopIteration

    scheduler = MapsJobScheduler(
        jobs=[],
        tick_seconds=60,
        sleep_fn=sleep_fn,
        now_fn=now_fn,
    )

    try:
        scheduler.run_loop()
    except StopIteration:
        pass

    assert sleep_calls == [60.0, 60.0, 60.0]


def test_from_runner_and_jobs_builds_four_jobs():
    runner_calls: list[None] = []
    scorer_calls: list[None] = []
    utility_calls: list[None] = []
    export_calls: list[None] = []

    scheduler = MapsJobScheduler.from_runner_and_jobs(
        runner_fn=lambda: runner_calls.append(None),
        scorer_fn=lambda: scorer_calls.append(None),
        utility_fn=lambda: utility_calls.append(None),
        export_fn=lambda: export_calls.append(None),
    )

    assert len(scheduler.jobs) == 4
    assert scheduler.jobs[0].name == "generate_navigation_signals"
    assert scheduler.jobs[1].name == "score_pending_predictions"
    assert scheduler.jobs[2].name == "compute_signal_utility_scores"
    assert scheduler.jobs[3].name == "export_training_examples"

    result = scheduler.run_once()
    assert result.jobs_run == 4
    assert len(runner_calls) == 1
    assert len(scorer_calls) == 1
    assert len(utility_calls) == 1
    assert len(export_calls) == 1


def test_from_runner_and_jobs_includes_flow_graph():
    flow_graph_calls: list[None] = []

    scheduler = MapsJobScheduler.from_runner_and_jobs(
        runner_fn=lambda: None,
        flow_graph_fn=lambda: flow_graph_calls.append(None),
    )

    names = [j.name for j in scheduler.jobs]
    assert "assemble_flow_graph" in names
    assert len(scheduler.jobs) == 2

    result = scheduler.run_once()
    assert result.jobs_run == 2
    assert len(flow_graph_calls) == 1


def test_from_runner_and_jobs_includes_phase4_jobs_in_order():
    calls: list[str] = []

    scheduler = MapsJobScheduler.from_runner_and_jobs(
        runner_fn=lambda: calls.append("signals"),
        traffic_state_fn=lambda: calls.append("traffic_state"),
        cross_chain_activity_fn=lambda: calls.append("cross_chain"),
        maps_news_fn=lambda: calls.append("maps_news"),
    )

    names = [j.name for j in scheduler.jobs]
    assert names == [
        "generate_navigation_signals",
        "assemble_traffic_state",
        "assemble_cross_chain_activity",
        "generate_maps_news",
    ]

    result = scheduler.run_once()
    assert result.jobs_run == 4
    assert calls == ["signals", "traffic_state", "cross_chain", "maps_news"]


def test_from_runner_and_jobs_phase4_intervals_are_configurable():
    scheduler = MapsJobScheduler.from_runner_and_jobs(
        runner_fn=lambda: None,
        cross_chain_activity_fn=lambda: None,
        maps_news_fn=lambda: None,
        cross_chain_activity_interval=420,
        maps_news_interval=180,
    )

    cross_chain_job = next(j for j in scheduler.jobs if j.name == "assemble_cross_chain_activity")
    maps_news_job = next(j for j in scheduler.jobs if j.name == "generate_maps_news")
    assert cross_chain_job.interval_seconds == 420
    assert maps_news_job.interval_seconds == 180


def test_from_runner_and_jobs_flow_graph_uses_configured_interval():
    scheduler = MapsJobScheduler.from_runner_and_jobs(
        runner_fn=lambda: None,
        flow_graph_fn=lambda: None,
        flow_graph_interval=600,
    )

    fg_job = next(j for j in scheduler.jobs if j.name == "assemble_flow_graph")
    assert fg_job.interval_seconds == 600


def test_from_runner_and_jobs_omits_optional_jobs():
    scheduler = MapsJobScheduler.from_runner_and_jobs(
        runner_fn=lambda: None,
    )

    assert len(scheduler.jobs) == 1
    assert scheduler.jobs[0].name == "generate_navigation_signals"


def test_scheduler_uses_configured_intervals():
    scheduler = MapsJobScheduler.from_runner_and_jobs(
        runner_fn=lambda: None,
        scorer_fn=lambda: None,
        signals_interval=60,
        scoring_interval=120,
    )

    assert scheduler.jobs[0].interval_seconds == 60
    assert scheduler.jobs[1].interval_seconds == 120
