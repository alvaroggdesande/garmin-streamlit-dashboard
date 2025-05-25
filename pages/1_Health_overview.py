import streamlit as st
from datetime import date, timedelta
from utils import garmin_utils, data_processing, plotting_utils
import pandas as pd
import plotly.express as px

import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

st.set_page_config(layout="wide", page_title="Health Overview") # Ensure this is set in each page if not using a central app.py for config
st.title("Health Overview")

if not st.session_state.get('logged_in', False):
    st.warning("Please log in first using the sidebar on the main page.")
    st.stop()

client = st.session_state.garmin_client
username = st.session_state.current_user
start_date = st.session_state.get('date_range_start', date.today() - timedelta(days=30))
end_date = st.session_state.get('date_range_end', date.today())
force_refresh = st.session_state.get('force_refresh', False)

if client and username:
    st.markdown(f"Displaying data for **{username}** from **{start_date.strftime('%Y-%m-%d')}** to **{end_date.strftime('%Y-%m-%d')}**.")

    # --- Fetch and Process Data ---
    with st.spinner("Loading health data... This might take a moment."):
        # HRV Data
        hrv_raw_df = garmin_utils.get_hrv_data(client, username, start_date, end_date, force_refresh)
        hrv_processed_df = data_processing.process_hrv_df(hrv_raw_df)
        
        # Sleep Data
        sleep_raw_df = garmin_utils.get_sleep_data(client, username, start_date, end_date, force_refresh)
        sleep_processed_df = data_processing.process_sleep_df(sleep_raw_df)

        # Daily Summaries (for RHR, Stress etc.)
        daily_raw_df = garmin_utils.get_daily_summaries(client, username, start_date, end_date, force_refresh)
        # Daily summaries often have 'date' as string, convert it if not already
        if not daily_raw_df.empty and 'date' in daily_raw_df.columns:
            daily_raw_df['date'] = pd.to_datetime(daily_raw_df['date']).dt.date
        
        # Body Battery
        # bb_raw_df = garmin_utils.get_body_battery(client, username, start_date, end_date, force_refresh)
        # bb_processed_df = ... (you'll need a process_body_battery_df function)


    # --- Display Metrics and Plots ---
    st.subheader("Heart Rate Variability (HRV) & Related")
    if not hrv_processed_df.empty:
        # Prepare daily_summary_df for plotting_utils.plot_hrv_trend
        # It expects columns like 'restingHeartRate_daily' and 'date'
        daily_summary_for_plot = pd.DataFrame()
        if not daily_raw_df.empty:
            daily_summary_for_plot = daily_raw_df[['date', 'restingHeartRate']].copy()
            daily_summary_for_plot.rename(columns={'restingHeartRate': 'restingHeartRate_daily'}, inplace=True)

        # Prepare sleep_df for plotting_utils.plot_hrv_trend
        # It expects 'date_sleep' and 'duration_minutes_sleep'
        sleep_for_plot = pd.DataFrame()
        if not sleep_processed_df.empty:
            sleep_for_plot = sleep_processed_df[['date', 'duration_minutes']].copy()
            sleep_for_plot.rename(columns={'date': 'date_sleep', 'duration_minutes': 'duration_minutes_sleep'}, inplace=True)

        fig_hrv = plotting_utils.plot_hrv_trend(hrv_processed_df, daily_summary_for_plot, sleep_for_plot)
        st.plotly_chart(fig_hrv, use_container_width=True)
    else:
        st.info("No HRV data found for the selected period.")

    st.subheader("Sleep Analysis")
    if not sleep_processed_df.empty:
        # You might want a dedicated sleep plot (e.g., duration, stages)
        st.write("Sleep Data (Processed):")
        st.dataframe(sleep_processed_df[['date', 'sleep_score', 'duration_minutes', 'deep_minutes', 'light_minutes', 'rem_minutes', 'awake_minutes']].head())
        
        # Example: Plot sleep score over time
        if 'sleep_score' in sleep_processed_df.columns:
            fig_sleep_score = px.line(sleep_processed_df.dropna(subset=['sleep_score']), 
                                      x='date', y='sleep_score', title="Sleep Score Over Time", markers=True)
            st.plotly_chart(fig_sleep_score, use_container_width=True)

    else:
        st.info("No sleep data found for the selected period.")

    st.subheader("Sleep vs. HRV Correlation")
    # Merging needs to be done carefully if dates don't align perfectly or one dataset is sparser
    if not sleep_processed_df.empty and not hrv_processed_df.empty:
        merged_health_df = data_processing.merge_sleep_hrv_activity_data(
            sleep_processed_df, hrv_processed_df, daily_summaries_df=daily_raw_df
        )
        # Ensure column names match what plot_sleep_hrv_correlation expects
        # (e.g., 'duration_minutes_sleep', 'hrv_nightly_avg_hrv')
        # You might need to rename columns in merged_health_df before passing
        
        # Example: Rename for the plot function
        plot_corr_df = merged_health_df.copy()
        if 'duration_minutes_sleep' in plot_corr_df.columns and 'hrv_nightly_avg_hrv' in plot_corr_df.columns:
             fig_corr = plotting_utils.plot_sleep_hrv_correlation(
                 plot_corr_df, 
                 sleep_metric_col='duration_minutes_sleep', 
                 hrv_metric_col='hrv_nightly_avg_hrv'
             )
             st.plotly_chart(fig_corr, use_container_width=True)
        else:
            st.info("Required columns for sleep-HRV correlation not found in merged data. Check processing steps.")
            st.write("Columns in merged_health_df:", merged_health_df.columns.tolist())


    # Add more health metrics: Resting HR trend, Stress levels (from daily_summaries_df)
    if not daily_raw_df.empty:
        st.subheader("Daily Health Stats")
        if 'restingHeartRate' in daily_raw_df.columns:
            fig_rhr = px.line(daily_raw_df.dropna(subset=['restingHeartRate']), 
                              x='date', y='restingHeartRate', title="Resting Heart Rate Trend", markers=True)
            st.plotly_chart(fig_rhr, use_container_width=True)
        if 'averageStressLevel' in daily_raw_df.columns:
            stress_data = daily_raw_df[daily_raw_df['averageStressLevel'] != -1].dropna(subset=['averageStressLevel']) # -1 often means no data
            if not stress_data.empty:
                fig_stress = px.line(stress_data, x='date', y='averageStressLevel', title="Average Daily Stress Level", markers=True)
                st.plotly_chart(fig_stress, use_container_width=True)
else:
    st.info("Dashboard content will appear here once you are logged in and data is fetched.")