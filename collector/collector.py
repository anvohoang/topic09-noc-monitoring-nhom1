import time
from datetime import datetime, timezone
import psutil
import httpx


class NOCMetricsCollector:
    """Module thu thập chỉ số hệ thống (CPU, RAM, Disk, Network) 
    và trạng thái dịch vụ HTTP cho NOC Monitoring Toolkit.
    """

    def __init__(self, node_id: str = "node-01"):
        self.node_id = node_id
        # Lưu số byte ban đầu để tính lượng byte chênh lệch (delta)
        net_io = psutil.net_io_counters()
        self.last_bytes_sent = net_io.bytes_sent
        self.last_bytes_recv = net_io.bytes_recv

    def get_iso_utc_timestamp(self) -> str:
        """Trả về thời gian hiện tại theo chuẩn ISO 8601 UTC."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def collect_system_metrics(self) -> dict:
        """Thu thập CPU %, RAM %, Disk % và tính lượng byte phát sinh trong chu kỳ."""
        cpu_percent = psutil.cpu_percent(interval=1)
        ram_percent = psutil.virtual_memory().percent
        disk_percent = psutil.disk_usage('/').percent

        # Lấy số byte mạng hiện tại và tính chênh lệch so với lần đo trước
        net_io = psutil.net_io_counters()
        sent_bytes_per_cycle = net_io.bytes_sent - self.last_bytes_sent
        recv_bytes_per_cycle = net_io.bytes_recv - self.last_bytes_recv

        # Cập nhật trạng thái mới
        self.last_bytes_sent = net_io.bytes_sent
        self.last_bytes_recv = net_io.bytes_recv

        return {
            "cpu_percent": round(cpu_percent, 2),
            "ram_percent": round(ram_percent, 2),
            "disk_percent": round(disk_percent, 2),
            "network": {
                "sent_bytes_per_cycle": max(0, sent_bytes_per_cycle),
                "recv_bytes_per_cycle": max(0, recv_bytes_per_cycle)
            }
        }

    def check_http_endpoint(self, target_url: str, timeout: float = 3.0) -> dict:
        """Kiểm tra trạng thái UP/DOWN và đo độ trễ (latency ms) của HTTP endpoint."""
        try:
            start_time = time.perf_counter()
            with httpx.Client(timeout=timeout) as client:
                response = client.get(target_url)
            latency_ms = (time.perf_counter() - start_time) * 1000

            return {
                "endpoint": target_url,
                "is_up": response.status_code == 200,
                "status_code": response.status_code,
                "latency_ms": round(latency_ms, 2)
            }
        except Exception:
            return {
                "endpoint": target_url,
                "is_up": False,
                "status_code": None,
                "latency_ms": 0.0
            }

    def collect_payload(self, target_url: str) -> dict:
        """Đóng gói toàn bộ chỉ số theo chuẩn JSON đã chốt với SQLite DB."""
        return {
            "timestamp": self.get_iso_utc_timestamp(),
            "node_id": self.node_id,
            "system_metrics": self.collect_system_metrics(),
            "http_metrics": self.check_http_endpoint(target_url)
        }


if __name__ == "__main__":
    # Test thử Collector local
    collector = NOCMetricsCollector(node_id="server-dev-01")
    print("--- Đang kiểm tra chạy thử Collector ---")
    import json
    data = collector.collect_payload(target_url="https://httpbin.org/get")
    print(json.dumps(data, indent=2))