# pages/2_Running_Performance.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta

# Assuming utils are in a folder named 'utils' in the parent directory of 'pages'
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils import garmin_utils, data_processing, plotting_utils # plotting_utils might need new functions

from utils.data_processing import *

st.set_page_config(layout="wide", page_title="Running Performance")
st.title("🏃 Running Performance Analysis")

# --- process_activities_df (ensure it extracts 'activityType_key' and handles HR zones) ---
# This should be in data_processing.py. For completeness here:
def local_process_activities_df(activities_df_raw):
    if activities_df_raw.empty:
        return pd.DataFrame()
    
    df = activities_df_raw.copy()
    # Extract activityType_key
    if 'activityType' in df.columns:
        df['activityType_key'] = df['activityType'].apply(
            lambda x: x.get('typeKey') if isinstance(x, dict) else x if isinstance(x, str) else None
        )
    # Date and Time processing
    df['startTimeGMT_dt'] = pd.to_datetime(df['startTimeGMT'], errors='coerce') # Keep original GMT if needed
    df['date'] = pd.to_datetime(df['startTimeLocal'], errors='coerce').dt.date # Use startTimeLocal for 'date'

    # Duration
    df['duration_seconds'] = pd.to_numeric(df['duration'], errors='coerce')
    df['duration_minutes'] = df['duration_seconds'] / 60

    # Distance
    df['distance_meters'] = pd.to_numeric(df['distance'], errors='coerce')
    df['distance_km'] = df['distance_meters'] / 1000

    # Pace (min/km)
    mask_pace = (df['distance_km'] > 0) & (df['duration_minutes'] > 0)
    df['pace_min_per_km'] = np.nan
    df.loc[mask_pace, 'pace_min_per_km'] = df.loc[mask_pace, 'duration_minutes'] / df.loc[mask_pace, 'distance_km']

    # HR
    df['avgHR'] = pd.to_numeric(df['averageHR'], errors='coerce')
    df['maxHR'] = pd.to_numeric(df['maxHR'], errors='coerce')

    # Cadence (ensure columns exist, often specific to running)
    if 'averageRunningCadenceInStepsPerMinute' in df.columns:
        df['avgCadence'] = pd.to_numeric(df['averageRunningCadenceInStepsPerMinute'], errors='coerce') * 2 # Steps per leg to total steps
    if 'maxRunningCadenceInStepsPerMinute' in df.columns:
        df['maxCadence'] = pd.to_numeric(df['maxRunningCadenceInStepsPerMinute'], errors='coerce') * 2

    # VO2Max
    if 'vO2MaxValue' in df.columns:
        df['vo2MaxValue_activity'] = pd.to_numeric(df['vO2MaxValue'], errors='coerce')
    
    # TE
    df['aerobicTE'] = pd.to_numeric(df['aerobicTrainingEffect'], errors='coerce')
    df['anaerobicTE'] = pd.to_numeric(df['anaerobicTrainingEffect'], errors='coerce')

    # HR Zones (example, adjust based on your actual hrTimeInZone_X column names)
    for i in range(1, 6):
        col_name = f'hrTimeInZone_{i}' # Check exact column name from your activities_df sample
        # Sometimes it's hrTimeInZone[X] or timeInHeartRateZoneDTOs. Use your sample to confirm.
        # For now, assuming direct column names like your sample for daily_summaries,
        # but activity data often has them as hrTimeInZone_X.
        # Your sample data shows hrTimeInZone_1, hrTimeInZone_2 etc. as direct columns
        if col_name in df.columns:
            df[f'time_in_zone{i}_seconds'] = pd.to_numeric(df[col_name], errors='coerce').fillna(0)
            df[f'time_in_zone{i}_minutes'] = df[f'time_in_zone{i}_seconds'] / 60
        else: # If not found, create empty to avoid errors later
            df[f'time_in_zone{i}_seconds'] = 0.0
            df[f'time_in_zone{i}_minutes'] = 0.0
            
    df = df.sort_values(by='date').reset_index(drop=True)
    return df
