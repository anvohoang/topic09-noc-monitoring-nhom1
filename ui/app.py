"""NOC Dashboard (Streamlit) - đọc dữ liệu thật qua storage/database.py.
 
Chạy từ thư mục gốc dự án:  python -m streamlit run ui/app.py
Nếu DB chưa có dữ liệu, dashboard tự dùng dữ liệu mẫu.
"""
import sys
from pathlib import Path
 
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
 
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
 
from storage.database import (  # noqa: E402
    get_alerts,
    get_metrics,
    get_nodes,
    get_service_checks,
    initialize_database,
)
 
# ============================== CẤU HÌNH ==============================
REFRESH_SECONDS = 5
LOCAL_TZ = "Asia/Ho_Chi_Minh"
METRICS = [
    ("cpu_percent", "CPU (%)"),
    ("memory_percent", "RAM (%)"),
    ("disk_percent", "Ổ đĩa (%)"),
]
# Từ khóa để ghép cảnh báo (alerts.metric_name) với từng biểu đồ
METRIC_KEYS = {
    "cpu_percent": ("cpu",),
    "memory_percent": ("memory", "ram"),
    "disk_percent": ("disk",),
}
PALETTE = ["#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd", "#8c564b", "#17becf"]
TIME_FMT = "%H:%M:%S %d/%m/%Y"
 
COLS = {
    "metrics": ["node_id", "timestamp_utc", "cpu_percent", "memory_percent",
                "disk_percent", "network_sent_bytes", "network_recv_bytes"],
    "nodes": ["node_id", "last_seen_utc", "metrics_count"],
    "services": ["node_id", "timestamp_utc", "service_name", "url", "is_available",
                 "status_code", "response_time_ms", "error_message"],
    "alerts": ["node_id", "created_at_utc", "metric_name", "severity", "message",
               "status", "resolved_at_utc"],
}
 
st.set_page_config(page_title="NOC Monitoring", layout="wide")
 
 
# ============================ DATA LAYER ==============================
def _to_local(series: pd.Series) -> pd.Series:
    s = pd.to_datetime(series, utc=True, errors="coerce")
    try:
        return s.dt.tz_convert(LOCAL_TZ)
    except Exception:
        return s
 
 
def _prepare(df: pd.DataFrame, kind: str, time_col: str) -> pd.DataFrame:
    for c in COLS[kind]:
        if c not in df.columns:
            df[c] = pd.Series(dtype=object)
    df["ts"] = _to_local(df[time_col]) if not df.empty else pd.Series(dtype=object)
    return df
 
 
def _demo():
    rng = np.random.default_rng(42)
    ts = pd.date_range(end=pd.Timestamp.now(tz="UTC").floor("s"), periods=360, freq="10s")
    iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    metrics = pd.concat([
        pd.DataFrame({
            "node_id": node, "timestamp_utc": iso,
            "cpu_percent": np.clip(35 + rng.normal(0, 6, len(ts)), 0, 100),
            "memory_percent": np.clip(55 + rng.normal(0, 4, len(ts)), 0, 100),
            "disk_percent": np.clip(70 + rng.normal(0, 1, len(ts)), 0, 100),
        }) for node in ("server-01", "server-02")
    ], ignore_index=True)
    nodes = metrics.groupby("node_id").agg(
        last_seen_utc=("timestamp_utc", "max"), metrics_count=("timestamp_utc", "size")
    ).reset_index()
    services = pd.DataFrame([
        {"node_id": "server-01", "timestamp_utc": t, "service_name": name,
         "url": f"https://{name.lower()}.example.com", "is_available": 1,
         "status_code": 200, "response_time_ms": float(abs(rng.normal(base, 20))),
         "error_message": None}
        for name, base in (("Website", 120), ("API", 80)) for t in iso[::10]
    ])
    alerts = pd.DataFrame([
        {"node_id": "server-01", "created_at_utc": iso[250], "metric_name": "cpu_percent",
         "severity": "critical", "message": "CPU vượt ngưỡng 90% (mẫu)",
         "status": "active", "resolved_at_utc": None},
        {"node_id": "server-02", "created_at_utc": iso[150], "metric_name": "memory_percent",
         "severity": "warning", "message": "RAM cao bất thường (mẫu)",
         "status": "resolved", "resolved_at_utc": iso[170]},
    ])
    return metrics, nodes, services, alerts
 
 
