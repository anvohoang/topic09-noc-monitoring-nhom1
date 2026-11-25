
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from alerts.engine import AlertEngine
from analyzer import analyze_all_for_node
from integration.alert_adapter import adapt_analysis_results
from run_alerts import evaluate_all_nodes
from storage.database import (
    initialize_database,
    save_metrics,
    save_service_check,
    get_active_alerts,
)


class TestAlertIntegration(unittest.TestCase):

    def _timestamp(self, base, seconds):
        return (
            (base + timedelta(seconds=seconds))
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )

    def _seed_node(self, db_path, node_id, base, add_http=False):
        for i in range(12):
            save_metrics(
                {
                    "node_id": node_id,
                    "timestamp_utc": self._timestamp(base, i * 5),
                    "cpu_percent": 20.0,
                    "memory_percent": 40.0,
                    "disk_percent": 50.0,
                    "network_sent_bytes": 10000 + i * 100,
                    "network_recv_bytes": 20000 + i * 100,
                },
                db_path=db_path,
            )

        event_time = self._timestamp(base, 60)

        save_metrics(
            {
                "node_id": node_id,
                "timestamp_utc": event_time,
                "cpu_percent": 95.0,
                "memory_percent": 40.0,
                "disk_percent": 50.0,
                "network_sent_bytes": 11200,
                "network_recv_bytes": 21200,
            },
            db_path=db_path,
        )

        if add_http:
            save_service_check(
                {
                    "node_id": node_id,
                    "timestamp_utc": event_time,
                    "service_name": "test-web",
                    "url": "https://test-web.local",
                    "is_available": 0,
                    "status_code": None,
                    "response_time_ms": None,
                    "error_message": "Connection timeout",
                },
                db_path=db_path,
            )

    def test_adapter_normalizes_http_metrics(self):
        sample = [
            {
                "node_id": "node-test",
                "metric_name": "http_availability:httpbin.org",
                "current_value": 0.0,
                "severity": "CRITICAL",
                "message": "Service is DOWN",
            },
            {
                "node_id": "node-test",
                "metric_name": "http_latency_ms:httpbin.org",
                "current_value": 1500.0,
                "severity": "WARNING",
                "message": "Latency is high",
            },
        ]

        results = adapt_analysis_results("node-test", sample)

        self.assertEqual(
            results[0]["metric_name"],
            "service:httpbin.org:availability",
        )
        self.assertEqual(results[0]["severity"], "critical")

        self.assertEqual(
            results[1]["metric_name"],
            "service:httpbin.org:response_time_ms",
        )
        self.assertEqual(results[1]["severity"], "warning")

    def test_analyzer_alert_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "lifecycle.db"
            base = datetime(
                2026, 11, 24, 10, 0, 0, tzinfo=timezone.utc
            )
            node_id = "integration-test-node"

            initialize_database(db_path)
            self._seed_node(db_path, node_id, base)

            engine = AlertEngine(
                db_path=db_path,
                cooldown_seconds=300,
                auto_resolve=True,
                ack_state_path=Path(tmp) / "ack.json",
            )

            def analyze_and_process():
                results = analyze_all_for_node(
                    node_id=node_id,
                    limit=100,
                    db_path=db_path,
                )
                adapted = adapt_analysis_results(node_id, results)

                return engine.process_analysis_results(
                    node_id=node_id,
                    analysis_results=adapted,
                )

            first = analyze_and_process()
            cpu_first = next(
                item for item in first
                if item.metric_name == "cpu_percent"
            )

            self.assertTrue(cpu_first.alert_saved)
            self.assertEqual(cpu_first.severity, "critical")

            repeated = analyze_and_process()
            cpu_repeated = next(
                item for item in repeated
                if item.metric_name == "cpu_percent"
            )

            self.assertTrue(cpu_repeated.suppressed_by_cooldown)

            active = get_active_alerts(
                db_path=db_path,
                node_id=node_id,
            )
            self.assertEqual(len(active), 1)

            save_metrics(
                {
                    "node_id": node_id,
                    "timestamp_utc": self._timestamp(base, 65),
                    "cpu_percent": 20.0,
                    "memory_percent": 40.0,
                    "disk_percent": 50.0,
                    "network_sent_bytes": 11300,
                    "network_recv_bytes": 21300,
                },
                db_path=db_path,
            )

            recovery = analyze_and_process()
            cpu_recovery = next(
                item for item in recovery
                if item.metric_name == "cpu_percent"
            )

            self.assertEqual(cpu_recovery.severity, "normal")
            self.assertIn(
                cpu_first.alert_id,
                cpu_recovery.auto_resolved_ids,
            )

            active_after = get_active_alerts(
                db_path=db_path,
                node_id=node_id,
            )
            self.assertEqual(len(active_after), 0)

    def test_runner_processes_multiple_nodes_and_http_alerts(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "multi_node.db"
            base = datetime(
                2026, 11, 24, 10, 0, 0, tzinfo=timezone.utc
            )
            node_ids = ["runner-node-alpha", "runner-node-beta"]

            initialize_database(db_path)

            for node_id in node_ids:
                self._seed_node(
                    db_path,
                    node_id,
                    base,
                    add_http=True,
                )

            engine = AlertEngine(
                db_path=db_path,
                cooldown_seconds=300,
                auto_resolve=True,
                ack_state_path=Path(tmp) / "ack.json",
            )

            evaluate_all_nodes(engine)

            for node_id in node_ids:
                active = get_active_alerts(
                    db_path=db_path,
                    node_id=node_id,
                )

                metric_names = {
                    alert["metric_name"]: alert["severity"].lower()
                    for alert in active
                }

                self.assertEqual(
                    metric_names.get("cpu_percent"),
                    "critical",
                )
                self.assertEqual(
                    metric_names.get(
                        "service:test-web:availability"
                    ),
                    "critical",
                )


if __name__ == "__main__":
    unittest.main()
