from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from analyzer.anomaly import RollingZScoreDetector
from storage.database import (
    DB_PATH,
    get_active_alerts,
    get_metrics,
    get_service_checks,
    save_alert,
    update_alert_status,
)


SEVERITY_RANK = {
    "normal": 0,
    "warning": 1,
    "critical": 2,
}

DEFAULT_STATIC_THRESHOLDS: dict[str, tuple[float, float]] = {
    "cpu_percent": (75.0, 90.0),
    "memory_percent": (80.0, 90.0),
    "disk_percent": (85.0, 95.0),
    "response_time_ms": (1000.0, 3000.0),
}


@dataclass
class AlertEvaluationOutcome:
    """Kết quả xử lý một chỉ số trong một chu kỳ đánh giá."""

    node_id: str
    metric_name: str
    current_value: float
    severity: str
    triggered_by: str
    message: str
    alert_saved: bool = False
    alert_id: int | None = None
    suppressed_by_cooldown: bool = False
    auto_resolved_ids: list[int] = field(default_factory=list)


class AlertEngine:
    """Đánh giá dữ liệu của một Node và quản lý vòng đời cảnh báo."""

    def __init__(
        self,
        db_path: str | Path = DB_PATH,
        window_size: int = 30,
        min_samples: int = 10,
        cooldown_seconds: int = 300,
        auto_resolve: bool = True,
        static_thresholds: dict[str, tuple[float, float]] | None = None,
        ack_state_path: str | Path | None = None,
    ) -> None:
        if window_size < 2:
            raise ValueError("window_size must be >= 2")
        if min_samples < 2 or min_samples > window_size:
            raise ValueError("min_samples must be between 2 and window_size")
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be >= 0")

        self.db_path = Path(db_path)
        self.window_size = window_size
        self.min_samples = min_samples
        self.cooldown_seconds = cooldown_seconds
        self.auto_resolve = auto_resolve

        self.static_thresholds = dict(DEFAULT_STATIC_THRESHOLDS)
        if static_thresholds:
            self.static_thresholds.update(static_thresholds)

        self.detector = RollingZScoreDetector(
            window_size=window_size,
            min_samples=min_samples,
        )

        self.ack_state_path = (
            Path(ack_state_path)
            if ack_state_path is not None
            else self.db_path.with_name("acknowledged_alerts.json")
        )

        self._last_alert_time: dict[tuple[str, str], datetime] = {}
        self._acknowledged_ids: set[int] = self._load_ack_state()

    @staticmethod
    def _utc_now(now: datetime | None = None) -> datetime:
        """Trả về thời điểm có timezone UTC."""
        if now is None:
            return datetime.now(timezone.utc)
        if now.tzinfo is None:
            return now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc)

    @staticmethod
    def _format_utc(value: datetime) -> str:
        """Định dạng datetime thành ISO 8601 UTC."""
        utc_value = value.astimezone(timezone.utc)
        return utc_value.isoformat(timespec="seconds").replace("+00:00", "Z")

    @staticmethod
    def _parse_utc(value: str) -> datetime:
        """Đọc timestamp ISO 8601 và chuẩn hóa về UTC."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("timestamp must be a non-empty string")

        cleaned = value.strip()
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"

        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _load_ack_state(self) -> set[int]:
        """Đọc danh sách alert ID đã được acknowledge từ JSON."""
        if not self.ack_state_path.exists():
            return set()

        try:
            raw = json.loads(self.ack_state_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return {int(item) for item in raw}
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

        return set()

    def _save_ack_state(self) -> None:
        """Lưu danh sách alert ID đã acknowledge."""
        self.ack_state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = sorted(self._acknowledged_ids)
        self.ack_state_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    def acknowledge_alert(self, alert_id: int) -> bool:
        """Đánh dấu một cảnh báo đã được người vận hành xác nhận."""
        if isinstance(alert_id, bool) or int(alert_id) <= 0:
            raise ValueError("alert_id must be a positive integer")

        self._acknowledged_ids.add(int(alert_id))
        self._save_ack_state()
        return True

    def is_acknowledged(self, alert_id: int) -> bool:
        """Kiểm tra một cảnh báo đã được acknowledge hay chưa."""
        return int(alert_id) in self._acknowledged_ids

    def _evaluate_static(
        self,
        metric_name: str,
        value: float,
    ) -> tuple[str, str]:
        """Đánh giá giá trị theo ngưỡng tĩnh."""
        thresholds = self.static_thresholds.get(metric_name)

        if thresholds is None and metric_name.endswith(":response_time_ms"):
            thresholds = self.static_thresholds.get("response_time_ms")

        if thresholds is None:
            return "normal", ""

        warning_limit, critical_limit = thresholds

        if value >= critical_limit:
            return (
                "critical",
                f"Static threshold breached ({value:.2f} >= {critical_limit:.2f})",
            )

        if value >= warning_limit:
            return (
                "warning",
                f"Static threshold breached ({value:.2f} >= {warning_limit:.2f})",
            )

        return "normal", ""

    def _combine_signals(
        self,
        metric_name: str,
        current_value: float,
        history_values: list[float],
    ) -> tuple[str, str, str]:
        """Kết hợp kết quả ngưỡng tĩnh và Rolling Z-Score."""
        static_severity, static_message = self._evaluate_static(
            metric_name,
            current_value,
        )
        z_result = self.detector.evaluate(
            metric_name,
            history_values,
            only_spikes=True,
        )

        if SEVERITY_RANK[static_severity] >= SEVERITY_RANK[z_result.severity]:
            final_severity = static_severity
        else:
            final_severity = z_result.severity

        if static_severity != "normal" and z_result.is_anomaly:
            triggered_by = "both"
            message = f"[{metric_name}] {static_message} | {z_result.reason}"
        elif static_severity != "normal":
            triggered_by = "static"
            message = f"[{metric_name}] {static_message}"
        elif z_result.is_anomaly:
            triggered_by = "zscore"
            message = f"[{metric_name}] {z_result.reason}"
        else:
            triggered_by = "none"
            message = (
                f"[{metric_name}] Normal "
                f"(value={current_value:.2f}, z={z_result.z_score:.2f})"
            )

        return final_severity, triggered_by, message

    def _should_suppress_alert(
        self,
        node_id: str,
        metric_name: str,
        now: datetime,
        matching_active: list[dict[str, Any]],
    ) -> bool:
        """Không tạo cảnh báo mới nếu đã có cảnh báo active hoặc còn cooldown."""
        key = (node_id, metric_name)

        if matching_active:
            created_times = [
                self._parse_utc(alert["created_at_utc"])
                for alert in matching_active
                if alert.get("created_at_utc")
            ]
            if created_times:
                self._last_alert_time[key] = max(created_times)
            return True

        last_alert_time = self._last_alert_time.get(key)
        if last_alert_time is None:
            return False

        elapsed_seconds = (now - last_alert_time).total_seconds()
        return elapsed_seconds < self.cooldown_seconds

    def _handle_alert_lifecycle(
        self,
        node_id: str,
        metric_name: str,
        current_value: float,
        severity: str,
        triggered_by: str,
        message: str,
        now: datetime,
        active_alerts: list[dict[str, Any]],
    ) -> AlertEvaluationOutcome:
        """Tạo, chống trùng hoặc tự động resolve cảnh báo."""
        severity = severity.lower()
        if severity not in SEVERITY_RANK:
            raise ValueError(f"Unsupported severity: {severity}")

        matching_active = [
            alert
            for alert in active_alerts
            if alert.get("metric_name") == metric_name
            and alert.get("node_id") in (node_id, None)
        ]

        if severity == "normal":
            resolved_ids: list[int] = []

            if self.auto_resolve and matching_active:
                ack_changed = False

                for alert in matching_active:
                    alert_id = int(alert["id"])

                    # Storage tự thiết lập resolved_at_utc khi status = resolved.
                    updated = update_alert_status(
                        alert_id,
                        "resolved",
                        db_path=self.db_path,
                    )

                    if updated:
                        resolved_ids.append(alert_id)
                        if alert_id in self._acknowledged_ids:
                            self._acknowledged_ids.discard(alert_id)
                            ack_changed = True

                if ack_changed:
                    self._save_ack_state()

            return AlertEvaluationOutcome(
                node_id=node_id,
                metric_name=metric_name,
                current_value=current_value,
                severity="normal",
                triggered_by="none",
                message=message,
                auto_resolved_ids=resolved_ids,
            )

        if self._should_suppress_alert(
            node_id,
            metric_name,
            now,
            matching_active,
        ):
            return AlertEvaluationOutcome(
                node_id=node_id,
                metric_name=metric_name,
                current_value=current_value,
                severity=severity,
                triggered_by=triggered_by,
                message=message,
                suppressed_by_cooldown=True,
            )

        created_at_utc = self._format_utc(now)
        new_alert_id = save_alert(
            {
                "node_id": node_id,
                "created_at_utc": created_at_utc,
                "metric_name": metric_name,
                "severity": severity,
                "message": message,
                "status": "active",
            },
            db_path=self.db_path,
        )

        self._last_alert_time[(node_id, metric_name)] = now

        return AlertEvaluationOutcome(
            node_id=node_id,
            metric_name=metric_name,
            current_value=current_value,
            severity=severity,
            triggered_by=triggered_by,
            message=message,
            alert_saved=True,
            alert_id=int(new_alert_id) if new_alert_id is not None else None,
        )

    @staticmethod
    def _chronological_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Sắp xếp bản ghi cũ đến mới để phân tích chuỗi thời gian."""
        return sorted(
            rows,
            key=lambda row: (
                str(row.get("timestamp_utc", "")),
                int(row.get("id", 0) or 0),
            ),
        )

    def evaluate_node(
        self,
        node_id: str,
        now: datetime | None = None,
    ) -> list[AlertEvaluationOutcome]:
        """Đánh giá metrics và service checks mới nhất của một Node."""
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("node_id must be a non-empty string")

        node_id = node_id.strip()
        evaluation_time = self._utc_now(now)
        outcomes: list[AlertEvaluationOutcome] = []

        active_alerts = get_active_alerts(
            db_path=self.db_path,
            node_id=node_id,
        )

        # Đánh giá CPU, RAM và Disk.
        metric_rows = get_metrics(
            limit=self.window_size + 1,
            db_path=self.db_path,
            node_id=node_id,
        )

        if metric_rows:
            chronological_metrics = self._chronological_rows(metric_rows)

            for column in ("cpu_percent", "memory_percent", "disk_percent"):
                values = [
                    float(row[column])
                    for row in chronological_metrics
                    if row.get(column) is not None
                ]
                if not values:
                    continue

                current_value = values[-1]
                severity, triggered_by, message = self._combine_signals(
                    column,
                    current_value,
                    values,
                )

                outcomes.append(
                    self._handle_alert_lifecycle(
                        node_id=node_id,
                        metric_name=column,
                        current_value=current_value,
                        severity=severity,
                        triggered_by=triggered_by,
                        message=message,
                        now=evaluation_time,
                        active_alerts=active_alerts,
                    )
                )

        # Đánh giá tình trạng và độ trễ của từng dịch vụ HTTP.
        service_rows = get_service_checks(
            limit=(self.window_size + 1) * 10,
            db_path=self.db_path,
            node_id=node_id,
        )

        if service_rows:
            grouped_services: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in service_rows:
                service_name = row.get("service_name")
                if service_name:
                    grouped_services[str(service_name)].append(row)

            for service_name, unsorted_rows in grouped_services.items():
                rows = self._chronological_rows(unsorted_rows)
                latest = rows[-1]
                is_available = latest.get("is_available")

                availability_metric = f"service:{service_name}:availability"

                if is_available is not None:
                    is_up = int(is_available) == 1
                    availability_value = 1.0 if is_up else 0.0

                    if is_up:
                        availability_severity = "normal"
                        availability_trigger = "none"
                        availability_message = (
                            f"[{availability_metric}] Service '{service_name}' is UP"
                        )
                    else:
                        url_info = f" ({latest.get('url')})" if latest.get("url") else ""
                        error_info = (
                            f" - {latest.get('error_message')}"
                            if latest.get("error_message")
                            else ""
                        )
                        availability_severity = "critical"
                        availability_trigger = "static"
                        availability_message = (
                            f"[{availability_metric}] Service '{service_name}' "
                            f"is DOWN{url_info}{error_info}"
                        )

                    outcomes.append(
                        self._handle_alert_lifecycle(
                            node_id=node_id,
                            metric_name=availability_metric,
                            current_value=availability_value,
                            severity=availability_severity,
                            triggered_by=availability_trigger,
                            message=availability_message,
                            now=evaluation_time,
                            active_alerts=active_alerts,
                        )
                    )

                latency_values = [
                    float(row["response_time_ms"])
                    for row in rows
                    if row.get("response_time_ms") is not None
                ]

                if latency_values:
                    latency_metric = f"service:{service_name}:response_time_ms"
                    current_latency = latency_values[-1]
                    severity, triggered_by, message = self._combine_signals(
                        latency_metric,
                        current_latency,
                        latency_values,
                    )

                    outcomes.append(
                        self._handle_alert_lifecycle(
                            node_id=node_id,
                            metric_name=latency_metric,
                            current_value=current_latency,
                            severity=severity,
                            triggered_by=triggered_by,
                            message=message,
                            now=evaluation_time,
                            active_alerts=active_alerts,
                        )
                    )

        return outcomes