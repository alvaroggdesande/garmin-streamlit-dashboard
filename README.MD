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
4.  Log in with your Garmin Connect credentials via the sidebar.

## Important Notes

*   **Credentials:** This application requires you to enter your Garmin Connect credentials. These are used to log in via the `python-garminconnect` library and are stored in the Streamlit session state *only for the duration of your session* if you use the login form. They are not persistently stored by the application in a way that's committed to Git.
*   **Data Caching:** Fetched data from Garmin is cached locally in the `data/` directory as Parquet files to speed up subsequent loads and reduce API calls. **This `data/` directory is ignored by Git (`.gitignore`) and should NOT be committed, as it will contain your personal health data.**
*   **`python-garminconnect`:** This project uses an unofficial library to interact with Garmin Connect. Garmin may change its API at any time, which could break functionality.

## Disclaimer

This is a personal project. Handle your personal data and credentials with care. The author is not responsible for any issues arising from the use of this software.