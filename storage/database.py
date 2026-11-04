"""SQLite storage layer for the NOC Monitoring Toolkit.

The module stores system metrics, HTTP service checks, and alerts.
All records support node-level identification through ``node_id``.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DB_PATH = Path(__file__).resolve().parent / "noc_monitoring.db"
DEFAULT_NODE_ID = "node-unknown"


def get_connection(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    """Create and return a configured SQLite connection."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(str(path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def _validate_non_empty_string(value: Any, field_name: str) -> str:
    """Validate a required non-empty string and return its stripped value."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _get_node_id(data: dict[str, Any]) -> str:
    """Read node_id while keeping compatibility with older callers."""
    return _validate_non_empty_string(
        data.get("node_id", DEFAULT_NODE_ID), "node_id"
    )


def _validate_limit(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer")


def initialize_database(db_path: str | Path = DB_PATH) -> None:
    """Create tables/indexes and migrate older databases to include node_id."""
    connection = get_connection(db_path)

    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL DEFAULT 'node-unknown',
                timestamp_utc TEXT NOT NULL,
                cpu_percent REAL NOT NULL,
                memory_percent REAL NOT NULL,
                disk_percent REAL NOT NULL,
                network_sent_bytes INTEGER,
                network_recv_bytes INTEGER
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS service_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL DEFAULT 'node-unknown',
                timestamp_utc TEXT NOT NULL,
                service_name TEXT NOT NULL,
                url TEXT NOT NULL,
                is_available INTEGER NOT NULL
                    CHECK (is_available IN (0, 1)),
                status_code INTEGER,
                response_time_ms REAL,
                error_message TEXT
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL DEFAULT 'node-unknown',
                created_at_utc TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'resolved')),
                resolved_at_utc TEXT
            )
            """
        )

        # Migrate databases created before node_id was introduced.
        # Existing records receive the neutral value 'node-unknown'.
        for table_name in ("metrics", "service_checks", "alerts"):
            columns = {
                row["name"]
                for row in connection.execute(
                    f"PRAGMA table_info({table_name})"
                ).fetchall()
            }
            if "node_id" not in columns:
                connection.execute(
                    f"""ALTER TABLE {table_name}
                        ADD COLUMN node_id TEXT NOT NULL
                        DEFAULT '{DEFAULT_NODE_ID}'"""
                )

        # Retain the original indexes and add indexes for node-specific queries.
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_metrics_timestamp "
            "ON metrics(timestamp_utc)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_service_checks_timestamp "
            "ON service_checks(timestamp_utc)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_metrics_node_timestamp "
            "ON metrics(node_id, timestamp_utc)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_service_node_timestamp "
            "ON service_checks(node_id, timestamp_utc)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_node_status "
            "ON alerts(node_id, status)"
        )

        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()


