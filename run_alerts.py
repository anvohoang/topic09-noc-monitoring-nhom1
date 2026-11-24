from __future__ import annotations

import logging
import time

from alerts.engine import AlertEngine
from storage.database import initialize_database

NODE_ID = "windows-11-node-01"
CHECK_INTERVAL = 5  # seconds (ensures MTTD < 15s)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
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
        "NOC Alert Engine started for node '%s' (interval=%ss)",
        NODE_ID,
        CHECK_INTERVAL,
    )

    try:
        while True:
            cycle_start = time.monotonic()
            try:
                outcomes = engine.evaluate_node(NODE_ID)
                for item in outcomes:
                    if item.alert_saved:
                        logging.warning(
                            "NEW ALERT [ID=%s | %s | via=%s] %s",
                            item.alert_id,
                            item.severity.upper(),
                            item.triggered_by,
                            item.message,
                        )
                    elif item.suppressed_by_cooldown:
                        logging.info(
                            "COOLDOWN SUPPRESSED [%s] %s",
                            item.metric_name,
                            item.message,
                        )
                    elif item.auto_resolved_ids:
                        logging.info(
                            "AUTO-RESOLVED alert IDs %s for %s",
                            item.auto_resolved_ids,
                            item.metric_name,
                        )
            except Exception:
                logging.exception("Alert evaluation cycle failed")

            elapsed = time.monotonic() - cycle_start
            time.sleep(max(0.0, CHECK_INTERVAL - elapsed))
    except KeyboardInterrupt:
        logging.info("NOC Alert Engine stopped by user")


if __name__ == "__main__":
    main()