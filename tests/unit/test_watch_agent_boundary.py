from __future__ import annotations

import ast
from pathlib import Path

import pytest

# The Watch Agent is the reference public-contract consumer: it must read E3D
# Maps ONLY through the public /api/maps HTTP surface (WatchFeedClient) and must
# NOT import producer internals. This test enforces that boundary.

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

WATCH_MODULES = [
    "agents/watch_agent.py",
    "agents/watch_draft_generator.py",
    "jobs/run_watch_agent.py",
]

# Forbidden import substrings (producer internals).
FORBIDDEN_SUBSTRINGS = [
    "maps_news_agent",
    "jobs.generate_",
    "assembler",
    "_producer",
    "producer_",
]

# Specific producer modules that must never be imported by the watch path.
FORBIDDEN_MODULES = {
    "agents.maps_news_agent",
    "agents.runner",
    "agents.qwen_orchestrator",
    "services.cross_chain_activity_assembler",
    "jobs.generate_maps_news",
    "jobs.generate_navigation_signals",
}


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    return modules


@pytest.mark.parametrize("rel_path", WATCH_MODULES)
def test_watch_module_imports_no_producer_internals(rel_path):
    source = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
    modules = _imported_modules(source)

    for module in modules:
        for forbidden in FORBIDDEN_SUBSTRINGS:
            assert forbidden not in module, (
                f"{rel_path} imports forbidden producer internal {module!r} "
                f"(matched {forbidden!r})"
            )
        assert module not in FORBIDDEN_MODULES, (
            f"{rel_path} imports forbidden producer module {module!r}"
        )


@pytest.mark.parametrize("rel_path", WATCH_MODULES)
def test_watch_module_consumes_maps_only_via_feed_client(rel_path):
    """Any *_agent producer import other than the watch agents themselves is a
    boundary violation; the only Maps-read seam allowed is WatchFeedClient."""
    source = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
    modules = _imported_modules(source)

    producer_agents = {
        module
        for module in modules
        if module.startswith("agents.") and module.endswith("_agent")
        and module not in {"agents.watch_agent", "agents.base_agent"}
    }
    assert not producer_agents, f"{rel_path} imports producer agents: {producer_agents}"


def test_run_watch_agent_uses_watch_feed_client():
    source = (REPO_ROOT / "jobs/run_watch_agent.py").read_text(encoding="utf-8")
    assert "watch_feed_client" in source
