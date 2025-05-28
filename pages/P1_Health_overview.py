import streamlit as st
from datetime import date, timedelta
from utils import garmin_utils, data_processing, plotting_utils # Assuming plotting_utils has the plot functions
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np # For np.nan if needed in processing

import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

st.set_page_config(layout="wide", page_title="Health Overview")
st.title("Health Overview") # Changed emoji to match your file name convention

# --- Your process_daily_summary_for_plotting function ---
# Ensure this is defined here or correctly imported from data_processing.py
# (Using the one from the previous response as a base)
def process_daily_summary_for_plotting(df_raw):
    if df_raw.empty:
        return pd.DataFrame()
    df = df_raw.copy()

    df['calendarDate'] = pd.to_datetime(df['calendarDate']).dt.date
    
    time_cols_seconds = [
        'highlyActiveSeconds', 'activeSeconds', 'sedentarySeconds', 'sleepingSeconds',
        'stressDuration', 'restStressDuration', 'activityStressDuration',
        'lowStressDuration', 'mediumStressDuration', 'highStressDuration'
    ]
    for col_s in time_cols_seconds:
        if col_s in df.columns:
            df[col_s.replace('Seconds', 'Minutes')] = pd.to_numeric(df[col_s], errors='coerce').fillna(0) / 60
            if col_s == 'sleepingSeconds':
                 df[col_s.replace('Seconds', 'Hours')] = pd.to_numeric(df[col_s], errors='coerce').fillna(0) / 3600
    
    if 'totalDistanceMeters' in df.columns:
        df['totalDistanceKm'] = pd.to_numeric(df['totalDistanceMeters'], errors='coerce').fillna(0) / 1000

    numeric_cols_to_coerce = [
        'restingHeartRate', 'averageStressLevel', 'totalSteps', 'bodyBatteryMostRecentValue',
        'activeKilocalories', 'totalDistanceKm', 'moderateIntensityMinutes',
        'vigorousIntensityMinutes', 'intensityMinutesGoal', 'floorsAscended', 'dailyStepGoal',
        'bodyBatteryHighestValue', 'bodyBatteryLowestValue', 'bodyBatteryAtWakeTime',
        'minHeartRate', 'maxHeartRate', 'lastSevenDaysAvgRestingHeartRate' # Added more
    ]
    for col_num in numeric_cols_to_coerce:
        if col_num in df.columns:
            df[col_num] = pd.to_numeric(df[col_num], errors='coerce')
    
    # Sort by date after processing
    df = df.sort_values(by='calendarDate').reset_index(drop=True)
    return df
# ------------------------------------------------------------

if not st.session_state.get('logged_in', False):
    st.warning("Please log in first using the sidebar on the main page.")
    st.stop()

client = st.session_state.garmin_client
username = st.session_state.current_user
start_date_session = st.session_state.get('date_range_start', date.today() - timedelta(days=30))
end_date_session = st.session_state.get('date_range_end', date.today())
force_refresh_session = st.session_state.get('force_refresh', False)

# Cache the data loading and processing for this page
@st.cache_data(ttl=300) # Cache for 5 minutes
def load_and_process_health_data(_client, _username, _start_date, _end_date, _force_refresh):
    logger.info(f"HEALTH PAGE: Fetching/processing data for {_username} from {_start_date} to {_end_date}, force_refresh={_force_refresh}")
    # HRV Data
    hrv_raw = garmin_utils.get_hrv_data(_client, _username, _start_date, _end_date, _force_refresh)
    hrv_processed = data_processing.process_hrv_df(hrv_raw) # Assumes process_hrv_df is in data_processing
    
    # Sleep Data
    sleep_raw = garmin_utils.get_sleep_data(_client, _username, _start_date, _end_date, _force_refresh)
    sleep_processed = data_processing.process_sleep_df(sleep_raw) # Assumes process_sleep_df is in data_processing

    # Daily Summaries (for RHR, Stress etc.)
    daily_raw = garmin_utils.get_daily_summaries(_client, _username, _start_date, _end_date, _force_refresh)
    daily_processed = process_daily_summary_for_plotting(daily_raw) # Use the function defined/imported above
    
    return hrv_processed, sleep_processed, daily_processed

