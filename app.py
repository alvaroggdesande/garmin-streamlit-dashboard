import streamlit as st
from datetime import date, timedelta
from utils import garmin_utils # Assuming garmin_utils.py is in utils folder


st.set_page_config(layout="wide", page_title="Garmin Performance Dashboard")

st.sidebar.title("Garmin Dashboard")

# --- User Authentication ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'garmin_client' not in st.session_state:
    st.session_state.garmin_client = None
if 'current_user' not in st.session_state:
    st.session_state.current_user = None

username_input = st.sidebar.text_input("Garmin Email", key="garmin_email_main")
password_input = st.sidebar.text_input("Garmin Password", type="password", key="garmin_password_main")

if st.sidebar.button("Login", key="login_button_main"):
    if username_input and password_input:
        with st.spinner("Attempting to log in to Garmin Connect..."):
            client = garmin_utils.login_to_garmin(username_input, password_input)
        if client:
            st.session_state.garmin_client = client
            st.session_state.logged_in = True
            st.session_state.current_user = username_input
            st.sidebar.success(f"Logged in as {username_input}")
            # Force rerun to update UI reflecting login status, especially for pages
            st.experimental_rerun() 
        else:
            st.sidebar.error("Login failed. Please check credentials or Garmin Connect status.")
            st.session_state.logged_in = False
            st.session_state.garmin_client = None
            st.session_state.current_user = None
    else:
        st.sidebar.warning("Please enter both email and password.")

if st.session_state.logged_in:
    st.sidebar.markdown(f"**User:** {st.session_state.current_user}")
    if st.sidebar.button("Logout", key="logout_button_main"):
        st.session_state.logged_in = False
        st.session_state.garmin_client = None # Client is cached by @st.cache_resource, but clear session state
        st.session_state.current_user = None
        st.sidebar.info("Logged out.")
        st.experimental_rerun()

    st.sidebar.markdown("---")
    st.sidebar.header("Global Filters")
    
    # Date Range Selection
    # Default to last 30 days
    today = date.today()
    default_start_date = today - timedelta(days=30)
    default_end_date = today
    
    if 'date_range_start' not in st.session_state:
        st.session_state.date_range_start = default_start_date
    if 'date_range_end' not in st.session_state:
        st.session_state.date_range_end = default_end_date

    col1, col2 = st.sidebar.columns(2)
    with col1:
        st.session_state.date_range_start = st.date_input(
            "Start Date", 
            value=st.session_state.date_range_start, 
            max_value=today,
            key="global_start_date"
        )
    with col2:
        st.session_state.date_range_end = st.date_input(
            "End Date", 
            value=st.session_state.date_range_end, 
            min_value=st.session_state.date_range_start, 
            max_value=today,
            key="global_end_date"
        )
    
    st.session_state.force_refresh = st.sidebar.checkbox("Force Refresh Data from Garmin", value=False, key="force_refresh_main")

    st.sidebar.markdown("---")
    st.sidebar.info("Navigate to different views using the pages above.")

    # Display a welcome message or instructions on the main app page
    st.title("Welcome to your Garmin Performance Dashboard!")
    st.markdown("""
    Please log in using the sidebar to fetch and display your Garmin Connect data.
    Once logged in, you can:
    - Select a date range for analysis.
    - Navigate through different views like Health Overview, Running Performance, and Training Load.
    - Opt to force refresh data if you suspect cached data is stale (use sparingly).
    """)
    if not st.session_state.logged_in:
        st.warning("You are not logged in. Please use the sidebar.")

else:
    st.info("Please log in using the sidebar to access the dashboard features.")

# The rest of the content will be in the 'pages/' directory files.
# This app.py primarily handles login and global settings for the sidebar.