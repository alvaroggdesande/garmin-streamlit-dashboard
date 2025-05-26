# pages/4_Correlations.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta
import numpy as np

# Assuming utils are in a folder named 'utils' in the parent directory of 'pages'
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils import garmin_utils # data_processing is used via the local function here

st.set_page_config(layout="wide", page_title="Metric Correlations")
st.title("Explore Metric Correlations")

# --- Define process_daily_summary_for_plotting (same as before) ---
def process_daily_summary_for_plotting(df_raw):
    if df_raw.empty:
        return pd.DataFrame()
    df = df_raw.copy()
    df['calendarDate'] = pd.to_datetime(df['calendarDate']).dt.date
    time_cols_seconds = [
        'highlyActiveSeconds', 'activeSeconds', 'sedentarySeconds', 'sleepingSeconds',
        'stressDuration', 'restStressDuration', 'activityStressDuration',
        'uncategorizedStressDuration', 'totalStressDuration',
        'lowStressMinutes', 'mediumStressMinutes', 'highStressMinutes', # Already minutes in your sample
        'measurableAwakeDuration', 'measurableAsleepDuration'
    ]
    for col_s in time_cols_seconds:
        if col_s in df.columns:
            if col_s.endswith('Seconds'): # Only process if it's actually seconds
                 df[col_s.replace('Seconds', 'Minutes')] = pd.to_numeric(df[col_s], errors='coerce').fillna(0) / 60
                 if col_s == 'sleepingSeconds':
                     df[col_s.replace('Seconds', 'Hours')] = pd.to_numeric(df[col_s], errors='coerce').fillna(0) / 3600
            # If already minutes (like low/medium/highStressMinutes), ensure numeric
            elif col_s.endswith('Minutes'):
                 df[col_s] = pd.to_numeric(df[col_s], errors='coerce').fillna(0)

    if 'totalDistanceMeters' in df.columns:
        df['totalDistanceKm'] = pd.to_numeric(df['totalDistanceMeters'], errors='coerce').fillna(0) / 1000
    numeric_cols_to_coerce = [
        'totalKilocalories', 'activeKilocalories', 'bmrKilocalories', 'totalSteps',
        'wellnessDistanceMeters', 'moderateIntensityMinutes', 'vigorousIntensityMinutes',
        'floorsAscended', 'floorsDescended', 'minHeartRate', 'maxHeartRate',
        'restingHeartRate', 'lastSevenDaysAvgRestingHeartRate', 'averageStressLevel',
        'maxStressLevel', 'bodyBatteryChargedValue', 'bodyBatteryDrainedValue',
        'bodyBatteryHighestValue', 'bodyBatteryLowestValue', 'bodyBatteryMostRecentValue',
        'bodyBatteryDuringSleep', 'bodyBatteryAtWakeTime', 'avgWakingRespirationValue',
        'highestRespirationValue', 'lowestRespirationValue',
        'intensityMinutesGoal', 'userFloorsAscendedGoal', 'dailyStepGoal'
    ]
    for col_num in numeric_cols_to_coerce:
        if col_num in df.columns:
            df[col_num] = pd.to_numeric(df[col_num], errors='coerce')
    df = df.sort_values(by='calendarDate').reset_index(drop=True)
    return df
# ------------------------------------------------------------

@st.cache_data(ttl=300)
def load_correlation_page_data(_client, _username, _start_date, _end_date, _force_refresh):
    # st.markdown(f"CORR PAGE: Fetching/processing data for {_username} from {_start_date} to {_end_date}, force_refresh={_force_refresh}") # Less verbose
    raw_daily = garmin_utils.get_daily_summaries(_client, _username, _start_date, _end_date, _force_refresh)
    processed_daily = process_daily_summary_for_plotting(raw_daily)
    return processed_daily

if not st.session_state.get('logged_in', False):
    st.warning("Please log in first using the sidebar on the main page.")
    st.stop()

client = st.session_state.garmin_client
username = st.session_state.current_user
start_date_session = st.session_state.get('date_range_start', date.today() - timedelta(days=30))
end_date_session = st.session_state.get('date_range_end', date.today())
force_refresh_session = st.session_state.get('force_refresh', False)

daily_df = pd.DataFrame()
if client and username:
    with st.spinner("Loading daily summary data for correlations..."):
        daily_df = load_correlation_page_data(
            client, username, start_date_session, end_date_session, force_refresh_session
        )
