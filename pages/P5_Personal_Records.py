# pages/P5_Personal_Records.py
import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, timedelta, datetime 

# --- Python Path Setup for utils ---
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# --- End Path Setup ---

from utils import garmin_utils
from utils import data_processing 

st.set_page_config(layout="wide", page_title="Personal Records")
st.title("🏆 Personal Running Records")

# --- Helper for formatting time ---
def format_seconds_to_time_str(total_seconds, show_hours_explicitly=False):
    if pd.isna(total_seconds) or not isinstance(total_seconds, (int, float, np.number)) or total_seconds < 0:
        return "N/A"
    total_seconds = float(total_seconds)
    hours = int(total_seconds // 3600)
    remaining_seconds = total_seconds % 3600
    minutes = int(remaining_seconds // 60)
    seconds = int(round(remaining_seconds % 60))
    if show_hours_explicitly: # Used for longer distances like HM or full marathons
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        if hours > 0: # If run is over an hour, show total minutes
            total_minutes = hours * 60 + minutes
            return f"{total_minutes:02d}:{seconds:02d}"
        else: # Standard MM:SS
            return f"{minutes:02d}:{seconds:02d}"

# --- Helper function to display a record metric ---
def display_pr_metric(column, label, value, unit="", help_text=""):
    # Ensure value is a string for st.metric if it's not "N/A"
    display_value = str(value) if value not in [None, "N/A", np.nan] else "N/A"
    unit_str = str(unit) if unit not in [None, "N/A", np.nan] else ""
    
    if display_value == "N/A":
        column.metric(label, "N/A", help=help_text if help_text else None)
    else:
        column.metric(label, f"{display_value} {unit_str}".strip(), help=help_text if help_text else None)


@st.cache_data(ttl=1800)
def calculate_personal_records_detailed(_client, _username, _force_refresh_all_activities=False):
    # print(f"DEBUG CALC: Starting PR calculation for {_username}, force_refresh={_force_refresh_all_activities}") # Notebook/console print
    initial_start_date = date(2024, 1, 1)
    all_activities_raw = garmin_utils.get_activities(
        _client, _username, initial_start_date, date.today(), _force_refresh_all_activities
    )
    all_activities_p = data_processing.process_general_activities_df(all_activities_raw)

    running_activities = pd.DataFrame()
    if not all_activities_p.empty and 'activityType_key' in all_activities_p.columns:
        running_keys = ['running', 'trail_running', 'track_running', 'indoor_running', 'street_running']
        running_activities = all_activities_p[all_activities_p['activityType_key'].isin(running_keys)].copy()
        
        cols_to_make_numeric = [
            'distance_km', 'duration_seconds', 'pace_min_per_km', 'maxSpeed', 'maxPower', 
            'avgCadence', 'averageHR', 'elevationGain', 'vo2MaxValue_activity',
            'fastestSplit_1000', 'fastestSplit_1609', 'fastestSplit_5000', 'fastestSplit_10000'
        ]
        if not running_activities.empty:
            for col in cols_to_make_numeric:
                if col in running_activities.columns:
                    running_activities[col] = pd.to_numeric(running_activities[col], errors='coerce')
                # else: # This warning would appear in Streamlit UI if active
                #     st.warning(f"PR Calc Check: Column '{col}' for numeric conversion NOT FOUND in running_activities.")
    
    prs = {} 
    if running_activities.empty:
        # print("DEBUG CALC: No running activities found after filtering.") # Notebook/console print
        return prs

    def get_pr_details(best_row_series, value_col_name, unit, time_format_func=None, show_hours=False):
        if not isinstance(best_row_series, pd.Series) or value_col_name not in best_row_series:
            return {"value": None, "formatted_value": "N/A", "unit": unit, "date": None, "name": "N/A", "id": None}
        val = best_row_series[value_col_name]
        details = {
            "value": val if pd.notna(val) else None, "unit": unit,
            "date": pd.to_datetime(best_row_series.get('startTimeGMT_dt')).date() if 'startTimeGMT_dt' in best_row_series and pd.notna(best_row_series.get('startTimeGMT_dt')) else best_row_series.get('date'),
            "name": best_row_series.get('activityName', 'N/A'),
            "id": best_row_series.get('activityId')
        }
        if time_format_func and details["value"] is not None:
            details["formatted_value"] = time_format_func(details["value"], show_hours_explicitly=show_hours)
        elif isinstance(details["value"], float) and details["value"] is not None: # Check not None for float too
            details["formatted_value"] = f"{details['value']:.2f}"
        elif details["value"] is not None: # For integers or other types
            details["formatted_value"] = str(details["value"])
        else: # Value is None
            details["formatted_value"] = "N/A"
        return details

    # === SECTION 1: FASTEST SEGMENT PRS (from Garmin's summary fields) ===
    garmin_segment_prs_config = {
        "Fastest 1km (Segment)": 'fastestSplit_1000', "Fastest 1 Mile (Segment)": 'fastestSplit_1609',
        "Fastest 5km (Segment)": 'fastestSplit_5000', "Fastest 10km (Segment)": 'fastestSplit_10000',
    }
    for pr_label, column_name in garmin_segment_prs_config.items():
        if column_name in running_activities.columns:
            valid_splits = running_activities[running_activities[column_name].notna() & (running_activities[column_name] > 0)].copy()
            if not valid_splits.empty:
                best_row = valid_splits.loc[valid_splits[column_name].idxmin()]
                prs[pr_label] = get_pr_details(best_row, column_name, "", format_seconds_to_time_str, 
                                               show_hours=(best_row[column_name] >= 3600))

    # === SECTION 2: FASTEST TIMES FOR FULL RUN EVENTS ===
    full_run_event_prs_config = {
        "Fastest 5km (Full Event)": (4.90, 5.15), "Fastest 10km (Full Event)": (9.80, 10.25),
        "Fastest 15km (Full Event)": (14.75, 15.30), "Fastest Half Marathon (Full Event)": (20.75, 21.50)
    }
    if 'distance_km' in running_activities.columns and 'duration_seconds' in running_activities.columns:
        for pr_label, (min_d, max_d) in full_run_event_prs_config.items():
            candidates = running_activities[
                (running_activities['distance_km'] >= min_d) & (running_activities['distance_km'] <= max_d) &
                (running_activities['duration_seconds'] > 0)
            ].copy()
            # print(f"CALC DEBUG - Full Run Event '{pr_label}': Num Candidates={len(candidates)}") # Notebook/console
            if not candidates.empty and candidates['duration_seconds'].notna().any():
                best_row = candidates.loc[candidates['duration_seconds'].idxmin()]
                prs[pr_label] = get_pr_details(best_row, 'duration_seconds', "", format_seconds_to_time_str, 
                                               show_hours=(best_row['duration_seconds'] >= 3600))

    # === SECTION 3: FASTEST AVERAGE PACE BY DISTANCE CATEGORY ===
    distance_categories_config = {
        "(<5km)": (0.5, 4.99), "(5-10km)": (5.0, 9.99), "(10-15km)": (10.0, 14.99),
        "(15km-HM)": (15.0, 21.3), "(HM+)": (21.31, 1000.0) 
    }
    if 'distance_km' in running_activities.columns and 'pace_min_per_km' in running_activities.columns:
        for dist_label_suffix, (min_d, max_d) in distance_categories_config.items():
            pr_key = f"Fastest Pace {dist_label_suffix}"
            candidates = running_activities[
                (running_activities['distance_km'] >= min_d) & (running_activities['distance_km'] <= max_d) &
                (running_activities['pace_min_per_km'] > 0)
            ].copy()
            # print(f"CALC DEBUG - Pace Category '{pr_key}': Num Candidates={len(candidates)}") # Notebook/console
            if not candidates.empty and candidates['pace_min_per_km'].notna().any():
                best_row = candidates.loc[candidates['pace_min_per_km'].idxmin()]
                pace_in_seconds_per_km = best_row['pace_min_per_km'] * 60
                prs[pr_key] = get_pr_details(best_row, 'pace_min_per_km', "min/km")
                prs[pr_key]["formatted_value"] = format_seconds_to_time_str(pace_in_seconds_per_km)
                prs[pr_key]["distance_info"] = f"({best_row['distance_km']:.2f}km run)"

    # === SECTION 4: RUNNING FORM & EFFICIENCY BY DISTANCE CATEGORY ===
    # Highest Average Cadence
    if 'avgCadence' in running_activities.columns and 'distance_km' in running_activities.columns:
        for dist_label_suffix, (min_d, max_d) in distance_categories_config.items():
            pr_key = f"Highest Avg Cadence {dist_label_suffix}"
            candidates = running_activities[
                (running_activities['distance_km'] >= min_d) & (running_activities['distance_km'] <= max_d) &
                (running_activities['avgCadence'] > 0)
            ].copy()
            # print(f"CALC DEBUG - Cadence '{pr_key}': Num Candidates={len(candidates)}") # Notebook/console
            if not candidates.empty and candidates['avgCadence'].notna().any():
                best_row = candidates.loc[candidates['avgCadence'].idxmax()]
                prs[pr_key] = get_pr_details(best_row, 'avgCadence', "spm")
                prs[pr_key]["distance_info"] = f"({best_row['distance_km']:.2f}km run)"

    # Lowest Average HR
    if 'averageHR' in running_activities.columns and 'distance_km' in running_activities.columns:
        for dist_label_suffix, (min_d, max_d) in distance_categories_config.items():
            pr_key = f"Lowest Avg HR {dist_label_suffix}"
            candidates = running_activities[
                (running_activities['distance_km'] >= min_d) & (running_activities['distance_km'] <= max_d) &
                (running_activities['averageHR'] > 0)
            ].copy()
            # print(f"CALC DEBUG - Avg HR '{pr_key}': Num Candidates={len(candidates)}") # Notebook/console
            if not candidates.empty and candidates['averageHR'].notna().any():
                best_row = candidates.loc[candidates['averageHR'].idxmin()]
                prs[pr_key] = get_pr_details(best_row, 'averageHR', "bpm")
                prs[pr_key]["distance_info"] = f"({best_row['distance_km']:.2f}km run)"
                if 'pace_min_per_km' in best_row and pd.notna(best_row['pace_min_per_km']):
                    prs[pr_key]["pace_info"] = f"(Pace: {format_seconds_to_time_str(best_row['pace_min_per_km']*60)} min/km)"
    
    specific_hr_pace_label = "Efficient HR (~10k Target Pace)"
    hr_pace_brackets_config = { 
        specific_hr_pace_label: {'dist_min': 9.8, 'dist_max': 10.2, 'pace_min': 5.0, 'pace_max': 5.5}
    }
    if 'distance_km' in running_activities.columns and \
       'pace_min_per_km' in running_activities.columns and \
       'averageHR' in running_activities.columns:
        for label, criteria in hr_pace_brackets_config.items():
            candidates_hr_pace = running_activities[
                (running_activities['distance_km'] >= criteria['dist_min']) & (running_activities['distance_km'] <= criteria['dist_max']) &
                (running_activities['pace_min_per_km'] >= criteria['pace_min']) & (running_activities['pace_min_per_km'] <= criteria['pace_max']) &
                (running_activities['averageHR'] > 0)
            ].copy()
            # print(f"CALC DEBUG - Specific HR '{label}': Num Candidates={len(candidates_hr_pace)}") # Notebook/console
            if not candidates_hr_pace.empty and candidates_hr_pace['averageHR'].notna().any():
                best_row = candidates_hr_pace.loc[candidates_hr_pace['averageHR'].idxmin()]
                prs[label] = get_pr_details(best_row, 'averageHR', "bpm")
                prs[label]["pace_info"] = f"(Pace: {format_seconds_to_time_str(best_row['pace_min_per_km']*60)} min/km)"
                prs[label]["distance_info"] = f"({best_row['distance_km']:.2f}km run)"

    # === SECTION 5: GENERAL RUNNING MILESTONES ===
    general_milestone_config = {
        "Fastest Speed": {'col': 'maxSpeed', 'unit': 'km/h', 'func': 'idxmax', 'factor': 3.6, 'positive_only': True},
        "Peak Power": {'col': 'maxPower', 'unit': 'Watts', 'func': 'idxmax', 'positive_only': True},
        "Longest Run": {'col': 'distance_km', 'unit': 'km', 'func': 'idxmax'},
        "Max Elevation Gain (Run)": {'col': 'elevationGain', 'unit': 'm', 'func': 'idxmax'},
        "Highest VO2 Max (Activity)": {'col': 'vo2MaxValue_activity', 'unit': '', 'func': 'idxmax', 'positive_only': True}
    }
    for pr_label, cfg in general_milestone_config.items():
        col_name = cfg['col']
        if col_name in running_activities.columns:
            # Filter out NaNs and optionally non-positive values
            condition = running_activities[col_name].notna()
            if cfg.get('positive_only', False):
                condition &= (running_activities[col_name] > 0)
            
            valid_data = running_activities[condition].copy()
            if not valid_data.empty:
                best_row = None
                if cfg['func'] == 'idxmax':
                    best_row = valid_data.loc[valid_data[col_name].idxmax()]
                elif cfg['func'] == 'idxmin':
                    best_row = valid_data.loc[valid_data[col_name].idxmin()]
                
                if best_row is not None:
                    prs[pr_label] = get_pr_details(best_row, col_name, cfg['unit'])
                    if 'factor' in cfg and prs[pr_label]['value'] is not None:
                        prs[pr_label]['formatted_value'] = f"{(prs[pr_label]['value'] * cfg['factor']):.2f}"
    return prs
# --- End of calculate_personal_records_detailed ---


# --- Streamlit UI ---
if not st.session_state.get('logged_in', False):
    st.warning("Please log in first using the sidebar on the main page.")
    st.stop()

client = st.session_state.garmin_client
username = st.session_state.current_user
force_refresh_pr = st.sidebar.checkbox("Force Refresh ALL Activity Data for PRs", value=False, key="force_refresh_pr_page",
                                     help="Fetches all historical activities again. Use sparingly.")

personal_records_data = {} # Initialize
if client and username:
    with st.spinner("Calculating Personal Records... This may take some time for the first run or full refresh."):
        personal_records_data = calculate_personal_records_detailed(client, username, force_refresh_pr)

# --- UI DEBUG for personal_records_data dictionary ---
# st.subheader("Debug: `personal_records_data` (Final Dictionary)")
# st.write(personal_records_data) # This will show the entire dictionary in the UI
# --- END UI DEBUG ---

if personal_records_data:
    # --- Section 1: Fastest Times ---
    st.header("Fastest Times")
    st.subheader("Fastest Segments (Garmin-Detected)")
    cols_segment_prs_ui = st.columns(4) 
    segment_pr_keys_to_display_ui = [ 
        "Fastest 1km (Segment)", "Fastest 1 Mile (Segment)", 
        "Fastest 5km (Segment)", "Fastest 10km (Segment)" 
    ]
    for i, key_in_ui in enumerate(segment_pr_keys_to_display_ui):
        pr = personal_records_data.get(key_in_ui) 
        col_to_use = cols_segment_prs_ui[i % len(cols_segment_prs_ui)]
        if pr and pr.get("value") is not None:
            display_pr_metric(col_to_use, key_in_ui.replace(" (Segment)", ""), 
                              pr.get("formatted_value", "N/A"), "", 
                              f"On {pr.get('date', 'N/A')} - '{pr.get('name','N/A')}'")
        else:
            display_pr_metric(col_to_use, key_in_ui.replace(" (Segment)", ""), "N/A")
    st.caption("'(Segment)' times are based on Garmin's fastest split fields within any run.")
    st.markdown("---")

    st.subheader("Fastest Times (Full Run Events)")
    cols_full_run_prs_ui = st.columns(4) 
    full_run_event_keys_to_display_ui = [
        "Fastest 5km (Full Event)", "Fastest 10km (Full Event)",
        "Fastest 15km (Full Event)", "Fastest Half Marathon (Full Event)"
    ]
    for i, key_in_ui in enumerate(full_run_event_keys_to_display_ui):
        pr = personal_records_data.get(key_in_ui)
        col_to_use = cols_full_run_prs_ui[i % len(cols_full_run_prs_ui)]
        if pr and pr.get("value") is not None:
            display_pr_metric(col_to_use, key_in_ui.replace(" (Full Event)", ""), 
                              pr.get("formatted_value", "N/A"), "",
                              f"On {pr.get('date', 'N/A')} - '{pr.get('name','N/A')}'")
        else:
            display_pr_metric(col_to_use, key_in_ui.replace(" (Full Event)", ""), "N/A")
    st.caption("'(Full Event)' times are for activities where the total run distance closely matched the target event distance.")
    st.markdown("---")

    # --- Section 2: Fastest Average Paces by Distance Category ---
    st.header("Fastest Average Paces")
    # distance_categories_config keys are like "(<5km)", "(5-10km)" etc.
    # The PR keys are "Fastest Pace (<5km)", "Fastest Pace (5-10km)"
    # Need to reconstruct these for display iteration or use a fixed list
    ordered_dist_suffixes_for_pace_display = ["(<5km)", "(5-10km)", "(10-15km)", "(15km-HM)", "(HM+)"]
    cols_paces = st.columns(len(ordered_dist_suffixes_for_pace_display))

    for i, dist_suffix in enumerate(ordered_dist_suffixes_for_pace_display):
        key_in_ui = f"Fastest Pace {dist_suffix}" # Construct the key as used in calculation
        pr = personal_records_data.get(key_in_ui)
        label_display = f"Pace {dist_suffix}" # Shorter label for display
        col_to_use = cols_paces[i % len(cols_paces)]
        if pr and pr.get("value") is not None:
            help_text = f"{pr.get('distance_info','')} On {pr.get('date', 'N/A')} - '{pr.get('name','N/A')}'"
            display_pr_metric(col_to_use, label_display, pr.get("formatted_value", "N/A"), pr.get("unit", "min/km"), help_text)
        else:
            display_pr_metric(col_to_use, label_display, "N/A", "min/km")
    st.markdown("---")
    
    # --- Section 3: Running Form & Efficiency ---
    st.header("Running Form & Efficiency")
    ordered_dist_suffixes_for_form_display = ["(<5km)", "(5-10km)", "(10-15km)", "(15km-HM)", "(HM+)"] 
    
    st.subheader("Highest Average Cadence")
    cols_form_cadence = st.columns(len(ordered_dist_suffixes_for_form_display))
    for i, dist_suffix in enumerate(ordered_dist_suffixes_for_form_display):
        key_in_ui = f"Highest Avg Cadence {dist_suffix}"
        pr = personal_records_data.get(key_in_ui)
        label_display = f"Cadence {dist_suffix}"
        col_to_use = cols_form_cadence[i % len(cols_form_cadence)]
        if pr and pr.get("value") is not None:
            help_text = f"{pr.get('distance_info','')} On {pr.get('date', 'N/A')} - '{pr.get('name','N/A')}'"
            display_pr_metric(col_to_use, label_display, pr.get("formatted_value", "N/A"), pr.get("unit", "spm"), help_text)
        else:
            display_pr_metric(col_to_use, label_display, "N/A", "spm")
    st.markdown("---")

    st.subheader("Lowest Average Heart Rate")
    cols_form_hr = st.columns(len(ordered_dist_suffixes_for_form_display))
    for i, dist_suffix in enumerate(ordered_dist_suffixes_for_form_display):
        key_in_ui = f"Lowest Avg HR {dist_suffix}"
        pr = personal_records_data.get(key_in_ui)
        label_display = f"Avg HR {dist_suffix}"
        col_to_use = cols_form_hr[i % len(cols_form_hr)]
        if pr and pr.get("value") is not None:
            help_text = f"{pr.get('distance_info','')} {pr.get('pace_info','')} On {pr.get('date', 'N/A')} - '{pr.get('name','N/A')}'"
            display_pr_metric(col_to_use, label_display, pr.get("formatted_value", "N/A"), pr.get("unit", "bpm"), help_text)
        else:
            display_pr_metric(col_to_use, label_display, "N/A", "bpm")
    
    specific_hr_pace_key = "Efficient HR (~10k Target Pace)" 
    pr_specific_hr = personal_records_data.get(specific_hr_pace_key)
    if pr_specific_hr and pr_specific_hr.get("value") is not None:
        cols_specific_hr = st.columns(1) 
        display_pr_metric(cols_specific_hr[0], specific_hr_pace_key, pr_specific_hr.get("formatted_value", "N/A"), pr_specific_hr.get("unit", "bpm"), 
                          f"{pr_specific_hr.get('distance_info','')} {pr_specific_hr.get('pace_info','')} On {pr_specific_hr.get('date', 'N/A')} - '{pr_specific_hr.get('name','N/A')}'")
    st.markdown("---")

    # --- Section 4: General Running Milestones ---
    st.header("General Running Milestones")
    cols_general_achievements = st.columns(3)
    general_keys_display_order = [
        "Fastest Speed", "Peak Power", "Longest Run", 
        "Max Elevation Gain (Run)", "Highest VO2 Max (Activity)"
    ]
    current_col_idx_gen = 0
    for key_internal in general_keys_display_order:
        pr = personal_records_data.get(key_internal)
        display_label = key_internal 
        if pr and pr.get("value") is not None:
            help_text = f"On {pr.get('date', 'N/A')} - '{pr.get('name','N/A')}'"
            if pr.get("distance_info"): help_text = f"{pr['distance_info']} {help_text}"
            if pr.get("pace_info"): help_text = f"{pr['pace_info']} {help_text}"
            display_pr_metric(cols_general_achievements[current_col_idx_gen % len(cols_general_achievements)], 
                              display_label, pr.get("formatted_value", "N/A"), pr.get("unit", ""), help_text)
            current_col_idx_gen +=1
        else:
            display_pr_metric(cols_general_achievements[current_col_idx_gen % len(cols_general_achievements)], display_label, "N/A", "")
            
    st.markdown("---")
    st.info("Future enhancements could include PRs from within longer runs by analyzing detailed split/segment data.")

elif client and username: # personal_records_data is empty but client and username exist
    st.info("No personal records were calculated. This might be due to no running activities in your history, or an issue fetching/processing data.")
    if not force_refresh_pr:
        st.warning("Consider using the 'Force Refresh ALL Activity Data for PRs' option in the sidebar if you have recent running activities.")
else: # Not logged in
    st.info("Log in to calculate and view personal records.")