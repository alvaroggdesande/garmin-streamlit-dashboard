import pandas as pd
import numpy as np
from datetime import timedelta
import math

import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def safe_float(value, default=np.nan):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_int(value, default=np.nan):
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def process_activities_df(activities_df):
    if activities_df.empty:
        return pd.DataFrame()

    processed_activities = activities_df.copy()

    # Date and Time processing
    processed_activities['startTimeGMT'] = pd.to_datetime(processed_activities['startTimeGMT'], unit='ms', errors='coerce')
    processed_activities['date'] = processed_activities['startTimeGMT'].dt.date

    # Duration - usually in seconds
    processed_activities['duration_seconds'] = processed_activities['duration'].apply(safe_float)
    processed_activities['duration_minutes'] = processed_activities['duration_seconds'] / 60
    processed_activities['duration_hours'] = processed_activities['duration_minutes'] / 60

    # Distance - usually in meters
    processed_activities['distance_meters'] = processed_activities['distance'].apply(safe_float)
    processed_activities['distance_km'] = processed_activities['distance_meters'] / 1000

    # Pace for running/cycling (min/km or min/mile)
    # Only calculate pace if distance > 0 and duration > 0
    mask = (processed_activities['distance_km'] > 0) & (processed_activities['duration_minutes'] > 0)
    processed_activities['pace_min_per_km'] = np.nan
    processed_activities.loc[mask, 'pace_min_per_km'] = \
        processed_activities.loc[mask, 'duration_minutes'] / processed_activities.loc[mask, 'distance_km']

    # Average HR
    processed_activities['avgHR'] = processed_activities['averageHR'].apply(safe_float)
    processed_activities['maxHR'] = processed_activities['maxHR'].apply(safe_float)

    # Calories
    processed_activities['calories'] = processed_activities['calories'].apply(safe_float)

    # Training Effect (Aerobic and Anaerobic)
    processed_activities['aerobicTrainingEffect'] = processed_activities['aerobicTrainingEffect'].apply(safe_float)
    processed_activities['anaerobicTrainingEffect'] = processed_activities['anaerobicTrainingEffect'].apply(safe_float)

    # Extract HR zones if available (this part is highly dependent on API response structure)
    # Example: Assuming 'timeInHrZone' is a list of dicts like [{'zoneNumber': 1, 'timeInSeconds': 300}, ...]
    # This is a common pattern but verify with your actual data.
    for i in range(1, 6): # Assuming 5 HR zones
        processed_activities[f'time_in_zone{i}_seconds'] = 0.0

    for index, row in processed_activities.iterrows():
        time_in_hr_zone_data = row.get('timeInHrZone') # Or similar field name
        if isinstance(time_in_hr_zone_data, list):
            for zone_data in time_in_hr_zone_data:
                if isinstance(zone_data, dict):
                    zone_number = zone_data.get('zoneNumber')
                    time_in_seconds = safe_float(zone_data.get('timeInSeconds'), 0.0)
                    if zone_number and 1 <= zone_number <= 5:
                        processed_activities.loc[index, f'time_in_zone{zone_number}_seconds'] = time_in_seconds
    
    # Convert zone times to minutes
    for i in range(1, 6):
        processed_activities[f'time_in_zone{i}_minutes'] = processed_activities[f'time_in_zone{i}_seconds'] / 60


    # Add more processing as needed: VO2 Max, stride length, cadence, etc.
    # Example: 'vO2MaxValue' or 'maxMetValue' could be VO2 Max related
    processed_activities['vo2_max_activity'] = processed_activities.get('vO2MaxValue', pd.Series(dtype='float64')).apply(safe_float)

    return processed_activities

def identify_zone2_runs(processed_activities_df, max_hr_estimate=None):
    if processed_activities_df.empty:
        return pd.DataFrame()
    
    # Filter for "running" activities first
    runs_df = processed_activities_df[processed_activities_df['activityType'].isin(['running', 'street_running', 'track_running', 'trail_running'])].copy()
    
    if runs_df.empty:
        return pd.DataFrame()

    # Method 1: If 'time_in_zone2_minutes' is reliably populated
    # Define "Zone 2 run" as, e.g., >60% of time in Zone 2
    # runs_df['is_zone2_run_by_time'] = (runs_df['time_in_zone2_minutes'] / runs_df['duration_minutes']) > 0.60

    # Method 2: If you have max_hr_estimate (e.g., from user settings or calculated)
    # Zone 2 is typically 60-70% of Max HR.
    if max_hr_estimate:
        z2_lower_bound = max_hr_estimate * 0.60
        z2_upper_bound = max_hr_estimate * 0.70
        runs_df['is_zone2_run_by_avg_hr'] = (runs_df['avgHR'] >= z2_lower_bound) & \
                                           (runs_df['avgHR'] <= z2_upper_bound)
        # Prioritize the avg HR method if available
        runs_df['is_zone2_run'] = runs_df['is_zone2_run_by_avg_hr']
    elif 'time_in_zone2_minutes' in runs_df.columns:
         # Fallback to time in zone if max_hr_estimate is not provided
        runs_df['is_zone2_run'] = (runs_df['time_in_zone2_minutes'] > 0) & \
                                  ((runs_df['time_in_zone2_minutes'] / runs_df['duration_minutes'].replace(0, np.nan)) > 0.50) # e.g., >50% time
    else:
        # Cannot determine without HR zone info or max HR estimate
        runs_df['is_zone2_run'] = False

    return runs_df[runs_df['is_zone2_run']].copy()


