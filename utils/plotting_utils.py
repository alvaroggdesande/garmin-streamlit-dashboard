import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

# --- Existing plot_hrv_trend, plot_sleep_hrv_correlation from before ---
# (Make sure plot_hrv_trend correctly handles potentially empty daily_summary_for_plot or sleep_for_plot)
def plot_hrv_trend(hrv_df, daily_summary_df=None, sleep_df=None):
    if hrv_df.empty or 'date' not in hrv_df.columns or 'hrv_nightly_avg' not in hrv_df.columns: # Check your HRV column name
        return go.Figure().update_layout(title="No HRV Data to Display")

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(x=hrv_df['date'], y=hrv_df['hrv_nightly_avg'], name="HRV (Nightly Avg ms)", mode='lines+markers'),
        secondary_y=False,
    )
    if daily_summary_df is not None and not daily_summary_df.empty and \
       'date' in daily_summary_df.columns and 'restingHeartRate_daily' in daily_summary_df.columns:
        rhr_data = daily_summary_df.dropna(subset=['restingHeartRate_daily'])
        fig.add_trace(
            go.Scatter(x=rhr_data['date'], y=rhr_data['restingHeartRate_daily'], name="Resting HR (bpm)", mode='lines+markers'),
            secondary_y=True,
        )
    if sleep_df is not None and not sleep_df.empty and \
       'date_sleep' in sleep_df.columns and 'duration_minutes_sleep' in sleep_df.columns: # Matches your rename
        sleep_data_plot = sleep_df.dropna(subset=['duration_minutes_sleep'])
        sleep_data_plot['sleep_hours_plot'] = sleep_data_plot['duration_minutes_sleep'] / 60
        fig.add_trace(
            go.Scatter(x=sleep_data_plot['date_sleep'], y=sleep_data_plot['sleep_hours_plot'], 
                       name="Sleep Duration (hours)", mode='lines+markers', line=dict(dash='dash')),
            secondary_y=True,
        )
    fig.update_layout(title_text="HRV Nightly Average & Related Metrics", hovermode="x unified")
    fig.update_xaxes(title_text="Date")
    fig.update_yaxes(title_text="<b>HRV (ms)</b>", secondary_y=False)
    fig.update_yaxes(title_text="<b>RHR (bpm) / Sleep (hours)</b>", secondary_y=True, showgrid=False)
    return fig

def plot_sleep_hrv_correlation(merged_df, sleep_metric_col='duration_minutes_sleep', hrv_metric_col='hrv_nightly_avg_hrv'):
    if merged_df.empty or sleep_metric_col not in merged_df.columns or hrv_metric_col not in merged_df.columns:
        return go.Figure().update_layout(title="Insufficient Data for Sleep-HRV Correlation")
    plot_df = merged_df[[sleep_metric_col, hrv_metric_col]].dropna()
    if plot_df.empty: return go.Figure().update_layout(title="No Overlapping Sleep-HRV Data")
    fig = px.scatter(plot_df, x=sleep_metric_col, y=hrv_metric_col,
                     title=f"Correlation: {sleep_metric_col.replace('_sleep','')} vs. {hrv_metric_col.replace('_hrv','')}",
                     trendline="ols",
                     labels={
                         sleep_metric_col: sleep_metric_col.replace('_sleep','').replace('_',' ').title(),
                         hrv_metric_col: hrv_metric_col.replace('_hrv','').replace('_',' ').title()
                     })
    return fig
# ------------------------------------------------------------------------


def plot_rhr_and_stress(daily_df):
    if daily_df.empty or 'restingHeartRate' not in daily_df.columns:
        return go.Figure().update_layout(title="RHR data not available.")
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=daily_df['calendarDate'], y=daily_df['restingHeartRate'],
        name='Resting HR (bpm)', mode='lines+markers', yaxis='y1'
    ))
    if 'lastSevenDaysAvgRestingHeartRate' in daily_df.columns:
        fig.add_trace(go.Scatter(
            x=daily_df['calendarDate'], y=daily_df['lastSevenDaysAvgRestingHeartRate'],
            name='7-Day Avg RHR (bpm)', mode='lines', line=dict(dash='dot'), yaxis='y1'
        ))
    if 'averageStressLevel' in daily_df.columns:
        stress_plot_data = daily_df[daily_df['averageStressLevel'] != -1].copy() # Filter out -1 if it means no data
        fig.add_trace(go.Scatter(
            x=stress_plot_data['calendarDate'], y=stress_plot_data['averageStressLevel'],
            name='Average Stress Level', mode='lines+markers', yaxis='y2',
            line=dict(color='rgba(255,165,0,0.7)')
        ))
    fig.update_layout(
        xaxis_title='Date',
        yaxis=dict(title='Heart Rate (bpm)'),
        yaxis2=dict(title='Average Stress Level', overlaying='y', side='right', showgrid=False),
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        hovermode="x unified",
        title="Resting Heart Rate & Average Stress"
    )
    return fig

def plot_stress_distribution(daily_df):
    if daily_df.empty:
        return go.Figure().update_layout(title="Stress data not available.")
    
    stress_duration_cols_minutes = [
        'lowStressMinutes', 'mediumStressMinutes', 'highStressMinutes',
        'restStressMinutes', 'activityStressMinutes' # activityStressMinutes might be very high if includes workout time
    ]
    # Use only columns that actually exist in the DataFrame
    valid_stress_cols = [col for col in stress_duration_cols_minutes if col in daily_df.columns and daily_df[col].sum() > 0]

    if not valid_stress_cols:
        return go.Figure().update_layout(title="No stress duration data to plot.")

    fig = px.bar(
        daily_df, x='calendarDate', y=valid_stress_cols,
        title="Time in Stress States (Minutes per Day)",
        labels={'value': 'Duration (Minutes)', 'variable': 'Stress Type'},
        barmode='stack'
    )
    fig.update_layout(hovermode="x unified")
    return fig

