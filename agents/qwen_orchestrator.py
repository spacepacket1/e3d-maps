from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from agents.adapter_manager import AdapterManager

if TYPE_CHECKING:
    from agents.runner import MapsRunner
    from settings import MapsRuntimeSettings


@dataclass(frozen=True)
class OrchestratorResult:
    maps_cycle_ran: bool
    adapter_mode: str
    message: str


class QwenOrchestrator:
    """Coordinates the Maps adapter lifecycle within the Qwen runtime.

    Maps and the trading floor both send an X-Adapter-Path header per request.
    The Qwen server caches adapters and queues concurrent requests internally —
    no cross-app coordination is needed at the client level.

    In stub mode (enable_runtime_loading=False, the default), no explicit
    adapter loading or unloading occurs. The adapter name and path are
    forwarded as request headers. This is the correct mode for per-request
    adapter serving.

    In runtime mode (enable_runtime_loading=True), the orchestrator calls
    the adapter manager's load/unload callbacks before and after each Maps
    cycle. Use this when moving to a backend that requires explicit adapter
    management between inference runs.

    offset_seconds introduces a startup delay before the first Maps cycle.
    Use this when scheduling Maps after story scripts or thesis updates to
    avoid starting before upstream data is ready.
    """

    def __init__(
        self,
        adapter_manager: AdapterManager,
        *,
        maps_runner_factory: Callable[[], "MapsRunner"] | None = None,
        offset_seconds: int = 0,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self.adapter_manager = adapter_manager
        self._maps_runner_factory = maps_runner_factory
        self.offset_seconds = offset_seconds
        self._sleep_fn = sleep_fn

    def run_maps_cycle(self, *, dry_run: bool = False) -> OrchestratorResult:
        """Load the Maps adapter, run one cycle, then unload the adapter."""
        if self.offset_seconds > 0 and self._sleep_fn is not None:
            self._sleep_fn(float(self.offset_seconds))

        adapter_state = self.adapter_manager.load()
        ran = False
        try:
            if self._maps_runner_factory is not None:
                runner = self._maps_runner_factory()
                runner.run_once(dry_run=dry_run)
                ran = True
        finally:
            self.adapter_manager.unload()

        return OrchestratorResult(
            maps_cycle_ran=ran,
            adapter_mode=adapter_state.load_mode,
            message=(
                f"Maps cycle {'completed' if ran else 'skipped (no runner configured)'}. "
                f"Adapter mode: {adapter_state.load_mode}. "
                f"Runtime loading: {self.adapter_manager.enable_runtime_loading}."
            ),
        )

    @classmethod
    def from_settings(
        cls,
        settings: "MapsRuntimeSettings",
        *,
        maps_runner_factory: Callable[[], "MapsRunner"] | None = None,
        offset_seconds: int = 0,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> "QwenOrchestrator":
        return cls(
            adapter_manager=AdapterManager.from_settings(settings),
            maps_runner_factory=maps_runner_factory,
            offset_seconds=offset_seconds,
            sleep_fn=sleep_fn,
        )
