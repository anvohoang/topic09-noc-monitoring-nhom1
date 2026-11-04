
import time
import logging

from collector import NOCMetricsCollector
from integration.collector_storage import persist_collector_payload


# Cau hinh collector
NODE_ID = "windows-11-node-01"
TARGET_URL = "https://httpbin.org/get"
COLLECTION_INTERVAL = 5  # seconds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


def main():
    collector = NOCMetricsCollector(node_id=NODE_ID)

    logging.info("NOC Collector started")
    logging.info("Node ID: %s", NODE_ID)
    logging.info("Collection interval: %s seconds", COLLECTION_INTERVAL)

    try:
        while True:
            cycle_start = time.monotonic()

            try:
                # Thu thap du lieu
                payload = collector.collect_payload(TARGET_URL)

                # Luu vao SQLite
                result = persist_collector_payload(
                    payload,
                    service_name="httpbin",
                )

                logging.info(
                    "Collection successful | CPU: %.2f%% | RAM: %.2f%% | "
                    "Disk: %.2f%% | HTTP: %s | Metrics ID: %s",
                    payload["system_metrics"]["cpu_percent"],
                    payload["system_metrics"]["ram_percent"],
                    payload["system_metrics"]["disk_percent"],
                    payload["http_metrics"]["status_code"],
                    result["metrics_id"],
                )

            except Exception:
                logging.exception("Collection cycle failed")

            # Duy tri khoang cach toi thieu giua hai lan bat dau
            elapsed = time.monotonic() - cycle_start
            remaining = max(0, COLLECTION_INTERVAL - elapsed)
            time.sleep(remaining)

    except KeyboardInterrupt:
        logging.info("NOC Collector stopped by user")


if __name__ == "__main__":
    main()
