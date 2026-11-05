"""Module Analyzer phát hiện bất thường bằng Rolling Z-Score và Static Thresholds."""

from __future__ import annotations

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

    for idx, record in enumerate(chronological_records):
        byte_delta = record.get(byte_column)
        if byte_delta is None:
            continue

        delta_sec = default_cycle_sec
        if idx > 0:
            prev_ts = _parse_iso_utc(chronological_records[idx - 1].get("timestamp_utc", ""))
            curr_ts = _parse_iso_utc(record.get("timestamp_utc", ""))
            if prev_ts is not None and curr_ts is not None:
                measured_sec = (curr_ts - prev_ts).total_seconds()
                if 0.0 < measured_sec <= 60.0:
                    delta_sec = measured_sec

        rate_bps = max(0.0, float(byte_delta)) / delta_sec
        ts_str = str(record.get("timestamp_utc", ""))
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

    abs_z = abs(z_score)

    if abs_z >= CRITICAL_Z_THRESHOLD:
        is_anomaly = True
        severity = "CRITICAL"
        direction = "spiked" if z_score > 0 else "dropped"
        message = (
            f"[CRITICAL] {metric_name} on {node_id} {direction} to {curr_val:.2f} "
            f"(mean={mean_val:.2f}, std={std_val:.2f}, z_score={z_score:.2f})."
        )
    elif abs_z > WARNING_Z_THRESHOLD:
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
        key=lambda r: (str(r.get("timestamp_utc", "")), int(r.get("id", 0))),
    )

    latest_record = chronological[-1]
    history_records = chronological[:-1]
    latest_ts = str(latest_record.get("timestamp_utc", ""))
    target_node = str(latest_record.get("node_id", node_id))

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
        svc_name = str(record.get("service_name", "http_service"))
        checks_by_service.setdefault(svc_name, []).append(record)

    results: list[dict[str, Any]] = []

    for svc_name, service_checks in checks_by_service.items():
        chronological = sorted(
            service_checks,
            key=lambda r: (str(r.get("timestamp_utc", "")), int(r.get("id", 0))),
        )

        latest = chronological[-1]
        history = chronological[:-1]
        latest_ts = str(latest.get("timestamp_utc", ""))
        target_node = str(latest.get("node_id", node_id))

        is_up = int(latest.get("is_available", 0)) == 1
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
                if int(r.get("is_available", 0)) == 1 and r.get("response_time_ms") is not None
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

            if curr_latency > HTTP_LATENCY_CRITICAL_MS and latency_result["severity"] != "CRITICAL":
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

if __name__ == "__main__":
    from pprint import pprint
    import tempfile
    from storage.database import initialize_database, save_metrics, save_service_check

    print("=== KIỂM THỬ MODULE ANALYZER (KHOA) VỚI DATABASE (ÂN) & COLLECTOR (TIẾN ANH) ===")

    with tempfile.TemporaryDirectory() as tmp_dir:
        test_db_path = Path(tmp_dir) / "test_noc_monitoring.db"
        initialize_database(test_db_path)

        for i in range(30):
            total_sec = i * 5
            mm = total_sec // 60
            ss = total_sec % 60
            ts = f"2026-11-04T15:{mm:02d}:{ss:02d}Z"

            save_metrics(
                {
                    "node_id": "windows-11-node-01",
                    "timestamp_utc": ts,
                    "cpu_percent": 22.0 + (i % 3),
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
                    "timestamp_utc": ts,
                    "service_name": "portal-web",
                    "url": "https://httpbin.org/get",
                    "is_available": True,
                    "status_code": 200,
                    "response_time_ms": 120.0 + (i % 5),
                },
                db_path=test_db_path,
            )

        latest_ts = "2026-11-04T15:02:30Z"
        save_metrics(
            {
                "node_id": "windows-11-node-01",
                "timestamp_utc": latest_ts,
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
                "timestamp_utc": latest_ts,
                "service_name": "portal-web",
                "url": "https://httpbin.org/get",
                "is_available": True,
                "status_code": 200,
                "response_time_ms": 1250.0,
            },
            db_path=test_db_path,
        )

        print("\n--- 1. Kết quả analyze_node() (5 chỉ số hệ thống) ---")
        node_results = analyze_node(node_id="windows-11-node-01", db_path=test_db_path)
        pprint(node_results, sort_dicts=False)

        print("\n--- 2. Kết quả analyze_service_checks() (Trạng thái & Độ trễ HTTP) ---")
        http_results = analyze_service_checks(node_id="windows-11-node-01", db_path=test_db_path)
        pprint(http_results, sort_dicts=False)
