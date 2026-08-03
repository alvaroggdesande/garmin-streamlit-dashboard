# Garmin Streamlit Dashboard

A Streamlit application to visualize and analyze your Garmin Connect fitness and health data.

## Features (Planned/Implemented)

*   Health Overview (HRV, Sleep, RHR)
*   Running Performance Analysis (Aerobic Efficiency, HR Zones)
*   Customizable Training Load Calculation

## Setup

1.  **Clone the repository (or download the source):**
    ```bash
    git clone https://github.com/YourGitHubUsername/garmin-streamlit-dashboard.git
    cd garmin-streamlit-dashboard
    ```

2.  **Create and activate a Python virtual environment:**
    ```bash
    # On macOS/Linux
    python3 -m venv venv_garmin
    source venv_garmin/bin/activate

    # On Windows
    # python -m venv venv_garmin
    # venv_garmin\Scripts\activate.bat
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Create necessary directories:**
    Make sure a `data/` directory exists in the project root for caching fetched data:
    ```bash
    mkdir data
    ```

## Running the Application

1.  Ensure your virtual environment is activated.
2.  Run the Streamlit app:
    ```bash
    streamlit run app.py
    ```
3.  Open your web browser and go to the local URL provided by Streamlit (usually `http://localhost:8501`).
4.  **Log in.** If a durable token secret is set (see below), the app auto-authenticates on load with no form. Otherwise, expand **Advanced / local login** in the sidebar and enter your Garmin Connect credentials.

## Deploying to Streamlit Community Cloud (token persistence)

The dashboard is designed to run on Streamlit Community Cloud. On Cloud, the app's IP is **shared across many apps**, and running the full Garmin SSO login on every cold start gets **rate-limited (HTTP 429)**. To avoid that, the app resumes from a **pre-minted OAuth token** stored in a Streamlit secret instead of logging in fresh each time.

**How it works:**

*   `login_to_garmin` is **token-first**: given a token blob it resumes the session (`garth` loads, no SSO handshake); with no token it falls back to a username/password login.
*   `app.py` reads the token from the `garmin_token_base64` secret and auto-logs-in. A manual login form remains as a fallback (behind the **Advanced / local login** expander).

**One-time setup — mint the token, then paste it into the Cloud secret:**

1.  **Mint the token from your home machine** (not from Cloud — it must be a clean, non-rate-limited IP). Provide credentials via env vars or a local `.env` file, then run the helper:
    ```powershell
    # PowerShell (Windows)
    $env:GARMIN_EMAIL="you@example.com"; $env:GARMIN_PASSWORD="your-password"
    python scripts\mint_garmin_token.py
    ```
    The script prints a `garmin_token_base64 = "..."` line. It **never prints your password** and **never writes the token to disk**.

2.  **Add the token to Streamlit Cloud secrets** — this is in the **Cloud management console**, *not* the in-app Settings menu (which only has theme/wide-mode). Go to **share.streamlit.io** → your app → **⋮ → Settings → Secrets** (or **Manage app → ⋮ → Settings → Secrets** from the running app), and paste:
    ```toml
    garmin_token_base64 = "<the-blob-from-step-1>"
    ```
    Save; the app reboots and auto-authenticates.

**What to expect / maintenance:**

*   The token grants roughly **~1 year** of full-account access — **treat it like a password**. It lives only in the Cloud secret (never committed, never on disk).
*   When it **expires** or Garmin **rate-limits** it, the app shows a friendly message in the sidebar. Fix it by **re-running `scripts/mint_garmin_token.py` from home** and updating the `garmin_token_base64` secret — no code change needed.
*   For **local development** you don't need the token at all — just use the Advanced / local login form.

## Important Notes

*   **Credentials & token:** You authenticate either with your Garmin Connect credentials (via the login form, used only for the duration of your session) or with a pre-minted OAuth token stored in the `garmin_token_base64` Streamlit secret (see *Deploying to Streamlit Community Cloud* above). Neither credentials nor the token are ever committed to Git or written to disk by the app; the token lives only in the Cloud secret. Both grant full account access — handle them like passwords.
*   **Data Caching:** Fetched data from Garmin is cached locally in the `data/` directory as Parquet files to speed up subsequent loads and reduce API calls. **This `data/` directory is ignored by Git (`.gitignore`) and should NOT be committed, as it will contain your personal health data.**
*   **`python-garminconnect`:** This project uses an unofficial library to interact with Garmin Connect. Garmin may change its API at any time, which could break functionality.

## Disclaimer

This is a personal project. Handle your personal data and credentials with care. The author is not responsible for any issues arising from the use of this software.