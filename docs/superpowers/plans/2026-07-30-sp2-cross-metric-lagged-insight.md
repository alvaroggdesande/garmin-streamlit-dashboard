# SP2 — Cross-Metric & Lagged Insight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the naïve same-day correlation page with a statistically-honest lagged-correlation explorer, and add a new page relating a transparent morning-readiness score to realized training performance.

**Architecture:** All statistics live in a new pure-Python module `utils/analysis_stats.py` (no Streamlit, no Garmin imports) built test-first with pytest. Two Streamlit pages consume it: `P4` is reworked into the Lagged Correlation Explorer, and a new `P6` renders Readiness → Performance. Data reaches both pages through a single unified daily DataFrame assembled from the existing fetchers plus a new daily activity aggregation.

**Tech Stack:** Python, pandas 2.2.2, numpy 1.24.4, scipy 1.15.3 (`scipy.stats`), plotly 5.20, streamlit 1.33, pytest.

## Global Constraints

- Auth/data access stays on Option A (unofficial `garminconnect`, email+password). **No auth, no new data sources, no export/GDPR path.** Copied verbatim from spec: "SP2 does not touch data access, auth, or add new data sources."
- `utils/analysis_stats.py` MUST NOT import `streamlit` or `garminconnect` — it is pure and unit-tested.
- No ML, no forecasting, no causal-inference claims. Correlation reported honestly; never labeled causation.
- Missing readiness components are **skipped, not imputed**.
- Every reported relationship must carry **n, coefficient, p-value, and 95% CI**, with an explicit muted state when `n < 3` or `p >= alpha`.
- Pure functions are covered by pytest; Streamlit pages are verified **manually by the author** (repo convention — do not write self-running Streamlit smoke tests).
- Significance threshold default `alpha = 0.05`; minimum sample `MIN_N = 3`.

---

## File Structure

- **Create** `utils/analysis_stats.py` — pure stats/aggregation: `corr_with_significance`, `lagged_correlation`, `aggregate_activities_daily`, `readiness_score`, `build_unified_daily_frame`.
- **Create** `tests/test_analysis_stats.py` — unit tests for the module.
- **Create** `conftest.py` (repo root) — makes `from utils import analysis_stats` importable under pytest.
- **Modify** `requirements.txt` — add `pytest`.
- **Rewrite** `pages/P4_Correlations.py` — Lagged Correlation Explorer (Feature 1) + optional heatmap (Feature 3).
- **Create** `pages/P6_Readiness_and_Performance.py` — Readiness → Performance (Feature 2).

Tasks 1–5 build and test the pure module (TDD). Tasks 6–7 build the pages (manual verification). Task 8 is the optional heatmap.

---

### Task 1: Stats primitive — `corr_with_significance`

**Files:**
- Create: `utils/analysis_stats.py`
- Create: `tests/test_analysis_stats.py`
- Create: `conftest.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `corr_with_significance(x, y, method="pearson") -> dict` with keys
  `{"r": float, "p": float, "n": int, "ci_low": float, "ci_high": float, "too_few": bool}`.
  `method` ∈ `{"pearson", "spearman"}`. NaN-aligned pairwise; returns NaNs + `too_few=True`
  when `n < 3` or either series has < 2 unique values.
- Produces module constants `MIN_N = 3`, `DEFAULT_ALPHA = 0.05`.

- [ ] **Step 1: Add pytest to requirements**

Append to `requirements.txt`:

```
pytest==8.2.2
```

- [ ] **Step 2: Create `conftest.py` at repo root**

```python
# conftest.py — ensure repo root is importable so `from utils import ...` works under pytest.
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
```

- [ ] **Step 3: Write the failing test**

Create `tests/test_analysis_stats.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_analysis_stats.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'utils.analysis_stats'`.

- [ ] **Step 5: Implement `corr_with_significance`**

Create `utils/analysis_stats.py`:

```python
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
    if n > 3 and abs(r) < 1.0:
        z = np.arctanh(r)
        se = 1.0 / np.sqrt(n - 3)
        out["ci_low"] = float(np.tanh(z - 1.96 * se))
        out["ci_high"] = float(np.tanh(z + 1.96 * se))
    return out
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_analysis_stats.py -v`
Expected: PASS (4 passed).

- [ ] **Step 7: Commit**

```bash
git add requirements.txt conftest.py utils/analysis_stats.py tests/test_analysis_stats.py
git commit -m "feat(stats): corr_with_significance with n, p-value and CI"
```

---

### Task 2: `lagged_correlation`

**Files:**
- Modify: `utils/analysis_stats.py`
- Modify: `tests/test_analysis_stats.py`

**Interfaces:**
- Consumes: `corr_with_significance`, `MIN_N`, `DEFAULT_ALPHA`.
- Produces: `lagged_correlation(df, x_col, y_col, lags=range(0, 8), method="pearson", alpha=DEFAULT_ALPHA, min_n=MIN_N) -> pd.DataFrame`
  with columns `["lag", "r", "p", "n", "ci_low", "ci_high", "significant"]`, one row per lag.
  Lag `k` correlates driver `x[t]` with outcome `y[t+k]` (i.e. `y` shifted by `-k`).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_analysis_stats.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_analysis_stats.py::test_lagged_correlation_finds_offset_peak -v`
