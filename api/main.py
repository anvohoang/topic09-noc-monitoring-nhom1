
"""
Central API Server for NOC Monitoring Toolkit.

Responsibilities:
- Receive and validate monitoring data from Collector Agents.
- Authenticate requests using API keys.
- Store monitoring data in SQLite.
- Provide read APIs for the Web Dashboard.
- Expose anomaly analysis results from the Analyzer module.
"""

from __future__ import annotations

import hmac
import logging
import os

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from analyzer import analyze_all_for_node
from integration.collector_storage import persist_collector_payload

from storage.database import (
    get_alerts,
    get_metrics,
    get_nodes,
    get_service_checks,
    initialize_database,
)


# ============================================================
# LOGGING CONFIGURATION
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("noc.central")


# ============================================================
# DATA VALIDATION MODELS
# ============================================================

class NetworkMetrics(BaseModel):
    """Network traffic metrics collected during one cycle."""

    model_config = ConfigDict(extra="forbid")

    sent_bytes_per_cycle: int = Field(ge=0)
    recv_bytes_per_cycle: int = Field(ge=0)


class SystemMetrics(BaseModel):
    """System resource metrics collected by an Agent."""

    model_config = ConfigDict(extra="forbid")

    cpu_percent: float = Field(ge=0, le=100)
    ram_percent: float = Field(ge=0, le=100)
    disk_percent: float = Field(ge=0, le=100)

    network: NetworkMetrics


class HTTPMetrics(BaseModel):
    """HTTP endpoint health-check result."""

    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(min_length=1)
    is_up: bool

    status_code: int | None = Field(
        default=None,
        ge=100,
        le=599,
    )

    latency_ms: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
    )

    error: str | None = None