def calculate_aerobic_efficiency(zone2_runs_df):
    if zone2_runs_df.empty or 'avgHR' not in zone2_runs_df.columns or 'pace_min_per_km' not in zone2_runs_df.columns:
        return pd.DataFrame()
    
    # Aerobic efficiency: Pace (e.g., m/s) / Avg HR
    # Or simply track Pace @ Zone 2 HR over time.
    # We'll return relevant columns for plotting.
    aerobic_efficiency_data = zone2_runs_df[['date', 'pace_min_per_km', 'avgHR', 'distance_km']].copy()
    aerobic_efficiency_data = aerobic_efficiency_data.dropna(subset=['pace_min_per_km', 'avgHR'])
    return aerobic_efficiency_data

def calculate_hr_zone_distribution(processed_activities_df, period='W'):
    if processed_activities_df.empty:
        return pd.DataFrame()

    df = processed_activities_df.copy()
    if 'date' not in df.columns or not pd.api.types.is_datetime64_any_dtype(df['date']):
         df['date'] = pd.to_datetime(df.get('date', df.get('startTimeGMT')), errors='coerce').dt.date
    
    df = df.dropna(subset=['date'])
    df['date'] = pd.to_datetime(df['date']) # Ensure it's datetime for resampling

    zone_cols = [f'time_in_zone{i}_minutes' for i in range(1, 6) if f'time_in_zone{i}_minutes' in df.columns]
    if not zone_cols:
        return pd.DataFrame() # No zone time columns found

    # Sum time in zones per period (e.g., weekly)
    # Set date as index for resampling
    zone_distribution = df.set_index('date')[zone_cols].fillna(0).resample(period).sum()
    return zone_distribution.reset_index()

def process_hrv_df(hrv_df):

    logger.info(f"Input to process_hrv_df. Shape: {hrv_df.shape}, Columns: {hrv_df.columns.tolist()}")

    if hrv_df.empty:
        return pd.DataFrame()
    
    processed_hrv = hrv_df.copy()
    # Ensure 'date' column exists and is datetime
    if 'date' in processed_hrv.columns:
        processed_hrv['date'] = pd.to_datetime(processed_hrv['date']).dt.date
    elif 'calendarDate' in processed_hrv.columns: # Common alternative
        processed_hrv['date'] = pd.to_datetime(processed_hrv['calendarDate']).dt.date

    # Key HRV metrics: 'hrvValue', 'hrvStatus', 'baselineLow', 'baselineHigh'
    # 'lastNightAvg' or 'weeklyAvg' might be 'hrvValue' or separate. Inspect your data.
    # Example: Use 'hrvValue' if it's the nightly average.
    # The structure from client.get_hrv_data(date) is usually like:
    # {'hrvSummary': {'weeklyAvg': X, 'lastNightAvg': Y, ...}, 'hrvValue': Z }
    # Or it might be a list of hrvSummaries if fetched over a range
    # The current garmin_utils.get_hrv_data aims to create rows from hrvSummaries
    
    # Columns to keep/rename (adjust based on actual data)
    # Common fields in `hrvSummaries` include:
    # 'status', 'value', 'userProfilePk', 'type' (e.g., 'WEEKLY_AVERAGE', 'LAST_NIGHT_AVERAGE')
    # 'feedbackPhrase', 'feedbackSubTrail'
    # 'baselineLow', 'baselineHigh', 'baselineLower', 'baselineUpper' (check which ones are present)
    
    # We are particularly interested in the nightly average, often under `value` when `type` is `LAST_NIGHT_AVERAGE`
    # Or if `hrvValue` is a top-level key for the day.
    if 'value' in processed_hrv.columns and 'type' in processed_hrv.columns:
        nightly_hrv = processed_hrv[processed_hrv['type'] == 'LAST_NIGHT_AVERAGE'].copy()
        nightly_hrv = nightly_hrv.rename(columns={'value': 'hrv_nightly_avg'})
        return nightly_hrv[['date', 'hrv_nightly_avg', 'status', 'baselineLow', 'baselineHigh']].dropna(subset=['date'])
    elif 'hrvValue' in processed_hrv.columns: # Alternative structure
        return processed_hrv[['date', 'hrvValue', 'hrvStatus']].dropna(subset=['date'])
    
    return pd.DataFrame() # If key columns are not found

