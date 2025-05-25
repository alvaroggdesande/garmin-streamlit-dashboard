import streamlit as st
from garminconnect import (
    Garmin,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
    GarminConnectAuthenticationError,
)
import pandas as pd
from datetime import datetime, date, timedelta
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DATA_DIR = "data" # Ensure this directory exists

# --- Authentication & Client Management ---
@st.cache_resource(ttl=3600) # Cache the client object for 1 hour
def login_to_garmin(username, password):
    """
    Logs into Garmin Connect and returns a Garmin client object.
    Caches the client object to avoid re-login on every script run.
    """
    try:
        # For testing, you might need to provide a full path to a token store
        # or handle it more robustly if deploying.
        # For local dev, garminconnect might create a .garminconnect file
        client = Garmin(username, password)
        client.login()
        logger.info(f"Successfully logged in as {username}")
        return client
    except (GarminConnectConnectionError, GarminConnectTooManyRequestsError, GarminConnectAuthenticationError) as e:
        logger.error(f"Garmin login failed for {username}: {e}")
        st.error(f"Login Failed: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred during Garmin login: {e}")
        st.error(f"An unexpected error occurred: {e}")
        return None

# --- Data Fetching & Caching ---
def get_user_data_path(username, data_type, start_date_str, end_date_str):
    """Generates a unique path for cached data."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    user_dir = os.path.join(DATA_DIR, username.replace("@", "_").replace(".", "_")) # Sanitize username for path
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)
    return os.path.join(user_dir, f"{data_type}_{start_date_str}_to_{end_date_str}.parquet")

def fetch_data_with_cache(client, username, data_type, fetch_function, start_date, end_date=None, force_refresh=False):
    """
    Generic function to fetch data, using a Parquet file cache.
    'fetch_function' is the actual Garmin API call.
    """
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d") if end_date else start_date_str
    
    cache_path = get_user_data_path(username, data_type, start_date_str, end_date_str)

    if not force_refresh and os.path.exists(cache_path):
        try:
            logger.info(f"Loading {data_type} for {username} from cache: {cache_path}")
            return pd.read_parquet(cache_path)
        except Exception as e:
            logger.warning(f"Failed to load {data_type} from cache {cache_path}: {e}. Fetching new data.")

    logger.info(f"Fetching {data_type} for {username} from Garmin API for range {start_date_str} to {end_date_str}")
    try:
        if data_type in ["hrv", "sleep", "body_battery"]: # These typically take a single date or a range
            if end_date: # Assuming functions that take start_date, end_date
                 raw_data = fetch_function(start_date.isoformat(), end_date.isoformat())
            else: # Assuming functions that take a single date
                 raw_data = fetch_function(start_date.isoformat())
        elif data_type == "activities":
            # get_activities takes start_index, limit. We need to fetch in chunks or get all for a date range.
            # The garminconnect library's get_activities(start_date, end_date) simplifies this
            raw_data = client.get_activities_by_date(start_date.isoformat(), end_date.isoformat())
        elif data_type == "daily_summary": # For RHR etc. - usually fetched per day
            # This might need to be looped for a date range if fetching daily summaries
            all_daily_data = []
            current_date = start_date
            while current_date <= end_date:
                daily_data = fetch_function(current_date.isoformat()) # e.g., client.get_stats(date)
                if daily_data:
                    # Add date to make it easier to create a DataFrame later
                    if isinstance(daily_data, dict):
                        daily_data['date'] = current_date.isoformat()
                    all_daily_data.append(daily_data)
                current_date += timedelta(days=1)
            raw_data = all_daily_data
        else:
            # Default for functions that take start_date, end_date strings
            raw_data = fetch_function(start_date.isoformat(), end_date.isoformat())

        if raw_data:
            df = pd.DataFrame(raw_data) # May need further processing based on actual structure
            df.to_parquet(cache_path, index=False)
            logger.info(f"Saved {data_type} for {username} to cache: {cache_path}")
            return df
        else:
            logger.info(f"No {data_type} data found for {username} for the period.")
            # Save an empty DataFrame to cache to avoid re-fetching if truly no data
            pd.DataFrame().to_parquet(cache_path, index=False)
            return pd.DataFrame()

    except Exception as e:
        logger.error(f"Error fetching {data_type} for {username}: {e}")
        st.warning(f"Could not fetch {data_type}: {e}")
        return pd.DataFrame() # Return empty DataFrame on error

def get_activities(client, username, start_date, end_date, force_refresh=False):
    """Fetches activities for a date range."""
    # The client.get_activities_by_date directly uses start and end dates.
    return fetch_data_with_cache(client, username, "activities",
                                 lambda sd, ed: client.get_activities_by_date(sd, ed),
                                 start_date, end_date, force_refresh)

def get_hrv_data(client, username, start_date, end_date, force_refresh=False):
    """Fetches HRV data for a date range."""
    # garminconnect fetches HRV day by day, so we need to loop if a range is given
    all_hrv_data = []
    current_date = start_date
    cache_key_start_date_str = start_date.strftime("%Y-%m-%d")
    cache_key_end_date_str = end_date.strftime("%Y-%m-%d")
    cache_path = get_user_data_path(username, "hrv", cache_key_start_date_str, cache_key_end_date_str)

    if not force_refresh and os.path.exists(cache_path):
        try:
            logger.info(f"Loading HRV for {username} from cache: {cache_path}")
            return pd.read_parquet(cache_path)
        except Exception as e:
            logger.warning(f"Failed to load HRV from cache {cache_path}: {e}. Fetching new data.")

    logger.info(f"Fetching HRV for {username} from Garmin API for range {cache_key_start_date_str} to {cache_key_end_date_str}")
    while current_date <= end_date:
        try:
            hrv_day_data = client.get_hrv_data(current_date.isoformat()) # Get HRV for one day
            if hrv_day_data and hrv_day_data.get('hrvSummaries'):
                # Add date to each summary for easier DataFrame creation
                for summary in hrv_day_data['hrvSummaries']:
                    summary['date'] = current_date.isoformat()
                all_hrv_data.extend(hrv_day_data['hrvSummaries'])
        except Exception as e:
            logger.warning(f"Could not fetch HRV for {current_date.isoformat()}: {e}")
        current_date += timedelta(days=1)

    logger.info(f"Raw HRV data fetched before DataFrame creation: {all_hrv_data}")

    if all_hrv_data:
        df = pd.DataFrame(all_hrv_data)
        df.to_parquet(cache_path, index=False)
        logger.info(f"Saved HRV for {username} to cache: {cache_path}")
        return df
    else:
        logger.info(f"No HRV data found for {username} for the period.")
        pd.DataFrame().to_parquet(cache_path, index=False)
        return pd.DataFrame()


def get_sleep_data(client, username, start_date, end_date, force_refresh=False):
    """Fetches sleep data for a date range."""
    # Similar to HRV, sleep data might be fetched day by day or via a range method if available
    # Assuming client.get_sleep_data(date_str) exists and fetches for one day
    all_sleep_data = []
    current_date = start_date
    cache_key_start_date_str = start_date.strftime("%Y-%m-%d")
    cache_key_end_date_str = end_date.strftime("%Y-%m-%d")
    cache_path = get_user_data_path(username, "sleep", cache_key_start_date_str, cache_key_end_date_str)

    if not force_refresh and os.path.exists(cache_path):
        try:
            logger.info(f"Loading sleep data for {username} from cache: {cache_path}")
            return pd.read_parquet(cache_path)
        except Exception as e:
            logger.warning(f"Failed to load sleep data from cache {cache_path}: {e}. Fetching new data.")

    logger.info(f"Fetching sleep data for {username} from Garmin API for range {cache_key_start_date_str} to {cache_key_end_date_str}")

    # The library provides get_sleep_data(api. σήμερα().isoformat()) for one day
    # And get_daily_sleep_data(start_date.isoformat(), end_date.isoformat()) for a range
    try:
        raw_sleep_data = client.get_daily_sleep_data(start_date.isoformat(), end_date.isoformat())

        logger.info(f"Raw sleep data fetched: {raw_sleep_data}")

        if raw_sleep_data:
            # The structure can be complex, often a list of sleep entries
            # Each entry might have 'dailySleepDTO' and 'sleepLevels'
            # We'll try to flatten it a bit or just store the DTOs
            processed_sleep_list = []
            for entry in raw_sleep_data:
                dto = entry.get('dailySleepDTO', {})
                dto['sleepStartTimestampGMT'] = entry.get('sleepStartTimestampGMT') # Capture more fields if needed
                dto['sleepEndTimestampGMT'] = entry.get('sleepEndTimestampGMT')
                # You might want to process sleepLevelsMap here if needed
                processed_sleep_list.append(dto)
            all_sleep_data = processed_sleep_list
    except Exception as e:
        logger.error(f"Error fetching sleep data range for {username}: {e}")


    if all_sleep_data:

        logger.info(f"Processed sleep list before DataFrame: {all_sleep_data}")

        df = pd.DataFrame(all_sleep_data)
        df.to_parquet(cache_path, index=False)
        logger.info(f"Saved sleep data for {username} to cache: {cache_path}")
        return df
    else:
        logger.info(f"No sleep data found for {username} for the period.")
        pd.DataFrame().to_parquet(cache_path, index=False)
        return pd.DataFrame()

def get_daily_summaries(client, username, start_date, end_date, force_refresh=False):
    """Fetches daily summary stats (contains RHR) for a date range."""
    # client.get_stats(date_str) gets daily stats
    return fetch_data_with_cache(client, username, "daily_summary",
                                 lambda d: client.get_stats(d), # This lambda is for the single date case in fetch_data_with_cache
                                 start_date, end_date, force_refresh)

def get_body_battery(client, username, start_date, end_date, force_refresh=False):
    """Fetches body battery data."""
    # client.get_body_battery([dates])
    all_bb_data = []
    current_date = start_date
    cache_key_start_date_str = start_date.strftime("%Y-%m-%d")
    cache_key_end_date_str = end_date.strftime("%Y-%m-%d")
    cache_path = get_user_data_path(username, "body_battery", cache_key_start_date_str, cache_key_end_date_str)

    if not force_refresh and os.path.exists(cache_path):
        try:
            logger.info(f"Loading body battery for {username} from cache: {cache_path}")
            return pd.read_parquet(cache_path)
        except Exception as e:
            logger.warning(f"Failed to load body battery from cache {cache_path}: {e}. Fetching new data.")

    logger.info(f"Fetching body battery for {username} from Garmin API for range {cache_key_start_date_str} to {cache_key_end_date_str}")
    
    dates_list = []
    temp_date = start_date
    while temp_date <= end_date:
        dates_list.append(temp_date.isoformat())
        temp_date += timedelta(days=1)

    if dates_list:
        try:
            bb_data_list = client.get_body_battery(dates_list) # Pass list of date strings
            if bb_data_list:
                # Flatten the data if it's a list of lists/dicts per day
                for day_data in bb_data_list:
                    if isinstance(day_data, list): # It often returns a list of readings for the day
                        all_bb_data.extend(day_data)
                    elif isinstance(day_data, dict): # Or a single summary
                        all_bb_data.append(day_data)

        except Exception as e:
            logger.error(f"Error fetching body battery for {username}: {e}")

    if all_bb_data:
        df = pd.DataFrame(all_bb_data)
        # Add a proper date column if not present or needs conversion from timestamp
        if 'chargedDate' in df.columns: # Example column name
             df['date'] = pd.to_datetime(df['chargedDate']).dt.date
        elif 'epochTimestamp' in df.columns:
             df['date'] = pd.to_datetime(df['epochTimestamp'], unit='ms').dt.date

        df.to_parquet(cache_path, index=False)
        logger.info(f"Saved body battery for {username} to cache: {cache_path}")
        return df
    else:
        logger.info(f"No body battery data found for {username} for the period.")
        pd.DataFrame().to_parquet(cache_path, index=False)
        return pd.DataFrame()


# Note: get_training_load_data - Garmin Connect API (via python-garminconnect)
# might not have a direct aggregated "training load" endpoint like Polar does.
# Training Load/Status is often a derived metric shown on the device/app.
# You might get "Training Effect" per activity, or "Load Focus".
# You might need to calculate custom training load in data_processing.py
# based on activity data (duration, HR, type).
# Check `client.get_training_status(date_str)` for potential insights.

if __name__ == '__main__':
    # Example Usage (requires credentials - be careful)
    # Replace with your actual credentials or use environment variables
    GARMIN_EMAIL = os.getenv("GARMIN_EMAIL")
    GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD")

    if not GARMIN_EMAIL or not GARMIN_PASSWORD:
        print("Please set GARMIN_EMAIL and GARMIN_PASSWORD environment variables for testing.")
    else:
        print("Attempting to log in (this will create a client object)...")
        client = login_to_garmin(GARMIN_EMAIL, GARMIN_PASSWORD) # Function is cached
        if client:
            print("Login successful.")
            test_username = GARMIN_EMAIL # Use the email as username for cache path
            today = date.today()
            start_test_date = today - timedelta(days=7)
            end_test_date = today - timedelta(days=1) # Fetch up to yesterday

            print(f"\nFetching activities for {test_username} from {start_test_date} to {end_test_date}...")
            activities = get_activities(client, test_username, start_test_date, end_test_date)
            if not activities.empty:
                print(f"Fetched {len(activities)} activities. Columns: {activities.columns.tolist()}")
                print(activities.head())
            else:
                print("No activities found or error fetching.")

            print(f"\nFetching HRV data for {test_username} from {start_test_date} to {end_test_date}...")
            hrv = get_hrv_data(client, test_username, start_test_date, end_test_date)
            if not hrv.empty:
                print(f"Fetched {len(hrv)} HRV entries. Columns: {hrv.columns.tolist()}")
                print(hrv.head())
            else:
                print("No HRV data found or error fetching.")

            print(f"\nFetching sleep data for {test_username} from {start_test_date} to {end_test_date}...")
            sleep = get_sleep_data(client, test_username, start_test_date, end_test_date)
            if not sleep.empty:
                print(f"Fetched {len(sleep)} sleep entries. Columns: {sleep.columns.tolist()}")
                print(sleep.head())
            else:
                print("No sleep data found or error fetching.")

            print(f"\nFetching daily summaries for {test_username} from {start_test_date} to {end_test_date}...")
            daily_summaries = get_daily_summaries(client, test_username, start_test_date, end_test_date)
            if not daily_summaries.empty:
                print(f"Fetched {len(daily_summaries)} daily summary entries. Columns: {daily_summaries.columns.tolist()}")
                if 'restingHeartRate' in daily_summaries.columns:
                    print(daily_summaries[['date', 'restingHeartRate']].head())
            else:
                print("No daily summaries found or error fetching.")
            
            print(f"\nFetching body battery for {test_username} from {start_test_date} to {end_test_date}...")
            bb = get_body_battery(client, test_username, start_test_date, end_test_date)
            if not bb.empty:
                print(f"Fetched {len(bb)} body battery entries. Columns: {bb.columns.tolist()}")
                print(bb.head())
            else:
                print("No body battery data or error fetching.")

        else:
            print("Login failed. Cannot proceed with tests.")