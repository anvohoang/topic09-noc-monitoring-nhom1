from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import time

from alerts.engine import AlertEngine
from storage.database import (
    get_active_alerts,
    initialize_database,
    save_metrics,
    save_service_check,
)


def run_simulation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "noc_simulation.db"
        initialize_database(db_path)
        node_id = "windows-11-node-01"
        engine = AlertEngine(
            db_path=db_path,
            window_size=30,
            min_samples=10,
            cooldown_seconds=300,
            auto_resolve=True,
        )

        base_time = datetime(2026, 11, 14, 14, 0, 0, tzinfo=timezone.utc)
        print("=== GIAI DOAN 1: NAP 20 MAU NEN ON DINH (BASELINE) ===")
        for i in range(20):
            ts = (base_time + timedelta(seconds=i * 5)).isoformat(timespec="seconds").replace("+00:00", "Z")
            save_metrics(
                {
                    "node_id": node_id,
                    "timestamp_utc": ts,
                    "cpu_percent": 18.0 + (i % 4) * 0.6,
                    "memory_percent": 44.0 + (i % 3) * 0.4,
                    "disk_percent": 52.0,
                },
                db_path=db_path,
            )
            save_service_check(
                {
                    "node_id": node_id,
                    "timestamp_utc": ts,
                    "service_name": "httpbin",
                    "url": "https://httpbin.org/status/200",
                    "is_available": 1,
                    "response_time_ms": 145.0 + (i % 5) * 4.0,
                },
                db_path=db_path,
            )
        engine.evaluate_node(node_id, now=base_time + timedelta(seconds=95))

        print("\n=== GIAI DOAN 2: MO PHONG 4 KICH BAN SU CO ===")

        # Kich ban 1: Dot bien CPU som (68% < nguong tinh 75%, nhung Z-Score bat duoc!)
        t1 = base_time + timedelta(seconds=100)
        ts1 = t1.isoformat(timespec="seconds").replace("+00:00", "Z")
        save_metrics(
            {
                "node_id": node_id,
                "timestamp_utc": ts1,
                "cpu_percent": 68.0,
                "memory_percent": 44.5,
                "disk_percent": 52.0,
            },
            db_path=db_path,
        )
        t_start = time.perf_counter()
        out1 = engine.evaluate_node(node_id, now=t1)
        ms1 = (time.perf_counter() - t_start) * 1000
        for o in out1:
            if o.alert_saved:
                print(f"[KB1 - Phat hien som ({ms1:.2f} ms)] {o.severity.upper()} | via={o.triggered_by} | {o.message}")

        # Kich ban 2: Tran RAM (94%) + CPU van giu 69% (kiem tra Cooldown)
        t2 = base_time + timedelta(seconds=105)
        ts2 = t2.isoformat(timespec="seconds").replace("+00:00", "Z")
        save_metrics(
            {
                "node_id": node_id,
                "timestamp_utc": ts2,
                "cpu_percent": 69.0,
                "memory_percent": 94.0,
                "disk_percent": 52.0,
            },
            db_path=db_path,
        )
        t_start = time.perf_counter()
        out2 = engine.evaluate_node(node_id, now=t2)
        ms2 = (time.perf_counter() - t_start) * 1000
        for o in out2:
            if o.alert_saved:
                print(f"[KB2 - Tran RAM ({ms2:.2f} ms)] {o.severity.upper()} | via={o.triggered_by} | {o.message}")
            elif o.suppressed_by_cooldown:
                print(f"[KB2 - Cooldown nen trung lap] {o.metric_name} da duoc nen khong tao ban ghi moi")

        # Kich ban 3: Do tre HTTP tang vot 820ms (< nguong tinh 1000ms, Z-Score bat duoc!)
        t3 = base_time + timedelta(seconds=110)
        ts3 = t3.isoformat(timespec="seconds").replace("+00:00", "Z")
        save_service_check(
            {
                "node_id": node_id,
                "timestamp_utc": ts3,
                "service_name": "httpbin",
                "url": "https://httpbin.org/status/200",
                "is_available": 1,
                "response_time_ms": 820.0,
            },
            db_path=db_path,
        )
        t_start = time.perf_counter()
        out3 = engine.evaluate_node(node_id, now=t3)
        ms3 = (time.perf_counter() - t_start) * 1000
        for o in out3:
            if o.alert_saved:
                print(f"[KB3 - Tre HTTP ({ms3:.2f} ms)] {o.severity.upper()} | via={o.triggered_by} | {o.message}")

        # Kich ban 4: Dich vu HTTP bi sap (is_available=0)
        t4 = base_time + timedelta(seconds=115)
        ts4 = t4.isoformat(timespec="seconds").replace("+00:00", "Z")
        save_service_check(
            {
                "node_id": node_id,
                "timestamp_utc": ts4,
                "service_name": "httpbin",
                "url": "https://httpbin.org/status/200",
                "is_available": 0,
                "response_time_ms": None,
                "error_message": "HTTP 503 Service Unavailable",
            },
            db_path=db_path,
        )
        t_start = time.perf_counter()
        out4 = engine.evaluate_node(node_id, now=t4)
        ms4 = (time.perf_counter() - t_start) * 1000
        for o in out4:
            if o.alert_saved:
                print(f"[KB4 - Dich vu DOWN ({ms4:.2f} ms)] {o.severity.upper()} | via={o.triggered_by} | {o.message}")

        active_now = get_active_alerts(db_path=db_path, node_id=node_id)
        print(f"\n=== TONG KET: Tong so canh bao ACTIVE duy nhat trong DB = {len(active_now)} ===")


if __name__ == "__main__":
    run_simulation()