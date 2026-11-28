"""Anomaly detection for the NOC monitoring toolkit."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from pathlib import Path
from typing import Any

from storage.database import DB_PATH, get_metrics, get_service_checks

WINDOW_SIZE = 30
MIN_HISTORY_SAMPLES = 5
WARNING_Z_THRESHOLD = 3.0
CRITICAL_Z_THRESHOLD = 5.0

DEFAULT_CYCLE_SECONDS = 5.0

MIN_STD_PERCENT = 0.5
MIN_STD_NETWORK_BPS = 100.0
MIN_STD_LATENCY_MS = 5.0

DISK_WARNING_THRESHOLD = 85.0
DISK_CRITICAL_THRESHOLD = 90.0
HTTP_LATENCY_CRITICAL_MS = 1000.0


@dataclass
class AnomalyResult:
    metric_name: str
    current_value: float
    mean: float
    std: float
    z_score: float
    is_anomaly: bool
    severity: str
    reason: str


class RollingZScoreDetector:
    def __init__(
        self,
        window_size: int = 30,
        min_samples: int = 10,
        warning_threshold: float = 2.0,
        critical_threshold: float = 3.0,
        min_std_floor: float = 1.0,
    ) -> None:
        if window_size < 2:
            raise ValueError("window_size must be >= 2")

        if min_samples < 2 or min_samples > window_size:
            raise ValueError("min_samples must be between 2 and window_size")

        if warning_threshold <= 0 or critical_threshold <= warning_threshold:
            raise ValueError("Thresholds must satisfy 0 < warning < critical")

        if min_std_floor <= 0:
            raise ValueError("min_std_floor must be > 0")

        self.window_size = window_size
        self.min_samples = min_samples
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.min_std_floor = min_std_floor

    def evaluate(
        self,
        metric_name: str,
        values: list[float],
        only_spikes: bool = True,
    ) -> AnomalyResult:
        if not values:
            raise ValueError("values list cannot be empty")

        current_value = float(values[-1])
        history = [float(v) for v in values[:-1]]

        if len(history) < self.min_samples:
            return AnomalyResult(
                metric_name=metric_name,
                current_value=current_value,
                mean=current_value,
                std=0.0,
                z_score=0.0,
                is_anomaly=False,
                severity="normal",
                reason=(
                    f"Insufficient baseline samples "
                    f"({len(history)}/{self.min_samples})"
                ),
            )

        baseline = history[-self.window_size:]
        mean, std = _calculate_mean_and_std(baseline)

        if std == 0.0 and math.isclose(current_value, mean, abs_tol=1e-9):
            z_score = 0.0
        else:
            effective_std = max(std, self.min_std_floor)
            z_score = (current_value - mean) / effective_std

        score_to_check = z_score if only_spikes else abs(z_score)
        direction = "spike" if z_score >= 0 else "drop"

        if score_to_check >= self.critical_threshold:
            severity = "critical"
            is_anomaly = True
            reason = (
                f"Critical Z-Score {direction} on {metric_name}: "
                f"current={current_value:.2f}, "
                f"mean={mean:.2f}, "
                f"std={std:.2f}, "
                f"z={z_score:.2f}"
            )
        elif score_to_check >= self.warning_threshold:
            severity = "warning"
            is_anomaly = True
            reason = (
                f"Warning Z-Score {direction} on {metric_name}: "
                f"current={current_value:.2f}, "
                f"mean={mean:.2f}, "
                f"std={std:.2f}, "
                f"z={z_score:.2f}"
            )
        else:
            severity = "normal"
            is_anomaly = False
            reason = f"Normal (z={z_score:.2f})"

        return AnomalyResult(
            metric_name=metric_name,
            current_value=current_value,
            mean=round(mean, 4),
            std=round(std, 4),
            z_score=round(z_score, 4),
            is_anomaly=is_anomaly,
            severity=severity,
            reason=reason,
        )


def _parse_iso_utc(timestamp_str: str) -> datetime | None:
    if not isinstance(timestamp_str, str) or not timestamp_str.strip():
        return None
    try:
        clean_str = timestamp_str.strip().replace("Z", "+00:00")
        return datetime.fromisoformat(clean_str)
    except ValueError:
        return None


def _calculate_mean_and_std(values: list[float]) -> tuple[float, float]:
    n = len(values)
    if n == 0:
        return 0.0, 0.0

    mean_val = sum(values) / n
    variance = sum((x - mean_val) ** 2 for x in values) / n
    std_val = math.sqrt(variance)
    return mean_val, std_val


def _convert_network_delta_to_bps(
    chronological_records: list[dict[str, Any]],
    byte_column: str,
    default_cycle_sec: float = DEFAULT_CYCLE_SECONDS,
) -> list[tuple[str, float]]:
    bps_list: list[tuple[str, float]] = []
    prev_valid_ts: datetime | None = None

    for record in chronological_records:
        byte_delta = record.get(byte_column)
        if byte_delta is None:
            continue

        ts_str = str(record.get("timestamp_utc") or "")
        curr_ts = _parse_iso_utc(ts_str)

        delta_sec = default_cycle_sec
        if (
            prev_valid_ts is not None
            and curr_ts is not None
            and (prev_valid_ts.tzinfo is None) == (curr_ts.tzinfo is None)
        ):
            measured_sec = (curr_ts - prev_valid_ts).total_seconds()
            if measured_sec > 0.0:
                delta_sec = measured_sec

        if curr_ts is not None:
            prev_valid_ts = curr_ts

        rate_bps = max(0.0, float(byte_delta)) / delta_sec
        bps_list.append((ts_str, rate_bps))

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
    only_spikes: bool = True,
) -> dict[str, Any]:
    baseline_window = [float(x) for x in historical_values[-window_size:]]
    curr_val = float(current_value)

    if len(baseline_window) < min_samples:
        is_anomaly = False
        severity = "NORMAL"
        message = (
            f"Insufficient historical data for {metric_name} on {node_id} "
            f"({len(baseline_window)}/{min_samples} samples collected)."
        )

        if metric_name == "disk_percent":
            if curr_val > DISK_CRITICAL_THRESHOLD:
                is_anomaly = True
                severity = "CRITICAL"
                message = (
                    f"[CRITICAL] disk_percent on {node_id} is {curr_val:.2f}% "
                    f"(exceeded static threshold > {DISK_CRITICAL_THRESHOLD}%)."
                )
            elif curr_val > DISK_WARNING_THRESHOLD:
                is_anomaly = True
                severity = "WARNING"
                message = (
                    f"[WARNING] disk_percent on {node_id} is {curr_val:.2f}% "
                    f"(exceeded static threshold > {DISK_WARNING_THRESHOLD}%)."
                )

        return {
            "node_id": node_id,
            "timestamp_utc": timestamp_utc,
            "metric_name": metric_name,
            "current_value": round(curr_val, 2),
            "mean": None,
            "std": None,
            "z_score": None,
            "is_anomaly": is_anomaly,
            "severity": severity,
            "message": message,
        }

    mean_val, std_val = _calculate_mean_and_std(baseline_window)

    if std_val == 0.0:
        if math.isclose(curr_val, mean_val, abs_tol=1e-9):
            z_score = 0.0
        else:
            z_score = (curr_val - mean_val) / min_std_floor
    else:
        effective_std = max(std_val, min_std_floor)
        z_score = (curr_val - mean_val) / effective_std

    score_to_check = z_score if only_spikes else abs(z_score)

    if score_to_check >= CRITICAL_Z_THRESHOLD:
        is_anomaly = True
        severity = "CRITICAL"
        direction = "spiked" if z_score > 0 else "dropped"
        message = (
            f"[CRITICAL] {metric_name} on {node_id} {direction} to {curr_val:.2f} "
            f"(mean={mean_val:.2f}, std={std_val:.2f}, z_score={z_score:.2f})."
        )
    elif score_to_check >= WARNING_Z_THRESHOLD:
        is_anomaly = True
        severity = "WARNING"
        direction = "increased" if z_score > 0 else "decreased"
        message = (
            f"[WARNING] {metric_name} on {node_id} {direction} abnormally to {curr_val:.2f} "
            f"(mean={mean_val:.2f}, std={std_val:.2f}, z_score={z_score:.2f})."
        )
    else:
        is_anomaly = False
        severity = "NORMAL"
        message = (
            f"{metric_name} on {node_id} is normal at {curr_val:.2f} "
            f"(mean={mean_val:.2f}, std={std_val:.2f}, z_score={z_score:.2f})."
        )

    if metric_name == "disk_percent":
        if curr_val > DISK_CRITICAL_THRESHOLD and severity != "CRITICAL":
            is_anomaly = True
            severity = "CRITICAL"
            message = (
                f"[CRITICAL] disk_percent on {node_id} reached {curr_val:.2f}% "
                f"(exceeded static threshold > {DISK_CRITICAL_THRESHOLD}%, z_score={z_score:.2f})."
            )
        elif curr_val > DISK_WARNING_THRESHOLD and severity == "NORMAL":
            is_anomaly = True
            severity = "WARNING"
            message = (
                f"[WARNING] disk_percent on {node_id} reached {curr_val:.2f}% "
                f"(exceeded static threshold > {DISK_WARNING_THRESHOLD}%, z_score={z_score:.2f})."
            )

    return {
        "node_id": node_id,
        "timestamp_utc": timestamp_utc,
        "metric_name": metric_name,
        "current_value": round(curr_val, 2),
        "mean": round(mean_val, 2),
        "std": round(std_val, 2),
        "z_score": round(z_score, 2),
        "is_anomaly": is_anomaly,
        "severity": severity,
        "message": message,
    }


def analyze_node(
    node_id: str = "windows-11-node-01",
    limit: int = 100,
    window_size: int = WINDOW_SIZE,
    db_path: str | Path = DB_PATH,
) -> list[dict[str, Any]]:
    records = get_metrics(limit=limit, db_path=db_path, node_id=node_id)
    if not records:
        return []

    chronological = sorted(
        records,
        key=lambda r: (str(r.get("timestamp_utc") or ""), int(r.get("id") or 0)),
    )

    latest_record = chronological[-1]
    history_records = chronological[:-1]
    latest_ts = str(latest_record.get("timestamp_utc") or "")
    target_node = str(latest_record.get("node_id") or node_id)

    results: list[dict[str, Any]] = []

    for col_name in ("cpu_percent", "memory_percent", "disk_percent"):
        if col_name not in latest_record or latest_record[col_name] is None:
            continue

        curr_val = float(latest_record[col_name])
        hist_vals = [
            float(r[col_name])
            for r in history_records
            if col_name in r and r[col_name] is not None
        ]

        results.append(
            analyze_metric_series(
                node_id=target_node,
                timestamp_utc=latest_ts,
                metric_name=col_name,
                current_value=curr_val,
                historical_values=hist_vals,
                window_size=window_size,
                min_std_floor=MIN_STD_PERCENT,
            )
        )

    network_columns = (
        ("network_sent_bytes", "network_sent_bytes_per_sec"),
        ("network_recv_bytes", "network_recv_bytes_per_sec"),
    )

    for raw_col, bps_metric_name in network_columns:
        bps_series = _convert_network_delta_to_bps(chronological, raw_col)
        if not bps_series:
            continue

        curr_ts, curr_bps = bps_series[-1]
        hist_bps = [val for _, val in bps_series[:-1]]

        results.append(
            analyze_metric_series(
                node_id=target_node,
                timestamp_utc=curr_ts,
                metric_name=bps_metric_name,
                current_value=curr_bps,
                historical_values=hist_bps,
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
        svc_name = str(record.get("service_name") or "http_service")
        checks_by_service.setdefault(svc_name, []).append(record)

    results: list[dict[str, Any]] = []

    for svc_name, service_checks in checks_by_service.items():
        chronological = sorted(
            service_checks,
            key=lambda r: (str(r.get("timestamp_utc") or ""), int(r.get("id") or 0)),
        )

        latest = chronological[-1]
        history = chronological[:-1]
        latest_ts = str(latest.get("timestamp_utc") or "")
        target_node = str(latest.get("node_id") or node_id)

        is_up = int(latest.get("is_available") or 0) == 1
        results.append(
            {
                "node_id": target_node,
                "timestamp_utc": latest_ts,
                "metric_name": f"http_availability:{svc_name}",
                "current_value": 1.0 if is_up else 0.0,
                "mean": 1.0,
                "std": 0.0,
                "z_score": 0.0 if is_up else None,
                "is_anomaly": not is_up,
                "severity": "NORMAL" if is_up else "CRITICAL",
                "message": (
                    f"HTTP service '{svc_name}' ({latest.get('url')}) on {target_node} is UP."
                    if is_up
                    else f"[CRITICAL] HTTP service '{svc_name}' ({latest.get('url')}) on {target_node} is DOWN!"
                ),
            }
        )

        if is_up and latest.get("response_time_ms") is not None:
            curr_latency = float(latest["response_time_ms"])
            hist_latencies = [
                float(r["response_time_ms"])
                for r in history
                if int(r.get("is_available") or 0) == 1
                and r.get("response_time_ms") is not None
            ]

            latency_result = analyze_metric_series(
                node_id=target_node,
                timestamp_utc=latest_ts,
                metric_name=f"http_latency_ms:{svc_name}",
                current_value=curr_latency,
                historical_values=hist_latencies,
                window_size=window_size,
                min_std_floor=MIN_STD_LATENCY_MS,
            )

            if (
                curr_latency > HTTP_LATENCY_CRITICAL_MS
                and latency_result["severity"] != "CRITICAL"
            ):
                latency_result["is_anomaly"] = True
                latency_result["severity"] = "CRITICAL"
                z_score = latency_result["z_score"]
                z_score_text = f"{z_score:.2f}" if z_score is not None else "N/A"
                latency_result["message"] = (
                    f"[CRITICAL] http_latency_ms:{svc_name} on {target_node} reached {curr_latency:.2f}ms "
                    f"(exceeded static threshold > {HTTP_LATENCY_CRITICAL_MS}ms, "
                    f"z_score={z_score_text})."
                )

            results.append(latency_result)

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
