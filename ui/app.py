"""NOC Dashboard (Streamlit).
 
Chạy:  python -m streamlit run ui/app.py
 
Nếu chưa có DB / bảng đúng tên, dashboard tự dùng dữ liệu mẫu để bạn thấy giao diện.
"""
import sqlite3
from pathlib import Path
 
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
 
# ============ CẤU HÌNH: chỉnh cho khớp storage/database.py ============
DB_PATH = Path(__file__).resolve().parent.parent / "noc.db"
METRICS_TABLE = "metrics"   # cột giả định: ts, node, metric, value
ALERTS_TABLE = "alerts"     # cột giả định: ts, node, metric, severity, status, message
REFRESH_SECONDS = 5
# =====================================================================
 
st.set_page_config(page_title="NOC Monitoring", layout="wide")
 
 
# ---------------------------- Data layer ----------------------------
def _query(sql: str):
    """Đọc SQLite ở chế độ chỉ-đọc. Trả về None nếu DB/bảng chưa sẵn sàng."""
    if not DB_PATH.exists():
        return None
    conn = None
    try:
        conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
        return pd.read_sql_query(sql, conn)
    except Exception:
        return None
    finally:
        if conn:
            conn.close()
 
 
def _demo_metrics(minutes: int = 60) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    ts = pd.date_range(end=pd.Timestamp.now(tz="UTC").floor("s"),
                       periods=minutes * 6, freq="10s")
    frames = []
    for node in ["server-01", "server-02"]:
        for metric, base in [("cpu_percent", 35), ("ram_percent", 55), ("disk_percent", 70)]:
            vals = np.clip(base + rng.normal(0, 5, len(ts)), 0, 100)
            frames.append(pd.DataFrame({"ts": ts, "node": node, "metric": metric, "value": vals}))
    return pd.concat(frames, ignore_index=True)
 
 
@st.cache_data(ttl=3)
def load_metrics():
    df = _query(f"SELECT ts, node, metric, value FROM {METRICS_TABLE} "
                f"ORDER BY ts DESC LIMIT 20000")
    demo = df is None or df.empty
    if demo:
        df = _demo_metrics()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)  # DB lưu UTC
    return df.sort_values("ts"), demo
 
 
@st.cache_data(ttl=3)
def load_alerts() -> pd.DataFrame:
    df = _query(f"SELECT ts, node, metric, severity, status, message FROM {ALERTS_TABLE} "
                f"ORDER BY ts DESC LIMIT 200")
    if df is None:
        return pd.DataFrame(columns=["ts", "node", "metric", "severity", "status", "message"])
    return df
 
 
# ------------------------------- UI --------------------------------
st.title("NOC Infrastructure Monitoring")
 
metrics, is_demo = load_metrics()
if is_demo:
    st.warning("Chưa đọc được dữ liệu thật từ SQLite, đang hiển thị DỮ LIỆU MẪU. "
               "Kiểm tra DB_PATH / tên bảng ở đầu file.")
 
with st.sidebar:
    st.header("Bộ lọc")
    minutes = st.select_slider("Khoảng thời gian (phút)", [5, 15, 30, 60, 180, 720], value=30)
    nodes = sorted(metrics["node"].unique())
    selected = st.multiselect("Node", nodes, default=nodes)
 
 
@st.fragment(run_every=REFRESH_SECONDS)  # chỉ làm mới phần này, không reload cả trang
def render(minutes: int, selected: list):
    df, _ = load_metrics()
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=minutes)
    df = df[(df["ts"] >= cutoff) & (df["node"].isin(selected))]
    if df.empty:
        st.info("Không có dữ liệu trong khoảng thời gian / node đã chọn.")
        return
 
    # KPI: giá trị mới nhất của mỗi chỉ số (trung bình các node đã chọn)
    latest = df.sort_values("ts").groupby(["node", "metric"]).tail(1)
    kpi = latest.groupby("metric")["value"].mean()
    cols = st.columns(len(kpi))
    for col, (name, val) in zip(cols, kpi.items()):
        col.metric(name, f"{val:.1f}")
 
    # Biểu đồ theo thời gian
    fig = px.line(df, x="ts", y="value", color="node", facet_row="metric",
                  height=220 * df["metric"].nunique())
    fig.update_yaxes(matches=None, title=None)
    fig.update_xaxes(title=None)
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    st.plotly_chart(fig, width="stretch")
 
    # Cảnh báo
    st.subheader("Cảnh báo")
    alerts = load_alerts()
    if alerts.empty:
        st.success("Không có cảnh báo nào.")
    else:
        st.dataframe(alerts, width="stretch", hide_index=True)
 
 
render(minutes, selected)
 