import pandas as pd
import pytest

from utils import data_processing as d


def _raw_run():
    return pd.DataFrame([{
        "activityType": {"typeKey": "running"},
        "startTimeGMT": "2026-01-05 08:00:00",
        "startTimeLocal": "2026-01-05 09:00:00",
        "duration": 3000.0,           # 50 min
        "distance": 10000.0,          # 10 km
        "averageHR": 150.0,
        "maxHR": 165.0,
        "averageRunningCadenceInStepsPerMinute": 85.0,
        "maxRunningCadenceInStepsPerMinute": 95.0,
        "vO2MaxValue": 52.0,
        "aerobicTrainingEffect": 3.1,
        "anaerobicTrainingEffect": 0.4,
        "hrTimeInZone_1": 0.0,
        "hrTimeInZone_2": 2100.0,     # 35 min in Z2
        "hrTimeInZone_3": 600.0,
        "hrTimeInZone_4": 300.0,
        "hrTimeInZone_5": 0.0,
    }])


def test_process_running_activities_df_derives_expected_columns():
    out = d.process_running_activities_df(_raw_run())
    row = out.iloc[0]
    assert row["activityType_key"] == "running"
    assert str(row["date"]) == "2026-01-05"
    assert row["duration_minutes"] == pytest.approx(50.0)
    assert row["distance_km"] == pytest.approx(10.0)
    assert row["pace_min_per_km"] == pytest.approx(5.0)
    assert row["avgHR"] == pytest.approx(150.0)
    assert row["time_in_zone2_minutes"] == pytest.approx(35.0)
    assert row["vo2MaxValue_activity"] == pytest.approx(52.0)


def test_process_running_activities_df_empty_input():
    assert d.process_running_activities_df(pd.DataFrame()).empty