if client and username:
    st.markdown(f"Displaying data for **{username}** from **{start_date_session.strftime('%Y-%m-%d')}** to **{end_date_session.strftime('%Y-%m-%d')}**.")

    with st.spinner("Loading health data... This might take a moment."):
        hrv_df, sleep_df, daily_df = load_and_process_health_data(
            client, username, start_date_session, end_date_session, force_refresh_session
        )

    # --- 1. Daily Wellness Snapshot ---
    if not daily_df.empty:
        latest_day_data = daily_df.iloc[-1]
        st.subheader(f"Daily Snapshot: {latest_day_data['calendarDate'].strftime('%Y-%m-%d')}")
        cols_snapshot = st.columns(5)
        with cols_snapshot[0]:
            st.metric("Resting HR", f"{latest_day_data.get('restingHeartRate', 'N/A')} bpm")
        with cols_snapshot[1]:
            st.metric("Avg Stress", f"{latest_day_data.get('averageStressLevel', 'N/A')}")
        with cols_snapshot[2]:
            st.metric("Total Steps", f"{int(latest_day_data.get('totalSteps', 0)):,}")
        with cols_snapshot[3]:
            st.metric("Sleep", f"{latest_day_data.get('sleepingHours', 0):.1f} hrs")
        with cols_snapshot[4]:
            st.metric("Body Battery (Last)", f"{latest_day_data.get('bodyBatteryMostRecentValue', 'N/A')}")
        st.markdown("---")
    else:
        st.info("No daily summary data available for snapshot.")

    # --- 2. Resting Heart Rate (RHR) Deep Dive (with Stress Overlay) ---
    st.subheader("Resting Heart Rate & Average Stress")
    if not daily_df.empty and 'restingHeartRate' in daily_df.columns:
        # This plot logic can be moved to plotting_utils.py if preferred
        fig_rhr_stress = plotting_utils.plot_rhr_and_stress(daily_df) # New function in plotting_utils
        st.plotly_chart(fig_rhr_stress, use_container_width=True)
    else:
        st.info("Resting heart rate or average stress data not available.")
    st.markdown("---")

    # --- HRV Section (using your existing logic but with potentially empty hrv_df) ---
    st.subheader("Heart Rate Based Recovery (Resting HR)")
    st.info("""
    Direct HRV data (nightly average in ms, HRV status) is often difficult to retrieve reliably
    via the current unofficial Garmin API. We are using Resting Heart Rate (RHR) and its trends
    as a key indicator of cardiovascular recovery and stress response.
    """)
    # The plot_rhr_and_stress is already showing RHR, so this section mostly becomes informational,
    # or you could show a simpler RHR plot here if plot_rhr_and_stress is too busy for some.
    # For instance, just RHR and its 7-day average without the stress overlay again.
    if not daily_df.empty and 'restingHeartRate' in daily_df.columns:
        fig_rhr_simple = go.Figure()
        fig_rhr_simple.add_trace(go.Scatter(
            x=daily_df['calendarDate'], y=daily_df['restingHeartRate'],
            name='Resting HR (bpm)', mode='lines+markers'
        ))
        if 'lastSevenDaysAvgRestingHeartRate' in daily_df.columns:
            fig_rhr_simple.add_trace(go.Scatter(
                x=daily_df['calendarDate'], y=daily_df['lastSevenDaysAvgRestingHeartRate'],
                name='7-Day Avg RHR (bpm)', mode='lines', line=dict(dash='dot')
            ))
        fig_rhr_simple.update_layout(title="Resting Heart Rate Trend", hovermode="x unified")
        st.plotly_chart(fig_rhr_simple, use_container_width=True)
    else:
        st.info("Resting Heart Rate data not available.")
    st.markdown("---")

    # --- 3. Stress Level Analysis ---
    st.subheader("Daily Stress Breakdown")
    if not daily_df.empty:
        fig_stress_dist = plotting_utils.plot_stress_distribution(daily_df) # New function
        st.plotly_chart(fig_stress_dist, use_container_width=True)
    else:
        st.info("No stress duration data available.")
    st.markdown("---")
    
    # --- 4. Body Battery Exploration (Plotting `bodyBatteryAtWakeTime`) ---
    st.subheader("Morning Body Battery (At Wake Time)")
    if not daily_df.empty and 'bodyBatteryAtWakeTime' in daily_df.columns:
        fig_bb_wake = plotting_utils.plot_body_battery_at_wake(daily_df) # New function
        st.plotly_chart(fig_bb_wake, use_container_width=True)
    else:
        st.info("No Body Battery at Wake Time data found.")
    st.markdown("---")

    # --- 5. Activity Level Breakdown (Weekly Average) ---
    st.subheader("Weekly Activity Level Distribution (Average Minutes per Day)")
    if not daily_df.empty:
        fig_activity_weekly = plotting_utils.plot_weekly_activity_distribution(daily_df) # New function
        st.plotly_chart(fig_activity_weekly, use_container_width=True)
    else:
        st.info("No activity level duration data available.")
    st.markdown("---")

    # --- 6. Intensity Minutes vs. Goal (Weekly) ---
    st.subheader("Weekly Intensity Minutes vs. Goal")
    if not daily_df.empty and 'moderateIntensityMinutes' in daily_df.columns and \
       'vigorousIntensityMinutes' in daily_df.columns and 'intensityMinutesGoal' in daily_df.columns:
        fig_intensity = plotting_utils.plot_weekly_intensity_minutes(daily_df) # New function
        st.plotly_chart(fig_intensity, use_container_width=True)
    else:
        st.info("Intensity minutes or goal data not available.")
    st.markdown("---")
    
    # --- Sleep Analysis Section (using your existing logic but with potentially empty sleep_df) ---
    st.subheader("Sleep Duration Analysis (from Daily Summary)")
    if not daily_df.empty and 'sleepingHours' in daily_df.columns:
        sleep_duration_data = daily_df[['calendarDate', 'sleepingHours']].dropna()
        if not sleep_duration_data.empty:
            fig_sleep_duration_daily = px.line(
                sleep_duration_data,
                x='calendarDate', y='sleepingHours',
                title="Total Sleep Duration per Night (from Daily Summary)",
                markers=True, labels={'sleepingHours': 'Sleep (Hours)'}
            )
            st.plotly_chart(fig_sleep_duration_daily, use_container_width=True)

            # Optional: Add a bar chart for consistency (less useful than line for duration trend)
            # fig_sleep_bar = px.bar(sleep_duration_data, x='calendarDate', y='sleepingHours', title="Total Sleep Duration")
            # st.plotly_chart(fig_sleep_bar, use_container_width=True)
        else:
            st.info("No sleep duration data found in daily summaries.")
    else:
        st.info("`sleepingHours` column not found in processed daily summary data.")
    st.markdown("---")
    
    # --- MODIFIED Sleep vs. "HRV Proxy" (RHR) Correlation ---
    # This plot should ideally move to the 4_Correlations.py page as a curated plot.
    # If you keep it here, it would be:
    st.subheader("Sleep Duration vs. Next Day's Resting HR")
    if not daily_df.empty and 'sleepingHours' in daily_df.columns and 'restingHeartRate' in daily_df.columns:
        corr_df_sleep_rhr = daily_df.copy()
        # Ensure calendarDate is present for hover data
        if 'calendarDate' not in corr_df_sleep_rhr.columns and 'date' in corr_df_sleep_rhr.columns: # common alternative name
            corr_df_sleep_rhr['calendarDate'] = corr_df_sleep_rhr['date']

        corr_df_sleep_rhr['next_day_RHR'] = corr_df_sleep_rhr['restingHeartRate'].shift(-1)
        
        plot_data_sleep_rhr = corr_df_sleep_rhr[['calendarDate', 'sleepingHours', 'next_day_RHR']].dropna() # Include calendarDate

        if not plot_data_sleep_rhr.empty and len(plot_data_sleep_rhr) >= 2:
            # Use a unique figure variable name here
            fig_sleep_vs_next_rhr = px.scatter( # << RENAMED VARIABLE
                plot_data_sleep_rhr,
                x='sleepingHours',
                y='next_day_RHR',
                title="Sleep Duration vs. Next Day's Resting HR",
                trendline="ols",
                labels={
                    'sleepingHours': "Sleep Duration (Hours)",
                    'next_day_RHR': "Next Day's Resting HR (bpm)"
                },
                hover_data=['calendarDate'] # <<< ADDED HOVER DATA
            )
            st.plotly_chart(fig_sleep_vs_next_rhr, use_container_width=True) # << USE CORRECTED VARIABLE
            
            corr_coef = plot_data_sleep_rhr['sleepingHours'].corr(plot_data_sleep_rhr['next_day_RHR'])
            st.write(f"Pearson Correlation Coefficient: **{corr_coef:.2f}** (Based on {len(plot_data_sleep_rhr)} nights)")
        else:
            st.info("Not enough data to plot Sleep Duration vs. Next Day's RHR.")
    else:
        st.info("Required columns for Sleep vs. RHR correlation not found.")
    st.markdown("---")

else:
    st.info("Dashboard content will appear here once you are logged in and data is fetched.")