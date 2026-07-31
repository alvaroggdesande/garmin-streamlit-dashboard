# pages/P4_Correlations.py — Lagged Correlation Explorer
import sys
import os
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from utils import garmin_utils, data_processing, analysis_stats

st.set_page_config(layout="wide", page_title="Lagged Correlations")
st.title("Lagged Correlation Explorer")
st.caption(
    "Exploratory, not confirmatory. Correlation is not causation, and scanning many "
    "metric/lag pairs inflates false positives — treat highlighted lags as hypotheses."
)


def _process_daily(df_raw):
    if df_raw.empty:
        return pd.DataFrame()
    df = df_raw.copy()
    df["calendarDate"] = pd.to_datetime(df["calendarDate"]).dt.date
    if "sleepingSeconds" in df.columns:
        df["sleepingHours"] = pd.to_numeric(df["sleepingSeconds"], errors="coerce") / 3600
    for col in ["restingHeartRate", "averageStressLevel", "totalSteps",
                "bodyBatteryAtWakeTime", "activeKilocalories",
                "moderateIntensityMinutes", "vigorousIntensityMinutes",
                "maxStressLevel", "lastSevenDaysAvgRestingHeartRate"]:
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
start = st.session_state.get("date_range_start", date.today() - timedelta(days=30))
end = st.session_state.get("date_range_end", date.today())
force = st.session_state.get("force_refresh", False)

with st.spinner("Loading & unifying daily data..."):
    udf = load_unified(client, username, start, end, force)

if udf.empty:
    st.info("No daily data available for the selected range.")
    st.stop()

numeric_cols = sorted(
    c for c in udf.columns
    if c != "date" and pd.api.types.is_numeric_dtype(udf[c])
    and udf[c].nunique(dropna=True) > 1
)
if len(numeric_cols) < 2:
    st.info("Not enough numeric metrics to correlate.")
    st.stop()

c1, c2, c3 = st.columns(3)
driver = c1.selectbox("Driver (X, day t)", numeric_cols,
                      index=numeric_cols.index("sleepingHours") if "sleepingHours" in numeric_cols else 0)
outcome = c2.selectbox("Outcome (Y, day t+lag)", numeric_cols,
                       index=numeric_cols.index("restingHeartRate") if "restingHeartRate" in numeric_cols else min(1, len(numeric_cols) - 1))
method = c3.radio("Method", ["pearson", "spearman"], horizontal=True)
max_lag = st.slider("Max lag (days)", 1, 14, 7)

lag_df = analysis_stats.lagged_correlation(udf, driver, outcome, lags=range(0, max_lag + 1), method=method)

st.subheader("Correlation vs lag")
bar = px.bar(lag_df, x="lag", y="r", color="significant",
             color_discrete_map={True: "#2c7fb8", False: "#cccccc"},
             labels={"r": f"{method.title()} r", "lag": "Lag (days)"},
             title=f"{driver} (t) vs {outcome} (t+lag)")
bar.add_hline(y=0, line_dash="dot", line_color="grey")
st.plotly_chart(bar, use_container_width=True)

sig = lag_df[lag_df["significant"]]
default_lag = int(sig.loc[sig["r"].abs().idxmax(), "lag"]) if not sig.empty else 0
sel_lag = st.selectbox("Inspect lag", list(lag_df["lag"]), index=list(lag_df["lag"]).index(default_lag))

row = lag_df[lag_df["lag"] == sel_lag].iloc[0]
scatter_df = pd.DataFrame({
    "date": udf["date"], driver: udf[driver], outcome: udf[outcome].shift(-sel_lag),
}).dropna(subset=[driver, outcome])

st.subheader(f"Scatter at lag {sel_lag}")
if len(scatter_df) >= 2:
    fig = px.scatter(scatter_df, x=driver, y=outcome, trendline="ols",
                     hover_data=["date"],
                     labels={outcome: f"{outcome} (t+{sel_lag})"})
    st.plotly_chart(fig, use_container_width=True)

if row["too_few"] if "too_few" in row else (row["n"] < analysis_stats.MIN_N):
    st.warning(f"Too few overlapping points (n={int(row['n'])}) — no reliable estimate.")
elif not row["significant"]:
    st.info(f"r = {row['r']:.2f} (n={int(row['n'])}, p = {row['p']:.3f}) — **not significant**, likely noise.")
else:
    ci = "" if pd.isna(row["ci_low"]) else f", 95% CI [{row['ci_low']:.2f}, {row['ci_high']:.2f}]"
    st.success(f"r = {row['r']:.2f} (n={int(row['n'])}, p = {row['p']:.3f}{ci}) — significant at α=0.05.")

st.markdown("---")
st.subheader("Correlation heatmap (lag 0, significant cells only)")
import numpy as np  # local import; keeps the section self-contained

heat_cols = st.multiselect("Metrics", numeric_cols,
                           default=numeric_cols[: min(6, len(numeric_cols))])
if len(heat_cols) >= 2:
    mat = pd.DataFrame(np.nan, index=heat_cols, columns=heat_cols)
    for i in heat_cols:
        for j in heat_cols:
            s = analysis_stats.corr_with_significance(udf[i], udf[j], method=method)
            # blank non-significant off-diagonal cells
            if i == j:
                mat.loc[i, j] = 1.0
            elif not s["too_few"] and pd.notna(s["p"]) and s["p"] < analysis_stats.DEFAULT_ALPHA:
                mat.loc[i, j] = s["r"]
    heat = px.imshow(mat, text_auto=".2f", zmin=-1, zmax=1,
                     color_continuous_scale="RdBu", aspect="auto")
    st.plotly_chart(heat, use_container_width=True)
    st.caption("Blank cells = not significant at α=0.05 or too few points.")