def process_sleep_df(sleep_df):
    if sleep_df.empty:
        return pd.DataFrame()
    
    processed_sleep = sleep_df.copy()
    # 'sleepStartTimestampGMT' and 'sleepEndTimestampGMT' are usually epoch ms
    # 'calendarDate' is often the date the sleep *ended* or was logged for.
    if 'calendarDate' in processed_sleep.columns:
        processed_sleep['date'] = pd.to_datetime(processed_sleep['calendarDate']).dt.date
    elif 'sleepStartTimestampGMT' in processed_sleep.columns: # Fallback to sleep start
        processed_sleep['date'] = pd.to_datetime(processed_sleep['sleepStartTimestampGMT'], unit='ms').dt.date

    # Durations are often in seconds
    for col in ['durationInSeconds', 'deepSleepDurationInSeconds', 'lightSleepDurationInSeconds',
                'remSleepInSeconds', 'awakeDurationInSeconds']:
        if col in processed_sleep.columns:
            processed_sleep[col.replace('InSeconds', '_minutes')] = processed_sleep[col].apply(safe_float) / 60
    
    # Sleep score
    if 'overallSleepScore' in processed_sleep.columns and 'value' in processed_sleep['overallSleepScore'].iloc[0]: # Check if it's a dict
        processed_sleep['sleep_score'] = processed_sleep['overallSleepScore'].apply(lambda x: x.get('value') if isinstance(x, dict) else np.nan)

    return processed_sleep.dropna(subset=['date'])


def merge_sleep_hrv_activity_data(sleep_df, hrv_df, activities_df=None, daily_summaries_df=None):
    """
    Merges sleep, HRV, and optionally activity/daily summary data on 'date'.
    Assumes each df has a 'date' column (datetime.date objects).
    """
    merged_df = pd.DataFrame()

    if not sleep_df.empty and 'date' in sleep_df.columns:
        sleep_df = sleep_df.add_suffix('_sleep')
        sleep_df = sleep_df.rename(columns={'date_sleep': 'date'})
        merged_df = sleep_df

    if not hrv_df.empty and 'date' in hrv_df.columns:
        hrv_df = hrv_df.add_suffix('_hrv')
        hrv_df = hrv_df.rename(columns={'date_hrv': 'date'})
        if not merged_df.empty:
            merged_df = pd.merge(merged_df, hrv_df, on='date', how='outer')
        else:
            merged_df = hrv_df
            
    if daily_summaries_df is not None and not daily_summaries_df.empty and 'date' in daily_summaries_df.columns:
        # Select relevant columns like RHR, steps, stress
        cols_to_keep = ['date', 'restingHeartRate', 'averageStressLevel', 'maxStressLevel', 'totalSteps']
        daily_subset = daily_summaries_df[[col for col in cols_to_keep if col in daily_summaries_df.columns]].copy()
        daily_subset = daily_subset.add_suffix('_daily')
        daily_subset = daily_subset.rename(columns={'date_daily': 'date'})
        if not merged_df.empty:
            merged_df = pd.merge(merged_df, daily_subset, on='date', how='outer')
        else:
            merged_df = daily_subset

    # For activities, you might want to aggregate them per day first (e.g., total duration, avg TE)
    # before merging, or merge and then deal with multiple activities per day.
    # For simplicity, we'll skip direct activity merge here, as it's often plotted separately.

    if not merged_df.empty:
        merged_df = merged_df.sort_values(by='date').reset_index(drop=True)
    return merged_df


