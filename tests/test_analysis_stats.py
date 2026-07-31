import numpy as np
import pandas as pd
import pytest

from utils import analysis_stats as a


def test_perfect_positive_correlation():
    x = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    y = pd.Series([2.0, 4.0, 6.0, 8.0, 10.0])
    res = a.corr_with_significance(x, y, method="pearson")
    assert res["n"] == 5
    assert res["too_few"] is False
    assert res["r"] == pytest.approx(1.0, abs=1e-9)
    assert res["p"] < 0.05
    assert res["ci_low"] <= res["r"] <= res["ci_high"]


def test_too_few_points_flagged():
    x = pd.Series([1.0, 2.0])
    y = pd.Series([2.0, 1.0])
    res = a.corr_with_significance(x, y)
    assert res["too_few"] is True
    assert np.isnan(res["r"])


def test_nan_pairs_dropped():
    x = pd.Series([1.0, 2.0, np.nan, 4.0, 5.0])
    y = pd.Series([2.0, 4.0, 6.0, np.nan, 10.0])
    res = a.corr_with_significance(x, y)
    assert res["n"] == 3  # only rows 0,1,4 are complete


def test_spearman_handles_monotonic_nonlinear():
    x = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    y = pd.Series([1.0, 4.0, 9.0, 16.0, 25.0])  # monotonic, non-linear
    res = a.corr_with_significance(x, y, method="spearman")
    assert res["r"] == pytest.approx(1.0, abs=1e-9)


def test_n3_returns_nan_ci_by_design():
    """At n=3 (minimum valid sample), Fisher-z CI stays NaN because SE = 1/sqrt(n-3) is undefined.

    This documents the contract: too_few=False, r is computed and valid, but CI bounds
    remain NaN as intended (callers treat NaN CI as "not shown").
    """
    x = pd.Series([1.0, 2.0, 3.0])
    y = pd.Series([2.0, 4.0, 6.0])
    res = a.corr_with_significance(x, y, method="pearson")
    assert res["n"] == 3
    assert res["too_few"] is False
    assert not np.isnan(res["r"])  # r is valid
    assert np.isnan(res["ci_low"])  # but CI bounds remain NaN
    assert np.isnan(res["ci_high"])


def test_lagged_correlation_finds_offset_peak():
    rng = np.random.default_rng(0)
    x = pd.Series(rng.normal(size=60))
    # outcome equals the driver from 3 days earlier: y[t] = x[t-3]
    y = x.shift(3)
    df = pd.DataFrame({"driver": x, "outcome": y})
    res = a.lagged_correlation(df, "driver", "outcome", lags=range(0, 8))
    assert list(res["lag"]) == list(range(0, 8))
    peak_lag = int(res.loc[res["r"].abs().idxmax(), "lag"])
    assert peak_lag == 3
    assert bool(res.loc[res["lag"] == 3, "significant"].iloc[0]) is True


def test_lagged_correlation_marks_noise_not_significant():
    rng = np.random.default_rng(1)
    df = pd.DataFrame({"a": rng.normal(size=40), "b": rng.normal(size=40)})
    res = a.lagged_correlation(df, "a", "b", lags=range(0, 4))
    # independent noise: at least the lag-0 relationship should be non-significant
    assert bool(res.loc[res["lag"] == 0, "significant"].iloc[0]) is False


def test_aggregate_activities_daily_sums_and_means():
    acts = pd.DataFrame({
        "date": ["2026-01-01", "2026-01-01", "2026-01-02"],
        "duration_minutes": [30.0, 60.0, 45.0],
        "distance_km": [5.0, 10.0, 9.0],
        "pace_min_per_km": [6.0, 6.0, 5.0],
        "avgHR": [140.0, 150.0, 160.0],
        "aerobicTE": [2.0, 3.0, 4.0],
        "activityType_key": ["running", "cycling", "running"],
    })
    out = a.aggregate_activities_daily(acts)
    day1 = out[out["date"] == "2026-01-01"].iloc[0]
    assert day1["total_duration_min"] == 90.0
    assert day1["total_distance_km"] == 15.0
    assert day1["n_activities"] == 2
    assert day1["n_runs"] == 1
    assert day1["mean_avg_hr"] == pytest.approx(145.0)
    # speed = 15 km / 1.5 h = 10 km/h; efficiency = 10 / 145
    assert day1["aerobic_efficiency"] == pytest.approx(10.0 / 145.0, rel=1e-6)


def test_aggregate_activities_daily_empty():
    out = a.aggregate_activities_daily(pd.DataFrame())
    assert list(out.columns) == [
        "date", "total_duration_min", "total_distance_km", "mean_pace_min_per_km",
        "mean_avg_hr", "aerobic_efficiency", "total_aerobic_te", "n_activities", "n_runs",
    ]
    assert out.empty


def test_readiness_inverts_rhr_and_flags_bad_day():
    dates = pd.date_range("2026-01-01", periods=12, freq="D").date
    rhr = [50] * 11 + [70]          # last day: RHR spikes -> readiness should drop
    sleep = [8.0] * 12
    df = pd.DataFrame({"date": dates, "restingHeartRate": rhr, "sleepingHours": sleep})
    out = a.readiness_score(df, baseline_window=7)
    assert "readiness" in out.columns
    assert out["readiness"].iloc[-1] < 0        # high RHR = worse readiness
    assert out["readiness_n_components"].iloc[-1] >= 1


def test_readiness_skips_missing_components():
    dates = pd.date_range("2026-01-01", periods=10, freq="D").date
    df = pd.DataFrame({"date": dates, "sleepingHours": [6, 7, 8, 7, 6, 9, 8, 7, 6, 8]})
    out = a.readiness_score(df, baseline_window=5)
    # only sleep present -> at most 1 component, never errors on absent columns
    assert out["readiness_n_components"].max() <= 1
