# pages/5_Personal_Records.py
import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, timedelta, datetime # For time formatting

# --- Python Path Setup for utils ---
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# --- End Path Setup ---

from utils import garmin_utils
from utils import data_processing # Assuming process_general_activities_df is here
# from utils.formatting_utils import format_time_seconds_to_ms # Assuming this is now in a util

st.set_page_config(layout="wide", page_title="Personal Records")
st.title("🏆 Personal Records (Running)")

# --- Helper for formatting time (move to formatting_utils.py ideally) ---
def format_time_seconds_to_ms(total_seconds, show_hours=False):
    if pd.isna(total_seconds) or not isinstance(total_seconds, (int, float, np.number)): return "N/A"
    if total_seconds < 0: return "N/A"
    
    total_seconds = float(total_seconds) # Ensure it's float for calculations

    hours = int(total_seconds // 3600)
    remaining_seconds = total_seconds % 3600
    minutes = int(remaining_seconds // 60)
    seconds = int(round(remaining_seconds % 60))

    if not show_hours and hours > 0: # If not explicitly showing hours, add them to minutes
        minutes += hours * 60
        hours = 0
        
    parts = []
    if show_hours and hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or (hours == 0 and minutes == 0): # Show seconds if it's the only unit or non-zero
        parts.append(f"{seconds}s")
    
    return " ".join(parts) if parts else "0s"
# ------------------------------------------------------------------


@st.cache_data(ttl=600) # Cache PR data longer
def calculate_personal_records(_client, _username, _force_refresh_all_activities=False):
    # Fetch ALL activities for the user (PRs could be from any time)
    # Be mindful of API limits if user has thousands of activities.
    # For now, let's fetch last 2 years as an example, or you can fetch all if performance allows.
    # It's better to fetch all and then filter, but for dev, a shorter period is faster.
    # For a real PR page, you'd likely want to scan *all* historical data once, then update.
    # This initial_start_date is a placeholder; for true PRs, you might not limit the start date.
    initial_start_date = date(2000, 1, 1) # A very early date to try and get all data
    # If too slow, limit to a few years for testing:
    # initial_start_date = date.today() - timedelta(days=2*365) 
    
    all_activities_raw = garmin_utils.get_activities(
        _client, _username, 
        initial_start_date, 
        date.today(), 
        _force_refresh_all_activities # Force refresh for PR calculation might be desired sometimes
    )
    all_activities_p = data_processing.process_general_activities_df(all_activities_raw)
    
    running_activities = pd.DataFrame()
    if not all_activities_p.empty and 'activityType_key' in all_activities_p.columns:
        running_activities = all_activities_p[all_activities_p['activityType_key'] == 'running'].copy()

    prs = {}
    if running_activities.empty:
        return prs

    # 1. Fastest 1k & 1 mile from activity summary fields
    # These fields are usually in seconds.
    if 'fastestSplit_1000' in running_activities.columns:
        fastest_1k_row = running_activities.loc[running_activities['fastestSplit_1000'].idxmin()] if pd.notna(running_activities['fastestSplit_1000']).any() else None
        if fastest_1k_row is not None:
            prs['fastest_1k'] = {
                'time_seconds': fastest_1k_row['fastestSplit_1000'],
                'date': fastest_1k_row['date'],
                'activityName': fastest_1k_row.get('activityName', 'N/A'),
                'activityId': fastest_1k_row['activityId']
            }
    
    if 'fastestSplit_1609' in running_activities.columns: # Approx 1 mile
        fastest_1mile_row = running_activities.loc[running_activities['fastestSplit_1609'].idxmin()] if pd.notna(running_activities['fastestSplit_1609']).any() else None
        if fastest_1mile_row is not None:
            prs['fastest_1mile'] = {
                'time_seconds': fastest_1mile_row['fastestSplit_1609'],
                'date': fastest_1mile_row['date'],
                'activityName': fastest_1mile_row.get('activityName', 'N/A'),
                'activityId': fastest_1mile_row['activityId']
            }

    # 2. Longest Run (Distance & Duration)
    if 'distance_km' in running_activities.columns:
        longest_dist_row = running_activities.loc[running_activities['distance_km'].idxmax()]
        prs['longest_run_distance'] = {
            'distance_km': longest_dist_row['distance_km'],
            'date': longest_dist_row['date'],
            'activityName': longest_dist_row.get('activityName', 'N/A'),
            'activityId': longest_dist_row['activityId']
        }
    if 'duration_minutes' in running_activities.columns:
        longest_dur_row = running_activities.loc[running_activities['duration_minutes'].idxmax()]
        prs['longest_run_duration'] = {
            'duration_minutes': longest_dur_row['duration_minutes'],
            'date': longest_dur_row['date'],
            'activityName': longest_dur_row.get('activityName', 'N/A'),
            'activityId': longest_dur_row['activityId']
        }
        
    # 3. Fastest Pace for Run > 10km
    runs_over_10k = running_activities[running_activities['distance_km'] > 10].copy()
    if not runs_over_10k.empty and 'pace_min_per_km' in runs_over_10k.columns:
        fastest_10k_plus_run_row = runs_over_10k.loc[runs_over_10k['pace_min_per_km'].idxmin()] if pd.notna(runs_over_10k['pace_min_per_km']).any() else None
        if fastest_10k_plus_run_row is not None:
            prs['fastest_pace_gt_10k'] = {
                'pace_min_per_km': fastest_10k_plus_run_row['pace_min_per_km'],
                'distance_km': fastest_10k_plus_run_row['distance_km'],
                'date': fastest_10k_plus_run_row['date'],
                'activityName': fastest_10k_plus_run_row.get('activityName', 'N/A'),
                'activityId': fastest_10k_plus_run_row['activityId']
            }
            
    # 4. Highest VO2 Max from an activity
    if 'vo2MaxValue_activity' in running_activities.columns:
        highest_vo2_row = running_activities.loc[running_activities['vo2MaxValue_activity'].idxmax()] if pd.notna(running_activities['vo2MaxValue_activity']).any() else None
        if highest_vo2_row is not None:
            prs['highest_vo2max_activity'] = {
                'vo2max': highest_vo2_row['vo2MaxValue_activity'],
                'date': highest_vo2_row['date'],
                'activityName': highest_vo2_row.get('activityName', 'N/A'),
                'activityId': highest_vo2_row['activityId']
            }

    # TODO: Implement 5k, 10k, HM, M PRs from splitSummaries (complex)
    # This requires iterating through each run's splitSummaries,
    # finding consecutive splits that sum to the target distance, and minimizing time.
    # For now, we'll leave placeholders.
    prs['fastest_5k_calculated'] = None # Placeholder
    prs['fastest_10k_calculated'] = None # Placeholder
    
    return prs


if not st.session_state.get('logged_in', False):
    st.warning("Please log in first using the sidebar on the main page.")
    st.stop()

client = st.session_state.garmin_client
username = st.session_state.current_user
force_refresh_pr = st.sidebar.checkbox("Force Refresh PR Activity Data", value=False, key="force_refresh_pr_page")


personal_records = {}
if client and username:
    with st.spinner("Calculating Personal Records... This may take some time for the first run."):
        personal_records = calculate_personal_records(client, username, force_refresh_pr)

if personal_records:
    st.header("Your Running Personal Bests")

    cols_pr1 = st.columns(3)
    if 'fastest_1k' in personal_records and personal_records['fastest_1k']:
        pr = personal_records['fastest_1k']
        cols_pr1[0].metric("Fastest 1km", 
                           format_time_seconds_to_ms(pr['time_seconds']),
                           help=f"On {pr['date']} during '{pr.get('activityName','N/A')}'")
    if 'fastest_1mile' in personal_records and personal_records['fastest_1mile']:
        pr = personal_records['fastest_1mile']
        cols_pr1[1].metric("Fastest 1 Mile", 
                           format_time_seconds_to_ms(pr['time_seconds']),
                           help=f"On {pr['date']} during '{pr.get('activityName','N/A')}'")
    # Add calculated 5k if available
    if 'fastest_5k_calculated' in personal_records and personal_records['fastest_5k_calculated']: # Placeholder
        pr = personal_records['fastest_5k_calculated']
        cols_pr1[2].metric("Fastest 5km (Calculated)", 
                           format_time_seconds_to_ms(pr['time_seconds']),
                           help=f"On {pr['date']} during '{pr.get('activityName','N/A')}'")
    else:
        cols_pr1[2].metric("Fastest 5km", "Not Calculated Yet")


    cols_pr2 = st.columns(3)
    # Add calculated 10k if available
    if 'fastest_10k_calculated' in personal_records and personal_records['fastest_10k_calculated']: # Placeholder
        pr = personal_records['fastest_10k_calculated']
        cols_pr2[0].metric("Fastest 10km (Calculated)", 
                           format_time_seconds_to_ms(pr['time_seconds']),
                           help=f"On {pr['date']} during '{pr.get('activityName','N/A')}'")
    else:
        cols_pr2[0].metric("Fastest 10km", "Not Calculated Yet")

    if 'longest_run_distance' in personal_records and personal_records['longest_run_distance']:
        pr = personal_records['longest_run_distance']
        cols_pr2[1].metric("Longest Run (Distance)", 
                           f"{pr['distance_km']:.2f} km",
                           help=f"On {pr['date']} - '{pr.get('activityName','N/A')}'")
    if 'longest_run_duration' in personal_records and personal_records['longest_run_duration']:
        pr = personal_records['longest_run_duration']
        cols_pr2[2].metric("Longest Run (Duration)", 
                           format_time_seconds_to_ms(pr['duration_minutes']*60, show_hours=True),
                           help=f"On {pr['date']} - '{pr.get('activityName','N/A')}'")

    cols_pr3 = st.columns(2)
    if 'fastest_pace_gt_10k' in personal_records and personal_records['fastest_pace_gt_10k']:
        pr = personal_records['fastest_pace_gt_10k']
        cols_pr3[0].metric("Fastest Avg Pace (>10km Run)", 
                           format_time_seconds_to_ms(pr['pace_min_per_km']*60),
                           help=f"{pr['distance_km']:.2f}km on {pr['date']} - '{pr.get('activityName','N/A')}'")
    if 'highest_vo2max_activity' in personal_records and personal_records['highest_vo2max_activity']:
        pr = personal_records['highest_vo2max_activity']
        cols_pr3[1].metric("Highest VO2 Max (Activity)", 
                           f"{pr['vo2max']:.1f}",
                           help=f"On {pr['date']} - '{pr.get('activityName','N/A')}'")
        
    st.caption("Note: Some PRs like 5k/10k might be based on your fastest recorded kilometer/mile splits from any run, or segments if that data is parsed. Garmin's official PRs for these distances are not directly available via this API version.")
    st.markdown("---")
    st.info("Calculation of PRs for standard distances (5k, 10k, HM, M) from within longer runs by analyzing split data is a complex feature planned for future updates.")

elif client and username: # Data was fetched but no PRs found (e.g. no running activities)
    st.info("No running activities found to calculate personal records from.")
else:
    st.info("Log in to calculate and view personal records.")