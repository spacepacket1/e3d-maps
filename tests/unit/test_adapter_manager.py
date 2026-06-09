from __future__ import annotations

import pytest

from agents.adapter_manager import AdapterManager, AdapterManagerError


def test_adapter_manager_returns_stub_state_when_runtime_loading_is_disabled():
    manager = AdapterManager(
        adapter_name="base-v0",
        adapter_path="/models/base-v0",
        enable_runtime_loading=False,
    )

    state = manager.load()

    assert state.name == "base-v0"
    assert state.path == "/models/base-v0"
    assert state.is_loaded is False
    assert state.load_mode == "stub"
    assert "stub interface" in state.message
    assert manager.qwen_request_options() == {
        "adapter_name": "base-v0",
        "adapter_path": "/models/base-v0",
    }


def test_adapter_manager_calls_loader_and_unloader_when_runtime_loading_is_enabled():
    calls = []

    def loader(name, path):
        calls.append(("load", name, path))

    def unloader(name, path):
        calls.append(("unload", name, path))

    manager = AdapterManager(
        adapter_name="maps-v0.1",
        adapter_path="/models/maps-v0.1",
        enable_runtime_loading=True,
        loader=loader,
        unloader=unloader,
    )

    loaded_state = manager.load()
    unloaded_state = manager.unload()

    assert loaded_state.is_loaded is True
    assert loaded_state.load_mode == "runtime"
    assert unloaded_state.is_loaded is False
    assert calls == [
        ("load", "maps-v0.1", "/models/maps-v0.1"),
        ("unload", "maps-v0.1", "/models/maps-v0.1"),
    ]


def test_adapter_manager_requires_loader_when_runtime_loading_is_enabled():
    manager = AdapterManager(
        adapter_name="maps-v0.1",
        enable_runtime_loading=True,
    )

    with pytest.raises(AdapterManagerError, match="no loader callable"):
        manager.load()
