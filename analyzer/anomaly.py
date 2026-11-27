"""Anomaly detection for the NOC monitoring toolkit."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
from typing import Any

from storage.database import DB_PATH, get_metrics, get_service_checks

WINDOW_SIZE = 30
MIN_HISTORY_SAMPLES = 5
WARNING_Z_THRESHOLD = 3.0
CRITICAL_Z_THRESHOLD = 5.0

DEFAULT_CYCLE_SECONDS = 5.0
MAX_VALID_CYCLE_SECONDS = 60.0

MIN_STD_PERCENT = 0.5
MIN_STD_NETWORK_BPS = 100.0
MIN_STD_LATENCY_MS = 5.0

DISK_WARNING_THRESHOLD = 85.0
DISK_CRITICAL_THRESHOLD = 90.0
HTTP_LATENCY_CRITICAL_MS = 1000.0

RESULT_FIELDS = {
    "node_id",
    "timestamp_utc",
    "metric_name",
    "current_value",
    "mean",
    "std",
    "z_score",
    "is_anomaly",
    "severity",
    "message",
}

def _parse_iso_utc(timestamp_str: str) -> datetime | None:
    if not isinstance(timestamp_str, str) or not timestamp_str.strip():
        return None

    try:
        clean_str = timestamp_str.strip().replace("Z", "+00:00")
        return datetime.fromisoformat(clean_str)
    except ValueError:
        return None

def _calculate_mean_and_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0

    n = len(values)
    mean_val = sum(values) / n
    variance = sum((value - mean_val) ** 2 for value in values) / n
    std_val = math.sqrt(variance)

    return mean_val, std_val

def _make_result(
    *,
    node_id: str,
    timestamp_utc: str,
    metric_name: str,
    current_value: float,
    mean: float | None,
    std: float | None,
    z_score: float | None,
    is_anomaly: bool,
    severity: str,
    message: str,
) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "timestamp_utc": timestamp_utc,
        "metric_name": metric_name,
        "current_value": round(current_value, 2),
        "mean": round(mean, 2) if mean is not None else None,
        "std": round(std, 2) if std is not None else None,
        "z_score": round(z_score, 2) if z_score is not None else None,
        "is_anomaly": is_anomaly,
        "severity": severity,
        "message": message,
    }

def _apply_static_threshold(
    metric_name: str,
    current_value: float,
) -> tuple[str, str] | None:
    if metric_name == "disk_percent":
        if current_value > DISK_CRITICAL_THRESHOLD:
            return (
                "CRITICAL",
                f"[CRITICAL] disk usage is {current_value:.2f}% "
                f"(exceeded {DISK_CRITICAL_THRESHOLD}%).",
            )
        if current_value > DISK_WARNING_THRESHOLD:
            return (
                "WARNING",
                f"[WARNING] disk usage is {current_value:.2f}% "
                f"(exceeded {DISK_WARNING_THRESHOLD}%).",
            )

    if metric_name.startswith("http_latency_ms"):
        if current_value > HTTP_LATENCY_CRITICAL_MS:
            return (
                "CRITICAL",
                f"[CRITICAL] HTTP latency is {current_value:.2f}ms "
                f"(exceeded {HTTP_LATENCY_CRITICAL_MS:.0f}ms).",
            )

    return None

def _severity_rank(severity: str) -> int:
    return {"NORMAL": 0, "WARNING": 1, "CRITICAL": 2}.get(severity, 0)

def _convert_network_delta_to_bps(
    chronological_records: list[dict[str, Any]],
    byte_column: str,
    default_cycle_sec: float = DEFAULT_CYCLE_SECONDS,
) -> list[tuple[str, float]]:
    if default_cycle_sec <= 0:
        raise ValueError("default_cycle_sec must be greater than 0")

    bps_list: list[tuple[str, float]] = []

    for idx, record in enumerate(chronological_records):
        byte_delta = record.get(byte_column)
        if byte_delta is None:
            continue

        delta_sec = default_cycle_sec

        if idx > 0:
            previous_record = chronological_records[idx - 1]
            previous_ts = _parse_iso_utc(previous_record.get("timestamp_utc", ""))
            current_ts = _parse_iso_utc(record.get("timestamp_utc", ""))

            if previous_ts is not None and current_ts is not None:
                measured_sec = (current_ts - previous_ts).total_seconds()
                if 0.0 < measured_sec <= MAX_VALID_CYCLE_SECONDS:
                    delta_sec = measured_sec

        byte_value = max(0.0, float(byte_delta))
        rate_bps = byte_value / delta_sec
        timestamp = str(record.get("timestamp_utc", ""))
        bps_list.append((timestamp, rate_bps))

    return bps_list

def analyze_metric_series(
    node_id: str,
    timestamp_utc: str,
    metric_name: str,
    current_value: float,
    historical_values: list[float],
    window_size: int = WINDOW_SIZE,
    min_samples: int = MIN_HISTORY_SAMPLES,
    min_std_floor: float = MIN_STD_PERCENT,
) -> dict[str, Any]:
    if window_size < 1:
        raise ValueError("window_size must be at least 1")
    if min_samples < 1:
        raise ValueError("min_samples must be at least 1")
    if min_std_floor <= 0:
        raise ValueError("min_std_floor must be greater than 0")

    current = float(current_value)
    if not math.isfinite(current):
        raise ValueError("current_value must be a finite number")

    baseline_window = [
        float(value)
        for value in historical_values[-window_size:]
        if value is not None and math.isfinite(float(value))
    ]

    mean_val: float | None = None
    std_val: float | None = None
    z_score: float | None = None
    is_anomaly = False
    severity = "NORMAL"

    if len(baseline_window) < min_samples:
        message = (
            f"Insufficient historical data for {metric_name} on {node_id} "
            f"({len(baseline_window)}/{min_samples} samples collected)."
        )
    else:
        mean_val, std_val = _calculate_mean_and_std(baseline_window)
        effective_std = max(std_val, min_std_floor)
        z_score = (current - mean_val) / effective_std
        abs_z = abs(z_score)

        if abs_z >= CRITICAL_Z_THRESHOLD:
            is_anomaly = True
            severity = "CRITICAL"
            direction = "increased" if z_score > 0 else "decreased"
            message = (
                f"[CRITICAL] {metric_name} on {node_id} {direction} to {current:.2f} "
                f"(mean={mean_val:.2f}, std={std_val:.2f}, z_score={z_score:.2f})."
            )
        elif abs_z > WARNING_Z_THRESHOLD:
            is_anomaly = True
            severity = "WARNING"
            direction = "increased" if z_score > 0 else "decreased"
            message = (
                f"[WARNING] {metric_name} on {node_id} {direction} abnormally to {current:.2f} "
                f"(mean={mean_val:.2f}, std={std_val:.2f}, z_score={z_score:.2f})."
            )
        else:
            message = (
                f"{metric_name} on {node_id} is normal at {current:.2f} "
                f"(mean={mean_val:.2f}, std={std_val:.2f}, z_score={z_score:.2f})."
            )

    static_alert = _apply_static_threshold(metric_name, current)
    if static_alert is not None:
        static_severity, static_message = static_alert
        if _severity_rank(static_severity) >= _severity_rank(severity):
            is_anomaly = True
            severity = static_severity
            message = static_message

    return _make_result(
        node_id=node_id,
        timestamp_utc=timestamp_utc,
        metric_name=metric_name,
        current_value=current,
        mean=mean_val,
        std=std_val,
        z_score=z_score,
        is_anomaly=is_anomaly,
        severity=severity,
        message=message,
    )

def _sort_records_chronologically(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda record: (
            str(record.get("timestamp_utc", "")),
            int(record.get("id", 0)),
        ),
    )

def analyze_node(
    node_id: str = "windows-11-node-01",
    limit: int = 100,
    window_size: int = WINDOW_SIZE,
    db_path: str | Path = DB_PATH,
) -> list[dict[str, Any]]:
    records = get_metrics(limit=limit, db_path=db_path, node_id=node_id)
    if not records:
        return []

    chronological = _sort_records_chronologically(records)
    latest_record = chronological[-1]
    history_records = chronological[:-1]
    latest_timestamp = str(latest_record.get("timestamp_utc", ""))
    target_node = str(latest_record.get("node_id", node_id))

    results: list[dict[str, Any]] = []

    for metric_name in ("cpu_percent", "memory_percent", "disk_percent"):
        current_raw = latest_record.get(metric_name)
        if current_raw is None:
            continue

        historical_values = [
            float(record[metric_name])
            for record in history_records
            if record.get(metric_name) is not None
        ]

        results.append(
            analyze_metric_series(
                node_id=target_node,
                timestamp_utc=latest_timestamp,
                metric_name=metric_name,
                current_value=float(current_raw),
                historical_values=historical_values,
                window_size=window_size,
                min_std_floor=MIN_STD_PERCENT,
            )
        )

    network_columns = (
        ("network_sent_bytes", "network_sent_bytes_per_sec"),
        ("network_recv_bytes", "network_recv_bytes_per_sec"),
    )

    for source_column, metric_name in network_columns:

        if latest_record.get(source_column) is None:
            continue

        bps_series = _convert_network_delta_to_bps(chronological, source_column)
        if not bps_series:
            continue

        current_timestamp, current_bps = bps_series[-1]
        historical_bps = [value for _, value in bps_series[:-1]]

        results.append(
            analyze_metric_series(
                node_id=target_node,
                timestamp_utc=current_timestamp,
                metric_name=metric_name,
                current_value=current_bps,
                historical_values=historical_bps,
                window_size=window_size,
                min_std_floor=MIN_STD_NETWORK_BPS,
            )
        )

    return results

def analyze_service_checks(
    node_id: str = "windows-11-node-01",
    service_name: str | None = None,
    limit: int = 100,
    window_size: int = WINDOW_SIZE,
    db_path: str | Path = DB_PATH,
) -> list[dict[str, Any]]:
    checks = get_service_checks(
        service_name=service_name,
        limit=limit,
        db_path=db_path,
        node_id=node_id,
    )
    if not checks:
        return []

    checks_by_service: dict[str, list[dict[str, Any]]] = {}
    for record in checks:
        service = str(record.get("service_name", "http_service"))
        checks_by_service.setdefault(service, []).append(record)

    results: list[dict[str, Any]] = []

    for service, service_records in checks_by_service.items():
        chronological = _sort_records_chronologically(service_records)
        latest = chronological[-1]
        history = chronological[:-1]

        timestamp = str(latest.get("timestamp_utc", ""))
        target_node = str(latest.get("node_id", node_id))
        is_up = int(latest.get("is_available", 0)) == 1
        url = latest.get("url")

        results.append(
            _make_result(
                node_id=target_node,
                timestamp_utc=timestamp,
                metric_name=f"http_availability:{service}",
                current_value=1.0 if is_up else 0.0,
                mean=None,
                std=None,
                z_score=None,
                is_anomaly=not is_up,
                severity="NORMAL" if is_up else "CRITICAL",
                message=(
                    f"HTTP service '{service}' ({url}) on {target_node} is UP."
                    if is_up
                    else f"[CRITICAL] HTTP service '{service}' ({url}) on {target_node} is DOWN."
                ),
            )
        )

        current_latency = latest.get("response_time_ms")
        if not is_up or current_latency is None:
            continue

        historical_latencies = [
            float(record["response_time_ms"])
            for record in history
            if int(record.get("is_available", 0)) == 1
            and record.get("response_time_ms") is not None
        ]

        results.append(
            analyze_metric_series(
                node_id=target_node,
                timestamp_utc=timestamp,
                metric_name=f"http_latency_ms:{service}",
                current_value=float(current_latency),
                historical_values=historical_latencies,
                window_size=window_size,
                min_std_floor=MIN_STD_LATENCY_MS,
            )
        )

    return results

def analyze_all_for_node(
    node_id: str = "windows-11-node-01",
    limit: int = 100,
    window_size: int = WINDOW_SIZE,
    db_path: str | Path = DB_PATH,
) -> list[dict[str, Any]]:
    system_results = analyze_node(
        node_id=node_id,
        limit=limit,
        window_size=window_size,
        db_path=db_path,
    )
    service_results = analyze_service_checks(
        node_id=node_id,
        limit=limit,
        window_size=window_size,
        db_path=db_path,
    )
    return system_results + service_results

if __name__ == "__main__":
    from pprint import pprint
    import tempfile

    from storage.database import initialize_database, save_metrics, save_service_check

    print("=== NOC Analyzer demo ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        test_db_path = Path(temp_dir) / "test_noc_monitoring.db"
        initialize_database(test_db_path)

        start_time = datetime(2026, 11, 4, 15, 0, 0, tzinfo=timezone.utc)

        for index in range(30):
            timestamp = (start_time + timedelta(seconds=index * 5)).isoformat()
            timestamp = timestamp.replace("+00:00", "Z")

            save_metrics(
                {
                    "node_id": "windows-11-node-01",
                    "timestamp_utc": timestamp,
                    "cpu_percent": 22.0 + (index % 3),
                    "memory_percent": 65.0,
                    "disk_percent": 91.5,
                    "network_sent_bytes": 10000,
                    "network_recv_bytes": 25000,
                },
                db_path=test_db_path,
            )

            save_service_check(
                {
                    "node_id": "windows-11-node-01",
                    "timestamp_utc": timestamp,
                    "service_name": "portal-web",
                    "url": "http://localhost/health",
                    "is_available": True,
                    "status_code": 200,
                    "response_time_ms": 120.0 + (index % 5),
                },
                db_path=test_db_path,
            )

        latest_timestamp = (start_time + timedelta(seconds=30 * 5)).isoformat()
        latest_timestamp = latest_timestamp.replace("+00:00", "Z")

        save_metrics(
            {
                "node_id": "windows-11-node-01",
                "timestamp_utc": latest_timestamp,
                "cpu_percent": 88.0,
                "memory_percent": 65.0,
                "disk_percent": 91.5,
                "network_sent_bytes": 80000,
                "network_recv_bytes": 25000,
            },
            db_path=test_db_path,
        )

        save_service_check(
            {
                "node_id": "windows-11-node-01",
                "timestamp_utc": latest_timestamp,
                "service_name": "portal-web",
                "url": "http://localhost/health",
                "is_available": True,
                "status_code": 200,
                "response_time_ms": 1250.0,
            },
            db_path=test_db_path,
        )

        results = analyze_all_for_node(
            node_id="windows-11-node-01",
            db_path=test_db_path,
        )

        for result in results:
            assert set(result.keys()) == RESULT_FIELDS

        pprint(results, sort_dicts=False)
