
from pathlib import Path
import math
import sqlite3
from datetime import datetime, timezone


# Duong dan den database
DB_PATH = Path(__file__).resolve().parent / "noc_monitoring.db"


def get_connection(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    """
    Tao ket noi den SQLite database.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(str(db_path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def initialize_database(db_path: str | Path = DB_PATH) -> None:
    """
    Khoi tao database va cac bang neu chua ton tai.
    """
    connection = get_connection(db_path)

    try:
        cursor = connection.cursor()

        # Bang 1: Luu chi so he thong
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_utc TEXT NOT NULL,
                cpu_percent REAL NOT NULL,
                memory_percent REAL NOT NULL,
                disk_percent REAL NOT NULL,
                network_sent_bytes INTEGER,
                network_recv_bytes INTEGER
            )
        """)

        # Bang 2: Luu ket qua kiem tra dich vu HTTP
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS service_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_utc TEXT NOT NULL,
                service_name TEXT NOT NULL,
                url TEXT NOT NULL,
                is_available INTEGER NOT NULL
                    CHECK (is_available IN (0, 1)),
                status_code INTEGER,
                response_time_ms REAL,
                error_message TEXT
            )
        """)

        # Bang 3: Luu lich su canh bao
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at_utc TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'resolved')),
                resolved_at_utc TEXT
            )
        """)

        # Tao index de truy van nhanh hon
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_metrics_timestamp
            ON metrics(timestamp_utc)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_service_checks_timestamp
            ON service_checks(timestamp_utc)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_status
            ON alerts(status)
        """)

        connection.commit()

    except sqlite3.Error:
        connection.rollback()
        raise

    finally:
        connection.close()


def save_metrics(
    metrics: dict,
    db_path: str | Path = DB_PATH
) -> int:
    """
    Luu mot ban ghi chi so he thong vao SQLite.
    Tra ve ID cua ban ghi vua duoc tao.
    """

    required_fields = [
        "timestamp_utc",
        "cpu_percent",
        "memory_percent",
        "disk_percent",
    ]

    missing_fields = [
        field for field in required_fields
        if field not in metrics
    ]

    if missing_fields:
        raise ValueError(f"Missing fields: {missing_fields}")

    timestamp = metrics["timestamp_utc"]

    if not isinstance(timestamp, str) or not timestamp.strip():
        raise ValueError("timestamp_utc must be a non-empty string")

    try:
        cpu = float(metrics["cpu_percent"])
        memory = float(metrics["memory_percent"])
        disk = float(metrics["disk_percent"])
    except (TypeError, ValueError) as error:
        raise ValueError("CPU, memory and disk must be numeric") from error

    # Kiem tra gia tri phan tram
    for name, value in [
        ("cpu_percent", cpu),
        ("memory_percent", memory),
        ("disk_percent", disk),
    ]:
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError(f"{name} must be between 0 and 100")

    network_sent = metrics.get("network_sent_bytes")
    network_recv = metrics.get("network_recv_bytes")

    # Kiem tra du lieu mang
    for name, value in [
        ("network_sent_bytes", network_sent),
        ("network_recv_bytes", network_recv),
    ]:
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")

    connection = get_connection(db_path)

    try:
        cursor = connection.execute(
            """
            INSERT INTO metrics (
                timestamp_utc,
                cpu_percent,
                memory_percent,
                disk_percent,
                network_sent_bytes,
                network_recv_bytes
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                cpu,
                memory,
                disk,
                network_sent,
                network_recv,
            ),
        )

        connection.commit()
        return cursor.lastrowid

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
) -> list[dict]:
    """
    Truy van cac chi so he thong.
    Ho tro loc theo khoang thoi gian.
    """

    if limit <= 0:
        raise ValueError("limit must be greater than 0")

    query = "SELECT * FROM metrics"
    conditions = []
    parameters = []

    if start_time is not None:
        conditions.append("timestamp_utc >= ?")
        parameters.append(start_time)

    if end_time is not None:
        conditions.append("timestamp_utc <= ?")
        parameters.append(end_time)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY timestamp_utc DESC, id DESC LIMIT ?"
    parameters.append(limit)

    connection = get_connection(db_path)

    try:
        cursor = connection.execute(query, parameters)
        rows = cursor.fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def save_service_check(
    service_check: dict,
    db_path: str | Path = DB_PATH
) -> int:
    """
    Luu ket qua kiem tra dich vu HTTP.
    Tra ve ID cua ban ghi.
    """

    required_fields = [
        "timestamp_utc",
        "service_name",
        "url",
        "is_available",
    ]

    missing_fields = [
        field for field in required_fields
        if field not in service_check
    ]

    if missing_fields:
        raise ValueError(f"Missing fields: {missing_fields}")

    timestamp = service_check["timestamp_utc"]
    service_name = service_check["service_name"]
    url = service_check["url"]
    is_available = service_check["is_available"]

    if not isinstance(timestamp, str) or not timestamp.strip():
        raise ValueError("Invalid timestamp_utc")

    if not isinstance(service_name, str) or not service_name.strip():
        raise ValueError("Invalid service_name")

    if not isinstance(url, str) or not url.strip():
        raise ValueError("Invalid url")

    if isinstance(is_available, bool):
        is_available = int(is_available)
    elif isinstance(is_available, int) and is_available in (0, 1):
        pass
    else:
        raise ValueError("is_available must be True, False, 0 or 1")

    status_code = service_check.get("status_code")
    response_time = service_check.get("response_time_ms")
    error_message = service_check.get("error_message")

    if status_code is not None:
        if (
            isinstance(status_code, bool)
            or not isinstance(status_code, int)
            or not 100 <= status_code <= 599
        ):
            raise ValueError("Invalid HTTP status_code")

    if response_time is not None:
        response_time = float(response_time)

        if not math.isfinite(response_time) or response_time < 0:
            raise ValueError("Invalid response_time_ms")

    if error_message is not None and not isinstance(error_message, str):
        raise ValueError("error_message must be a string or None")

    connection = get_connection(db_path)

    try:
        cursor = connection.execute(
            """
            INSERT INTO service_checks (
                timestamp_utc,
                service_name,
                url,
                is_available,
                status_code,
                response_time_ms,
                error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
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
        return cursor.lastrowid

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
) -> list[dict]:
    """
    Truy van ket qua kiem tra dich vu HTTP.
    Ho tro loc theo thoi gian va ten dich vu.
    """

    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer")

    query = "SELECT * FROM service_checks"
    conditions = []
    parameters = []

    if start_time is not None:
        conditions.append("timestamp_utc >= ?")
        parameters.append(start_time)

    if end_time is not None:
        conditions.append("timestamp_utc <= ?")
        parameters.append(end_time)

    if service_name is not None:
        conditions.append("service_name = ?")
        parameters.append(service_name)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY timestamp_utc DESC, id DESC LIMIT ?"
    parameters.append(limit)

    connection = get_connection(db_path)

    try:
        cursor = connection.execute(query, parameters)
        return [dict(row) for row in cursor.fetchall()]

    finally:
        connection.close()

def save_alert(
    alert: dict,
    db_path: str | Path = DB_PATH
) -> int:
    """
    Luu mot canh bao moi vao SQLite.
    Tra ve ID cua canh bao.
    """

    required_fields = [
        "created_at_utc",
        "metric_name",
        "severity",
        "message",
    ]

    missing_fields = [
        field for field in required_fields
        if field not in alert
    ]

    if missing_fields:
        raise ValueError(f"Missing fields: {missing_fields}")

    timestamp = alert["created_at_utc"]
    metric_name = alert["metric_name"]
    severity = alert["severity"]
    message = alert["message"]
    status = alert.get("status", "active")
    resolved_at = alert.get("resolved_at_utc")

    for name, value in [
        ("created_at_utc", timestamp),
        ("metric_name", metric_name),
        ("severity", severity),
        ("message", message),
    ]:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")

    if status not in ("active", "resolved"):
        raise ValueError("Invalid alert status")

    if resolved_at is not None and not isinstance(resolved_at, str):
        raise ValueError("resolved_at_utc must be a string or None")

    connection = get_connection(db_path)

    try:
        cursor = connection.execute(
            """
            INSERT INTO alerts (
                created_at_utc,
                metric_name,
                severity,
                message,
                status,
                resolved_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                metric_name,
                severity,
                message,
                status,
                resolved_at,
            ),
        )

        connection.commit()
        return cursor.lastrowid

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
) -> list[dict]:
    """
    Truy van lich su canh bao.
    Ho tro loc theo thoi gian, muc do va trang thai.
    """

    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer")

    if status is not None and status not in ("active", "resolved"):
        raise ValueError("Invalid alert status")

    query = "SELECT * FROM alerts"
    conditions = []
    parameters = []

    if start_time is not None:
        conditions.append("created_at_utc >= ?")
        parameters.append(start_time)

    if end_time is not None:
        conditions.append("created_at_utc <= ?")
        parameters.append(end_time)

    if severity is not None:
        conditions.append("severity = ?")
        parameters.append(severity)

    if status is not None:
        conditions.append("status = ?")
        parameters.append(status)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY created_at_utc DESC, id DESC LIMIT ?"
    parameters.append(limit)

    connection = get_connection(db_path)

    try:
        cursor = connection.execute(query, parameters)
        return [dict(row) for row in cursor.fetchall()]

    finally:
        connection.close()


def get_active_alerts(
    limit: int = 100,
    db_path: str | Path = DB_PATH
) -> list[dict]:
    """
    Lay danh sach canh bao dang hoat dong.
    """

    return get_alerts(
        status="active",
        limit=limit,
        db_path=db_path,
    )


def update_alert_status(
    alert_id: int,
    status: str,
    db_path: str | Path = DB_PATH
) -> bool:
    """
    Cap nhat trang thai canh bao.
    Tu dong ghi thoi gian khi canh bao duoc giai quyet.
    """

    if isinstance(alert_id, bool) or not isinstance(alert_id, int) or alert_id <= 0:
        raise ValueError("alert_id must be a positive integer")

    if status not in ("active", "resolved"):
        raise ValueError("Invalid alert status")

    if status == "resolved":
        resolved_at = (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
    else:
        resolved_at = None

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
