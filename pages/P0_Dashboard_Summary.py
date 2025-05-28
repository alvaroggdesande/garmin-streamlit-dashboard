# pages/0_Dashboard_Summary.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta
import numpy as np # For np.nan

# --- Python Path Setup for utils ---
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# --- End Path Setup ---

from utils import garmin_utils
from utils import data_processing # Import your consolidated data_processing module
# from utils.formatting_utils import format_time_seconds_to_ms # Assuming this is now in a util

st.set_page_config(layout="wide", page_title="Performance Summary")
st.title("Performance Summary Dashboard")

# --- Helper for formatting time (move to formatting_utils.py ideally) ---
def format_time_seconds_to_ms(total_seconds):
    if pd.isna(total_seconds) or not isinstance(total_seconds, (int, float)): return "N/A"
    if total_seconds < 0: return "N/A"
    minutes = int(total_seconds // 60)
    seconds = int(round(total_seconds % 60))
    if minutes == 0 and seconds == 0: return "0s"
    output = ""
    if minutes > 0: output += f"{minutes}m "
    output += f"{seconds}s"
    return output.strip()
# ------------------------------------------------------------------

if not st.session_state.get('logged_in', False):
    st.warning("Please log in first using the sidebar on the main page.")
    st.stop()

client = st.session_state.garmin_client
username = st.session_state.current_user
start_date_session = st.session_state.get('date_range_start', date.today() - timedelta(days=30))
end_date_session = st.session_state.get('date_range_end', date.today() + timedelta(days=1))
force_refresh_session = st.session_state.get('force_refresh', False)

# Cached data loading function for this page
@st.cache_data(ttl=300) # Cache for 5 minutes
def load_summary_page_data(_client, _username, _start_date, _end_date, _force_refresh):
    activities_raw = garmin_utils.get_activities(_client, _username, _start_date, _end_date, _force_refresh)
    # Use the centralized processing function from data_processing.py
    all_activities_p = data_processing.process_general_activities_df(activities_raw)
    
    daily_raw = garmin_utils.get_daily_summaries(_client, _username, _start_date, _end_date, _force_refresh)
    # Use the centralized processing function from data_processing.py
    daily_p = data_processing.process_daily_summary_for_plotting(daily_raw)
    return all_activities_p, daily_p

all_activities_df = pd.DataFrame()
daily_df = pd.DataFrame()

if client and username:
    with st.spinner("Loading summary data..."):
        all_activities_df, daily_df = load_summary_page_data(
            client, username, start_date_session, end_date_session, force_refresh_session
        )

# Filter for running activities
running_df = pd.DataFrame()
if not all_activities_df.empty and 'activityType_key' in all_activities_df.columns:
    running_df = all_activities_df[all_activities_df['activityType_key'] == 'running'].copy()
else:
    if not all_activities_df.empty:
        st.warning("Could not filter running activities: 'activityType_key' column missing. Check processing.")


# --- Scorecards ---
if not running_df.empty:
    st.header(f"Running Summary ({start_date_session.strftime('%b %d, %Y')} - {end_date_session.strftime('%b %d, %Y')})")

    total_runs = len(running_df)
    total_km_run = running_df['distance_km'].sum()
    total_duration_minutes_val = running_df['duration_minutes'].sum() # get the value
    avg_pace_overall_min_per_km_val = (total_duration_minutes_val / total_km_run) if total_km_run > 0 else 0
    avg_hr_overall_val = running_df['avgHR'].mean()
    # total_calories_running = running_df['calories'].sum() # Ensure 'calories' is processed

    formatted_total_duration = format_time_seconds_to_ms(total_duration_minutes_val * 60)
    formatted_avg_pace = format_time_seconds_to_ms(avg_pace_overall_min_per_km_val * 60) if avg_pace_overall_min_per_km_val > 0 else "N/A"

    cols_scorecard = st.columns(5)
    with cols_scorecard[0]: st.metric("Total Runs", f"{total_runs}")
    with cols_scorecard[1]: st.metric("Total Distance", f"{total_km_run:.2f} km")
    with cols_scorecard[2]: st.metric("Total Time Running", formatted_total_duration)
    with cols_scorecard[3]: st.metric("Avg. Pace", formatted_avg_pace)
    with cols_scorecard[4]: st.metric("Avg. HR", f"{avg_hr_overall_val:.0f} bpm" if pd.notna(avg_hr_overall_val) else "N/A")
    st.markdown("---")

    # --- Weekly/Monthly Aggregations (Running) ---
    st.subheader("Aggregations Over Time (Running)")
    running_df_dated = running_df.copy()
    if 'date' in running_df_dated.columns:
        running_df_dated['date'] = pd.to_datetime(running_df_dated['date'])
        running_df_dated = running_df_dated.set_index('date')

        agg_period_running = st.radio("Running Aggregation Period:", ("Weekly", "Monthly"), horizontal=True, key="summary_agg_period_running")
        resample_rule_running = 'W-MON' if agg_period_running == "Weekly" else 'ME'

        aggregated_running_data = running_df_dated.resample(resample_rule_running, label='left', closed='left').agg(
            total_distance_km=('distance_km', 'sum'),
            total_duration_minutes=('duration_minutes', 'sum'),
            number_of_runs=('activityId', 'count'),
            avg_hr=('avgHR', 'mean'),
            # Add other metrics if processed, e.g., avg_cadence, avg_vo2max
        ).reset_index()
        aggregated_running_data['avg_pace_min_per_km'] = aggregated_running_data.apply(
            lambda row: (row['total_duration_minutes'] / row['total_distance_km']) if row['total_distance_km'] > 0 else np.nan, axis=1
        )

        if not aggregated_running_data.empty:
            # Plot Total Distance per period
            fig_dist_agg = px.bar(aggregated_running_data, x='date', y='total_distance_km', title=f"{agg_period_running} Total Running Distance")
            st.plotly_chart(fig_dist_agg, use_container_width=True)
            # Plot Number of Runs and Avg Pace (dual axis)
            fig_runs_pace_agg = go.Figure() # ... (same plotting logic as before) ...
            # ... (Code for fig_runs_pace_agg from previous response) ...
            # Create the dual-axis plot for runs and pace
            fig_runs_pace_agg = go.Figure()
            fig_runs_pace_agg.add_trace(go.Bar(
                x=aggregated_running_data['date'], y=aggregated_running_data['number_of_runs'],
                name='Number of Runs', yaxis='y1'
            ))
            fig_runs_pace_agg.add_trace(go.Scatter(
                x=aggregated_running_data['date'], y=aggregated_running_data['avg_pace_min_per_km'],
                name='Average Pace (min/km)', mode='lines+markers', yaxis='y2'
            ))
            fig_runs_pace_agg.update_layout(
                title=f"{agg_period_running} Number of Runs & Average Pace",
                xaxis_title="Period Start",
                yaxis=dict(title="Number of Runs"),
                yaxis2=dict(title="Average Pace (min/km)", overlaying='y', side='right', autorange="reversed", showgrid=False),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                hovermode="x unified"
            )
            st.plotly_chart(fig_runs_pace_agg, use_container_width=True)

            # Table
            st.write(f"{agg_period_running} Aggregated Running Data Table:")
            # ... (same table display logic as before) ...
            display_agg_df = aggregated_running_data.copy()
            if 'avg_pace_min_per_km' in display_agg_df.columns:
                display_agg_df['Avg Pace (Formatted)'] = display_agg_df['avg_pace_min_per_km'].apply(lambda x: format_time_seconds_to_ms(x*60) if pd.notna(x) else "N/A")
            st.dataframe(display_agg_df, use_container_width=True)
        else:
            st.info(f"No running data to aggregate {agg_period_running.lower()}.")
    else:
        st.info("Date column not found in running data for aggregation.") # Add check
else:
    st.info("No running activities found in the selected period to summarize.")


# --- Daily Wellness Summary Aggregations ---
if not daily_df.empty:
    st.markdown("---")
    st.header(f"Daily Wellness Summary ({start_date_session.strftime('%b %d, %Y')} - {end_date_session.strftime('%b %d, %Y')})")
    daily_df_dated_wellness = daily_df.copy()
    if 'calendarDate' in daily_df_dated_wellness.columns:
        daily_df_dated_wellness['calendarDate'] = pd.to_datetime(daily_df_dated_wellness['calendarDate'])
        daily_df_dated_wellness = daily_df_dated_wellness.set_index('calendarDate')

        wellness_agg_period = st.radio("Wellness Aggregation Period:", ("Weekly", "Monthly"), horizontal=True, key="wellness_agg_period")
        wellness_resample_rule = 'W-MON' if wellness_agg_period == "Weekly" else 'ME'
        
        wellness_aggregated = daily_df_dated_wellness.resample(wellness_resample_rule, label='left', closed='left').agg(
            avg_RHR=('restingHeartRate', 'mean'),
            avg_Stress=('averageStressLevel', lambda x: x[x != -1].mean() if not x[x != -1].empty else np.nan),
            avg_Sleep=('sleepingHours', 'mean'), # Assuming 'sleepingHours' is processed
            total_Steps=('totalSteps', 'sum')
        ).reset_index()

        if not wellness_aggregated.empty:
            st.subheader(f"{wellness_agg_period} Wellness Trends")

            # Plot Avg RHR and Stress (already in your code, ensure it uses wellness_aggregated)
            fig_wellness_rhr_stress = go.Figure()
            if 'avg_RHR' in wellness_aggregated.columns:
                fig_wellness_rhr_stress.add_trace(go.Scatter(x=wellness_aggregated['calendarDate'], y=wellness_aggregated['avg_RHR'], name="Avg RHR (bpm)", yaxis='y1', mode='lines+markers'))
            if 'avg_Stress' in wellness_aggregated.columns:
                fig_wellness_rhr_stress.add_trace(go.Scatter(x=wellness_aggregated['calendarDate'], y=wellness_aggregated['avg_Stress'], name="Avg Stress Level", yaxis='y2', mode='lines+markers'))
            
            if 'avg_RHR' in wellness_aggregated.columns or 'avg_Stress' in wellness_aggregated.columns: # only plot if at least one exists
                fig_wellness_rhr_stress.update_layout(
                    title=f"{wellness_agg_period} Average RHR & Stress",
                    xaxis_title="Period Start",
                    yaxis=dict(title="Avg RHR (bpm)"),
                    yaxis2=dict(title="Avg Stress Level", overlaying='y', side='right', showgrid=False),
                    hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig_wellness_rhr_stress, use_container_width=True)

            # Plot Average Sleep Duration per period
            if 'avg_Sleep' in wellness_aggregated.columns and not wellness_aggregated['avg_Sleep'].isnull().all():
                fig_wellness_sleep = px.line(
                    wellness_aggregated.dropna(subset=['avg_Sleep']),
                    x='calendarDate', y='avg_Sleep',
                    title=f"{wellness_agg_period} Average Sleep Duration",
                    markers=True, labels={'avg_Sleep': 'Average Sleep (Hours)'}
                )
                st.plotly_chart(fig_wellness_sleep, use_container_width=True)

            # Plot Total Steps per period
            if 'total_Steps' in wellness_aggregated.columns and not wellness_aggregated['total_Steps'].isnull().all():
                fig_wellness_steps = px.bar(
                    wellness_aggregated.dropna(subset=['total_Steps']),
                    x='calendarDate', y='total_Steps',
                    title=f"{wellness_agg_period} Total Steps",
                    labels={'total_Steps': 'Total Steps'}
                )
                st.plotly_chart(fig_wellness_steps, use_container_width=True)
        else:
            st.info(f"No wellness data to aggregate {wellness_agg_period.lower()}.")