else:
    st.info("Login via the main page to load data.")

# --- Function to generate a single correlation plot ---
def create_correlation_plot(df, x_col, y_col, title, x_label=None, y_label=None, y_col_is_next_day=False):
    if df.empty or x_col not in df.columns:
        st.info(f"Missing data for X-axis: {x_col}")
        return
    
    # Ensure 'calendarDate' exists for hover info.
    # If your 'date' column is named something else, adjust here or ensure it's renamed to 'calendarDate' earlier.
    date_col_name = 'calendarDate'
    if date_col_name not in df.columns:
        if 'date' in df.columns: # common alternative
            date_col_name = 'date'
        else:
            st.warning(f"Date column ('calendarDate' or 'date') not found in DataFrame for hover data in '{title}'.")
            # Proceed without date in hover if not found, or you could return.
            # For now, we'll let it proceed but hover might be less informative.

    plot_df = df.copy()
    y_data_col = y_col

    if y_col_is_next_day:
        if y_col not in df.columns:
            st.info(f"Missing data for Y-axis (base for next day): {y_col}")
            return
        plot_df[y_col + '_next_day'] = plot_df[y_col].shift(-1)
        y_data_col = y_col + '_next_day'
        y_label_final = y_label or f"{y_col.replace('_', ' ').title()} (Next Day)"
    else:
        if y_col not in df.columns:
            st.info(f"Missing data for Y-axis: {y_col}")
            return
        y_label_final = y_label or y_col.replace('_', ' ').title()

    x_label_final = x_label or x_col.replace('_', ' ').title()

    # Columns needed for the plot, including the date for hover
    cols_for_plot = [x_col, y_data_col]
    if date_col_name in plot_df.columns: # Only add if found
        cols_for_plot.append(date_col_name)
    
    correlation_data = plot_df[cols_for_plot].dropna(subset=[x_col, y_data_col]) # Ensure we only drop based on x and y

    if not correlation_data.empty and len(correlation_data) >= 2:
        hover_data_config = {}
        if date_col_name in correlation_data.columns:
            # Format the date in hover to be more readable if it's a date object
            # If it's already string, this won't apply. If it's datetime, it's fine.
            # hover_data_config[date_col_name] = True # Default format
            hover_data_config[date_col_name] = ':%Y-%m-%d' # Example date format

        fig = px.scatter(
            correlation_data, x=x_col, y=y_data_col,
            title=title, trendline="ols",
            labels={x_col: x_label_final, y_data_col: y_label_final},
            hover_name=date_col_name if date_col_name in correlation_data.columns else None, # Puts date in bold at top of hover
            hover_data=hover_data_config if hover_data_config else None # More detailed hover control
            # Or simpler: hover_data=[date_col_name] if date_col_name in correlation_data.columns else None
        )
        st.plotly_chart(fig, use_container_width=True)
        corr_coef = correlation_data[x_col].corr(correlation_data[y_data_col])
        st.write(f"Pearson Correlation: **{corr_coef:.2f}** (Points: {len(correlation_data)})")
    else:
        st.info(f"Not enough overlapping data for '{title}'. Required: {x_col}, {y_data_col}. Found points: {len(correlation_data)}")
    st.markdown("---")
    
# --- Curated "Key Insight" Correlation Plots ---
if not daily_df.empty:
    st.header("Key Health Correlations")

    # 1. Average Stress vs. Resting HR (same day)
    create_correlation_plot(daily_df, 
                            x_col='averageStressLevel', y_col='restingHeartRate',
                            title="Average Stress vs. Resting Heart Rate (Same Day)")

    # 2. Sleep Duration vs. Next Day's Resting HR
    create_correlation_plot(daily_df,
                            x_col='sleepingHours', y_col='restingHeartRate',
                            title="Sleep Duration vs. Next Day's Resting Heart Rate",
                            y_col_is_next_day=True)
                            
    # 3. Sleep Duration vs. Next Day's Average Stress
    create_correlation_plot(daily_df,
                            x_col='sleepingHours', y_col='averageStressLevel',
                            title="Sleep Duration vs. Next Day's Average Stress",
                            y_col_is_next_day=True)

    # 4. Active Kilocalories vs. Average Stress (same day)
    create_correlation_plot(daily_df,
                            x_col='activeKilocalories', y_col='averageStressLevel',
                            title="Active Calories vs. Average Stress (Same Day)")
                            
    # 5. Total Steps vs. Sleeping Hours (same day night)
    create_correlation_plot(daily_df,
                            x_col='totalSteps', y_col='sleepingHours',
                            title="Total Steps vs. Sleep Duration (Same Day's Night)")

    # 6. Body Battery at Wake vs. Previous Night's Sleep
    #    (This assumes 'bodyBatteryAtWakeTime' is the BB *after* the sleep reported on 'sleepingHours' for the same calendarDate)
    create_correlation_plot(daily_df,
                            x_col='sleepingHours', y_col='bodyBatteryAtWakeTime',
                            title="Previous Night's Sleep vs. Morning Body Battery")

    st.markdown("---") # Separator before the custom plotter