def plot_body_battery_at_wake(daily_df):
    if daily_df.empty or 'bodyBatteryAtWakeTime' not in daily_df.columns:
        return go.Figure().update_layout(title="Body Battery at Wake Time data not found.")

    bb_wake_data = daily_df[['calendarDate', 'bodyBatteryAtWakeTime']].dropna(subset=['bodyBatteryAtWakeTime'])
    if bb_wake_data.empty:
        return go.Figure().update_layout(title="No valid Body Battery at Wake Time data points.")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=bb_wake_data['calendarDate'], y=bb_wake_data['bodyBatteryAtWakeTime'],
        name='Body Battery at Wake (%)', yaxis='y1', mode='lines+markers'
    ))

    # Optional: overlay sleep duration from the *previous* night
    if 'sleepingHours' in daily_df.columns:
        daily_df_copy = daily_df.copy() # Work on a copy to avoid SettingWithCopyWarning
        daily_df_copy['previousNightSleepHours'] = daily_df_copy['sleepingHours'].shift(1)
        merged_bb_sleep = pd.merge(bb_wake_data, daily_df_copy[['calendarDate', 'previousNightSleepHours']],
                                   on='calendarDate', how='left')
        
        fig.add_trace(go.Scatter(
            x=merged_bb_sleep['calendarDate'], y=merged_bb_sleep['previousNightSleepHours'],
            name='Previous Night Sleep (Hours)', yaxis='y2',
            mode='lines+markers', line=dict(dash='dot', color='rgba(100,149,237,0.7)')
        ))
    
    fig.update_layout(
        title="Morning Body Battery vs. Previous Night's Sleep",
        xaxis_title='Date',
        yaxis=dict(title='Body Battery (%)'),
        yaxis2=dict(title='Sleep (Hours)', overlaying='y', side='right', showgrid=False),
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        hovermode="x unified"
    )
    return fig

def plot_weekly_activity_distribution(daily_df):
    if daily_df.empty:
        return go.Figure().update_layout(title="Activity level data not available.")

    activity_level_cols_minutes = [
        'highlyActiveMinutes', 'activeMinutes', 'sedentaryMinutes', 'sleepingMinutes'
    ]
    valid_activity_cols = [col for col in activity_level_cols_minutes if col in daily_df.columns and daily_df[col].sum() > 0]

    if not valid_activity_cols:
        return go.Figure().update_layout(title="No activity level duration data for weekly plot.")

    temp_df_for_weekly = daily_df.copy()
    # Ensure calendarDate is datetime for resampling
    temp_df_for_weekly['calendarDate'] = pd.to_datetime(temp_df_for_weekly['calendarDate'])
    
    weekly_avg_activity = temp_df_for_weekly.set_index('calendarDate')[valid_activity_cols].resample('W-MON', label='left', closed='left').mean().reset_index()
    
    if weekly_avg_activity.empty:
        return go.Figure().update_layout(title="Could not compute weekly average activity.")

    weekly_avg_activity_melted = weekly_avg_activity.melt(
        id_vars='calendarDate', value_vars=valid_activity_cols,
        var_name='ActivityLevel', value_name='AverageMinutes'
    )
    
    fig = px.bar(
        weekly_avg_activity_melted, x='calendarDate', y='AverageMinutes',
        color='ActivityLevel', title="Weekly Average Daily Time Spent by Activity Level",
        labels={'calendarDate': 'Week Starting', 'AverageMinutes': 'Avg. Daily Minutes'}
    )
    return fig

def plot_weekly_intensity_minutes(daily_df):
    if daily_df.empty or not all(col in daily_df.columns for col in ['moderateIntensityMinutes', 'vigorousIntensityMinutes', 'intensityMinutesGoal']):
        return go.Figure().update_layout(title="Intensity minutes or goal data not available.")

    temp_df_for_intensity = daily_df.copy()
    temp_df_for_intensity['calendarDate'] = pd.to_datetime(temp_df_for_intensity['calendarDate'])
    
    temp_df_for_intensity['weightedIntensityMinutes'] = temp_df_for_intensity['moderateIntensityMinutes'].fillna(0) + \
                                                        (temp_df_for_intensity['vigorousIntensityMinutes'].fillna(0) * 2)
    
    weekly_intensity = temp_df_for_intensity.set_index('calendarDate')[['weightedIntensityMinutes', 'intensityMinutesGoal']].resample('W-MON', label='left', closed='left').agg(
        {'weightedIntensityMinutes': 'sum', 'intensityMinutesGoal': 'first'}
    ).reset_index()

    if weekly_intensity.empty:
        return go.Figure().update_layout(title="Could not aggregate weekly intensity minutes.")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=weekly_intensity['calendarDate'], y=weekly_intensity['weightedIntensityMinutes'],
        name='Achieved Intensity Minutes (Weighted)'
    ))
    fig.add_trace(go.Scatter(
        x=weekly_intensity['calendarDate'], y=weekly_intensity['intensityMinutesGoal'],
        name='Weekly Goal', mode='lines+markers', line=dict(color='red', dash='dash')
    ))
    fig.update_layout(
        title="Weekly Intensity Minutes (Vigorous x2) vs. Goal",
        xaxis_title="Week Starting", yaxis_title="Intensity Minutes", barmode='group'
    )
    return fig