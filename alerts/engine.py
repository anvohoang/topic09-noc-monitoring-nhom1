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

SEVERITY_RANK = {"normal": 0, "warning": 1, "critical": 2}

DEFAULT_STATIC_THRESHOLDS: dict[str, tuple[float, float]] = {
    "cpu_percent": (75.0, 90.0),
    "memory_percent": (80.0, 90.0),
    "disk_percent": (85.0, 95.0),
    "response_time_ms": (1000.0, 3000.0),
}


@dataclass
class AlertEvaluationOutcome:
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
        if now is None:
            return datetime.now(timezone.utc)
        if now.tzinfo is None:
            return now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc)

    @staticmethod
    def _format_utc(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    @staticmethod
    def _parse_utc(ts: str) -> datetime:
        cleaned = ts.strip()
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _load_ack_state(self) -> set[int]:
        if not self.ack_state_path.exists():
            return set()
        try:
            raw = json.loads(self.ack_state_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return {int(x) for x in raw}
        except (OSError, ValueError, TypeError):
            pass
        return set()

    def _save_ack_state(self) -> None:
        self.ack_state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = sorted(self._acknowledged_ids)
        self.ack_state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def acknowledge_alert(self, alert_id: int) -> bool:
        self._acknowledged_ids.add(int(alert_id))
        self._save_ack_state()
        return True

    def is_acknowledged(self, alert_id: int) -> bool:
        return int(alert_id) in self._acknowledged_ids

    def _evaluate_static(self, metric_name: str, value: float) -> tuple[str, str]:
        thresholds = self.static_thresholds.get(metric_name)
        if thresholds is None and metric_name.endswith(":response_time_ms"):
            thresholds = self.static_thresholds.get("response_time_ms")
        if thresholds is None:
            return "normal", ""

        warn_limit, crit_limit = thresholds
        if value >= crit_limit:
            return "critical", f"Static threshold breached ({value:.2f} >= {crit_limit:.2f})"
        if value >= warn_limit:
            return "warning", f"Static threshold breached ({value:.2f} >= {warn_limit:.2f})"
        return "normal", ""

    def _combine_signals(
        self,
        metric_name: str,
        current_value: float,
        history_values: list[float],
    ) -> tuple[str, str, str]:
        static_sev, static_msg = self._evaluate_static(metric_name, current_value)
        z_res = self.detector.evaluate(metric_name, history_values, only_spikes=True)

        if SEVERITY_RANK[static_sev] > SEVERITY_RANK[z_res.severity]:
            final_sev = static_sev
        else:
            final_sev = z_res.severity

        if static_sev != "normal" and z_res.is_anomaly:
            triggered_by = "both"
            message = f"[{metric_name}] {static_msg} | {z_res.reason}"
        elif static_sev != "normal":
            triggered_by = "static"
            message = f"[{metric_name}] {static_msg}"
        elif z_res.is_anomaly:
            triggered_by = "zscore"
            message = f"[{metric_name}] {z_res.reason}"
        else:
            triggered_by = "none"
            message = f"[{metric_name}] Normal (value={current_value:.2f}, z={z_res.z_score:.2f})"

        return final_sev, triggered_by, message

    def _should_suppress_alert(
        self,
        node_id: str,
        metric_name: str,
        now: datetime,
        matching_active: list[dict[str, Any]],
    ) -> bool:
        if matching_active:
            latest_created = max(
                self._parse_utc(a["created_at_utc"]) for a in matching_active
            )
            self._last_alert_time[(node_id, metric_name)] = latest_created
            return True

        last_dt = self._last_alert_time.get((node_id, metric_name))
        if last_dt is not None and (now - last_dt).total_seconds() < self.cooldown_seconds:
            return True

        return False

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
        matching_active = [
            a
            for a in active_alerts
            if a.get("metric_name") == metric_name
            and (a.get("node_id") in (node_id, None))
        ]

        if severity == "normal":
            resolved_ids: list[int] = []
            if self.auto_resolve and matching_active:
                now_iso = self._format_utc(now)
                ack_changed = False
                for alert in matching_active:
                    aid = int(alert["id"])
                    if update_alert_status(
                        aid,
                        "resolved",
                        resolved_at_utc=now_iso,
                        db_path=self.db_path,
                    ):
                        resolved_ids.append(aid)
                        if aid in self._acknowledged_ids:
                            self._acknowledged_ids.discard(aid)
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

        if self._should_suppress_alert(node_id, metric_name, now, matching_active):
            return AlertEvaluationOutcome(
                node_id=node_id,
                metric_name=metric_name,
                current_value=current_value,
                severity=severity,
                triggered_by=triggered_by,
                message=message,
                suppressed_by_cooldown=True,
            )

        now_iso = self._format_utc(now)
        new_id = save_alert(
            {
                "node_id": node_id,
                "created_at_utc": now_iso,
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
            alert_id=int(new_id) if new_id is not None else None,
        )

    def evaluate_node(
        self,
        node_id: str,
        now: datetime | None = None,
    ) -> list[AlertEvaluationOutcome]:
        eval_time = self._utc_now(now)
        outcomes: list[AlertEvaluationOutcome] = []
        active_alerts = get_active_alerts(db_path=self.db_path, node_id=node_id)

        metric_rows = get_metrics(
            limit=self.window_size + 1,
            db_path=self.db_path,
            node_id=node_id,
        )
        if metric_rows:
            chronological_metrics = list(reversed(metric_rows))
            for col in ("cpu_percent", "memory_percent", "disk_percent"):
                series = [
                    float(r[col])
                    for r in chronological_metrics
                    if r.get(col) is not None
                ]
                if not series:
                    continue
                current_val = series[-1]
                sev, trig, msg = self._combine_signals(col, current_val, series)
                outcomes.append(
                    self._handle_alert_lifecycle(
                        node_id=node_id,
                        metric_name=col,
                        current_value=current_val,
                        severity=sev,
                        triggered_by=trig,
                        message=msg,
                        now=eval_time,
                        active_alerts=active_alerts,
                    )
                )

        service_rows = get_service_checks(
            limit=(self.window_size + 1) * 10,
            db_path=self.db_path,
            node_id=node_id,
        )
        if service_rows:
            grouped_services: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in reversed(service_rows):
                svc_name = row.get("service_name")
                if svc_name:
                    grouped_services[str(svc_name)].append(row)

            for svc_name, rows in grouped_services.items():
                latest = rows[-1]
                is_up = latest.get("is_available")
                avail_metric = f"service:{svc_name}:availability"

                if is_up is not None:
                    up_val = float(int(is_up))
                    if int(is_up) == 0:
                        url_info = f" ({latest.get('url')})" if latest.get("url") else ""
                        err_info = (
                            f" - {latest.get('error_message')}"
                            if latest.get("error_message")
                            else ""
                        )
                        outcomes.append(
                            self._handle_alert_lifecycle(
                                node_id=node_id,
                                metric_name=avail_metric,
                                current_value=up_val,
                                severity="critical",
                                triggered_by="static",
                                message=f"[{avail_metric}] Service '{svc_name}' is DOWN{url_info}{err_info}",
                                now=eval_time,
                                active_alerts=active_alerts,
                            )
                        )
                    else:
                        outcomes.append(
                            self._handle_alert_lifecycle(
                                node_id=node_id,
                                metric_name=avail_metric,
                                current_value=up_val,
                                severity="normal",
                                triggered_by="none",
                                message=f"[{avail_metric}] Service '{svc_name}' is UP",
                                now=eval_time,
                                active_alerts=active_alerts,
                            )
                        )

                latency_series = [
                    float(r["response_time_ms"])
                    for r in rows
                    if r.get("response_time_ms") is not None
                ]
                if latency_series:
                    lat_metric = f"service:{svc_name}:response_time_ms"
                    cur_lat = latency_series[-1]
                    sev, trig, msg = self._combine_signals(
                        lat_metric, cur_lat, latency_series
                    )
                    outcomes.append(
                        self._handle_alert_lifecycle(
                            node_id=node_id,
                            metric_name=lat_metric,
                            current_value=cur_lat,
                            severity=sev,
                            triggered_by=trig,
                            message=msg,
                            now=eval_time,
                            active_alerts=active_alerts,
                        )
                    )

        return outcomes