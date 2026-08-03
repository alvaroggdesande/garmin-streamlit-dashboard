"""Pure running-efficiency metrics for the 'Am I Improving?' page.

No Streamlit and no garminconnect imports live here, so every function is
unit-testable with small in-memory DataFrames (mirrors utils/analysis_stats.py).
"""
import numpy as np
import pandas as pd
from scipy import stats

EASY_Z2_FRACTION = 0.60
MIN_WINDOW_N = 4
REF_HR_DEFAULT = 145


def efficiency_factor(distance_m, duration_min, avg_hr):
    """EF = (distance_m / duration_min) / avg_hr  [metres per heartbeat].

    Returns nan if any input is missing or non-positive.
    """
    vals = [distance_m, duration_min, avg_hr]
    if any(v is None or (isinstance(v, float) and np.isnan(v)) or v <= 0 for v in vals):
        return float("nan")
    speed_m_per_min = distance_m / duration_min
    return speed_m_per_min / avg_hr


def add_efficiency_columns(runs_df):
    """Return a copy with per-row `ef` and `is_easy` columns added."""
    df = runs_df.copy()
    df["ef"] = df.apply(
        lambda r: efficiency_factor(
            r.get("distance_km", np.nan) * 1000 if pd.notna(r.get("distance_km", np.nan)) else np.nan,
            r.get("duration_minutes", np.nan),
            r.get("avgHR", np.nan),
        ),
        axis=1,
    )
    if "time_in_zone2_minutes" in df.columns and "duration_minutes" in df.columns:
        frac = df["time_in_zone2_minutes"] / df["duration_minutes"]
        df["is_easy"] = frac >= EASY_Z2_FRACTION
    else:
        df["is_easy"] = False
    return df
