from __future__ import annotations

from pathlib import Path

from agents.runner import MapsRunner, MapsRunnerSettings, MapsRuntimeSettings


ROOT = Path(__file__).resolve().parents[2]


def test_default_question_queue_tightens_cross_chain_coverage():
    runner = MapsRunner(
        runtime_settings=MapsRuntimeSettings(),
        runner_settings=MapsRunnerSettings(),
    )

    queue = runner.load_question_queue()
    questions = {item.question for item in queue}

    assert len(queue) <= 34
    assert len(queue) == 30
    assert "Where is capital likely moving over the next 24 hours?" not in questions
    assert "Which destinations are gaining probability?" not in questions
    assert (
        "Is capital rotating from Binance-linked exchange balances into Solana or Base over the next 24 hours?"
        in questions
    )
    assert (
        "Are Base, Arbitrum, or Optimism becoming more attractive capital destinations over the next 24 hours?"
        in questions
    )
    assert (
        "Are any bridge routes into Solana or major L2s becoming hazardous or congested right now?"
        in questions
    )
    assert (
        "Is capital leaving Ethereum for Base, Arbitrum, Optimism, Solana, or Binance-linked routes over the next 24 hours?"
        in questions
    )
    assert (
        "Is capital moving into Ethereum from CEX or cross-chain bridge routes over the next 24 hours?"
        in questions
    )


def test_cross_chain_prompts_include_canonical_route_naming_rules():
    prompt_paths = [
        "prompts/capital_migration_agent.md",
        "prompts/destination_prediction_agent.md",
        "prompts/route_hazard_agent.md",
        "prompts/route_closure_agent.md",
        "prompts/route_emergence_agent.md",
        "prompts/congestion_agent.md",
    ]

    required_snippets = (
        "If the evidence does not support `Binance`, prefer `CEX`.",
        "If the evidence does not support a specific L2 name, prefer `L2_NETWORKS`.",
        "Prefer explicit route wording",
    )

    for relative_path in prompt_paths:
        content = (ROOT / relative_path).read_text(encoding="utf-8")
        for snippet in required_snippets:
            assert snippet in content, f"Missing {snippet!r} in {relative_path}"