class CollectorPayload(BaseModel):
    """Complete monitoring payload sent by a Collector Agent."""

    model_config = ConfigDict(extra="forbid")

    timestamp: str

    node_id: str = Field(
        min_length=1,
        max_length=100,
    )

    system_metrics: SystemMetrics
    http_metrics: HTTPMetrics

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        """Require an ISO 8601 timestamp with timezone information."""

        try:
            parsed = datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )

        except ValueError as error:
            raise ValueError(
                "timestamp must use ISO 8601 format"
            ) from error

        if parsed.tzinfo is None:
            raise ValueError(
                "timestamp must include timezone information"
            )

        return value

    @field_validator("node_id")
    @classmethod
    def validate_node_id(cls, value: str) -> str:
        """Remove surrounding whitespace and validate node ID."""

        value = value.strip()

        if not value:
            raise ValueError(
                "node_id cannot be empty"
            )

        return value


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database when the API starts."""

    initialize_database()

    logger.info(
        "Central SQLite database initialized"
    )

    logger.info(
        "NOC Monitoring Central API started"
    )

    yield

    logger.info(
        "NOC Monitoring Central API stopped"
    )


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="NOC Monitoring Central API",
    description=(
        "Central API for receiving monitoring data "
        "from Collector Agents, providing Dashboard data, "
        "and exposing anomaly analysis results."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ============================================================
# API KEY AUTHENTICATION
# ============================================================

def verify_api_key(
    api_key: str | None,
) -> None:
    """Verify the API key against the Central Server configuration."""

    expected_key = os.getenv("NOC_API_KEY")

    if not expected_key:
        raise HTTPException(
            status_code=503,
            detail="Central API key is not configured",
        )

    if not api_key or not hmac.compare_digest(
        api_key,
        expected_key,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
        )


def require_api_key(
    x_api_key: str | None = Header(
        default=None,
        alias="X-API-Key",
    ),
) -> None:
    """FastAPI dependency used to protect private endpoints."""

    verify_api_key(x_api_key)


# ============================================================
# SYSTEM - HEALTH CHECK
# ============================================================

@app.get(
    "/health",
    tags=["System"],
)
def health_check() -> dict[str, str]:
    """Check whether the Central API is running."""

    return {
        "status": "ok",
        "service": "NOC Monitoring Central API",
        "version": "1.0.0",
    }


# ============================================================
# COLLECTOR - RECEIVE MONITORING DATA
# ============================================================

@app.post(
    "/api/v1/collector/payload",
    tags=["Collector"],
    dependencies=[Depends(require_api_key)],
)
def receive_collector_payload(
    payload: CollectorPayload,
) -> dict[str, Any]:
    """Receive, validate and store one Collector payload."""

    try:
        result = persist_collector_payload(
            payload.model_dump(),
            service_name=None,
        )

    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    except Exception as error:
        logger.exception(
            "Failed to save payload from node %s",
            payload.node_id,
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to save monitoring data",
        ) from error

    logger.info(
        "Payload received and saved | node=%s | metrics_id=%s",
        payload.node_id,
        result["metrics_id"],
    )

    return {
        "status": "accepted",
        "node_id": payload.node_id,
        "metrics_id": result["metrics_id"],
        "service_check_id": result["service_check_id"],
    }


# ============================================================
# DASHBOARD - NODE APIs
# ============================================================

@app.get(
    "/api/v1/nodes",
    tags=["Dashboard"],
    dependencies=[Depends(require_api_key)],
)
def list_nodes() -> dict[str, Any]:
    """Get all nodes with stored monitoring metrics."""

    nodes = get_nodes()

    return {
        "count": len(nodes),
        "items": nodes,
    }


# ============================================================
# DASHBOARD - METRICS APIs
# ============================================================

@app.get(
    "/api/v1/metrics/latest",
    tags=["Dashboard"],
    dependencies=[Depends(require_api_key)],
)
def get_latest_metrics(
    node_id: str | None = None,
) -> dict[str, Any]:
    """Get the latest metrics, optionally filtered by node."""

    try:
        records = get_metrics(
            limit=1,
            node_id=node_id,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    return {
        "item": records[0] if records else None,
    }


@app.get(
    "/api/v1/metrics",
    tags=["Dashboard"],
    dependencies=[Depends(require_api_key)],
)
def read_metrics(
    node_id: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = Query(
        default=100,
        ge=1,
        le=1000,
    ),
) -> dict[str, Any]:
    """Get historical system metrics."""

    try:
        records = get_metrics(
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            node_id=node_id,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    return {
        "count": len(records),
        "items": records,
    }


# ============================================================
# DASHBOARD - SERVICE CHECK APIs
# ============================================================

@app.get(
    "/api/v1/service-checks",
    tags=["Dashboard"],
    dependencies=[Depends(require_api_key)],
)
def read_service_checks(
    node_id: str | None = None,
    service_name: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = Query(
        default=100,
        ge=1,
        le=1000,
    ),
) -> dict[str, Any]:
    """Get HTTP service-check history."""

    try:
        records = get_service_checks(
            start_time=start_time,
            end_time=end_time,
            service_name=service_name,
            limit=limit,
            node_id=node_id,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    return {
        "count": len(records),
        "items": records,
    }


# ============================================================
# DASHBOARD - ALERT APIs
# ============================================================

@app.get(
    "/api/v1/alerts",
    tags=["Dashboard"],
    dependencies=[Depends(require_api_key)],
)
def read_alerts(
    node_id: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = Query(
        default=100,
        ge=1,
        le=1000,
    ),
) -> dict[str, Any]:
    """Get alert history with optional filters."""

    try:
        records = get_alerts(
            start_time=start_time,
            end_time=end_time,
            severity=severity,
            status=status,
            limit=limit,
            node_id=node_id,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    return {
        "count": len(records),
        "items": records,
    }


# ============================================================
# ANALYZER - ANOMALY DETECTION API
# ============================================================

@app.get(
    "/api/v1/analyzer/{node_id}",
    tags=["Analyzer"],
    dependencies=[Depends(require_api_key)],
)
def read_node_analysis(
    node_id: str,
    limit: int = Query(
        default=100,
        ge=6,
        le=1000,
    ),
    window_size: int = Query(
        default=30,
        ge=5,
        le=100,
    ),
) -> dict[str, Any]:
    """
    Analyze system metrics and HTTP service checks for one node.

    This endpoint:
    - Reads historical data from SQLite.
    - Runs the Analyzer module.
    - Returns normal and anomalous analysis results.

    It does not automatically create or store alerts.
    """

    node_id = node_id.strip()

    if not node_id:
        raise HTTPException(
            status_code=422,
            detail="node_id cannot be empty",
        )

    try:
        results = analyze_all_for_node(
            node_id=node_id,
            limit=limit,
            window_size=window_size,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    except Exception as error:
        logger.exception(
            "Analyzer failed for node %s",
            node_id,
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to analyze monitoring data",
        ) from error

    anomaly_count = sum(
        1
        for item in results
        if item.get("is_anomaly") is True
    )

    logger.info(
        "Node analysis completed | node=%s | results=%s | anomalies=%s",
        node_id,
        len(results),
        anomaly_count,
    )

    return {
        "node_id": node_id,
        "count": len(results),
        "anomaly_count": anomaly_count,
        "items": results,
    }
