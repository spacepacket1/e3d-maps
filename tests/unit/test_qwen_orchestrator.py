from __future__ import annotations

from agents.adapter_manager import AdapterManager
from agents.qwen_orchestrator import OrchestratorResult, QwenOrchestrator


def make_manager(*, enable_runtime_loading: bool = False) -> AdapterManager:
    return AdapterManager(
        adapter_name="base-v0",
        adapter_path="./adapters_maps_v1",
        enable_runtime_loading=enable_runtime_loading,
    )


def test_orchestrator_runs_maps_cycle_in_stub_mode():
    runner_calls: list[bool] = []

    def factory():
        class FakeRunner:
            def run_once(self, *, dry_run: bool) -> None:
                runner_calls.append(dry_run)
        return FakeRunner()

    orchestrator = QwenOrchestrator(
        adapter_manager=make_manager(),
        maps_runner_factory=factory,
    )

    result = orchestrator.run_maps_cycle(dry_run=True)

    assert isinstance(result, OrchestratorResult)
    assert result.maps_cycle_ran is True
    assert result.adapter_mode == "stub"
    assert len(runner_calls) == 1
    assert runner_calls[0] is True


def test_orchestrator_without_runner_reports_not_ran():
    orchestrator = QwenOrchestrator(adapter_manager=make_manager())

    result = orchestrator.run_maps_cycle()

    assert result.maps_cycle_ran is False
    assert "skipped" in result.message


def test_orchestrator_applies_offset_delay_before_cycle():
    sleep_calls: list[float] = []

    orchestrator = QwenOrchestrator(
        adapter_manager=make_manager(),
        offset_seconds=30,
        sleep_fn=sleep_calls.append,
    )

    orchestrator.run_maps_cycle()

    assert sleep_calls == [30.0]


def test_orchestrator_no_delay_when_offset_is_zero():
    sleep_calls: list[float] = []

    orchestrator = QwenOrchestrator(
        adapter_manager=make_manager(),
        offset_seconds=0,
        sleep_fn=sleep_calls.append,
    )

    orchestrator.run_maps_cycle()

    assert sleep_calls == []


def test_orchestrator_unloads_adapter_even_if_runner_raises():
    unload_calls: list[str] = []

    def loader(name, path):
        pass

    def unloader(name, path):
        unload_calls.append(name)

    manager = AdapterManager(
        adapter_name="base-v0",
        adapter_path=None,
        enable_runtime_loading=True,
        loader=loader,
        unloader=unloader,
    )

    def factory():
        class BrokenRunner:
            def run_once(self, *, dry_run: bool) -> None:
                raise RuntimeError("runner failure")
        return BrokenRunner()

    orchestrator = QwenOrchestrator(
        adapter_manager=manager,
        maps_runner_factory=factory,
    )

    try:
        orchestrator.run_maps_cycle()
    except RuntimeError:
        pass

    assert unload_calls == ["base-v0"]


def test_orchestrator_from_settings():
    from settings import MapsRuntimeSettings

    settings = MapsRuntimeSettings(
        qwen_base_url="http://127.0.0.1:5050",
        maps_adapter_name="base-v0",
        maps_adapter_path="./adapters_maps_v1",
        maps_enable_adapter_loading=False,
    )
    orchestrator = QwenOrchestrator.from_settings(settings)

    assert isinstance(orchestrator, QwenOrchestrator)
    assert orchestrator.adapter_manager.adapter_name == "base-v0"
