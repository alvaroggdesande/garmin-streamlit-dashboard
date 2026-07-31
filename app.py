import streamlit as st
from datetime import date, timedelta
from utils import garmin_utils

st.set_page_config(layout="wide", page_title="Garmin Performance Dashboard")
st.sidebar.title("Garmin Dashboard")

# --- Session init ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'garmin_client' not in st.session_state:
    st.session_state.garmin_client = None
if 'current_user' not in st.session_state:
    st.session_state.current_user = None

# --- Durable owner token from Streamlit secrets (persists across Cloud cold starts) ---
try:
    _token_blob = st.secrets.get("garmin_token_base64", None)
except Exception:
    _token_blob = None

# --- Auto-login from the secret token (resume; no SSO handshake -> avoids the 429 login flow) ---
if not st.session_state.logged_in and _token_blob:
    try:
        client = garmin_utils.login_to_garmin(token_blob=_token_blob)
        st.session_state.garmin_client = client
        st.session_state.logged_in = True
        st.session_state.current_user = "owner"
    except Exception as e:
        kind = garmin_utils.classify_login_error(e)
        if kind == "rate_limited":
            st.sidebar.error("Garmin is rate-limiting the shared Streamlit IP. Re-mint your token locally and update the `garmin_token_base64` secret, or try again later.")
        elif kind == "auth":
            st.sidebar.error("Saved Garmin token is invalid or expired. Re-mint it and update the secret.")
        else:
            st.sidebar.error(f"Token login failed: {e}")

# --- Fallback manual login (local dev / token expiry) ---
if not st.session_state.logged_in:
    with st.sidebar.expander("Advanced / local login", expanded=not _token_blob):
        username_input = st.text_input("Garmin Email", key="garmin_email_main")
        password_input = st.text_input("Garmin Password", type="password", key="garmin_password_main")
        if st.button("Login", key="login_button_main"):
            if username_input and password_input:
                try:
                    with st.spinner("Logging in to Garmin Connect..."):
                        client = garmin_utils.login_to_garmin(username=username_input, password=password_input)
                    st.session_state.garmin_client = client
                    st.session_state.logged_in = True
                    st.session_state.current_user = username_input
                    st.rerun()
                except Exception as e:
                    kind = garmin_utils.classify_login_error(e)
                    if kind == "rate_limited":
                        st.error("Garmin is rate-limiting this IP (429). Wait ~1h, or mint a token locally.")
                    elif kind == "auth":
                        st.error("Login failed: check your credentials.")
                    else:
                        st.error(f"Login failed: {e}")
            else:
                st.warning("Please enter both email and password.")

# --- Logged-in UI ---
if st.session_state.logged_in:
    st.sidebar.markdown(f"**User:** {st.session_state.current_user}")
    if st.sidebar.button("Logout", key="logout_button_main"):
        st.session_state.logged_in = False
        st.session_state.garmin_client = None
        st.session_state.current_user = None
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.header("Global Filters")

    today = date.today()
    if 'date_range_start' not in st.session_state:
        st.session_state.date_range_start = today - timedelta(days=30)
    if 'date_range_end' not in st.session_state:
        st.session_state.date_range_end = today

    col1, col2 = st.sidebar.columns(2)
    with col1:
        st.session_state.date_range_start = st.date_input(
            "Start Date", value=st.session_state.date_range_start,
            max_value=today, key="global_start_date")
    with col2:
        st.session_state.date_range_end = st.date_input(
            "End Date", value=st.session_state.date_range_end,
            min_value=st.session_state.date_range_start, max_value=today,
            key="global_end_date")

    st.session_state.force_refresh = st.sidebar.checkbox(
        "Force Refresh Data from Garmin", value=False, key="force_refresh_main")

    st.sidebar.markdown("---")
    st.sidebar.info("Navigate to different views using the pages above.")

    st.title("Welcome to your Garmin Performance Dashboard!")
    st.markdown("""
    You're logged in. Use the sidebar to pick a date range, then explore the pages:
    Health Overview, Running Performance, Training Load, Correlations, Readiness & Performance, and Personal Records.
    """)
else:
    st.info("Not logged in. If you're the owner, set the `garmin_token_base64` secret; otherwise expand **Advanced / local login** in the sidebar.")
