"""Loop 6: Adapter Health Monitoring job.

Reads scored PredictionOutcomes for the configured evaluation window,
buckets them by confidence, and writes an AdapterHealthReport.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Sequence
from uuid import uuid4

from clients.clickhouse_client import ClickHouseClient
from schemas.adapter_health_report import AdapterHealthReport, CalibrationBucket
from schemas.shared_enums import DriftSeverity
from settings import MapsRunnerSettings

EVALUATION_WINDOW_DAYS: int = int(os.environ.get("MAPS_ADAPTER_HEALTH_WINDOW_DAYS", "7"))
ADAPTER_NAME: str = os.environ.get("MAPS_ADAPTER_NAME", "base-v0")
DRIFT_MILD_THRESHOLD: float = float(os.environ.get("MAPS_ADAPTER_DRIFT_MILD", "0.10"))
DRIFT_MODERATE_THRESHOLD: float = float(os.environ.get("MAPS_ADAPTER_DRIFT_MODERATE", "0.20"))
DRIFT_SEVERE_THRESHOLD: float = float(os.environ.get("MAPS_ADAPTER_DRIFT_SEVERE", "0.30"))
MIN_SAMPLE_BUCKET: int = int(os.environ.get("MAPS_ADAPTER_MIN_BUCKET_SAMPLE", "5"))

CONFIDENCE_BUCKETS = [
    ("0.0–0.3", 0.0, 0.3),
    ("0.3–0.5", 0.3, 0.5),
    ("0.5–0.7", 0.5, 0.7),
    ("0.7–0.9", 0.7, 0.9),
    ("0.9–1.0", 0.9, 1.0),
]


def _fetch_scored_outcomes(
    reader: "Any",
    *,
    since: datetime,
    now: datetime,
) -> list[dict]:
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    return reader.select(
        "SELECT po.id, ns.signal_type, ns.confidence, po.prediction_accuracy "
        "FROM PredictionOutcomes po "
        "LEFT JOIN NavigationSignals ns ON po.navigation_signal_id = ns.id "
        f"WHERE po.created_at >= '{since_str}' AND po.created_at < '{now_str}' "
        "FORMAT JSONEachRow"
    )


def run(
    *,
    dry_run: bool = False,
    now: datetime | None = None,
) -> int:
    from jobs.compute_signal_utility_scores import ClickHouseReadClient  # lazy to avoid UTC import
    settings = MapsRunnerSettings.from_env()
    ts = now or datetime.now(timezone.utc).replace(tzinfo=None)
    since = ts - timedelta(days=EVALUATION_WINDOW_DAYS)

    reader = ClickHouseReadClient(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        database=settings.clickhouse_database,
        username=settings.clickhouse_username,
        password=settings.clickhouse_password,
        secure=settings.clickhouse_secure,
        timeout=settings.clickhouse_timeout,
    )
    writer = ClickHouseClient(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        database=settings.clickhouse_database,
        username=settings.clickhouse_username,
        password=settings.clickhouse_password,
        secure=settings.clickhouse_secure,
        timeout=settings.clickhouse_timeout,
        dry_run=dry_run,
    )

    outcomes = _fetch_scored_outcomes(reader, since=since, now=ts)
    if not outcomes:
        return 0

    accuracy_by_signal_type: dict[str, float] = {}
    type_counts: dict[str, int] = {}
    type_accuracy_sums: dict[str, float] = {}
    all_confidences: list[float] = []
    all_accuracies: list[float] = []
    calibration_errors: list[float] = []

    for row in outcomes:
        conf = row.get("confidence")
        acc = row.get("prediction_accuracy")
        if conf is None or acc is None:
            continue
        try:
            conf_f = float(conf)
            acc_f = float(acc)
        except (TypeError, ValueError):
            continue
        all_confidences.append(conf_f)
        all_accuracies.append(acc_f)
        calibration_errors.append(abs(conf_f - acc_f))

        sig_type = row.get("signal_type") or "unknown"
        type_counts[sig_type] = type_counts.get(sig_type, 0) + 1
        type_accuracy_sums[sig_type] = type_accuracy_sums.get(sig_type, 0.0) + acc_f

    for sig_type, count in type_counts.items():
        accuracy_by_signal_type[sig_type] = round(type_accuracy_sums[sig_type] / count, 4)

    overall_calibration_error = (
        round(sum(calibration_errors) / len(calibration_errors), 4)
        if calibration_errors
        else 0.0
    )

    # Build calibration buckets.
    bucket_models: list[CalibrationBucket] = []
    bucket_errors: list[float] = []
    for label, low, high in CONFIDENCE_BUCKETS:
        indices = [
            i for i, c in enumerate(all_confidences) if low <= c < high
        ]
        sample_size = len(indices)
        thin = sample_size < MIN_SAMPLE_BUCKET
        if sample_size == 0:
            mid = (low + high) / 2
            realized = 0.0
            bucket_error = mid
        else:
            realized = sum(all_accuracies[i] for i in indices) / sample_size
            predicted = sum(all_confidences[i] for i in indices) / sample_size
            bucket_error = abs(predicted - realized)
        bucket_errors.append(bucket_error)
        bucket_models.append(
            CalibrationBucket(
                bucket_label=label,
                predicted_confidence=(low + high) / 2,
                realized_accuracy=round(realized, 4),
                sample_size=sample_size,
                thin_data=thin,
            )
        )

    # Drift detection: compare current calibration error to last period.
    # Simplified: flag drift if overall error is above thresholds.
    drift_detected = overall_calibration_error >= DRIFT_MILD_THRESHOLD
    if overall_calibration_error >= DRIFT_SEVERE_THRESHOLD:
        drift_severity = DriftSeverity.SEVERE
    elif overall_calibration_error >= DRIFT_MODERATE_THRESHOLD:
        drift_severity = DriftSeverity.MODERATE
    elif overall_calibration_error >= DRIFT_MILD_THRESHOLD:
        drift_severity = DriftSeverity.MILD
    else:
        drift_severity = DriftSeverity.NONE

    retraining_recommended = drift_severity in (DriftSeverity.MODERATE, DriftSeverity.SEVERE)

    notes = (
        f"Evaluated {len(outcomes)} scored outcomes over {EVALUATION_WINDOW_DAYS} days. "
        f"Overall calibration error: {overall_calibration_error:.4f}."
    )

    report = AdapterHealthReport(
        id=f"adapter_{uuid4().hex[:12]}",
        adapter_name=ADAPTER_NAME,
        evaluation_window_days=EVALUATION_WINDOW_DAYS,
        total_scored_signals=len(outcomes),
        overall_calibration_error=overall_calibration_error,
        accuracy_by_signal_type=accuracy_by_signal_type,
        confidence_buckets=bucket_models,
        drift_detected=drift_detected,
        drift_severity=drift_severity,
        retraining_recommended=retraining_recommended,
        notes=notes,
        created_at=ts,
    )
    writer.insert_adapter_health_report(report)
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Monitor LoRA adapter calibration health.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    count = run(dry_run=args.dry_run)
    print(f"Wrote {count} AdapterHealthReport(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
