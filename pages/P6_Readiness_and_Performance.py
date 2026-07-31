# pages/P6_Readiness_and_Performance.py — Readiness vs realized training performance
import sys
import os
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from utils import garmin_utils, data_processing, analysis_stats

st.set_page_config(layout="wide", page_title="Readiness & Performance")
st.title("Morning Readiness vs Realized Performance")
st.caption("Readiness is a transparent z-scored composite of recovery signals — not a Garmin metric.")


def _process_daily(df_raw):
    if df_raw.empty:
        return pd.DataFrame()
    df = df_raw.copy()
    df["calendarDate"] = pd.to_datetime(df["calendarDate"]).dt.date
    if "sleepingSeconds" in df.columns:
        df["sleepingHours"] = pd.to_numeric(df["sleepingSeconds"], errors="coerce") / 3600
    for col in ["restingHeartRate", "averageStressLevel", "bodyBatteryAtWakeTime"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("calendarDate").reset_index(drop=True)


@st.cache_data(ttl=300)
def load_unified(_client, _username, _start, _end, _force):
    daily = _process_daily(garmin_utils.get_daily_summaries(_client, _username, _start, _end, _force))
    hrv = data_processing.process_hrv_df(garmin_utils.get_hrv_data(_client, _username, _start, _end, _force))
    sleep = data_processing.process_sleep_df(garmin_utils.get_sleep_data(_client, _username, _start, _end, _force))
    acts = data_processing.process_general_activities_df(garmin_utils.get_activities(_client, _username, _start, _end, _force))
    acts_daily = analysis_stats.aggregate_activities_daily(acts)
    return analysis_stats.build_unified_daily_frame(daily, hrv, sleep, acts_daily)


if not st.session_state.get("logged_in", False):
    st.warning("Please log in first using the sidebar on the main page.")
    st.stop()

client = st.session_state.garmin_client
username = st.session_state.current_user
start = st.session_state.get("date_range_start", date.today() - timedelta(days=60))
end = st.session_state.get("date_range_end", date.today())
force = st.session_state.get("force_refresh", False)
window = st.sidebar.number_input("Readiness baseline window (days)", 7, 90, 28)

with st.spinner("Loading data & computing readiness..."):
    udf = load_unified(client, username, start, end, force)

if udf.empty:
    st.info("No daily data available for the selected range.")
    st.stop()

scored = analysis_stats.readiness_score(udf, baseline_window=int(window))
comp_cols = [c for c in scored.columns if c.startswith("z_")]

if scored["readiness"].notna().sum() == 0:
    st.info("Not enough history to compute a readiness baseline. Widen the date range.")
    st.stop()

used = [c.replace("z_", "") for c in comp_cols]
st.markdown(f"**Readiness components used:** {', '.join(used) if used else 'none'}")

st.subheader("Readiness over time")
line = px.line(scored, x="date", y="readiness", markers=True,
               labels={"readiness": "Readiness (z, 0 = personal baseline)"})
line.add_hline(y=0, line_dash="dot", line_color="grey")
st.plotly_chart(line, use_container_width=True)
with st.expander("Show individual readiness components"):
    if comp_cols:
        comp_long = scored.melt(id_vars="date", value_vars=comp_cols,
                                var_name="component", value_name="z")
        st.plotly_chart(px.line(comp_long, x="date", y="z", color="component"), use_container_width=True)
    else:
        st.info("No individual components available in this range.")

perf_options = [c for c in ["aerobic_efficiency", "mean_pace_min_per_km", "total_aerobic_te"]
                if c in scored.columns and scored[c].notna().sum() >= 2]
if not perf_options:
    st.info("No training-performance metric available in this range (no activities with the needed fields).")
    st.stop()

perf = st.selectbox("Performance metric", perf_options)
st.subheader(f"Readiness vs {perf} (same day)")
if perf == "mean_pace_min_per_km":
    st.caption(
        "Lower pace = faster. A negative correlation here means higher readiness "
        "is associated with faster runs (an improvement)."
    )
pair = scored[["date", "readiness", perf]].dropna()
if len(pair) >= 2:
    fig = px.scatter(pair, x="readiness", y=perf, trendline="ols", hover_data=["date"])
    st.plotly_chart(fig, use_container_width=True)
    stat = analysis_stats.corr_with_significance(pair["readiness"], pair[perf])
    if stat["too_few"]:
        st.warning(f"Too few paired days (n={stat['n']}).")
    elif stat["p"] >= analysis_stats.DEFAULT_ALPHA:
        st.info(f"r = {stat['r']:.2f} (n={stat['n']}, p = {stat['p']:.3f}) — not significant.")
    else:
        ci = "" if pd.isna(stat["ci_low"]) else f", 95% CI [{stat['ci_low']:.2f}, {stat['ci_high']:.2f}]"
        st.success(f"r = {stat['r']:.2f} (n={stat['n']}, p = {stat['p']:.3f}{ci}).")

    st.subheader("Readiness & performance over time")
    dual = make_subplots(specs=[[{"secondary_y": True}]])
    dual.add_trace(go.Scatter(x=scored["date"], y=scored["readiness"], name="Readiness"), secondary_y=False)
    dual.add_trace(go.Scatter(x=pair["date"], y=pair[perf], name=perf, mode="markers+lines"), secondary_y=True)
    dual.update_yaxes(title_text="Readiness (z)", secondary_y=False)
    dual.update_yaxes(title_text=perf, secondary_y=True, showgrid=False)
    st.plotly_chart(dual, use_container_width=True)
else:
    st.info("Fewer than 2 paired readiness/performance days — scatter and time series not shown.")