def calculate_custom_training_load(processed_activities_df, method='trimp_exp'):
    if processed_activities_df.empty:
        return pd.DataFrame()

    load_df = processed_activities_df[['date', 'duration_minutes', 'avgHR', 'activityType', 'aerobicTrainingEffect']].copy()
    load_df = load_df.dropna(subset=['duration_minutes', 'avgHR'])
    load_df['custom_load'] = 0.0

    # Banister's TRIMP (Exponential) - needs individual Max HR and Resting HR
    # For simplicity, we might use a simpler TRIMP or just use Garmin's Aerobic TE.
    # TRIMP_exp = Duration * ( (AvgHR - RestHR) / (MaxHR - RestHR) ) * 0.64 * exp(1.92 * ( (AvgHR - RestHR) / (MaxHR - RestHR) ))
    # This requires MaxHR and RestHR, which might not be readily available per activity.

    # Simpler TRIMP (Edwards') = Sum of (duration in zone * zone_factor)
    # Zone factors: Z1=1, Z2=2, Z3=3, Z4=4, Z5=5
    if method == 'trimp_edwards':
        for index, row in load_df.iterrows():
            trimp_score = 0
            for i in range(1, 6):
                time_in_zone_col = f'time_in_zone{i}_minutes'
                if time_in_zone_col in processed_activities_df.columns:
                    time_in_zone = processed_activities_df.loc[index, time_in_zone_col]
                    if pd.notna(time_in_zone):
                        trimp_score += time_in_zone * i # Zone factor = zone number
            load_df.loc[index, 'custom_load'] = trimp_score
    elif method == 'aerobic_te_sum': # Sum of Aerobic Training Effect per day
        # This requires daily aggregation
        load_df['custom_load'] = load_df['aerobicTrainingEffect'].fillna(0)
        daily_load = load_df.groupby('date')['custom_load'].sum().reset_index()
        return daily_load
    else: # Default: Duration * AvgHR (very basic)
        load_df['custom_load'] = load_df['duration_minutes'] * load_df['avgHR']

    # If not summing TE, aggregate load per day
    if method != 'aerobic_te_sum':
        daily_load = load_df.groupby('date')['custom_load'].sum().reset_index()
        return daily_load
    
    return load_df # Should have been returned as daily_load


def process_daily_summary_for_plotting(df_raw):
    if df_raw.empty:
        return pd.DataFrame()
    df = df_raw.copy()

    # Ensure 'calendarDate' is datetime
    df['calendarDate'] = pd.to_datetime(df['calendarDate']).dt.date # Keep as date object for grouping/plotting

    # Convert seconds to minutes/hours
    for col_s in ['highlyActiveSeconds', 'activeSeconds', 'sedentarySeconds', 'sleepingSeconds',
                  'stressDuration', 'restStressDuration', 'activityStressDuration',
                  'lowStressDuration', 'mediumStressDuration', 'highStressDuration']:
        if col_s in df.columns:
            df[col_s.replace('Seconds', 'Minutes')] = df[col_s].fillna(0) / 60
            if col_s == 'sleepingSeconds': # Also make hours for sleep
                 df[col_s.replace('Seconds', 'Hours')] = df[col_s].fillna(0) / 3600
    
    # Convert distance
    if 'totalDistanceMeters' in df.columns:
        df['totalDistanceKm'] = df['totalDistanceMeters'].fillna(0) / 1000

    # Handle potential non-numeric explicitly for metrics (e.g. Body Battery if it's fetched as string 'N/A')
    for col_num in ['restingHeartRate', 'averageStressLevel', 'totalSteps', 'bodyBatteryMostRecentValue',
                    'activeKilocalories', 'totalDistanceKm', 'moderateIntensityMinutes',
                    'vigorousIntensityMinutes', 'intensityMinutesGoal', 'floorsAscended', 'dailyStepGoal',
                    'bodyBatteryHighestValue', 'bodyBatteryLowestValue', 'bodyBatteryAtWakeTime']:
        if col_num in df.columns:
            df[col_num] = pd.to_numeric(df[col_num], errors='coerce') # Coerce errors to NaN

    return df

def format_time_minutes_seconds(decimal_minutes):
    """Converts decimal minutes to a string 'Xm Ys'."""
    if pd.isna(decimal_minutes) or not isinstance(decimal_minutes, (int, float)):
        return "N/A"
    if decimal_minutes < 0:
        return "N/A" # Or handle negative if it makes sense in some context

    minutes = int(decimal_minutes)
    seconds = int(round((decimal_minutes - minutes) * 60))
    
    if minutes == 0 and seconds == 0:
        return "0s" # Or handle as you prefer
    
    output = ""
    if minutes > 0:
        output += f"{minutes}m "
    output += f"{seconds}s"
    return output.strip()

