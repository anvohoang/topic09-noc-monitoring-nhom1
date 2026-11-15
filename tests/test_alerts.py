from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from alerts.engine import AlertEngine
from analyzer.anomaly import RollingZScoreDetector
from storage.database import (
    get_active_alerts,
    initialize_database,
    save_metrics,
    save_service_check,
)


class TestAlertModuleComprehensive(unittest.TestCase):
    def _seed_normal_metrics(
        self,
        db_path: Path,
        node: str,
        count: int = 12,
        cpu: float = 20.0,
        ram: float = 40.0,
        disk: float = 50.0,
    ) -> datetime:
        base = datetime(2026, 11, 14, 10, 0, 0, tzinfo=timezone.utc)
        for i in range(count):
            ts = (
                (base + timedelta(seconds=i * 5))
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            )
            save_metrics(
                {
                    "node_id": node,
                    "timestamp_utc": ts,
                    "cpu_percent": cpu + (i % 3) * 0.2,
                    "memory_percent": ram + (i % 2) * 0.3,
                    "disk_percent": disk,
                },
                db_path=db_path,
            )
        return base + timedelta(seconds=count * 5)

    def test_1_insufficient_baseline_samples_no_false_positive(self) -> None:
        detector = RollingZScoreDetector(window_size=30, min_samples=10)
        res = detector.evaluate("cpu_percent", [10.0, 12.0, 11.0, 65.0])
        self.assertFalse(res.is_anomaly)
        self.assertEqual(res.severity, "normal")

    def test_2_zero_std_constant_baseline_no_division_by_zero(self) -> None:
        detector = RollingZScoreDetector(window_size=30, min_samples=10)
        values = [25.0] * 12 + [35.0]
        res = detector.evaluate("cpu_percent", values)
        self.assertTrue(res.is_anomaly)
        self.assertEqual(res.severity, "critical")
        self.assertAlmostEqual(res.z_score, 10.0)

    def test_3_static_threshold_breach_creates_active_alert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test3.db"
            initialize_database(db_path)
            node = "win11-test-node"
            t0 = self._seed_normal_metrics(db_path, node, count=12, cpu=20.0)

            save_metrics(
                {
                    "node_id": node,
                    "timestamp_utc": t0.isoformat(timespec="seconds").replace("+00:00", "Z"),
                    "cpu_percent": 92.5,
                    "memory_percent": 41.0,
                    "disk_percent": 50.0,
                },
                db_path=db_path,
            )

            engine = AlertEngine(db_path=db_path)
            outcomes = engine.evaluate_node(node, now=t0)
            cpu_out = [o for o in outcomes if o.metric_name == "cpu_percent"][0]
            self.assertTrue(cpu_out.alert_saved)
            self.assertEqual(cpu_out.severity, "critical")
            self.assertEqual(len(get_active_alerts(db_path=db_path, node_id=node)), 1)

    def test_4_sustained_anomaly_over_5_minutes_no_duplicate_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test4.db"
            initialize_database(db_path)
            node = "win11-test-node"
            t0 = self._seed_normal_metrics(db_path, node, count=12, cpu=20.0)

            engine = AlertEngine(db_path=db_path, cooldown_seconds=300)

            save_metrics(
                {
                    "node_id": node,
                    "timestamp_utc": t0.isoformat(timespec="seconds").replace("+00:00", "Z"),
                    "cpu_percent": 95.0,
                    "memory_percent": 40.0,
                    "disk_percent": 50.0,
                },
                db_path=db_path,
            )
            out1 = engine.evaluate_node(node, now=t0)
            self.assertTrue([o for o in out1 if o.metric_name == "cpu_percent"][0].alert_saved)

            t_after_6m = t0 + timedelta(minutes=6)
            save_metrics(
                {
                    "node_id": node,
                    "timestamp_utc": t_after_6m.isoformat(timespec="seconds").replace("+00:00", "Z"),
                    "cpu_percent": 96.0,
                    "memory_percent": 40.0,
                    "disk_percent": 50.0,
                },
                db_path=db_path,
            )
            out2 = engine.evaluate_node(node, now=t_after_6m)
            cpu_out2 = [o for o in out2 if o.metric_name == "cpu_percent"][0]
            self.assertFalse(cpu_out2.alert_saved)
            self.assertTrue(cpu_out2.suppressed_by_cooldown)
            self.assertEqual(len(get_active_alerts(db_path=db_path, node_id=node)), 1)

    def test_5_auto_resolve_on_metric_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test5.db"
            initialize_database(db_path)
            node = "win11-test-node"
            t0 = self._seed_normal_metrics(db_path, node, count=12, cpu=20.0)
            engine = AlertEngine(db_path=db_path, auto_resolve=True)

            save_metrics(
                {
                    "node_id": node,
                    "timestamp_utc": t0.isoformat(timespec="seconds").replace("+00:00", "Z"),
                    "cpu_percent": 94.0,
                    "memory_percent": 40.0,
                    "disk_percent": 50.0,
                },
                db_path=db_path,
            )
            engine.evaluate_node(node, now=t0)
            self.assertEqual(len(get_active_alerts(db_path=db_path, node_id=node)), 1)

            t_rec = t0 + timedelta(seconds=10)
            save_metrics(
                {
                    "node_id": node,
                    "timestamp_utc": t_rec.isoformat(timespec="seconds").replace("+00:00", "Z"),
                    "cpu_percent": 21.0,
                    "memory_percent": 40.0,
                    "disk_percent": 50.0,
                },
                db_path=db_path,
            )
            out_rec = engine.evaluate_node(node, now=t_rec)
            cpu_rec = [o for o in out_rec if o.metric_name == "cpu_percent"][0]
            self.assertEqual(len(cpu_rec.auto_resolved_ids), 1)
            self.assertEqual(len(get_active_alerts(db_path=db_path, node_id=node)), 0)

    def test_6_acknowledge_persists_across_engine_restarts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test6.db"
            initialize_database(db_path)
            node = "win11-test-node"
            t0 = self._seed_normal_metrics(db_path, node, count=12, cpu=20.0)

            engine1 = AlertEngine(db_path=db_path)
            save_metrics(
                {
                    "node_id": node,
                    "timestamp_utc": t0.isoformat(timespec="seconds").replace("+00:00", "Z"),
                    "cpu_percent": 93.0,
                    "memory_percent": 40.0,
                    "disk_percent": 50.0,
                },
                db_path=db_path,
            )
            out = engine1.evaluate_node(node, now=t0)
            alert_id = [o for o in out if o.metric_name == "cpu_percent"][0].alert_id
            assert alert_id is not None

            engine1.acknowledge_alert(alert_id)
            engine2 = AlertEngine(db_path=db_path)
            self.assertTrue(engine2.is_acknowledged(alert_id))

    def test_7_multiple_http_services_evaluated_without_starvation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test7.db"
            initialize_database(db_path)
            node = "win11-test-node"
            base = datetime(2026, 11, 14, 10, 0, 0, tzinfo=timezone.utc)

            for i in range(12):
                ts = (base + timedelta(seconds=i * 5)).isoformat(timespec="seconds").replace("+00:00", "Z")
                save_service_check(
                    {
                        "node_id": node,
                        "timestamp_utc": ts,
                        "service_name": "svc_alpha",
                        "url": "https://alpha.local",
                        "is_available": 1,
                        "response_time_ms": 120.0,
                    },
                    db_path=db_path,
                )
                save_service_check(
                    {
                        "node_id": node,
                        "timestamp_utc": ts,
                        "service_name": "svc_beta",
                        "url": "https://beta.local",
                        "is_available": 1,
                        "response_time_ms": 150.0,
                    },
                    db_path=db_path,
                )

            t_down = base + timedelta(seconds=65)
            ts_down = t_down.isoformat(timespec="seconds").replace("+00:00", "Z")
            save_service_check(
                {
                    "node_id": node,
                    "timestamp_utc": ts_down,
                    "service_name": "svc_alpha",
                    "url": "https://alpha.local",
                    "is_available": 0,
                    "response_time_ms": None,
                    "error_message": "Connection timeout",
                },
                db_path=db_path,
            )
            save_service_check(
                {
                    "node_id": node,
                    "timestamp_utc": ts_down,
                    "service_name": "svc_beta",
                    "url": "https://beta.local",
                    "is_available": 1,
                    "response_time_ms": 155.0,
                },
                db_path=db_path,
            )

            engine = AlertEngine(db_path=db_path)
            engine.evaluate_node(node, now=t_down)
            active = get_active_alerts(db_path=db_path, node_id=node)
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0]["metric_name"], "service:svc_alpha:availability")

    def test_8_null_values_in_database_handled_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test8.db"
            initialize_database(db_path)
            node = "win11-test-node"
            base = datetime(2026, 11, 14, 10, 0, 0, tzinfo=timezone.utc)
            for i in range(12):
                ts = (base + timedelta(seconds=i * 5)).isoformat(timespec="seconds").replace("+00:00", "Z")
                save_metrics(
                    {
                        "node_id": node,
                        "timestamp_utc": ts,
                        "cpu_percent": 30.0 if i % 2 == 0 else None,
                        "memory_percent": None,
                        "disk_percent": 55.0,
                    },
                    db_path=db_path,
                )

            engine = AlertEngine(db_path=db_path)
            outcomes = engine.evaluate_node(node, now=base + timedelta(seconds=60))
            self.assertTrue(len(outcomes) >= 1)


if __name__ == "__main__":
    unittest.main()