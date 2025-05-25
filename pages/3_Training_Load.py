import streamlit as st
from datetime import date, timedelta
from utils import garmin_utils, data_processing, plotting_utils
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide", page_title="Training Load")
st.title("🏋️ Training Load Analysis")

if not st.session_state.get('logged_in', False):
    st.warning("Please log in first using the sidebar on the main page.")
    st.stop()

client = st.session_state.garmin_client
username = st.session_state.current_user
start_date = st.session_state.get('date_range_start', date.today() - timedelta(days=30))
end_date = st.session_state.get('date_range_end', date.today())
force_refresh = st.session_state.get('force_refresh', False)

if client and username:
    st.markdown(f"Displaying data for **{username}** from **{start_date.strftime('%Y-%m-%d')}** to **{end_date.strftime('%Y-%m-%d')}**.")

    with st.spinner("Loading activity data for training load calculation..."):
        activities_raw_df = garmin_utils.get_activities(client, username, start_date, end_date, force_refresh)
        activities_processed_df = data_processing.process_activities_df(activities_raw_df)

    if not activities_processed_df.empty:
        st.subheader("Custom Training Load")
        
        # Option to select load calculation method
        load_method = st.selectbox(
            "Select Load Calculation Method:",
            options=['aerobic_te_sum', 'trimp_edwards', 'duration_hr_basic'],
            index=0, # Default to aerobic_te_sum
            help="Aerobic TE Sum: Sums Garmin's Aerobic Training Effect daily. TRIMP Edwards: Uses time in HR zones. Duration*HR: Basic product of duration and average HR."
        )

        daily_load_df = data_processing.calculate_custom_training_load(activities_processed_df, method=load_method)
        
        if not daily_load_df.empty:
            fig_load = plotting_utils.plot_training_load(daily_load_df, load_col='custom_load')
            st.plotly_chart(fig_load, use_container_width=True)

            # You could add rolling averages (e.g., 7-day "acute", 28/42-day "chronic")
            # and calculate Acute:Chronic Workload Ratio (ACWR)
            if 'custom_load' in daily_load_df.columns:
                daily_load_df = daily_load_df.sort_values(by='date').set_index('date')
                daily_load_df['acute_load_7d'] = daily_load_df['custom_load'].rolling(window=7, min_periods=1).mean()
                daily_load_df['chronic_load_28d'] = daily_load_df['custom_load'].rolling(window=28, min_periods=7).mean() # min_periods to show earlier
                daily_load_df['acwr'] = (daily_load_df['acute_load_7d'] / daily_load_df['chronic_load_28d']).fillna(0)
                
                fig_acwr = px.line(daily_load_df.reset_index(), x='date', y=['acute_load_7d', 'chronic_load_28d', 'acwr'],
                                   title="Training Load (Acute, Chronic) & ACWR",
                                   labels={'value': "Load / Ratio"}, markers=False)
                # Add range indicators for ACWR (e.g., 0.8-1.3 is often considered optimal)
                fig_acwr.add_hrect(y0=0.8, y1=1.3, line_width=0, fillcolor="green", opacity=0.1, 
                                   annotation_text="Optimal ACWR Zone", annotation_position="top left")
                fig_acwr.add_hrect(y0=1.31, y1=max(2, daily_load_df['acwr'].max() if not daily_load_df['acwr'].empty else 2), 
                                   line_width=0, fillcolor="red", opacity=0.1,
                                   annotation_text="High Risk ACWR Zone", annotation_position="top left")
                st.plotly_chart(fig_acwr, use_container_width=True)

        else:
            st.info("Could not calculate training load. Ensure activities have necessary data (HR, duration, zones).")

        st.subheader("Garmin's Training Effect (Activity Based)")
        if 'aerobicTrainingEffect' in activities_processed_df.columns:
            te_data = activities_processed_df[['date', 'activityName', 'aerobicTrainingEffect', 'anaerobicTrainingEffect']].dropna(
                subset=['aerobicTrainingEffect']
            ).sort_values(by='date', ascending=False)
            st.write("Recent Training Effect Scores:")
            st.dataframe(te_data.head(15))
        
        # You might also fetch `client.get_training_status(date_str)` if you want to see Garmin's view on load.
        # This would require another fetch in garmin_utils and processing.

    else:
        st.info("No activity data found to calculate training load.")
else:
    st.info("Dashboard content will appear here once you are logged in and data is fetched.")