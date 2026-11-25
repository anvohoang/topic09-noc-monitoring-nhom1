
"""Adapter chuyển kết quả Analyzer thành dữ liệu cho Alert Engine."""

from __future__ import annotations

from typing import Any


def normalize_metric_name(metric_name: str) -> str:
    """Chuẩn hóa tên metric theo quy ước của Alerts."""

    if metric_name.startswith("http_availability:"):
        service_name = metric_name.split(":", 1)[1]
        return f"service:{service_name}:availability"

    if metric_name.startswith("http_latency_ms:"):
        service_name = metric_name.split(":", 1)[1]
        return f"service:{service_name}:response_time_ms"

    return metric_name


def adapt_analysis_results(
    node_id: str,
    analysis_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Chuẩn hóa kết quả Analyzer trước khi chuyển sang Alert Engine."""

    if not isinstance(node_id, str) or not node_id.strip():
        raise ValueError("node_id must be a non-empty string")

    if not isinstance(analysis_results, list):
        raise TypeError("analysis_results must be a list")

    node_id = node_id.strip()
    adapted_results: list[dict[str, Any]] = []

    valid_severities = {"normal", "warning", "critical"}

    for item in analysis_results:
        if not isinstance(item, dict):
            raise TypeError("Each analysis result must be a dictionary")

        result_node_id = str(item.get("node_id") or node_id)

        if result_node_id != node_id:
            raise ValueError(
                f"Node mismatch: expected {node_id}, "
                f"received {result_node_id}"
            )

        original_metric = item.get("metric_name")

        if not isinstance(original_metric, str) or not original_metric.strip():
            raise ValueError("Invalid metric_name")

        severity = str(
            item.get("severity", "NORMAL")
        ).strip().lower()

        if severity not in valid_severities:
            raise ValueError(f"Invalid severity: {severity}")

        current_value = float(item["current_value"])

        normalized_result = dict(item)
        normalized_result.update(
            {
                "node_id": node_id,
                "metric_name": normalize_metric_name(
                    original_metric.strip()
                ),
                "current_value": current_value,
                "severity": severity,
                "message": str(item.get("message") or ""),
            }
        )

        adapted_results.append(normalized_result)

    return adapted_results