Expected: FAIL — `AttributeError: module 'utils.analysis_stats' has no attribute 'lagged_correlation'`.

- [ ] **Step 3: Implement `lagged_correlation`**

Append to `utils/analysis_stats.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_analysis_stats.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add utils/analysis_stats.py tests/test_analysis_stats.py
git commit -m "feat(stats): lagged_correlation across a range of day lags"
```

---

### Task 3: `aggregate_activities_daily`

**Files:**
- Modify: `utils/analysis_stats.py`
- Modify: `tests/test_analysis_stats.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `aggregate_activities_daily(activities_df) -> pd.DataFrame` with columns
  `["date", "total_duration_min", "total_distance_km", "mean_pace_min_per_km",
  "mean_avg_hr", "aerobic_efficiency", "total_aerobic_te", "n_activities", "n_runs"]`.
  Input is a processed activities frame (from `data_processing.process_general_activities_df`)
  with columns `date, duration_minutes, distance_km, pace_min_per_km, avgHR, aerobicTE,
  activityType_key`. `aerobic_efficiency = speed_kmh / mean_avg_hr` (higher = more efficient).
  Returns an empty frame with the same columns when input is empty/None.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_analysis_stats.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_analysis_stats.py::test_aggregate_activities_daily_sums_and_means -v`
Expected: FAIL — `AttributeError: ... has no attribute 'aggregate_activities_daily'`.

- [ ] **Step 3: Implement `aggregate_activities_daily`**

Append to `utils/analysis_stats.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_analysis_stats.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add utils/analysis_stats.py tests/test_analysis_stats.py
git commit -m "feat(stats): aggregate_activities_daily to one row per day"
```

---

### Task 4: `readiness_score`

**Files:**
- Modify: `utils/analysis_stats.py`
- Modify: `tests/test_analysis_stats.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `readiness_score(daily_df, baseline_window=28) -> pd.DataFrame` — a copy of
  `daily_df` sorted by `date`, plus `z_<component>` columns, a `readiness` column (mean of
  available z-components), and `readiness_n_components` (count of components used that day).
  Components and signs are fixed in `COMPONENT_SPECS` (higher-worse metrics are inverted).
  Baseline is the trailing window **excluding the current day**. Missing components are skipped.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_analysis_stats.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_analysis_stats.py::test_readiness_inverts_rhr_and_flags_bad_day -v`
Expected: FAIL — `AttributeError: ... has no attribute 'readiness_score'`.

- [ ] **Step 3: Implement `readiness_score`**

Append to `utils/analysis_stats.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_analysis_stats.py -v`
Expected: PASS (10 passed).

- [ ] **Step 5: Commit**

```bash
git add utils/analysis_stats.py tests/test_analysis_stats.py
git commit -m "feat(stats): transparent trailing-baseline readiness score"
```

---

### Task 5: `build_unified_daily_frame`