@st.cache_data(ttl=3)
def load_all():
    try:
        initialize_database()
        metrics = pd.DataFrame(get_metrics(limit=20000))
        nodes = pd.DataFrame(get_nodes())
        services = pd.DataFrame(get_service_checks(limit=5000))
        alerts = pd.DataFrame(get_alerts(limit=500))
    except Exception:
        metrics = nodes = services = alerts = pd.DataFrame()
    demo = metrics.empty
    if demo:
        metrics, nodes, services, alerts = _demo()
    metrics = _prepare(metrics, "metrics", "timestamp_utc").sort_values("ts")
    nodes = _prepare(nodes, "nodes", "last_seen_utc")
    services = _prepare(services, "services", "timestamp_utc").sort_values("ts")
    alerts = _prepare(alerts, "alerts", "created_at_utc")
    return metrics, nodes, services, alerts, demo
 
 
def anomaly_points(alerts: pd.DataFrame, m: pd.DataFrame, key: str) -> pd.DataFrame:
    """Điểm đánh dấu: mỗi cảnh báo gắn vào điểm dữ liệu gần nhất của node đó."""
    out = []
    if not alerts.empty:
        keys = METRIC_KEYS[key]
        names = alerts["metric_name"].astype(str).str.lower()
        sel = alerts[names.apply(lambda s: any(k in s for k in keys))]
        for _, a in sel.iterrows():
            sub = m[m["node_id"] == a["node_id"]]
            if sub.empty or pd.isna(a["ts"]):
                continue
            i = (sub["ts"] - a["ts"]).abs().idxmin()
            out.append({"ts": a["ts"], "value": sub.loc[i, key],
                        "text": f'{a["severity"]}: {a["message"]}'})
    return pd.DataFrame(out, columns=["ts", "value", "text"])
 
 
# ================================ UI ==================================
st.title("NOC Infrastructure Monitoring")
 
metrics0, nodes0, _s, alerts0, is_demo = load_all()
if is_demo:
    st.warning("Database chưa có dữ liệu, đang hiển thị DỮ LIỆU MẪU. "
               "Hãy chạy API và agent để có dữ liệu thật.")
 
with st.sidebar:
    st.header("Bộ lọc")
    minutes = st.select_slider("Khoảng thời gian (phút)", [5, 15, 30, 60, 180, 720], value=30)
    all_nodes = sorted(set(nodes0["node_id"].dropna()) | set(metrics0["node_id"].dropna()))
    selected = st.multiselect("Node", all_nodes, default=all_nodes)
    down_after = st.slider("Coi node là DOWN sau (giây)", 10, 300, 60, step=10)
    st.divider()
    severities = st.multiselect("Mức độ cảnh báo (để trống = tất cả)",
                                sorted(alerts0["severity"].dropna().unique()))
    alert_status = st.radio("Trạng thái cảnh báo", ["Tất cả", "active", "resolved"],
                            horizontal=True)
 
 
