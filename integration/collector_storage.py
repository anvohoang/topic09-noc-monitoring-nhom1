
"""Adapter connecting the Collector module to SQLite Storage."""

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from storage.database import (
    DB_PATH,
    save_metrics,
    save_service_check,
)


def persist_collector_payload(
    payload: dict[str, Any],
    service_name: str | None = None,
    db_path: str | Path = DB_PATH,
) -> dict[str, int]:
    """
    Convert a Collector payload and persist it into SQLite.

    The Collector's original payload is not modified.
    Returns the IDs of the two inserted records.
    """
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dictionary")

    timestamp = payload["timestamp"]
    node_id = payload["node_id"]

    system = payload["system_metrics"]
    network = system["network"]
    http = payload["http_metrics"]

    # Convert system metrics to the Storage schema.
    metrics_data = {
        "node_id": node_id,
        "timestamp_utc": timestamp,
        "cpu_percent": system["cpu_percent"],
        "memory_percent": system["ram_percent"],
        "disk_percent": system["disk_percent"],
        "network_sent_bytes": network["sent_bytes_per_cycle"],
        "network_recv_bytes": network["recv_bytes_per_cycle"],
    }

    # Derive a service name from the URL when one is not supplied.
    url = http["endpoint"]
    if service_name is None:
        service_name = urlparse(url).hostname or url

    status_code = http.get("status_code")
    is_available = http["is_up"]

    # Do not store 0 ms as a real latency when the request failed
    # before receiving an HTTP response.
    response_time = (
        http.get("latency_ms")
        if status_code is not None
        else None
    )

    error_message = http.get("error")

    if not is_available and not error_message:
        if status_code is None:
            error_message = "HTTP request failed; no status code returned"
        else:
            error_message = f"HTTP endpoint returned status {status_code}"

    # Convert HTTP metrics to the Storage schema.
    service_data = {
        "node_id": node_id,
        "timestamp_utc": timestamp,
        "service_name": service_name,
        "url": url,
        "is_available": is_available,
        "status_code": status_code,
        "response_time_ms": response_time,
        "error_message": error_message,
    }

    metrics_id = save_metrics(metrics_data, db_path=db_path)
    service_id = save_service_check(service_data, db_path=db_path)

    return {
        "metrics_id": metrics_id,
        "service_check_id": service_id,
    }