**Files:**
- Modify: `utils/analysis_stats.py`
- Modify: `tests/test_analysis_stats.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (but is fed `aggregate_activities_daily` output at runtime).
- Produces: `build_unified_daily_frame(daily_df=None, hrv_df=None, sleep_df=None, activities_daily_df=None) -> pd.DataFrame`
  — outer-join of all supplied frames on a normalized `date` column (renames `calendarDate`→`date`,
  coerces to `datetime.date`), sorted by date. Returns `pd.DataFrame(columns=["date"])` when all inputs are empty/None.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_analysis_stats.py`:

```python
def test_build_unified_daily_frame_outer_joins_on_date():
    daily = pd.DataFrame({"calendarDate": ["2026-01-01", "2026-01-02"],
                          "restingHeartRate": [50, 52]})
    sleep = pd.DataFrame({"date": ["2026-01-02", "2026-01-03"],
                          "sleepingHours": [7.5, 8.0]})
    out = a.build_unified_daily_frame(daily_df=daily, sleep_df=sleep)
    assert "date" in out.columns
    assert "calendarDate" not in out.columns
    assert len(out) == 3  # union of the two date sets
    assert list(out["date"]) == sorted(out["date"])


def test_build_unified_daily_frame_all_empty():
    out = a.build_unified_daily_frame()
    assert list(out.columns) == ["date"]
    assert out.empty
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_analysis_stats.py::test_build_unified_daily_frame_outer_joins_on_date -v`
Expected: FAIL — `AttributeError: ... has no attribute 'build_unified_daily_frame'`.

- [ ] **Step 3: Implement `build_unified_daily_frame`**

Append to `utils/analysis_stats.py`:

```python
def _normalize_date_frame(df):
    if df is None or df.empty:
        return None
    d = df.copy()
    if "date" not in d.columns and "calendarDate" in d.columns:
        d = d.rename(columns={"calendarDate": "date"})
    if "date" not in d.columns:
        return None
    d["date"] = pd.to_datetime(d["date"]).dt.date
    return d


def build_unified_daily_frame(daily_df=None, hrv_df=None, sleep_df=None,
                              activities_daily_df=None):
    """Outer-join daily summary, HRV, sleep and daily activity frames on date."""
    base = None
    for df in (daily_df, hrv_df, sleep_df, activities_daily_df):
        norm = _normalize_date_frame(df)
        if norm is None:
            continue
        base = norm if base is None else pd.merge(
            base, norm, on="date", how="outer", suffixes=("", "_dup")
        )
    if base is None:
        return pd.DataFrame(columns=["date"])
    return base.sort_values("date").reset_index(drop=True)
```

- [ ] **Step 4: Run the FULL module test suite**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_analysis_stats.py -v`
Expected: PASS (12 passed).

- [ ] **Step 5: Commit**

```bash
git add utils/analysis_stats.py tests/test_analysis_stats.py
git commit -m "feat(stats): build_unified_daily_frame outer-joining all daily sources"
```

---

### Task 6: Rework `P4` into the Lagged Correlation Explorer

**Files:**
- Rewrite: `pages/P4_Correlations.py`

**Interfaces:**
- Consumes: `analysis_stats.build_unified_daily_frame`, `analysis_stats.aggregate_activities_daily`,
  `analysis_stats.lagged_correlation`, `analysis_stats.corr_with_significance`;
  existing `garmin_utils.get_daily_summaries / get_hrv_data / get_sleep_data / get_activities`,
  `data_processing.process_hrv_df / process_sleep_df / process_general_activities_df` and the
  page-local `process_daily_summary_for_plotting`.
- Produces: the reworked correlations page (no exported symbols).

This task is verified **manually** (Streamlit page). No automated test.

- [ ] **Step 1: Replace the page body**

Overwrite `pages/P4_Correlations.py` with:

```python
# pages/P4_Correlations.py — Lagged Correlation Explorer
import sys
import os
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from utils import garmin_utils, data_processing, analysis_stats

st.set_page_config(layout="wide", page_title="Lagged Correlations")
st.title("Lagged Correlation Explorer")
st.caption(
    "Exploratory, not confirmatory. Correlation is not causation, and scanning many "
    "metric/lag pairs inflates false positives — treat highlighted lags as hypotheses."
)


