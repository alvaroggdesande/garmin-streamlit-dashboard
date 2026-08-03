import sys
import os
from datetime import date, timedelta

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils import garmin_utils, data_processing, efficiency_stats as eff

st.set_page_config(layout="wide", page_title="Am I Improving?")
st.title("📈 Am I Improving?")
st.caption("Are you doing more with less heart rate? Efficiency Factor = metres travelled per heartbeat — higher is fitter.")

if not st.session_state.get("logged_in", False):
    st.warning("Please log in first using the sidebar on the main page.")
    st.stop()

client = st.session_state.garmin_client
username = st.session_state.current_user

# --- Own lookback control (independent of the global 30-day filter) ---
st.sidebar.header("Trend window")
preset = st.sidebar.radio("Lookback", ["3 months", "6 months", "1 year", "All (2 years)"],
                          index=1, key="improving_lookback")
months = {"3 months": 3, "6 months": 6, "1 year": 12, "All (2 years)": 24}[preset]
end_date = date.today()
start_date = end_date - timedelta(days=int(months * 30.4))
ref_hr = st.sidebar.number_input("Reference HR for pace comparison (bpm)",
                                 min_value=100, max_value=200,
                                 value=eff.REF_HR_DEFAULT, key="improving_ref_hr")
force_refresh = st.session_state.get("force_refresh", False)


@st.cache_data(ttl=300)
def _load_runs(_client, _username, _start, _end, _force):
    raw = garmin_utils.get_activities(_client, _username, _start, _end, _force)
    processed = data_processing.process_running_activities_df(raw)
    if processed.empty or "activityType_key" not in processed.columns:
        return pd.DataFrame()
    runs = processed[processed["activityType_key"] == "running"].copy()
    return runs


with st.spinner("Loading your running history..."):
    runs = _load_runs(client, username, start_date, end_date, force_refresh)

if runs.empty:
    st.info("No running activities found in this window. Try a longer lookback.")
    st.stop()

runs = eff.add_efficiency_columns(runs)
runs["date"] = pd.to_datetime(runs["date"])
easy = runs[runs["is_easy"]].copy()

# --- Verdict banner ---
verdict = eff.improvement_verdict(easy, as_of=end_date)
arrow = {"up": "⬆️", "flat": "➡️", "down": "⬇️"}[verdict["direction"]]
if verdict["muted"]:
    st.info(f"Not enough easy (Zone 2) runs yet to judge a trend "
            f"(recent: {verdict['n_recent']}, prior: {verdict['n_prior']}; "
            f"need {eff.MIN_WINDOW_N} in each 6-week window).")
else:
    pct = verdict["pct_change"]
    conf = "likely real" if verdict["confident"] else "within noise — not conclusive"
    verb = {"up": "up", "flat": "unchanged", "down": "down"}[verdict["direction"]]
    msg = (f"{arrow} Over the last 6 weeks your easy-run efficiency is **{verb} "
           f"{abs(pct):.1f}%** vs the prior 6 weeks "
           f"(n = {verdict['n_recent']} recent / {verdict['n_prior']} prior — {conf}).")
    (st.success if verdict["direction"] == "up" and verdict["confident"]
     else st.warning if verdict["direction"] == "down" and verdict["confident"]
     else st.info)(msg)

st.markdown("---")

# --- EF weekly trend (easy runs) ---
st.subheader("Efficiency Factor trend (easy runs, weekly median)")
trend = eff.weekly_ef_trend(easy)
if trend.empty:
    st.info("No easy-run efficiency data to plot yet.")
else:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=trend["week_start"], y=trend["ef_q75"], mode="lines",
        line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=trend["week_start"], y=trend["ef_q25"], mode="lines", fill="tonexty",
        line=dict(width=0), fillcolor="rgba(66,135,245,0.15)",
        name="IQR (25–75%)", hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=trend["week_start"], y=trend["ef_median"], mode="lines+markers",
        name="Median EF", line=dict(color="rgb(66,135,245)")))
    fig.update_layout(xaxis_title="Week", yaxis_title="Efficiency Factor (m/beat)",
                      hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Higher is better. The line rising over time means you're covering more ground per heartbeat.")

st.markdown("---")

# --- Pace at a fixed HR (frontier) ---
st.subheader(f"Pace vs Heart Rate — are you faster at {int(ref_hr)} bpm?")
frontier = runs.dropna(subset=["pace_min_per_km", "avgHR"]).copy()
if len(frontier) >= 2:
    frontier["days_ago"] = (pd.Timestamp(end_date) - frontier["date"]).dt.days
    fig2 = px.scatter(
        frontier, x="avgHR", y="pace_min_per_km", color="days_ago",
        color_continuous_scale="Blues_r", hover_data=["date", "distance_km"],
        labels={"avgHR": "Average HR (bpm)", "pace_min_per_km": "Pace (min/km)",
                "days_ago": "Days ago"},
        title="Each dot is a run — brighter = more recent")
    fig2.update_yaxes(autorange="reversed")  # faster pace lower

    # earlier-half vs recent-half fit lines
    midpoint = frontier["date"].median()
    recent_half = frontier[frontier["date"] >= midpoint]
    earlier_half = frontier[frontier["date"] < midpoint]
    p_recent = eff.pace_at_reference_hr(recent_half, ref_hr=ref_hr)
    p_earlier = eff.pace_at_reference_hr(earlier_half, ref_hr=ref_hr)
    hr_line = pd.Series(range(int(frontier["avgHR"].min()), int(frontier["avgHR"].max()) + 1))
    for res, name, dash in [(p_earlier, "Earlier fit", "dot"), (p_recent, "Recent fit", "solid")]:
        if res["ok"]:
            fig2.add_trace(go.Scatter(
                x=hr_line, y=res["intercept"] + res["slope"] * hr_line,
                mode="lines", name=name, line=dict(dash=dash)))
    st.plotly_chart(fig2, use_container_width=True)

    if p_recent["ok"] and p_earlier["ok"]:
        now = data_processing.format_time_minutes_seconds(p_recent["pace_at_ref"])
        then = data_processing.format_time_minutes_seconds(p_earlier["pace_at_ref"])
        st.success(f"At {int(ref_hr)} bpm you now run **{now}/km** — vs **{then}/km** earlier in this window.")
    else:
        st.info("Not enough spread in HR/pace to estimate pace-at-HR reliably yet.")
else:
    st.info("Not enough runs with pace and HR to draw the frontier.")

st.markdown("---")

# --- Hard-effort pace trend ---
st.subheader("Hard-effort speed (weekly best pace on harder runs)")
hard = runs.copy()
if "avgHR" in hard.columns and not easy.empty:
    hard = hard[~hard["is_easy"]].dropna(subset=["pace_min_per_km", "date"])
    if not hard.empty:
        hard_weekly = (hard.set_index("date")
                       .resample("W-MON", label="left", closed="left")["pace_min_per_km"]
                       .min().reset_index().dropna(subset=["pace_min_per_km"]))
        fig3 = px.line(hard_weekly, x="date", y="pace_min_per_km", markers=True,
                       labels={"date": "Week", "pace_min_per_km": "Best pace (min/km)"},
                       title="Fastest pace among harder runs, per week")
        fig3.update_yaxes(autorange="reversed")
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("No harder (non-easy) runs in this window yet.")
else:
    st.info("No harder-run data to show.")

st.markdown("---")

# --- VO2 max reference ---
with st.expander("VO2 max (Garmin's own estimate — for reference)"):
    if "vo2MaxValue_activity" in runs.columns and runs["vo2MaxValue_activity"].notna().any():
        vo2 = runs[["date", "vo2MaxValue_activity"]].dropna().sort_values("date")
        fig4 = px.line(vo2, x="date", y="vo2MaxValue_activity", markers=True,
                       labels={"vo2MaxValue_activity": "VO2 max"})
        st.plotly_chart(fig4, use_container_width=True)
    else:
        st.info("No VO2 max values recorded in this window.")
