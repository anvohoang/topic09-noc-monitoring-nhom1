
"""NOC Monitoring Agent - sends local metrics to Central API."""

import logging
import os
import socket
import time

import httpx

from collector import NOCMetricsCollector


# Configuration
NODE_ID = os.getenv("NOC_NODE_ID", socket.gethostname().lower())

CENTRAL_API_URL = os.getenv(
    "NOC_API_URL",
    "http://127.0.0.1:8000",
).rstrip("/")

TARGET_URL = os.getenv(
    "NOC_TARGET_URL",
    "https://httpbin.org/get",
)

COLLECTION_INTERVAL = float(
    os.getenv("NOC_INTERVAL_SECONDS", "5")
)

API_KEY = os.getenv("NOC_API_KEY")

API_ENDPOINT = (
    f"{CENTRAL_API_URL}/api/v1/collector/payload"
)


# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


def main():
    if not API_KEY:
        raise SystemExit("NOC_API_KEY is not configured.")

    if COLLECTION_INTERVAL <= 0:
        raise SystemExit("Collection interval must be greater than zero.")

    collector = NOCMetricsCollector(node_id=NODE_ID)

    logging.info("NOC Agent started")
    logging.info("Node ID: %s", NODE_ID)
    logging.info("Central API: %s", CENTRAL_API_URL)

    try:
        with httpx.Client(
            timeout=10.0,
            headers={"X-API-Key": API_KEY},
        ) as client:

            while True:
                cycle_start = time.monotonic()

                try:
                    # Collect data from this computer.
                    payload = collector.collect_payload(TARGET_URL)

                    # Send data to Central API.
                    response = client.post(
                        API_ENDPOINT,
                        json=payload,
                    )

                    response.raise_for_status()
                    result = response.json()

                    logging.info(
                        "DATA SENT | node=%s | CPU=%.2f%% | "
                        "RAM=%.2f%% | Disk=%.2f%% | Metrics ID=%s",
                        NODE_ID,
                        payload["system_metrics"]["cpu_percent"],
                        payload["system_metrics"]["ram_percent"],
                        payload["system_metrics"]["disk_percent"],
                        result["metrics_id"],
                    )

                except httpx.HTTPStatusError as error:
                    logging.error(
                        "API rejected payload: HTTP %s - %s",
                        error.response.status_code,
                        error.response.text,
                    )

                except httpx.RequestError as error:
                    logging.error(
                        "Cannot connect to Central API: %s",
                        error,
                    )

                except Exception:
                    logging.exception("Agent collection cycle failed")

                elapsed = time.monotonic() - cycle_start
                time.sleep(max(0, COLLECTION_INTERVAL - elapsed))

    except KeyboardInterrupt:
        logging.info("NOC Agent stopped by user")


if __name__ == "__main__":
    main()