def _process_daily(df_raw):
    if df_raw.empty:
        return pd.DataFrame()
    df = df_raw.copy()
    df["calendarDate"] = pd.to_datetime(df["calendarDate"]).dt.date
    if "sleepingSeconds" in df.columns:
        df["sleepingHours"] = pd.to_numeric(df["sleepingSeconds"], errors="coerce") / 3600
    for col in ["restingHeartRate", "averageStressLevel", "totalSteps",
                "bodyBatteryAtWakeTime", "activeKilocalories",
                "moderateIntensityMinutes", "vigorousIntensityMinutes",
                "maxStressLevel", "lastSevenDaysAvgRestingHeartRate"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("calendarDate").reset_index(drop=True)


@st.cache_data(ttl=300)
def load_unified(_client, _username, _start, _end, _force):
    daily = _process_daily(garmin_utils.get_daily_summaries(_client, _username, _start, _end, _force))
    hrv = data_processing.process_hrv_df(garmin_utils.get_hrv_data(_client, _username, _start, _end, _force))
    sleep = data_processing.process_sleep_df(garmin_utils.get_sleep_data(_client, _username, _start, _end, _force))
    acts = data_processing.process_general_activities_df(garmin_utils.get_activities(_client, _username, _start, _end, _force))
    acts_daily = analysis_stats.aggregate_activities_daily(acts)
    return analysis_stats.build_unified_daily_frame(daily, hrv, sleep, acts_daily)


if not st.session_state.get("logged_in", False):
    st.warning("Please log in first using the sidebar on the main page.")
    st.stop()

client = st.session_state.garmin_client
username = st.session_state.current_user
start = st.session_state.get("date_range_start", date.today() - timedelta(days=30))
end = st.session_state.get("date_range_end", date.today())
force = st.session_state.get("force_refresh", False)

with st.spinner("Loading & unifying daily data..."):
    udf = load_unified(client, username, start, end, force)

if udf.empty:
    st.info("No daily data available for the selected range.")
    st.stop()

numeric_cols = sorted(
    c for c in udf.columns
    if c != "date" and pd.api.types.is_numeric_dtype(udf[c])
    and udf[c].nunique(dropna=True) > 1
)
if len(numeric_cols) < 2:
    st.info("Not enough numeric metrics to correlate.")
    st.stop()

c1, c2, c3 = st.columns(3)
driver = c1.selectbox("Driver (X, day t)", numeric_cols,
                      index=numeric_cols.index("sleepingHours") if "sleepingHours" in numeric_cols else 0)
outcome = c2.selectbox("Outcome (Y, day t+lag)", numeric_cols,
                       index=numeric_cols.index("restingHeartRate") if "restingHeartRate" in numeric_cols else min(1, len(numeric_cols) - 1))
method = c3.radio("Method", ["pearson", "spearman"], horizontal=True)
max_lag = st.slider("Max lag (days)", 1, 14, 7)

lag_df = analysis_stats.lagged_correlation(udf, driver, outcome, lags=range(0, max_lag + 1), method=method)

st.subheader("Correlation vs lag")
bar = px.bar(lag_df, x="lag", y="r", color="significant",
             color_discrete_map={True: "#2c7fb8", False: "#cccccc"},
             labels={"r": f"{method.title()} r", "lag": "Lag (days)"},
             title=f"{driver} (t) vs {outcome} (t+lag)")
bar.add_hline(y=0, line_dash="dot", line_color="grey")
st.plotly_chart(bar, use_container_width=True)

sig = lag_df[lag_df["significant"]]
default_lag = int(sig.loc[sig["r"].abs().idxmax(), "lag"]) if not sig.empty else 0
sel_lag = st.selectbox("Inspect lag", list(lag_df["lag"]), index=list(lag_df["lag"]).index(default_lag))

row = lag_df[lag_df["lag"] == sel_lag].iloc[0]
scatter_df = pd.DataFrame({
    "date": udf["date"], driver: udf[driver], outcome: udf[outcome].shift(-sel_lag),
}).dropna(subset=[driver, outcome])

st.subheader(f"Scatter at lag {sel_lag}")
if len(scatter_df) >= 2:
    fig = px.scatter(scatter_df, x=driver, y=outcome, trendline="ols",
                     hover_data=["date"],
                     labels={outcome: f"{outcome} (t+{sel_lag})"})
    st.plotly_chart(fig, use_container_width=True)

if row["too_few"] if "too_few" in row else (row["n"] < analysis_stats.MIN_N):
    st.warning(f"Too few overlapping points (n={int(row['n'])}) — no reliable estimate.")
elif not row["significant"]:
    st.info(f"r = {row['r']:.2f} (n={int(row['n'])}, p = {row['p']:.3f}) — **not significant**, likely noise.")
else:
    ci = "" if pd.isna(row["ci_low"]) else f", 95% CI [{row['ci_low']:.2f}, {row['ci_high']:.2f}]"
    st.success(f"r = {row['r']:.2f} (n={int(row['n'])}, p = {row['p']:.3f}{ci}) — significant at α=0.05.")
```

- [ ] **Step 2: Manual verification**

Run: `venv_garmin/Scripts/streamlit run app.py`
Log in, pick a date range of ≥ 30 days, open the "Lagged Correlations" page. Confirm:
- driver/outcome selectors populate from unified metrics (including activity/sleep/HRV columns when present);
- the correlation-vs-lag bar chart renders with significant bars highlighted;
- selecting a lag updates the scatter and the n/p/CI readout beneath it;
- a small range (< 3 overlapping points) shows the "too few points" warning rather than erroring.

- [ ] **Step 3: Commit**

```bash
git add pages/P4_Correlations.py
git commit -m "feat(p4): rework into lagged correlation explorer with significance"
```

---

### Task 7: New `P6` — Readiness → Realized Performance

**Files:**
- Create: `pages/P6_Readiness_and_Performance.py`

**Interfaces:**
- Consumes: `analysis_stats.build_unified_daily_frame`, `analysis_stats.aggregate_activities_daily`,
  `analysis_stats.readiness_score`, `analysis_stats.corr_with_significance`; same fetchers/processors as Task 6.
- Produces: new readiness page (no exported symbols).

Verified **manually**.

- [ ] **Step 1: Create the page**

Create `pages/P6_Readiness_and_Performance.py`:

```python
# pages/P6_Readiness_and_Performance.py — Readiness vs realized training performance
import sys
import os
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from utils import garmin_utils, data_processing, analysis_stats

st.set_page_config(layout="wide", page_title="Readiness & Performance")
st.title("Morning Readiness vs Realized Performance")
st.caption("Readiness is a transparent z-scored composite of recovery signals — not a Garmin metric.")


def _process_daily(df_raw):
    if df_raw.empty:
        return pd.DataFrame()
    df = df_raw.copy()
    df["calendarDate"] = pd.to_datetime(df["calendarDate"]).dt.date
    if "sleepingSeconds" in df.columns:
        df["sleepingHours"] = pd.to_numeric(df["sleepingSeconds"], errors="coerce") / 3600
    for col in ["restingHeartRate", "averageStressLevel", "bodyBatteryAtWakeTime"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("calendarDate").reset_index(drop=True)


@st.cache_data(ttl=300)
def load_unified(_client, _username, _start, _end, _force):
    daily = _process_daily(garmin_utils.get_daily_summaries(_client, _username, _start, _end, _force))
    hrv = data_processing.process_hrv_df(garmin_utils.get_hrv_data(_client, _username, _start, _end, _force))
    sleep = data_processing.process_sleep_df(garmin_utils.get_sleep_data(_client, _username, _start, _end, _force))
    acts = data_processing.process_general_activities_df(garmin_utils.get_activities(_client, _username, _start, _end, _force))
    acts_daily = analysis_stats.aggregate_activities_daily(acts)
    return analysis_stats.build_unified_daily_frame(daily, hrv, sleep, acts_daily)


if not st.session_state.get("logged_in", False):
    st.warning("Please log in first using the sidebar on the main page.")
    st.stop()

client = st.session_state.garmin_client
username = st.session_state.current_user
start = st.session_state.get("date_range_start", date.today() - timedelta(days=60))
end = st.session_state.get("date_range_end", date.today())
force = st.session_state.get("force_refresh", False)
window = st.sidebar.number_input("Readiness baseline window (days)", 7, 90, 28)

with st.spinner("Loading data & computing readiness..."):
    udf = load_unified(client, username, start, end, force)

if udf.empty:
    st.info("No daily data available for the selected range.")
    st.stop()

scored = analysis_stats.readiness_score(udf, baseline_window=int(window))
comp_cols = [c for c in scored.columns if c.startswith("z_")]

if scored["readiness"].notna().sum() == 0:
    st.info("Not enough history to compute a readiness baseline. Widen the date range.")
    st.stop()

used = [c.replace("z_", "") for c in comp_cols]
st.markdown(f"**Readiness components used:** {', '.join(used) if used else 'none'}")

st.subheader("Readiness over time")
line = px.line(scored, x="date", y="readiness", markers=True,
               labels={"readiness": "Readiness (z, 0 = personal baseline)"})
line.add_hline(y=0, line_dash="dot", line_color="grey")
st.plotly_chart(line, use_container_width=True)
with st.expander("Show individual readiness components"):
    comp_long = scored.melt(id_vars="date", value_vars=comp_cols,
                            var_name="component", value_name="z")
    st.plotly_chart(px.line(comp_long, x="date", y="z", color="component"), use_container_width=True)

perf_options = [c for c in ["aerobic_efficiency", "mean_pace_min_per_km", "total_aerobic_te"]
                if c in scored.columns and scored[c].notna().sum() >= 2]
if not perf_options:
    st.info("No training-performance metric available in this range (no activities with the needed fields).")
    st.stop()

perf = st.selectbox("Performance metric", perf_options)
st.subheader(f"Readiness vs {perf} (same day)")
pair = scored[["date", "readiness", perf]].dropna()
if len(pair) >= 2:
    fig = px.scatter(pair, x="readiness", y=perf, trendline="ols", hover_data=["date"])
    st.plotly_chart(fig, use_container_width=True)
    stat = analysis_stats.corr_with_significance(pair["readiness"], pair[perf])
    if stat["too_few"]:
        st.warning(f"Too few paired days (n={stat['n']}).")
    elif stat["p"] >= analysis_stats.DEFAULT_ALPHA:
        st.info(f"r = {stat['r']:.2f} (n={stat['n']}, p = {stat['p']:.3f}) — not significant.")
    else:
        ci = "" if pd.isna(stat["ci_low"]) else f", 95% CI [{stat['ci_low']:.2f}, {stat['ci_high']:.2f}]"
        st.success(f"r = {stat['r']:.2f} (n={stat['n']}, p = {stat['p']:.3f}{ci}).")

st.subheader("Readiness & performance over time")
dual = make_subplots(specs=[[{"secondary_y": True}]])
dual.add_trace(go.Scatter(x=scored["date"], y=scored["readiness"], name="Readiness"), secondary_y=False)
dual.add_trace(go.Scatter(x=pair["date"], y=pair[perf], name=perf, mode="markers+lines"), secondary_y=True)
dual.update_yaxes(title_text="Readiness (z)", secondary_y=False)
dual.update_yaxes(title_text=perf, secondary_y=True, showgrid=False)
st.plotly_chart(dual, use_container_width=True)
```

- [ ] **Step 2: Manual verification**

Run: `venv_garmin/Scripts/streamlit run app.py`
Pick a date range of ≥ 45 days (readiness needs baseline history). Open "Readiness & Performance". Confirm:
- the readiness line renders and the component expander lists the z-scored signals actually present;
- when HRV is absent, the "components used" line reflects that and the score still computes;
- selecting a performance metric renders the scatter with an n/p/CI verdict;
- a too-short range shows the "widen the date range" message instead of erroring.

- [ ] **Step 3: Commit**

```bash
git add pages/P6_Readiness_and_Performance.py
git commit -m "feat(p6): readiness composite vs realized performance page"
```

---

### Task 8 (optional): Correlation heatmap on `P4`

**Files:**
- Modify: `pages/P4_Correlations.py`

**Interfaces:**
- Consumes: `analysis_stats.corr_with_significance`; the `udf` and `numeric_cols` already in P4.
- Produces: an added heatmap section (no exported symbols).

Include only if Tasks 1–7 landed without overrunning. Verified **manually**.

- [ ] **Step 1: Append the heatmap section to `pages/P4_Correlations.py`**

Add at the end of the file:

```python
st.markdown("---")
st.subheader("Correlation heatmap (lag 0, significant cells only)")
import numpy as np  # local import; keeps the section self-contained

heat_cols = st.multiselect("Metrics", numeric_cols,
                           default=numeric_cols[: min(6, len(numeric_cols))])
if len(heat_cols) >= 2:
    mat = pd.DataFrame(np.nan, index=heat_cols, columns=heat_cols)
    for i in heat_cols:
        for j in heat_cols:
            s = analysis_stats.corr_with_significance(udf[i], udf[j], method=method)
            # blank non-significant off-diagonal cells
            if i == j:
                mat.loc[i, j] = 1.0
            elif not s["too_few"] and pd.notna(s["p"]) and s["p"] < analysis_stats.DEFAULT_ALPHA:
                mat.loc[i, j] = s["r"]
    heat = px.imshow(mat, text_auto=".2f", zmin=-1, zmax=1,
                     color_continuous_scale="RdBu", aspect="auto")
    st.plotly_chart(heat, use_container_width=True)
    st.caption("Blank cells = not significant at α=0.05 or too few points.")
```

- [ ] **Step 2: Manual verification**

Reload the P4 page; pick ≥ 3 metrics; confirm the heatmap renders with non-significant cells blank and the diagonal = 1.

- [ ] **Step 3: Commit**

```bash
git add pages/P4_Correlations.py
git commit -m "feat(p4): optional significance-masked correlation heatmap"
```

---

## Self-Review

**Spec coverage:**
- Feature 1 (Lagged Correlation Explorer, reworks P4) → Task 6 (+ Tasks 1,2 stats). ✓
- Feature 2 (Readiness → Performance, new P6) → Task 7 (+ Tasks 3,4,5). ✓
- Feature 3 (optional heatmap) → Task 8. ✓
- Pure `utils/analysis_stats.py` with unit tests → Tasks 1–5. ✓
- Daily activity aggregation merged into unified frame → Tasks 3 & 5, consumed in 6 & 7. ✓
- Statistical honesty (n, p, CI, small-sample guard, rank option, exploratory caveat) → Task 1 primitive + surfaced in Tasks 6/7/8. ✓
- Graceful degradation when HRV missing → `readiness_score` skips missing components (Task 4) + P6 "components used" line (Task 7). ✓
- No Streamlit/Garmin in stats module → enforced in Task 1 header and constraints. ✓
- Keep-vs-replace `merge_sleep_hrv_activity_data` (spec open question) → resolved: **superseded** by `build_unified_daily_frame`; the old function is left untouched (still used elsewhere? it is not imported by any current page), so no removal needed and no duplication is introduced on the SP2 path.

**Placeholder scan:** No TBD/TODO/"handle edge cases" — every code step contains runnable code. ✓

**Type consistency:** `corr_with_significance` returns the same dict keys used by `lagged_correlation` and both pages; `aggregate_activities_daily` output columns (`aerobic_efficiency`, `mean_pace_min_per_km`, `total_aerobic_te`) match the P6 `perf_options`; `readiness_score` emits `readiness` / `readiness_n_components` / `z_*` consumed by P6; `build_unified_daily_frame` emits `date` consumed everywhere. ✓

**Note for executor:** P4 Step (row `too_few`): `lagged_correlation` rows do not carry a `too_few` column, so the page falls back to the `n < MIN_N` check — the code already handles both via the conditional. If preferred, add `too_few` to the `lagged_correlation` output in Task 2 and simplify; not required.