# ------------------------------------------------------------------------------

@st.cache_data(ttl=300)
def load_activity_data(_client, _username, _start_date, _end_date, _force_refresh):
    activities_raw = garmin_utils.get_activities(_client, _username, _start_date, _end_date, _force_refresh)
    activities_processed = local_process_activities_df(activities_raw) # Use the local or imported processing function
    return activities_processed

if not st.session_state.get('logged_in', False):
    st.warning("Please log in first using the sidebar on the main page.")
    st.stop()

client = st.session_state.garmin_client
username = st.session_state.current_user
start_date_session = st.session_state.get('date_range_start', date.today() - timedelta(days=30))
end_date_session = st.session_state.get('date_range_end', date.today())
force_refresh_session = st.session_state.get('force_refresh', False)

all_activities_df = pd.DataFrame()
if client and username:
    with st.spinner("Loading activity data..."):
        all_activities_df = load_activity_data(
            client, username, start_date_session, end_date_session, force_refresh_session
        )

if not all_activities_df.empty and 'activityType_key' in all_activities_df.columns:
    # --- Filter for Running Activities ---
    running_df = all_activities_df[all_activities_df['activityType_key'] == 'running'].copy()

    if not running_df.empty:
        st.header("Running Activity Trends")
        
        # --- Key Running Metrics Over Time ---
        metrics_to_plot = {
            'pace_min_per_km': "Average Pace (min/km)",
            'avgHR': "Average Heart Rate (bpm)",
            'distance_km': "Distance (km)",
            'vo2MaxValue_activity': "VO2 Max (from Activity)",
            'avgCadence': "Average Cadence (spm)"
        }
        
        # Allow user to select metrics for the trend plot
        selected_metrics = st.multiselect(
            "Select metrics to plot over time:",
            options=list(metrics_to_plot.keys()),
            default=[k for k,v in metrics_to_plot.items() if k in ['pace_min_per_km', 'avgHR', 'distance_km']] # Sensible defaults
        )

        if selected_metrics:
            fig_trends = go.Figure()
            for i, metric_col in enumerate(selected_metrics):
                if metric_col in running_df.columns and not running_df[metric_col].isnull().all():
                    use_secondary_y = i > 0 and metric_col != 'distance_km' # Example: put HR/Cadence/VO2 on secondary if Pace/Dist is primary
                    
                    fig_trends.add_trace(go.Scatter(
                        x=running_df['date'],
                        y=running_df[metric_col],
                        name=metrics_to_plot.get(metric_col, metric_col),
                        mode='lines+markers',
                        yaxis=f'y{i+1 if use_secondary_y and i<2 else 1}' # Limit to 2 y-axes for clarity
                    ))
            
            fig_trends.update_layout(
                title="Selected Running Metrics Over Time",
                xaxis_title="Date",
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            # Configure Y-axes (basic example, can be made more dynamic)
            fig_trends.update_layout(yaxis_title=metrics_to_plot.get(selected_metrics[0],selected_metrics[0]))
            if len(selected_metrics) > 1 and any(m != 'distance_km' for m in selected_metrics[1:]):
                 fig_trends.update_layout(yaxis2=dict(title="Secondary Metric", overlaying='y', side='right', showgrid=False))
            
            if 'pace_min_per_km' in selected_metrics: # Invert pace axis if selected
                fig_trends.update_yaxes(autorange="reversed", selector=dict(title_text=metrics_to_plot['pace_min_per_km']))

            st.plotly_chart(fig_trends, use_container_width=True)
        st.markdown("---")

        # --- Aggregated Time in HR Zones (NEW)---
        st.subheader("Time in HR Zones Distribution Over Time (Running)")
        hr_zone_agg_period = st.radio(
            "Select HR Zone Aggregation Period:",
            ("Weekly", "Monthly"),
            horizontal=True,
            key="hr_zone_agg_period"
        )
        hr_zone_resample_rule = 'W-MON' if hr_zone_agg_period == "Weekly" else 'ME'

        if not running_df.empty and 'date' in running_df.columns:
            running_df_for_hr_zones = running_df.copy()
            running_df_for_hr_zones['date'] = pd.to_datetime(running_df_for_hr_zones['date'])
            
            zone_cols_minutes = [f'time_in_zone{i}_minutes' for i in range(1, 6)]
            # Ensure all expected zone columns exist, fill with 0 if not (already done in processing)
            
            # Resample and sum time in zones per period
            # Need to set 'date' as index for resampling
            time_in_zones_over_time = running_df_for_hr_zones.set_index('date')[zone_cols_minutes].resample(
                hr_zone_resample_rule, label='left', closed='left'
            ).sum().reset_index()

            # Melt the DataFrame for Plotly Express stacked bar chart
            # Only include zones that have some data to avoid clutter
            cols_to_melt_zones = [col for col in zone_cols_minutes if time_in_zones_over_time[col].sum() > 0]

            if not time_in_zones_over_time.empty and cols_to_melt_zones:
                time_in_zones_melted = time_in_zones_over_time.melt(
                    id_vars='date',
                    value_vars=cols_to_melt_zones,
                    var_name='HR_Zone',
                    value_name='MinutesInZone'
                )
                # Clean up zone names for legend
                time_in_zones_melted['HR_Zone'] = time_in_zones_melted['HR_Zone'].str.replace(
                    'time_in_zone', 'Zone '
                ).str.replace('_minutes', '')

                fig_hr_zones_trend = px.bar(
                    time_in_zones_melted,
                    x='date',
                    y='MinutesInZone',
                    color='HR_Zone',
                    title=f"{hr_zone_agg_period} Distribution of Time in Heart Rate Zones",
                    labels={'date': f'{hr_zone_agg_period} Starting', 'MinutesInZone': 'Total Minutes in Zone'},
                    # Optional: Define a color map for zones
                    # color_discrete_map={
                    #     'Zone 1': 'lightgrey', 'Zone 2': 'lightblue', 
                    #     'Zone 3': 'lightgreen', 'Zone 4': 'orange', 'Zone 5': 'red'
                    # }
                )
                fig_hr_zones_trend.update_layout(xaxis_title=f"{hr_zone_agg_period} Start Date", yaxis_title="Total Minutes")
                st.plotly_chart(fig_hr_zones_trend, use_container_width=True)

                # Optional: Normalized (100% stacked bar) view
                time_in_zones_over_time['TotalMinutes'] = time_in_zones_over_time[cols_to_melt_zones].sum(axis=1)
                for col in cols_to_melt_zones:
                    time_in_zones_over_time[f'{col}_percent'] = (time_in_zones_over_time[col] / time_in_zones_over_time['TotalMinutes']) * 100
                
                percent_cols_to_melt = [f'{col}_percent' for col in cols_to_melt_zones]
                time_in_zones_percent_melted = time_in_zones_over_time.melt(
                    id_vars='date',
                    value_vars=percent_cols_to_melt,
                    var_name='HR_Zone_Percent',
                    value_name='PercentMinutesInZone'
                )
                time_in_zones_percent_melted['HR_Zone_Percent'] = time_in_zones_percent_melted['HR_Zone_Percent'].str.replace(
                    'time_in_zone', 'Zone '
                ).str.replace('_minutes_percent', '')

                fig_hr_zones_percent_trend = px.bar(
                    time_in_zones_percent_melted,
                    x='date',
                    y='PercentMinutesInZone',
                    color='HR_Zone_Percent',
                    title=f"{hr_zone_agg_period} Proportional Time in Heart Rate Zones (%)",
                    labels={'date': f'{hr_zone_agg_period} Starting', 'PercentMinutesInZone': 'Percentage of Time in Zone (%)'},
                )
                fig_hr_zones_percent_trend.update_layout(xaxis_title=f"{hr_zone_agg_period} Start Date", yaxis_title="Percentage of Time (%)")
                with st.expander("View Proportional Time in HR Zones (%)"):
                    st.plotly_chart(fig_hr_zones_percent_trend, use_container_width=True)

            else:
                st.info("Not enough HR Zone data to display a trend over time.")
        st.markdown("---")

        # ----- SECTION  "Pace per Zone Trend" ------
        st.subheader("Pace Improvement Trends by Dominant Heart Rate Zone")
        st.caption("Tracks average pace for runs where your average HR fell predominantly within a specific zone.")

        # --- User Input for HR Zones (Crucial for accuracy!) ---
        st.sidebar.subheader("Your HR Zone Definitions (BPM)")
        # These are examples, you should get these from user or their Garmin settings if possible
        # For now, let user input them for their profile.
        z1_max = st.sidebar.number_input("Zone 1 Max BPM", value=120, min_value=80, max_value=220)
        z2_min = st.sidebar.number_input("Zone 2 Min BPM", value=z1_max + 1, min_value=80, max_value=220)
        z2_max = st.sidebar.number_input("Zone 2 Max BPM", value=145, min_value=z2_min, max_value=220) # Example
        z3_min = st.sidebar.number_input("Zone 3 Min BPM", value=z2_max + 1, min_value=80, max_value=220)
        z3_max = st.sidebar.number_input("Zone 3 Max BPM", value=160, min_value=z3_min, max_value=220) # Example
        z4_min = st.sidebar.number_input("Zone 4 Min BPM", value=z3_max + 1, min_value=80, max_value=220)
        z4_max = st.sidebar.number_input("Zone 4 Max BPM", value=175, min_value=z4_min, max_value=220) # Example
        z5_min = st.sidebar.number_input("Zone 5 Min BPM", value=z4_max + 1, min_value=80, max_value=220)
        # Zone 5 Max is usually user's Max HR

        user_hr_zone_definitions = {
            "Zone 1": (0, z1_max), # Less relevant for pace trends typically
            "Zone 2 (Easy)": (z2_min, z2_max),
            "Zone 3 (Moderate/Tempo)": (z3_min, z3_max),
            "Zone 4 (Threshold/Hard)": (z4_min, z4_max),
            "Zone 5 (Max Effort)": (z5_min, 220) # Max effort runs are often not steady pace
        }
        # Update your existing identify_easy_runs to use these user-defined Zone 2 bounds for consistency
        # easy_runs_df = identify_easy_runs_by_avg_hr(running_df, user_hr_zone_definitions["Zone 2 (Easy)"][0], user_hr_zone_definitions["Zone 2 (Easy)"][1])
        # The Aerobic Efficiency plot should then use this easy_runs_df.

        if not running_df.empty:
            pace_per_zone_data = calculate_pace_per_zone_trend(running_df, user_hr_zone_definitions)

            if not pace_per_zone_data.empty:
                fig_pace_zone_trend = px.line(
                    pace_per_zone_data,
                    x='date',
                    y='pace_min_per_km',
                    color='primary_zone_by_avg_hr', # One line per zone
                    title="Average Pace Trend by Dominant HR Zone (Weekly Avg)",
                    labels={'date': "Week", 'pace_min_per_km': "Average Pace (min/km)", 
                            'primary_zone_by_avg_hr': "Dominant HR Zone"},
                    markers=True
                )
                fig_pace_zone_trend.update_yaxes(autorange="reversed") # Faster pace is lower
                fig_pace_zone_trend.update_layout(hovermode="x unified")
                st.plotly_chart(fig_pace_zone_trend, use_container_width=True)
            else:
                st.info("Not enough data to plot pace trends by HR zone. Ensure runs have HR data and HR zones are defined.")
        else:
            st.info("No running data available to calculate pace per zone trends.")
        st.markdown("---")



        # --- 2. Aerobic Efficiency (Pace for Easy Runs) ---
        st.subheader("Aerobic Efficiency (Easy Runs - Zone 2)")
        st.caption("This tracks your pace during easy (Zone 2) runs at a given heart rate. Improvement means faster pace at the same HR, or same pace at a lower HR.")

        # Identify Easy Runs (Zone 2) - This requires HR zone data per activity
        # We need to ensure 'time_in_zone2_minutes' and 'duration_minutes' are correctly processed
        # And a reasonable definition for a "Zone 2 run"

        # For identify_zone2_runs, we need max_hr or rely on time in zones.
        # Let's assume we primarily rely on a significant portion of time in Zone 2.
        # This logic should ideally be in data_processing.py
        def identify_easy_runs(df, z2_min_percentage=0.60):
            if 'time_in_zone2_minutes' not in df.columns or 'duration_minutes' not in df.columns:
                return pd.DataFrame() # Not enough info
            # Ensure duration is not zero to avoid division by zero
            df_filtered = df[df['duration_minutes'] > 0].copy()
            df_filtered['z2_percentage'] = (df_filtered['time_in_zone2_minutes'] / df_filtered['duration_minutes'])
            easy_runs = df_filtered[df_filtered['z2_percentage'] >= z2_min_percentage]
            return easy_runs

        easy_runs_df = identify_easy_runs(running_df)

        if not easy_runs_df.empty and 'pace_min_per_km' in easy_runs_df.columns and 'avgHR' in easy_runs_df.columns:
            fig_aerobic_eff = go.Figure()
            fig_aerobic_eff.add_trace(go.Scatter(
                x=easy_runs_df['date'],
                y=easy_runs_df['pace_min_per_km'],
                name='Easy Run Pace (min/km)',
                mode='lines+markers',
                yaxis='y1'
            ))
            fig_aerobic_eff.add_trace(go.Scatter(
                x=easy_runs_df['date'],
                y=easy_runs_df['avgHR'],
                name='Easy Run Avg HR (bpm)',
                mode='lines+markers',
                yaxis='y2'
            ))
            fig_aerobic_eff.update_layout(
                title="Easy Run Pace and Average HR Over Time",
                xaxis_title="Date",
                yaxis=dict(title="Pace (min/km)", autorange="reversed"),
                yaxis2=dict(title="Average HR (bpm)", overlaying='y', side='right', showgrid=False),
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_aerobic_eff, use_container_width=True)

            # Aerobic Decoupling (Pa:HR ratio) - Advanced concept
            # If you have access to average power for runs (e.g. Stryd) this is more accurate.
            # Otherwise, can be approximated if you have consistent HR and Pace for first/second half of easy long runs.
            # For now, we'll skip the direct plot of decoupling but note its importance.
            st.info("Consider tracking Aerobic Decoupling (Pace:HR or Power:HR ratio drift) on long easy runs for a deeper endurance insight.")
        else:
            st.info("Not enough easy (Zone 2) runs identified or missing pace/HR data for Aerobic Efficiency plot. Ensure activities have HR zone data.")
        st.markdown("---")


        # --- 3. Long Run Progression ---
        st.subheader("Long Run Progression")
        # Define what constitutes a "long run" - e.g., top 20% longest runs, or runs > X km
        # For simplicity, let's consider the longest run each week.
        if not running_df.empty and 'date' in running_df.columns and 'distance_km' in running_df.columns:
            running_df_for_long = running_df.copy()
            running_df_for_long['date'] = pd.to_datetime(running_df_for_long['date'])
            
            # Get the longest run per week
            # Ensure 'date' is the index for resampling
            longest_run_weekly = running_df_for_long.set_index('date').resample('W-MON', label='left', closed='left')['distance_km'].max().reset_index()
            longest_run_weekly = longest_run_weekly.dropna(subset=['distance_km']) # Remove weeks with no runs

            if not longest_run_weekly.empty:
                fig_long_run = px.bar(
                    longest_run_weekly,
                    x='date',
                    y='distance_km',
                    title="Longest Run Distance per Week",
                    labels={'date': "Week Starting", 'distance_km': "Distance (km)"}
                )
                st.plotly_chart(fig_long_run, use_container_width=True)
            else:
                st.info("Not enough data to plot weekly long run progression.")
        else:
            st.info("Distance or date data missing for long run progression.")
        st.markdown("---")


        # --- 4. VO2 Max (from Activities) Trend ---
        st.subheader("VO2 Max Trend (from Running Activities)")
        if not running_df.empty and 'vo2MaxValue_activity' in running_df.columns:
            vo2_data = running_df[['date', 'vo2MaxValue_activity']].dropna()
            if not vo2_data.empty:
                fig_vo2_activity = px.line(
                    vo2_data.sort_values(by='date'), 
                    x='date', y='vo2MaxValue_activity', 
                    title="VO2 Max Recorded During Running Activities", 
                    markers=True,
                    labels={'vo2MaxValue_activity': 'VO2 Max'}
                )
                st.plotly_chart(fig_vo2_activity, use_container_width=True)
            else:
                st.info("No VO2 Max data found in running activities for the selected period.")
        else:
            st.info("'vo2MaxValue_activity' column not found. Check data processing.")
        st.markdown("---")

        # --- Pace vs. HR Scatter Plot ---
        st.subheader("Pace vs. Average Heart Rate (All Runs)")
        scatter_data_pace_hr = running_df[['date', 'activityName', 'pace_min_per_km', 'avgHR', 'distance_km', 'aerobicTE']].dropna(subset=['pace_min_per_km', 'avgHR'])
        if not scatter_data_pace_hr.empty and len(scatter_data_pace_hr) >=2 :
            fig_pace_hr_scatter = px.scatter(
                scatter_data_pace_hr,
                x='pace_min_per_km',
                y='avgHR',
                color='distance_km',  # Color by distance
                size='aerobicTE',     # Size by Aerobic Training Effect (can be small if TE is low)
                hover_name='activityName',
                hover_data=['date', 'distance_km', 'aerobicTE'],
                title="Pace vs. Avg HR (Color: Distance, Size: Aerobic TE)"
            )
            fig_pace_hr_scatter.update_xaxes(autorange="reversed") # Faster pace (lower number) to the left
            st.plotly_chart(fig_pace_hr_scatter, use_container_width=True)
        else:
            st.info("Not enough data for Pace vs. HR scatter plot.")
        st.markdown("---")

        # --- Table of Recent/Filtered Runs ---
        st.subheader("Details of Running Activities")
        cols_to_show_in_table = [
            'date', 'activityName', 'distance_km', 'duration_minutes', 'pace_min_per_km', 
            'avgHR', 'maxHR', 'aerobicTE', 'vo2MaxValue_activity', 'avgCadence'
        ]
        # Filter out columns that might not exist or are all NaN
        existing_cols_for_table = [col for col in cols_to_show_in_table if col in running_df.columns and not running_df[col].isnull().all()]
        

        display_df = running_df[existing_cols_for_table].copy() # Work on a copy
        if 'pace_min_per_km' in display_df.columns:
            display_df['Pace (min/s)'] = display_df['pace_min_per_km'].apply(format_time_minutes_seconds)
        if 'duration_minutes' in display_df.columns:
            display_df['Duration (min/s)'] = display_df['duration_minutes'].apply(format_time_minutes_seconds)

        # Select columns for final display, including formatted ones, excluding original decimal ones if desired
        cols_for_final_table = ['date', 'activityName', 'distance_km', 'Duration (min/s)', 'Pace (min/s)', 
                                'avgHR', 'maxHR', 'aerobicTE', 'vo2MaxValue_activity', 'avgCadence']
        # Filter for only existing columns in display_df before trying to use them
        final_table_cols_exist = [col for col in cols_for_final_table if col in display_df.columns]

        st.dataframe(
            running_df[existing_cols_for_table].sort_values(by='date', ascending=False),
            use_container_width=True,
            # Optional: Column configuration for formatting
            column_config={
                 "distance_km": st.column_config.NumberColumn(format="%.2f km"),
                 "pace_min_per_km": st.column_config.NumberColumn(format="%.2f min/km"),
             }
        )

    else:
        st.info("No running activities found in the selected period.")
elif not all_activities_df.empty and 'activityType_key' not in all_activities_df.columns:
    st.error("Activity data was loaded, but 'activityType_key' could not be determined. Check `process_activities_df` function.")
else:
    st.info("No activity data loaded. Please check login and date range.")