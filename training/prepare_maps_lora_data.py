#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any, Iterable


SYSTEM_PROMPT = (
    "You are the E3D Maps navigation intelligence adapter. "
    "Return strict JSON only. Ground every prediction in the supplied context, "
    "avoid unsupported entities, and keep confidence calibrated."
)


AGENT_PROMPTS: dict[str, str] = {
    "watch_prediction": (
        "Given a notable Maps signal, emit one falsifiable watch prediction. "
        "Return JSON with claim, realized_direction_expected, magnitude_expected, "
        "and evaluation_window_hours."
    ),
    "default": (
        "Given the Maps question and context JSON, emit one NavigationSignal JSON object. "
        "The answer must be concise, evidence-bound, and calibrated."
    ),
}


def load_examples(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                key = json.dumps(
                    {
                        "source": row.get("source") or "navigation_signal",
                        "watch_prediction_id": row.get("watch_prediction_id"),
                        "navigation_signal_id": row.get("navigation_signal_id"),
                        "question": row.get("question"),
                        "answer": row.get("answer"),
                        "outcome_id": (row.get("outcome") or {}).get("id"),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)
    return rows


def prediction_accuracy(row: dict[str, Any]) -> float:
    outcome = row.get("outcome") or {}
    try:
        return float(outcome.get("prediction_accuracy") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def build_user_content(row: dict[str, Any]) -> str:
    payload = {
        "question": row.get("question"),
        "signal_type": row.get("signal_type"),
        "context": row.get("context") or {},
        "outcome_label": {
            "prediction_accuracy": prediction_accuracy(row),
            "realized_direction": (row.get("outcome") or {}).get("realized_direction"),
            "realized_magnitude": (row.get("outcome") or {}).get("realized_magnitude"),
            "scoring_method": row.get("scoring_method"),
        },
    }
    return "Maps training example:\n" + json.dumps(payload, sort_keys=True, separators=(",", ":"))


def build_assistant_content(row: dict[str, Any]) -> str:
    if row.get("source") == "watch_prediction":
        context = row.get("context") or {}
        payload = {
            "claim": row.get("answer"),
            "realized_direction_expected": context.get("realized_direction_expected"),
            "magnitude_expected": context.get("magnitude_expected"),
            "evaluation_window_hours": context.get("evaluation_window_hours"),
        }
    else:
        context = row.get("context") or {}
        payload = {
            "signal_type": row.get("signal_type"),
            "question": row.get("question"),
            "answer": row.get("answer"),
            "confidence": row.get("confidence"),
            "origin": context.get("origin"),
            "destination": context.get("destination"),
            "asset_scope": context.get("asset_scope") or [],
            "chain_scope": context.get("chain_scope") or [],
            "time_horizon_hours": context.get("time_horizon_hours"),
            "risk_level": context.get("risk_level"),
            "signal_strength": context.get("signal_strength"),
            "market_state": context.get("market_state"),
            "evidence": context.get("evidence") or [],
            "recommended_route": context.get("recommended_route"),
            "recommended_action": context.get("recommended_action"),
        }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def to_lora_row(row: dict[str, Any]) -> dict[str, Any]:
    source = str(row.get("source") or "navigation_signal")
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"{AGENT_PROMPTS.get(source, AGENT_PROMPTS['default'])}\n\n{build_user_content(row)}",
            },
            {"role": "assistant", "content": build_assistant_content(row)},
        ],
        "source": source,
        "signal_type": row.get("signal_type"),
        "navigation_signal_id": row.get("navigation_signal_id"),
        "watch_prediction_id": row.get("watch_prediction_id"),
        "prediction_accuracy": prediction_accuracy(row),
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def split_rows(rows: list[dict[str, Any]], *, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    shuffled = list(rows)
    random.Random(seed).shuffle(shuffled)
    n = len(shuffled)
    valid_n = max(1, int(n * 0.1)) if n >= 20 else max(0, n // 10)
    test_n = max(1, int(n * 0.1)) if n >= 20 else max(0, n // 10)
    valid = shuffled[:valid_n]
    test = shuffled[valid_n : valid_n + test_n]
    train = shuffled[valid_n + test_n :]
    return train, valid, test


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Maps examples for MLX LoRA training.")
    parser.add_argument("--input", action="append", default=[], help="JSONL export file. May be repeated.")
    parser.add_argument("--input-dir", default="training/exports", help="Directory of maps_training_examples_*.jsonl files.")
    parser.add_argument("--output", default="/Users/mini/clawd/e3d/data/maps", help="Output dataset directory.")
    parser.add_argument("--min-accuracy", type=float, default=0.6)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    input_paths = [Path(value) for value in args.input]
    input_dir = Path(args.input_dir)
    if input_dir.exists():
        input_paths.extend(sorted(input_dir.glob("maps_training_examples_*.jsonl")))

    raw_rows = load_examples(input_paths)
    filtered = [row for row in raw_rows if prediction_accuracy(row) >= args.min_accuracy]
    lora_rows = [to_lora_row(row) for row in filtered]
    train, valid, test = split_rows(lora_rows, seed=args.seed)

    output = Path(args.output)
    write_jsonl(output / "train.jsonl", train)
    write_jsonl(output / "valid.jsonl", valid)
    write_jsonl(output / "test.jsonl", test)
    summary = {
        "raw_count": len(raw_rows),
        "filtered_count": len(filtered),
        "min_accuracy": args.min_accuracy,
        "train": len(train),
        "valid": len(valid),
        "test": len(test),
    }
    (output / "metadata.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