@st.fragment(run_every=REFRESH_SECONDS)  # chỉ làm mới phần này, không tải lại cả trang
def render(minutes, selected, down_after, severities, alert_status):
    metrics, nodes, services, alerts, _ = load_all()
    now = pd.Timestamp.now(tz="UTC")
    cutoff = now - pd.Timedelta(minutes=minutes)
 
    m = metrics[(metrics["ts"] >= cutoff) & metrics["node_id"].isin(selected)]
    al_all = alerts[alerts["node_id"].isin(selected)]
    sv = services[services["node_id"].isin(selected)]
    sv_latest = (sv.groupby(["node_id", "service_name"]).tail(1)
                 if not sv.empty else sv)
 
    # ---- KPI ----
    latest = m.groupby("node_id").tail(1)
    cols = st.columns(5)
    for col, (key, label) in zip(cols[:3], METRICS):
        col.metric(label, f"{latest[key].mean():.1f}" if not latest.empty else "–")
    cols[3].metric("Cảnh báo đang active", int((al_all["status"] == "active").sum()))
    up = int((sv_latest["is_available"] == 1).sum()) if not sv_latest.empty else 0
    cols[4].metric("Dịch vụ UP", f"{up}/{len(sv_latest)}")
 
    # ---- Trạng thái node ----
    st.subheader("Trạng thái node")
    n = nodes[nodes["node_id"].isin(selected)].copy()
    if n.empty:
        st.info("Chưa có node nào.")
    else:
        age = (now - n["ts"]).dt.total_seconds()
        n["Trạng thái"] = np.where(age <= down_after, "UP", "DOWN")
        n["Cách đây (giây)"] = age.round().fillna(-1).astype(int)
        n["Lần cuối"] = n["ts"].dt.strftime(TIME_FMT)
        st.dataframe(
            n[["node_id", "Trạng thái", "Lần cuối", "Cách đây (giây)", "metrics_count"]]
            .rename(columns={"node_id": "Node", "metrics_count": "Số bản ghi"}),
            width="stretch", hide_index=True)
 
    # ---- Biểu đồ + điểm bất thường ----
    st.subheader("Chỉ số hệ thống")
    if m.empty:
        st.info("Không có dữ liệu trong khoảng thời gian / node đã chọn.")
    else:
        al_range = al_all[al_all["ts"] >= cutoff]
        fig = make_subplots(rows=len(METRICS), cols=1, shared_xaxes=True,
                            subplot_titles=[lbl for _, lbl in METRICS],
                            vertical_spacing=0.08)
        node_list = sorted(m["node_id"].unique())
        legend_anomaly = True
        for r, (key, _) in enumerate(METRICS, start=1):
            for i, node in enumerate(node_list):
                sub = m[m["node_id"] == node]
                fig.add_trace(go.Scatter(
                    x=sub["ts"], y=sub[key], mode="lines", name=node,
                    legendgroup=node, showlegend=(r == 1),
                    line=dict(color=PALETTE[i % len(PALETTE)], width=1.5)),
                    row=r, col=1)
            pts = anomaly_points(al_range, m, key)
            if not pts.empty:
                fig.add_trace(go.Scatter(
                    x=pts["ts"], y=pts["value"], mode="markers", name="Bất thường",
                    legendgroup="anomaly", showlegend=legend_anomaly, hovertext=pts["text"],
                    marker=dict(color="red", size=11, symbol="x")), row=r, col=1)
                legend_anomaly = False
        fig.update_layout(height=230 * len(METRICS), margin=dict(t=40, b=10))
        fig.update_yaxes(range=[0, 100])
        st.plotly_chart(fig, width="stretch")
 
    # ---- Dịch vụ HTTP ----
    st.subheader("Dịch vụ HTTP")
    if sv_latest.empty:
        st.info("Chưa có dữ liệu kiểm tra dịch vụ.")
    else:
        t = sv_latest.copy()
        t["Trạng thái"] = np.where(t["is_available"] == 1, "UP", "DOWN")
        t["Lần cuối"] = t["ts"].dt.strftime(TIME_FMT)
        t["error_message"] = t["error_message"].fillna("")
        st.dataframe(
            t[["service_name", "node_id", "Trạng thái", "status_code",
               "response_time_ms", "Lần cuối", "error_message"]]
            .rename(columns={"service_name": "Dịch vụ", "node_id": "Node",
                             "status_code": "Mã HTTP", "response_time_ms": "Độ trễ (ms)",
                             "error_message": "Lỗi"}),
            width="stretch", hide_index=True)
        hist = sv[(sv["ts"] >= cutoff)].dropna(subset=["response_time_ms"])
        if not hist.empty:
            hist = hist.assign(response_time_ms=hist["response_time_ms"].astype(float))
            f2 = px.line(hist, x="ts", y="response_time_ms", color="service_name",
                         labels={"ts": "", "response_time_ms": "Độ trễ (ms)",
                                 "service_name": "Dịch vụ"}, height=260)
            st.plotly_chart(f2, width="stretch")
 
    # ---- Cảnh báo ----
    st.subheader("Cảnh báo")
    a = al_all
    if severities:
        a = a[a["severity"].isin(severities)]
    if alert_status != "Tất cả":
        a = a[a["status"] == alert_status]
    if a.empty:
        st.success("Không có cảnh báo nào.")
    else:
        a = a.sort_values("ts", ascending=False).head(200).copy()
        a["Thời gian"] = a["ts"].dt.strftime(TIME_FMT)
        st.dataframe(
            a[["Thời gian", "node_id", "metric_name", "severity", "status", "message"]]
            .rename(columns={"node_id": "Node", "metric_name": "Chỉ số",
                             "severity": "Mức độ", "status": "Trạng thái",
                             "message": "Nội dung"}),
            width="stretch", hide_index=True)
 
    # ---- Xuất CSV ----
    c1, c2 = st.columns(2)
    if not m.empty:
        c1.download_button("Tải chỉ số (CSV)",
                           m.drop(columns="ts").to_csv(index=False).encode("utf-8-sig"),
                           "noc_metrics.csv", "text/csv", key="dl_metrics")
    if not a.empty:
        c2.download_button("Tải cảnh báo (CSV)",
                           a.drop(columns=["ts", "Thời gian"]).to_csv(index=False).encode("utf-8-sig"),
                           "noc_alerts.csv", "text/csv", key="dl_alerts")
 
 
render(minutes, selected, down_after, severities, alert_status)