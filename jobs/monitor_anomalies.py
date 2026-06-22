"""Loop 4: Signal Rate Anomaly Detection job.

Deterministically checks whether any signal type is emitting at an anomalous rate
compared to a rolling baseline and writes a SignalRateAnomaly record.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Sequence
from uuid import uuid4

from clients.clickhouse_client import ClickHouseClient
from schemas.shared_enums import AnomalySeverity
from schemas.signal_rate_anomaly import SignalRateAnomaly
from settings import MapsRunnerSettings

OBSERVATION_HOURS: int = int(os.environ.get("MAPS_ANOMALY_OBSERVATION_HOURS", "1"))
BASELINE_HOURS: int = int(os.environ.get("MAPS_ANOMALY_BASELINE_HOURS", "24"))
ELEVATED_THRESHOLD: float = float(os.environ.get("MAPS_ANOMALY_ELEVATED_THRESHOLD", "2.0"))
HIGH_THRESHOLD: float = float(os.environ.get("MAPS_ANOMALY_HIGH_THRESHOLD", "4.0"))
CRITICAL_THRESHOLD: float = float(os.environ.get("MAPS_ANOMALY_CRITICAL_THRESHOLD", "8.0"))
MIN_BASELINE_SIGNALS: int = int(os.environ.get("MAPS_ANOMALY_MIN_BASELINE_SIGNALS", "2"))


def _fetch_hourly_counts(
    reader: "Any",
    *,
    since: datetime,
    until: datetime,
) -> list[dict]:
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")
    until_str = until.strftime("%Y-%m-%d %H:%M:%S")
    return reader.select(
        f"SELECT signal_type, count() AS cnt FROM NavigationSignals "
        f"WHERE created_at >= '{since_str}' AND created_at < '{until_str}' "
        f"GROUP BY signal_type FORMAT JSONEachRow"
    )


def run(
    *,
    dry_run: bool = False,
    now: datetime | None = None,
) -> int:
    from jobs.compute_signal_utility_scores import ClickHouseReadClient  # lazy to avoid UTC import
    settings = MapsRunnerSettings.from_env()
    ts = now or datetime.now(timezone.utc).replace(tzinfo=None)

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

    obs_start = ts - timedelta(hours=OBSERVATION_HOURS)
    base_start = ts - timedelta(hours=BASELINE_HOURS)

    observed = {
        r["signal_type"]: int(r["cnt"])
        for r in _fetch_hourly_counts(reader, since=obs_start, until=ts)
    }
    baseline = {
        r["signal_type"]: int(r["cnt"])
        for r in _fetch_hourly_counts(reader, since=base_start, until=ts)
    }

    written = 0
    for signal_type, obs_count in observed.items():
        base_count = baseline.get(signal_type, 0)
        if base_count < MIN_BASELINE_SIGNALS:
            continue
        baseline_rate = base_count / BASELINE_HOURS
        observed_rate = obs_count / OBSERVATION_HOURS
        if baseline_rate == 0:
            continue
        spike_ratio = observed_rate / baseline_rate
        if spike_ratio < ELEVATED_THRESHOLD:
            continue

        if spike_ratio >= CRITICAL_THRESHOLD:
            severity = AnomalySeverity.CRITICAL
        elif spike_ratio >= HIGH_THRESHOLD:
            severity = AnomalySeverity.HIGH
        else:
            severity = AnomalySeverity.ELEVATED

        anomaly = SignalRateAnomaly(
            id=f"anomaly_{uuid4().hex[:12]}",
            signal_type=signal_type,
            baseline_rate_per_hour=round(baseline_rate, 4),
            observed_rate_per_hour=round(observed_rate, 4),
            spike_ratio=round(spike_ratio, 4),
            severity=severity,
            detected_at=ts,
        )
        writer.insert_signal_rate_anomaly(anomaly)
        written += 1

    return written


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Monitor signal rate anomalies.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    count = run(dry_run=args.dry_run)
    print(f"Wrote {count} SignalRateAnomaly record(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
