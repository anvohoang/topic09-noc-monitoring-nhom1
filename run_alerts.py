
"""Run Analyzer and Alert Engine for all monitored nodes."""

from __future__ import annotations

import logging
import time

from analyzer import analyze_all_for_node
from alerts.engine import AlertEngine
from integration.alert_adapter import adapt_analysis_results
from storage.database import get_nodes, initialize_database


CHECK_INTERVAL = 5
ANALYSIS_LIMIT = 100


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def log_outcomes(node_id: str, outcomes: list) -> None:
    """Log cảnh báo và kết quả xử lý của từng Node."""

    for item in outcomes:
        if item.alert_saved:
            logging.warning(
                "NEW ALERT [Node=%s | ID=%s | %s | via=%s] %s",
                node_id,
                item.alert_id,
                item.severity.upper(),
                item.triggered_by,
                item.message,
            )

        elif item.suppressed_by_cooldown:
            logging.info(
                "COOLDOWN SUPPRESSED [Node=%s | Metric=%s]",
                node_id,
                item.metric_name,
            )

        elif item.auto_resolved_ids:
            logging.info(
                "AUTO-RESOLVED [Node=%s | IDs=%s | Metric=%s]",
                node_id,
                item.auto_resolved_ids,
                item.metric_name,
            )


def evaluate_all_nodes(engine: AlertEngine) -> None:
    """Phân tích và đánh giá cảnh báo của tất cả Node."""

    nodes = get_nodes(db_path=engine.db_path)

    if not nodes:
        logging.warning("No nodes found in the database.")
        return

    logging.info("Found %s monitored nodes.", len(nodes))

    for node_record in nodes:
        node_id = node_record.get("node_id")

        if not isinstance(node_id, str) or not node_id.strip():
            continue

        try:
            logging.info("Analyzing Node: %s", node_id)

            # 1. Analyzer của Khoa phân tích dữ liệu Node.
            analysis_results = analyze_all_for_node(
                node_id=node_id,
                limit=ANALYSIS_LIMIT,
                window_size=engine.window_size,
                db_path=engine.db_path,
            )

            if not analysis_results:
                logging.info(
                    "No analysis results for Node %s.",
                    node_id,
                )
                continue

            # 2. Adapter của Ân chuẩn hóa kết quả.
            adapted_results = adapt_analysis_results(
                node_id=node_id,
                analysis_results=analysis_results,
            )

            # 3. Alert Engine của Lộc xử lý vòng đời cảnh báo.
            outcomes = engine.process_analysis_results(
                node_id=node_id,
                analysis_results=adapted_results,
            )

            # 4. Ghi nhận kết quả.
            log_outcomes(node_id, outcomes)

        except Exception:
            logging.exception(
                "Failed to process Node %s.",
                node_id,
            )


def main() -> None:
    configure_logging()
    initialize_database()

    engine = AlertEngine(
        window_size=30,
        min_samples=10,
        cooldown_seconds=300,
        auto_resolve=True,
    )

    logging.info(
        "NOC Analyzer-Alert Integration started. "
        "Check interval: %s seconds.",
        CHECK_INTERVAL,
    )

    try:
        while True:
            cycle_start = time.monotonic()

            evaluate_all_nodes(engine)

            elapsed = time.monotonic() - cycle_start
            sleep_time = max(0.0, CHECK_INTERVAL - elapsed)

            time.sleep(sleep_time)

    except KeyboardInterrupt:
        logging.info("NOC Analyzer-Alert Integration stopped.")


if __name__ == "__main__":
    main()
