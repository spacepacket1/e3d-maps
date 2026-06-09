from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from settings import MapsRuntimeSettings


class AdapterManagerError(RuntimeError):
    """Raised when adapter lifecycle orchestration fails."""


@dataclass(frozen=True)
class AdapterState:
    name: str
    path: str | None = None
    is_loaded: bool = False
    load_mode: str = "stub"
    message: str = ""


class AdapterManager:
    def __init__(
        self,
        *,
        adapter_name: str,
        adapter_path: str | None = None,
        enable_runtime_loading: bool = False,
        loader: Callable[[str, str | None], None] | None = None,
        unloader: Callable[[str, str | None], None] | None = None,
    ) -> None:
        self.adapter_name = adapter_name
        self.adapter_path = adapter_path
        self.enable_runtime_loading = enable_runtime_loading
        self._loader = loader
        self._unloader = unloader
        self._active_state: AdapterState | None = None

    @classmethod
    def from_settings(
        cls,
        settings: MapsRuntimeSettings,
        *,
        loader: Callable[[str, str | None], None] | None = None,
        unloader: Callable[[str, str | None], None] | None = None,
    ) -> "AdapterManager":
        return cls(
            adapter_name=settings.maps_adapter_name,
            adapter_path=settings.maps_adapter_path,
            enable_runtime_loading=settings.maps_enable_adapter_loading,
            loader=loader,
            unloader=unloader,
        )

    @property
    def active_state(self) -> AdapterState | None:
        return self._active_state

    def load(self) -> AdapterState:
        if not self.enable_runtime_loading:
            self._active_state = AdapterState(
                name=self.adapter_name,
                path=self.adapter_path,
                is_loaded=False,
                load_mode="stub",
                message=(
                    "Runtime adapter loading is not configured; using the stub interface "
                    "and preserving adapter metadata for callers."
                ),
            )
            return self._active_state

        if self._loader is None:
            raise AdapterManagerError(
                "Runtime adapter loading is enabled, but no loader callable was configured."
            )

        self._loader(self.adapter_name, self.adapter_path)
        self._active_state = AdapterState(
            name=self.adapter_name,
            path=self.adapter_path,
            is_loaded=True,
            load_mode="runtime",
            message="Maps adapter loaded.",
        )
        return self._active_state

    def unload(self) -> AdapterState:
        state = self._active_state or AdapterState(
            name=self.adapter_name,
            path=self.adapter_path,
            is_loaded=False,
            load_mode="stub" if not self.enable_runtime_loading else "runtime",
            message="Maps adapter was not active.",
        )

        if state.is_loaded and self._unloader is None:
            raise AdapterManagerError(
                "A runtime-loaded adapter is active, but no unloader callable was configured."
            )

        if state.is_loaded and self._unloader is not None:
            self._unloader(self.adapter_name, self.adapter_path)

        self._active_state = None
        return AdapterState(
            name=state.name,
            path=state.path,
            is_loaded=False,
            load_mode=state.load_mode,
            message="Maps adapter released." if state.is_loaded else state.message,
        )

    def qwen_request_options(self) -> dict[str, str]:
        payload = {"adapter_name": self.adapter_name}
        if self.adapter_path:
            payload["adapter_path"] = self.adapter_path
        return payload
