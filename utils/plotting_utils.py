import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

def plot_hrv_trend(hrv_df, daily_summary_df=None, sleep_df=None):
    """
    Plots HRV nightly average. Optionally overlays RHR and sleep duration.
    hrv_df should be processed with a 'date' and 'hrv_nightly_avg' column.
    daily_summary_df for 'restingHeartRate'.
    sleep_df for 'duration_minutes_sleep'.
    """
    if hrv_df.empty or 'date' not in hrv_df.columns or 'hrv_nightly_avg' not in hrv_df.columns:
        return go.Figure().update_layout(title="No HRV Data to Display")

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # HRV Trace
    fig.add_trace(
        go.Scatter(x=hrv_df['date'], y=hrv_df['hrv_nightly_avg'], name="HRV (Nightly Avg ms)", mode='lines+markers'),
        secondary_y=False,
    )
    
    # Optional HRV baseline
    if 'baselineLow_hrv' in hrv_df.columns and 'baselineHigh_hrv' in hrv_df.columns:
        fig.add_trace(
            go.Scatter(
                x=hrv_df['date'], y=hrv_df['baselineHigh_hrv'], name="HRV Baseline High",
                mode='lines', line=dict(dash='dot', color='lightgrey'), fill=None
            ), secondary_y=False
        )
        fig.add_trace(
            go.Scatter(
                x=hrv_df['date'], y=hrv_df['baselineLow_hrv'], name="HRV Baseline Low",
                mode='lines', line=dict(dash='dot', color='lightgrey'), fill='tonexty', # Fill to previous trace
                fillcolor='rgba(211,211,211,0.2)' 
            ), secondary_y=False
        )


    # Optional RHR
    if daily_summary_df is not None and not daily_summary_df.empty and \
       'date' in daily_summary_df.columns and 'restingHeartRate_daily' in daily_summary_df.columns:
        rhr_data = daily_summary_df.dropna(subset=['restingHeartRate_daily'])
        fig.add_trace(
            go.Scatter(x=rhr_data['date'], y=rhr_data['restingHeartRate_daily'], name="Resting HR (bpm)", mode='lines+markers'),
            secondary_y=True, # Plot on secondary y-axis
        )
    
    # Optional Sleep Duration
    if sleep_df is not None and not sleep_df.empty and \
       'date_sleep' in sleep_df.columns and 'duration_minutes_sleep' in sleep_df.columns:
        sleep_data_plot = sleep_df.dropna(subset=['duration_minutes_sleep'])
        sleep_data_plot['sleep_hours'] = sleep_data_plot['duration_minutes_sleep'] / 60
        fig.add_trace(
            go.Scatter(x=sleep_data_plot['date_sleep'], y=sleep_data_plot['sleep_hours'], 
                       name="Sleep Duration (hours)", mode='lines+markers', line=dict(dash='dash')),
            secondary_y=True, # Could also be on a third y-axis if needed or plotted separately
        )


    fig.update_layout(title_text="HRV Nightly Average & Related Metrics")
    fig.update_xaxes(title_text="Date")
    fig.update_yaxes(title_text="<b>HRV (ms)</b>", secondary_y=False)
    fig.update_yaxes(title_text="<b>RHR (bpm) / Sleep (hours)</b>", secondary_y=True, showgrid=False)
    return fig

def plot_pace_vs_hr(aerobic_efficiency_df):
    """
    Plots pace vs. average HR for Zone 2 runs.
    aerobic_efficiency_df needs 'date', 'pace_min_per_km', 'avgHR', 'distance_km'.
    """
    if aerobic_efficiency_df.empty:
        return go.Figure().update_layout(title="No Aerobic Efficiency Data to Display")

    fig = px.scatter(aerobic_efficiency_df, x='date', y='pace_min_per_km',
                     color='avgHR', size='distance_km',
                     title="Pace vs. Avg HR for Zone 2 Runs (Easy Runs)",
                     labels={'pace_min_per_km': "Pace (min/km)", 'avgHR': "Avg Heart Rate (bpm)", 'date': "Date"},
                     hover_data=['distance_km', 'avgHR'])
    fig.update_yaxes(autorange="reversed") # Lower pace (faster) is better
    return fig

def plot_hr_zone_distribution(zone_dist_df, period_name="Weekly"):
    """
    Plots distribution of time spent in HR zones.
    zone_dist_df needs 'date' and 'time_in_zoneX_minutes' columns.
    """
    if zone_dist_df.empty:
        return go.Figure().update_layout(title="No HR Zone Data to Display")

    zone_cols = [col for col in zone_dist_df.columns if col.startswith('time_in_zone') and col.endswith('_minutes')]
    if not zone_cols:
        return go.Figure().update_layout(title="No HR Zone Time Columns Found")

    fig = px.bar(zone_dist_df, x='date', y=zone_cols,
                 title=f"{period_name} Time in Heart Rate Zones",
                 labels={'value': "Time (minutes)", 'date': "Period Start Date", 'variable': "HR Zone"},
                 barmode='stack')
    return fig

def plot_sleep_hrv_correlation(merged_df, sleep_metric_col='duration_minutes_sleep', hrv_metric_col='hrv_nightly_avg_hrv'):
    """
    Plots correlation between a sleep metric and an HRV metric.
    merged_df needs the specified sleep and HRV columns.
    """
    if merged_df.empty or sleep_metric_col not in merged_df.columns or hrv_metric_col not in merged_df.columns:
        return go.Figure().update_layout(title="Insufficient Data for Sleep-HRV Correlation")

    plot_df = merged_df[[sleep_metric_col, hrv_metric_col]].dropna()
    if plot_df.empty:
        return go.Figure().update_layout(title="No Overlapping Sleep-HRV Data")

    fig = px.scatter(plot_df, x=sleep_metric_col, y=hrv_metric_col,
                     title=f"Correlation: {sleep_metric_col.replace('_sleep','')} vs. {hrv_metric_col.replace('_hrv','')}",
                     trendline="ols", # Ordinary Least Squares regression trendline
                     labels={
                         sleep_metric_col: sleep_metric_col.replace('_sleep','').replace('_',' ').title(),
                         hrv_metric_col: hrv_metric_col.replace('_hrv','').replace('_',' ').title()
                     })
    return fig

def plot_training_load(load_df, load_col='custom_load', date_col='date'):
    """
    Plots training load over time.
    load_df needs a date column and a load column.
    """
    if load_df.empty or date_col not in load_df.columns or load_col not in load_df.columns:
        return go.Figure().update_layout(title="No Training Load Data to Display")
    
    load_df_sorted = load_df.sort_values(by=date_col)

    fig = px.line(load_df_sorted, x=date_col, y=load_col,
                  title="Daily Training Load",
                  labels={load_col: "Training Load Score", date_col: "Date"},
                  markers=True)
    return fig

def plot_goal_progress(current_value, target_value, goal_name="Goal"):
    """Basic goal progress indicator."""
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = current_value,
        title = {'text': f"{goal_name} Progress"},
        domain = {'x': [0, 1], 'y': [0, 1]},
        gauge = {
            'axis': {'range': [0, target_value]},
            'bar': {'color': "darkblue"},
            'steps': [
                {'range': [0, target_value * 0.5], 'color': "lightgray"},
                {'range': [target_value * 0.5, target_value * 0.8], 'color': "gray"}],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': target_value
            }
        }
    ))
    return fig