import numpy as np
import pandas as pd
import pytest
from datetime import date, timedelta

from utils import efficiency_stats as e


def test_efficiency_factor_basic():
    # 10 km in 50 min => 200 m/min; /150 bpm => 1.3333 m/beat
    assert e.efficiency_factor(10000, 50, 150) == pytest.approx(200 / 150)


def test_efficiency_factor_invalid_inputs_return_nan():
    assert np.isnan(e.efficiency_factor(0, 50, 150))
    assert np.isnan(e.efficiency_factor(10000, 0, 150))
    assert np.isnan(e.efficiency_factor(10000, 50, 0))
    assert np.isnan(e.efficiency_factor(np.nan, 50, 150))


def test_add_efficiency_columns_adds_ef_and_is_easy():
    df = pd.DataFrame({
        "distance_km": [10.0, 8.0],
        "duration_minutes": [50.0, 40.0],
        "avgHR": [150.0, 140.0],
        "time_in_zone2_minutes": [35.0, 10.0],  # 0.70 easy, 0.25 not
    })
    out = e.add_efficiency_columns(df)
    assert out.loc[0, "ef"] == pytest.approx(200 / 150)
    assert bool(out.loc[0, "is_easy"]) is True
    assert bool(out.loc[1, "is_easy"]) is False
    # original frame untouched
    assert "ef" not in df.columns


def test_add_efficiency_columns_missing_zone_column_is_not_easy():
    df = pd.DataFrame({
        "distance_km": [10.0],
        "duration_minutes": [50.0],
        "avgHR": [150.0],
    })
    out = e.add_efficiency_columns(df)
    assert bool(out.loc[0, "is_easy"]) is False


def test_weekly_ef_trend_medians_and_counts():
    df = pd.DataFrame({
        "date": pd.to_datetime([
            "2026-01-05", "2026-01-07",   # week of Mon 2026-01-05
            "2026-01-12",                  # week of Mon 2026-01-12
        ]),
        "ef": [1.0, 2.0, 3.0],
    })
    out = e.weekly_ef_trend(df)
    assert list(out["week_start"]) == list(pd.to_datetime(["2026-01-05", "2026-01-12"]))
    assert out.loc[0, "n"] == 2
    assert out.loc[0, "ef_median"] == pytest.approx(1.5)
    assert out.loc[0, "ef_q25"] == pytest.approx(1.25)
    assert out.loc[0, "ef_q75"] == pytest.approx(1.75)
    assert out.loc[1, "n"] == 1
    assert out.loc[1, "ef_median"] == pytest.approx(3.0)


def test_weekly_ef_trend_drops_nan_and_handles_empty():
    df = pd.DataFrame({"date": pd.to_datetime(["2026-01-05"]), "ef": [np.nan]})
    out = e.weekly_ef_trend(df)
    assert out.empty
    assert list(out.columns) == ["week_start", "ef_median", "n", "ef_q25", "ef_q75"]


def test_pace_at_reference_hr_linear_fit():
    # pace = 10 - 0.03*HR exactly => at HR=145 pace = 10 - 4.35 = 5.65
    hr = np.array([130, 140, 150, 160, 170], dtype=float)
    pace = 10 - 0.03 * hr
    df = pd.DataFrame({"avgHR": hr, "pace_min_per_km": pace})
    res = e.pace_at_reference_hr(df, ref_hr=145)
    assert res["ok"] is True
    assert res["n"] == 5
    assert res["pace_at_ref"] == pytest.approx(5.65, abs=1e-6)
    assert res["slope"] == pytest.approx(-0.03, abs=1e-6)


def test_pace_at_reference_hr_too_few_runs():
    df = pd.DataFrame({"avgHR": [140.0, 150.0], "pace_min_per_km": [5.5, 5.2]})
    res = e.pace_at_reference_hr(df, ref_hr=145)
    assert res["ok"] is False
    assert res["pace_at_ref"] is None


def test_pace_at_reference_hr_insufficient_spread():
    # 6 runs but all within 3 bpm => cannot fit a trustworthy line
    df = pd.DataFrame({
        "avgHR": [144.0, 145.0, 145.0, 146.0, 146.0, 147.0],
        "pace_min_per_km": [5.5, 5.4, 5.6, 5.5, 5.3, 5.4],
    })
    res = e.pace_at_reference_hr(df, ref_hr=145)
    assert res["ok"] is False
    assert "spread" in res["reason"].lower()


def _runs(as_of, offsets_days, efs):
    return pd.DataFrame({
        "date": [pd.Timestamp(as_of - timedelta(days=d)) for d in offsets_days],
        "ef": efs,
    })


def test_improvement_verdict_up_and_confident():
    as_of = date(2026, 3, 1)
    # prior window (43-84 days ago) low EF; recent window (0-42 days) high EF
    prior = _runs(as_of, [50, 55, 60, 65, 70], [1.00, 1.02, 0.98, 1.01, 0.99])
    recent = _runs(as_of, [3, 8, 15, 22, 30], [1.20, 1.22, 1.18, 1.21, 1.19])
    df = pd.concat([prior, recent], ignore_index=True)
    v = e.improvement_verdict(df, as_of=as_of, recent_weeks=6)
    assert v["muted"] is False
    assert v["n_recent"] == 5 and v["n_prior"] == 5
    assert v["direction"] == "up"
    assert v["pct_change"] > 15
    assert v["confident"] is True


def test_improvement_verdict_muted_when_thin():
    as_of = date(2026, 3, 1)
    prior = _runs(as_of, [50, 60], [1.0, 1.0])       # only 2 runs
    recent = _runs(as_of, [3, 8, 15], [1.2, 1.2, 1.2])
    df = pd.concat([prior, recent], ignore_index=True)
    v = e.improvement_verdict(df, as_of=as_of, recent_weeks=6)
    assert v["muted"] is True
    assert v["confident"] is False


def test_improvement_verdict_flat_direction():
    as_of = date(2026, 3, 1)
    prior = _runs(as_of, [50, 55, 60, 65], [1.00, 1.01, 0.99, 1.00])
    recent = _runs(as_of, [3, 8, 15, 22], [1.005, 1.00, 1.01, 0.995])
    df = pd.concat([prior, recent], ignore_index=True)
    v = e.improvement_verdict(df, as_of=as_of, recent_weeks=6)
    assert v["direction"] == "flat"