# --- End of Curated Plots ---


# --- Custom Metric Correlation Plotter (Your existing logic, slightly refactored) ---
    st.header("Custom Metric Correlation Explorer")
    
    numeric_cols = [col for col in daily_df.columns if pd.api.types.is_numeric_dtype(daily_df[col])]
    cols_to_exclude_from_select = [
        'userProfileId', 'userDailySummaryId', 'wellnessStartTimeGmt', 'wellnessStartTimeLocal', 
        'wellnessEndTimeGmt', 'wellnessEndTimeLocal', 'durationInMilliseconds', 'source', 
        'bodyBatteryVersion', 'respirationAlgorithmVersion',
        'highlyActiveMinutes', 'activeMinutes', 'sedentaryMinutes',
        'stressDurationMinutes', 'restStressMinutes', 'activityStressMinutes',
        'uncategorizedStressMinutes', 'totalStressMinutes',
        'lowStressMinutes', 'mediumStressMinutes', 'highStressMinutes',
        'measurableAwakeMinutes', 'measurableAsleepMinutes'
    ] # Removed rule, uuid as they are not numeric
    
    selectable_cols = sorted([
        col for col in numeric_cols 
        if col not in cols_to_exclude_from_select 
        and not str(col).endswith("Goal") # Ensure col is string for endswith
        and daily_df[col].nunique(dropna=True) > 1 
        and not daily_df[col].isnull().all()
    ])
    
    if selectable_cols:
        default_x_index = selectable_cols.index('averageStressLevel') if 'averageStressLevel' in selectable_cols else 0
        col_x_custom = st.selectbox("Select Metric for X-axis:", selectable_cols, index=default_x_index, key="custom_corr_x")
        
        y_options_display_names_custom = []
        y_options_actual_cols_custom = []
        for col in selectable_cols:
            y_options_display_names_custom.append(col.replace("_", " ").title())
            y_options_actual_cols_custom.append(col)
            if col != col_x_custom:
                y_options_display_names_custom.append(f"{col.replace('_', ' ').title()} (Next Day's Value)")
                y_options_actual_cols_custom.append(col)
        
        default_y_custom_raw = 'restingHeartRate' if 'restingHeartRate' in selectable_cols else selectable_cols[1] if len(selectable_cols) > 1 else selectable_cols[0]
        default_y_custom_display_index = 0
        try:
            default_y_custom_display_index = y_options_display_names_custom.index(default_y_custom_raw.replace("_", " ").title())
        except ValueError: pass

        y_choice_label_custom = st.selectbox(
            "Select Metric for Y-axis (Custom):", 
            y_options_display_names_custom, 
            index=default_y_custom_display_index,
            key="custom_corr_y"
        )
        
        selected_y_option_index_custom = y_options_display_names_custom.index(y_choice_label_custom)
        col_y_original_custom = y_options_actual_cols_custom[selected_y_option_index_custom]
        is_y_shifted_custom = "(Next Day's Value)" in y_choice_label_custom
        
        create_correlation_plot(
            daily_df,
            x_col=col_x_custom,
            y_col=col_y_original_custom,
            title=f"Custom Correlation: {col_x_custom.replace('_',' ').title()} vs. {y_choice_label_custom}",
            x_label=col_x_custom.replace('_',' ').title(),
            y_label=y_choice_label_custom, # create_correlation_plot handles next day label internally
            y_col_is_next_day=is_y_shifted_custom
        )
    else:
        st.info("No suitable numeric columns found for custom correlation plotting.")
# --- End of Custom Plotter ---

else:
    st.info("Daily summary data is not loaded. Please ensure data is fetched.")