def save_metrics(metrics: dict[str, Any], db_path: str | Path = DB_PATH) -> int:
    """Save one system-metrics record and return its database ID.

    ``network_sent_bytes`` and ``network_recv_bytes`` represent the byte
    deltas collected during one sampling cycle, not cumulative counters.
    """
    if not isinstance(metrics, dict):
        raise TypeError("metrics must be a dictionary")

    required_fields = (
        "timestamp_utc",
        "cpu_percent",
        "memory_percent",
        "disk_percent",
    )
    missing_fields = [field for field in required_fields if field not in metrics]
    if missing_fields:
        raise ValueError(f"Missing fields: {missing_fields}")

    timestamp = _validate_non_empty_string(
        metrics["timestamp_utc"], "timestamp_utc"
    )
    node_id = _get_node_id(metrics)

    try:
        cpu = float(metrics["cpu_percent"])
        memory = float(metrics["memory_percent"])
        disk = float(metrics["disk_percent"])
    except (TypeError, ValueError) as error:
        raise ValueError("CPU, memory and disk must be numeric") from error

    for name, value in (
        ("cpu_percent", cpu),
        ("memory_percent", memory),
        ("disk_percent", disk),
    ):
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError(f"{name} must be a finite number between 0 and 100")

    network_sent = metrics.get("network_sent_bytes")
    network_recv = metrics.get("network_recv_bytes")
    for name, value in (
        ("network_sent_bytes", network_sent),
        ("network_recv_bytes", network_recv),
    ):
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
        ):
            raise ValueError(f"{name} must be a non-negative integer or None")

    connection = get_connection(db_path)
    try:
        cursor = connection.execute(
            """
            INSERT INTO metrics (
                node_id,
                timestamp_utc,
                cpu_percent,
                memory_percent,
                disk_percent,
                network_sent_bytes,
                network_recv_bytes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node_id,
                timestamp,
                cpu,
                memory,
                disk,
                network_sent,
                network_recv,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_metrics(
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 100,
    db_path: str | Path = DB_PATH,
    node_id: str | None = None,
) -> list[dict[str, Any]]:
    """Get metrics newest-first, optionally filtered by time and node."""
    _validate_limit(limit)
    query = "SELECT * FROM metrics"
    conditions: list[str] = []
    parameters: list[Any] = []

    if start_time is not None:
        conditions.append("timestamp_utc >= ?")
        parameters.append(_validate_non_empty_string(start_time, "start_time"))
    if end_time is not None:
        conditions.append("timestamp_utc <= ?")
        parameters.append(_validate_non_empty_string(end_time, "end_time"))
    if node_id is not None:
        conditions.append("node_id = ?")
        parameters.append(_validate_non_empty_string(node_id, "node_id"))

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY timestamp_utc DESC, id DESC LIMIT ?"
    parameters.append(limit)

    connection = get_connection(db_path)
    try:
        rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def save_service_check(
    service_check: dict[str, Any], db_path: str | Path = DB_PATH
) -> int:
    """Save one HTTP service-check result and return its database ID."""
    if not isinstance(service_check, dict):
        raise TypeError("service_check must be a dictionary")

    required_fields = ("timestamp_utc", "service_name", "url", "is_available")
    missing_fields = [
        field for field in required_fields if field not in service_check
    ]
    if missing_fields:
        raise ValueError(f"Missing fields: {missing_fields}")

    timestamp = _validate_non_empty_string(
        service_check["timestamp_utc"], "timestamp_utc"
    )
    node_id = _get_node_id(service_check)
    service_name = _validate_non_empty_string(
        service_check["service_name"], "service_name"
    )
    url = _validate_non_empty_string(service_check["url"], "url")

    is_available = service_check["is_available"]
    if isinstance(is_available, bool):
        is_available = int(is_available)
    elif not (
        isinstance(is_available, int)
        and not isinstance(is_available, bool)
        and is_available in (0, 1)
    ):
        raise ValueError("is_available must be True, False, 0 or 1")

    status_code = service_check.get("status_code")
    if status_code is not None and (
        isinstance(status_code, bool)
        or not isinstance(status_code, int)
        or not 100 <= status_code <= 599
    ):
        raise ValueError("status_code must be an integer between 100 and 599")

    response_time = service_check.get("response_time_ms")
    if response_time is not None:
        try:
            response_time = float(response_time)
        except (TypeError, ValueError) as error:
            raise ValueError("response_time_ms must be numeric or None") from error
        if not math.isfinite(response_time) or response_time < 0:
            raise ValueError("response_time_ms must be finite and non-negative")

    error_message = service_check.get("error_message")
    if error_message is not None and not isinstance(error_message, str):
        raise ValueError("error_message must be a string or None")

    connection = get_connection(db_path)
    try:
        cursor = connection.execute(
            """
            INSERT INTO service_checks (
                node_id,
                timestamp_utc,
                service_name,
                url,
                is_available,
                status_code,
                response_time_ms,
                error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node_id,
                timestamp,
                service_name,
                url,
                is_available,
                status_code,
                response_time,
                error_message,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_service_checks(
    start_time: str | None = None,
    end_time: str | None = None,
    service_name: str | None = None,
    limit: int = 100,
    db_path: str | Path = DB_PATH,
    node_id: str | None = None,
) -> list[dict[str, Any]]:
    """Get HTTP checks newest-first, optionally filtered by time/name/node."""
    _validate_limit(limit)
    query = "SELECT * FROM service_checks"
    conditions: list[str] = []
    parameters: list[Any] = []

    if start_time is not None:
        conditions.append("timestamp_utc >= ?")
        parameters.append(_validate_non_empty_string(start_time, "start_time"))
    if end_time is not None:
        conditions.append("timestamp_utc <= ?")
        parameters.append(_validate_non_empty_string(end_time, "end_time"))
    if service_name is not None:
        conditions.append("service_name = ?")
        parameters.append(_validate_non_empty_string(service_name, "service_name"))
    if node_id is not None:
        conditions.append("node_id = ?")
        parameters.append(_validate_non_empty_string(node_id, "node_id"))

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY timestamp_utc DESC, id DESC LIMIT ?"
    parameters.append(limit)

    connection = get_connection(db_path)
    try:
        rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def save_alert(alert: dict[str, Any], db_path: str | Path = DB_PATH) -> int:
    """Save one alert and return its database ID."""
    if not isinstance(alert, dict):
        raise TypeError("alert must be a dictionary")

    required_fields = ("created_at_utc", "metric_name", "severity", "message")
    missing_fields = [field for field in required_fields if field not in alert]
    if missing_fields:
        raise ValueError(f"Missing fields: {missing_fields}")

    node_id = _get_node_id(alert)
    timestamp = _validate_non_empty_string(
        alert["created_at_utc"], "created_at_utc"
    )
    metric_name = _validate_non_empty_string(alert["metric_name"], "metric_name")
    severity = _validate_non_empty_string(alert["severity"], "severity")
    message = _validate_non_empty_string(alert["message"], "message")
    status = alert.get("status", "active")
    resolved_at = alert.get("resolved_at_utc")

    if status not in ("active", "resolved"):
        raise ValueError("status must be 'active' or 'resolved'")
    if resolved_at is not None:
        resolved_at = _validate_non_empty_string(
            resolved_at, "resolved_at_utc"
        )

    connection = get_connection(db_path)
    try:
        cursor = connection.execute(
            """
            INSERT INTO alerts (
                node_id,
                created_at_utc,
                metric_name,
                severity,
                message,
                status,
                resolved_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node_id,
                timestamp,
                metric_name,
                severity,
                message,
                status,
                resolved_at,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_alerts(
    start_time: str | None = None,
    end_time: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    limit: int = 100,
    db_path: str | Path = DB_PATH,
    node_id: str | None = None,
) -> list[dict[str, Any]]:
    """Get alerts newest-first, optionally filtered by time/severity/status/node."""
    _validate_limit(limit)
    if status is not None and status not in ("active", "resolved"):
        raise ValueError("status must be 'active' or 'resolved'")

    query = "SELECT * FROM alerts"
    conditions: list[str] = []
    parameters: list[Any] = []

    if start_time is not None:
        conditions.append("created_at_utc >= ?")
        parameters.append(_validate_non_empty_string(start_time, "start_time"))
    if end_time is not None:
        conditions.append("created_at_utc <= ?")
        parameters.append(_validate_non_empty_string(end_time, "end_time"))
    if severity is not None:
        conditions.append("severity = ?")
        parameters.append(_validate_non_empty_string(severity, "severity"))
    if status is not None:
        conditions.append("status = ?")
        parameters.append(status)
    if node_id is not None:
        conditions.append("node_id = ?")
        parameters.append(_validate_non_empty_string(node_id, "node_id"))

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY created_at_utc DESC, id DESC LIMIT ?"
    parameters.append(limit)

    connection = get_connection(db_path)
    try:
        rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def get_active_alerts(
    limit: int = 100,
    db_path: str | Path = DB_PATH,
    node_id: str | None = None,
) -> list[dict[str, Any]]:
    """Get active alerts, optionally limited to one node."""
    return get_alerts(
        status="active",
        limit=limit,
        db_path=db_path,
        node_id=node_id,
    )


def update_alert_status(
    alert_id: int,
    status: str,
    db_path: str | Path = DB_PATH,
) -> bool:
    """Update alert status and manage its resolved timestamp."""
    if isinstance(alert_id, bool) or not isinstance(alert_id, int) or alert_id <= 0:
        raise ValueError("alert_id must be a positive integer")
    if status not in ("active", "resolved"):
        raise ValueError("status must be 'active' or 'resolved'")

    resolved_at = None
    if status == "resolved":
        resolved_at = (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )

    connection = get_connection(db_path)
    try:
        cursor = connection.execute(
            """
            UPDATE alerts
            SET status = ?, resolved_at_utc = ?
            WHERE id = ?
            """,
            (status, resolved_at, alert_id),
        )
        connection.commit()
        return cursor.rowcount > 0
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    initialize_database()
    print("Database initialized successfully!")
    print(f"Database location: {DB_PATH}")