def format_time_seconds_to_ms(total_seconds):
    """Converts total seconds to a string 'Xm Ys'."""
    if pd.isna(total_seconds) or not isinstance(total_seconds, (int, float)):
        return "N/A"
    if total_seconds < 0:
        return "N/A"

    minutes = int(total_seconds // 60)
    seconds = int(round(total_seconds % 60))

    if minutes == 0 and seconds == 0:
        return "0s"

    output = ""
    if minutes > 0:
        output += f"{minutes}m "
    output += f"{seconds}s"
    return output.strip()


def process_general_activities_df(activities_df_raw): # Renamed for clarity
    if activities_df_raw.empty:
        return pd.DataFrame()
    
    df = activities_df_raw.copy()
    # Extract activityType_key
    if 'activityType' in df.columns:
        df['activityType_key'] = df['activityType'].apply(
            lambda x: x.get('typeKey') if isinstance(x, dict) else x if isinstance(x, str) else None
        )
    # Date and Time processing
    df['startTimeGMT_dt'] = pd.to_datetime(df['startTimeGMT'], errors='coerce')
    df['date'] = pd.to_datetime(df['startTimeLocal'], errors='coerce').dt.date

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
    df['calories'] = pd.to_numeric(df['calories'], errors='coerce') # Added calories

    # Cadence
    if 'averageRunningCadenceInStepsPerMinute' in df.columns:
        # Cadence is often steps for ONE foot. Multiply by 2 for total steps per minute.
        df['avgCadence'] = pd.to_numeric(df['averageRunningCadenceInStepsPerMinute'], errors='coerce') * 2
    if 'maxRunningCadenceInStepsPerMinute' in df.columns:
        df['maxCadence'] = pd.to_numeric(df['maxRunningCadenceInStepsPerMinute'], errors='coerce') * 2

    # VO2Max
    if 'vO2MaxValue' in df.columns:
        df['vo2MaxValue_activity'] = pd.to_numeric(df['vO2MaxValue'], errors='coerce')
    
    # TE
    df['aerobicTE'] = pd.to_numeric(df['aerobicTrainingEffect'], errors='coerce')
    df['anaerobicTE'] = pd.to_numeric(df['anaerobicTrainingEffect'], errors='coerce')

    # HR Zones (using direct column names from your sample: hrTimeInZone_1, etc.)
    for i in range(1, 6):
        col_name = f'hrTimeInZone_{i}'
        if col_name in df.columns:
            df[f'time_in_zone{i}_seconds'] = pd.to_numeric(df[col_name], errors='coerce').fillna(0)
            df[f'time_in_zone{i}_minutes'] = df[f'time_in_zone{i}_seconds'] / 60
        else:
            df[f'time_in_zone{i}_seconds'] = 0.0
            df[f'time_in_zone{i}_minutes'] = 0.0
            
    df = df.sort_values(by='date').reset_index(drop=True)
    return df

def calculate_pace_per_zone_trend(running_df, hr_zone_definitions, min_duration_for_classification_minutes=10):
    """
    Calculates average pace for runs primarily in each HR zone.
    hr_zone_definitions: dict like {'Zone 2': (min_bpm, max_bpm), 'Zone 3': ...}
    """
    if running_df.empty or 'avgHR' not in running_df.columns or \
       'pace_min_per_km' not in running_df.columns or 'duration_minutes' not in running_df.columns:
        return pd.DataFrame()

    # Filter out very short runs that are hard to classify by avgHR
    df = running_df[running_df['duration_minutes'] >= min_duration_for_classification_minutes].copy()
    if df.empty:
        return pd.DataFrame()

    def get_primary_zone(avg_hr, zones_def):
        for zone_name, (min_bpm, max_bpm) in zones_def.items():
            if min_bpm <= avg_hr <= max_bpm:
                return zone_name
        return None # Or "Undefined"

    df['primary_zone_by_avg_hr'] = df['avgHR'].apply(lambda hr: get_primary_zone(hr, hr_zone_definitions))
    
    # Filter out runs that couldn't be classified or have no pace
    classified_runs = df.dropna(subset=['primary_zone_by_avg_hr', 'pace_min_per_km', 'date'])
    if classified_runs.empty:
        return pd.DataFrame()

    # Ensure date is datetime for resampling
    classified_runs['date'] = pd.to_datetime(classified_runs['date'])

    # Calculate average pace per zone over time (e.g., weekly average)
    # This groups by week and primary_zone, then calculates mean pace.
    # To plot trends, we want one line per zone.
    # We can pivot or plot iteratively.

    # For plotting, it's often easier to have one trace per zone.
    # Let's prepare data for that. We might average pace weekly/monthly per zone.
    
    # Example: Weekly average pace for each zone
    # This creates a multi-index (date, primary_zone_by_avg_hr)
    pace_trends = classified_runs.set_index('date').groupby([
        pd.Grouper(freq='W-MON', label='left', closed='left'), 
        'primary_zone_by_avg_hr'
    ])['pace_min_per_km'].mean().reset_index()
    
    return pace_trends
