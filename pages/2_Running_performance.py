import streamlit as st
from datetime import date, timedelta
from utils import garmin_utils, data_processing, plotting_utils
import pandas as pd

st.set_page_config(layout="wide", page_title="Running Performance")
st.title("🏃 Running Performance Analysis")

if not st.session_state.get('logged_in', False):
    st.warning("Please log in first using the sidebar on the main page.")
    st.stop()

client = st.session_state.garmin_client
username = st.session_state.current_user
start_date = st.session_state.get('date_range_start', date.today() - timedelta(days=30))
end_date = st.session_state.get('date_range_end', date.today())
force_refresh = st.session_state.get('force_refresh', False)

# You might want a user setting for Max HR if not reliably in Garmin data
# For now, we'll pass None to identify_zone2_runs
user_max_hr = st.session_state.get('user_max_hr', None) 
# To set this, you could add an input in the sidebar of app.py:
# st.session_state.user_max_hr = st.sidebar.number_input("Your Max HR (optional for Zone 2 calc)", value=185, min_value=100, max_value=250)


if client and username:
    st.markdown(f"Displaying data for **{username}** from **{start_date.strftime('%Y-%m-%d')}** to **{end_date.strftime('%Y-%m-%d')}**.")

    with st.spinner("Loading activity data..."):
        activities_raw_df = garmin_utils.get_activities(client, username, start_date, end_date, force_refresh)
        activities_processed_df = data_processing.process_activities_df(activities_raw_df)
    
    if not activities_processed_df.empty:
        running_activities_df = activities_processed_df[
            activities_processed_df['activityType'].str.contains('running', case=False, na=False)
        ].copy()

        if not running_activities_df.empty:
            st.subheader("Aerobic Efficiency (Pace vs. HR for Easy Runs)")
            # Identify Zone 2 runs - pass user_max_hr if available from session_state
            zone2_runs_df = data_processing.identify_zone2_runs(running_activities_df, max_hr_estimate=user_max_hr)
            if not zone2_runs_df.empty:
                aerobic_efficiency_plot_df = data_processing.calculate_aerobic_efficiency(zone2_runs_df)
                fig_ae = plotting_utils.plot_pace_vs_hr(aerobic_efficiency_plot_df)
                st.plotly_chart(fig_ae, use_container_width=True)
            else:
                st.info("No Zone 2 (easy) runs identified in the selected period to calculate aerobic efficiency. Ensure Max HR is set or HR zones are recorded in activities.")

            st.subheader("Heart Rate Zone Distribution (Running)")
            # Calculate weekly or monthly distribution
            zone_dist_weekly_df = data_processing.calculate_hr_zone_distribution(running_activities_df, period='W')
            if not zone_dist_weekly_df.empty:
                fig_zd_w = plotting_utils.plot_hr_zone_distribution(zone_dist_weekly_df, period_name="Weekly")
                st.plotly_chart(fig_zd_w, use_container_width=True)
            else:
                st.info("Could not calculate HR Zone distribution for running activities. Check if activities have HR zone data.")

            # Add more running-specific plots:
            # - VO2 Max trend from activities (if 'vo2_max_activity' is populated)
            # - Pace trends for specific run types (e.g., tempo runs if you can identify them)
            # - Cadence, Stride Length trends
            
            if 'vo2_max_activity' in running_activities_df.columns:
                vo2_data = running_activities_df[['date', 'vo2_max_activity']].dropna()
                if not vo2_data.empty:
                    fig_vo2 = px.line(vo2_data.sort_values(by='date'), x='date', y='vo2_max_activity', 
                                      title="VO2 Max (from Running Activities)", markers=True)
                    st.plotly_chart(fig_vo2, use_container_width=True)


            st.subheader("Recent Running Activities")
            st.dataframe(running_activities_df[[
                'date', 'activityName', 'distance_km', 'duration_minutes', 
                'pace_min_per_km', 'avgHR', 'aerobicTrainingEffect', 'vo2_max_activity'
            ]].sort_values(by='date', ascending=False).head(10))

        else:
            st.info("No running activities found in the selected period.")
    else:
        st.info("No activity data found for the selected period.")
else:
    st.info("Dashboard content will appear here once you are logged in and data is fetched.")