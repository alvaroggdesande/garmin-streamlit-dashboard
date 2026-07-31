"""Pure statistics + aggregation for cross-metric / lagged analysis.

No Streamlit and no Garmin imports live here so every function is unit-testable
with small in-memory DataFrames.
"""
import numpy as np
import pandas as pd
from scipy import stats

MIN_N = 3
DEFAULT_ALPHA = 0.05


def corr_with_significance(x, y, method="pearson"):
    """Correlation of two aligned series with n, p-value and 95% CI.

    Pairwise-drops NaNs. Returns NaNs with too_few=True when there are fewer
    than MIN_N complete pairs or either side is constant.
    """
    x = pd.Series(x).reset_index(drop=True)
    y = pd.Series(y).reset_index(drop=True)
    mask = x.notna() & y.notna()
    x, y = x[mask], y[mask]
    n = int(len(x))
    out = {"r": np.nan, "p": np.nan, "n": n,
           "ci_low": np.nan, "ci_high": np.nan, "too_few": n < MIN_N}
    if n < MIN_N or x.nunique() < 2 or y.nunique() < 2:
        out["too_few"] = True
        return out

    if method == "spearman":
        r, p = stats.spearmanr(x, y)
    else:
        r, p = stats.pearsonr(x, y)
    out["r"], out["p"] = float(r), float(p)

    # Fisher z-transform CI (approximate for spearman; needs n > 3).
    # At n=3 exactly, the standard error SE = 1/sqrt(n-3) is undefined,
    # so ci_low/ci_high remain NaN by design and callers treat NaN CI as "not shown".
    if n > 3:
        if abs(r) < 1.0:
            z = np.arctanh(r)
            se = 1.0 / np.sqrt(n - 3)
            out["ci_low"] = float(np.tanh(z - 1.96 * se))
            out["ci_high"] = float(np.tanh(z + 1.96 * se))
        else:
            # Perfect correlation: CI is [r, r]
            out["ci_low"] = float(r)
            out["ci_high"] = float(r)
    return out


def lagged_correlation(df, x_col, y_col, lags=range(0, 8),
                       method="pearson", alpha=DEFAULT_ALPHA, min_n=MIN_N):
    """Correlate driver x_col against outcome y_col across a range of day lags.

    Lag k aligns driver at day t with outcome at day t+k (y shifted by -k).
    """
    x = df[x_col]
    rows = []
    for k in lags:
        y_shift = df[y_col].shift(-k)
        s = corr_with_significance(x, y_shift, method=method)
        significant = (
            not s["too_few"]
            and pd.notna(s["p"])
            and s["p"] < alpha
            and s["n"] >= min_n
        )
        rows.append({"lag": k, "r": s["r"], "p": s["p"], "n": s["n"],
                     "ci_low": s["ci_low"], "ci_high": s["ci_high"],
                     "significant": significant})
    return pd.DataFrame(rows, columns=["lag", "r", "p", "n",
                                       "ci_low", "ci_high", "significant"])


_ACTIVITY_DAILY_COLS = [
    "date", "total_duration_min", "total_distance_km", "mean_pace_min_per_km",
    "mean_avg_hr", "aerobic_efficiency", "total_aerobic_te", "n_activities", "n_runs",
]


def aggregate_activities_daily(activities_df):
    """Collapse multiple activities per day into one row of daily training metrics."""
    if activities_df is None or activities_df.empty or "date" not in activities_df.columns:
        return pd.DataFrame(columns=_ACTIVITY_DAILY_COLS)

    df = activities_df.copy()
    type_key = df["activityType_key"] if "activityType_key" in df.columns else pd.Series(index=df.index, dtype=object)
    df["_is_run"] = type_key.eq("running")

    grouped = df.groupby("date")
    out = grouped.agg(
        total_duration_min=("duration_minutes", "sum"),
        total_distance_km=("distance_km", "sum"),
        mean_pace_min_per_km=("pace_min_per_km", "mean"),
        mean_avg_hr=("avgHR", "mean"),
        total_aerobic_te=("aerobicTE", "sum"),
        n_activities=("date", "size"),
        n_runs=("_is_run", "sum"),
    ).reset_index()

    speed_kmh = out["total_distance_km"] / (out["total_duration_min"] / 60.0)
    out["aerobic_efficiency"] = np.where(
        out["mean_avg_hr"] > 0, speed_kmh / out["mean_avg_hr"], np.nan
    )
    return out[_ACTIVITY_DAILY_COLS]


# component column -> sign (+1 higher is better, -1 higher is worse)
COMPONENT_SPECS = {
    "restingHeartRate": -1,
    "sleepingHours": +1,
    "hrv_nightly_avg": +1,
    "bodyBatteryAtWakeTime": +1,
    "averageStressLevel_prev": -1,  # prior-day overall stress
}


def _trailing_z(series, window):
    """z-score against the trailing window that EXCLUDES the current day."""
    min_p = max(3, window // 4)
    base_mean = series.shift(1).rolling(window, min_periods=min_p).mean()
    base_std = series.shift(1).rolling(window, min_periods=min_p).std()
    return (series - base_mean) / base_std


def readiness_score(daily_df, baseline_window=28):
    """Transparent morning-readiness composite from available recovery signals."""
    df = daily_df.copy().sort_values("date").reset_index(drop=True)
    if "averageStressLevel" in df.columns:
        df["averageStressLevel_prev"] = df["averageStressLevel"].shift(1)

    comp_cols = []
    for col, sign in COMPONENT_SPECS.items():
        if col in df.columns and df[col].notna().sum() >= 3:
            zc = f"z_{col}"
            df[zc] = _trailing_z(df[col], baseline_window) * sign
            comp_cols.append(zc)

    if comp_cols:
        df["readiness"] = df[comp_cols].mean(axis=1, skipna=True)
        df["readiness_n_components"] = df[comp_cols].notna().sum(axis=1)
    else:
        df["readiness"] = np.nan
        df["readiness_n_components"] = 0
    return df
