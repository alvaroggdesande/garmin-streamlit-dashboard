import numpy as np
import pandas as pd
import pytest

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
