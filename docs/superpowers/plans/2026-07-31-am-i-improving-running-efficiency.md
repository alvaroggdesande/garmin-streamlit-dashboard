# "Am I Improving?" Running Efficiency Page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a focused "Am I Improving?" page that answers *am I getting fitter?* and *can I do more with less heart rate?* from per-run summaries, using an Efficiency-Factor trend, a pace-at-fixed-HR comparison, and a plain-language verdict with statistical honesty.

**Architecture:** A new pure, unit-tested module `utils/efficiency_stats.py` computes everything (Efficiency Factor per run, weekly EF trend, pace-at-reference-HR linear fit, improvement verdict). A new Streamlit page `pages/P7_Am_I_Improving.py` renders it with its own 6-month-default lookback control, reusing `garmin_utils.get_activities` (a single API call) and `data_processing.process_activities_df`. Two misleading charts are removed from `pages/P2_Running_performance.py`.

**Tech Stack:** Python, pandas, numpy, scipy.stats, Streamlit, Plotly, pytest. Run tests with `venv_garmin/Scripts/python.exe -m pytest -q` from repo root.

## Global Constraints

- **Pure module rule:** `utils/efficiency_stats.py` imports only numpy/pandas/scipy — **no Streamlit, no garminconnect** — so every function is unit-testable with small in-memory DataFrames (mirrors `utils/analysis_stats.py`).
- **No new API calls / no 429 risk:** the page uses only per-run activity summaries already fetched via `get_activities` (one `get_activities_by_date` range call). Do **not** add per-activity detail/stream fetching. Within-run aerobic decoupling is explicitly out of scope.
- **Efficiency Factor** `EF = speed / avgHR` with `speed = distance_metres / duration_minutes` → units of metres per heartbeat; **higher is fitter**.
- **Easy run** = `time_in_zone2_minutes / duration_minutes >= 0.60`.
- **Weekly aggregation uses the median** (few runs/week; outlier-robust); weekly band is the **IQR (25th–75th percentile)**.
- **Verdict** compares **last 6 weeks vs the prior 6 weeks** of easy-run EF; confidence via **Mann-Whitney U** (`p < 0.05` = confident); **muted** when either window has fewer than `MIN_WINDOW_N = 4` runs.
- **Reference HR default = 145 bpm** (adjustable in the UI).
- **Purity of time:** any function needing "now" takes an explicit `as_of: date` argument (never calls `date.today()` internally) so it stays deterministic and testable. The page passes `date.today()`.
- Pure helpers are pytest-tested; the Streamlit page is browser-verified by the owner (no automated UI test), consistent with repo convention.

---

## File Structure

- **Create** `utils/efficiency_stats.py` — pure metrics: `efficiency_factor`, `add_efficiency_columns`, `weekly_ef_trend`, `pace_at_reference_hr`, `improvement_verdict`.
- **Create** `tests/test_efficiency_stats.py` — pure unit tests for all of the above.
- **Modify** `utils/data_processing.py` — add `process_running_activities_df` (the working per-run processor, lifted from P2's in-file `local_process_activities_df`) so the new page and P2 share one processor instead of duplicating it.
- **Modify** `tests/` — add `tests/test_data_processing_running.py` for `process_running_activities_df`.
- **Create** `pages/P7_Am_I_Improving.py` — the new page (lookback control, verdict banner, EF trend, pace-at-HR frontier, hard-effort trend, VO2 reference).
- **Modify** `pages/P2_Running_performance.py` — remove the two misleading charts and switch to the shared `process_running_activities_df`.

**Why a shared processor (read before Task 5):** the existing
`data_processing.process_activities_df` is **not** usable here — it omits
`activityType_key`, parses `startTimeGMT` with `unit='ms'` (the API returns a
datetime *string* → all `NaT`), reads HR-zone times from a nested
`timeInHrZone` field instead of the real `hrTimeInZone_{i}` columns (so
`time_in_zone2_minutes` would be all zeros and every run would count as
non-easy), and emits `vo2_max_activity` rather than `vo2MaxValue_activity`.
P2's in-file `local_process_activities_df` is the version that actually works
on real data; Task 5 promotes it to a shared, tested function.

---

### Task 1: `efficiency_factor` + `add_efficiency_columns`

**Files:**
- Create: `utils/efficiency_stats.py`
- Create: `tests/test_efficiency_stats.py`

**Interfaces:**
- Produces:
  - `efficiency_factor(distance_m, duration_min, avg_hr) -> float` — returns `(distance_m / duration_min) / avg_hr`, or `float('nan')` if any input is missing/non-positive.
  - `add_efficiency_columns(runs_df) -> DataFrame` — copies the frame and adds `ef` (per-row Efficiency Factor from `distance_km`, `duration_minutes`, `avgHR`) and `is_easy` (bool: `time_in_zone2_minutes / duration_minutes >= EASY_Z2_FRACTION`). Missing `time_in_zone2_minutes` → `is_easy = False`.
  - Module constants: `EASY_Z2_FRACTION = 0.60`, `MIN_WINDOW_N = 4`, `REF_HR_DEFAULT = 145`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_efficiency_stats.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_efficiency_stats.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'utils.efficiency_stats'`.

- [ ] **Step 3: Implement the module skeleton + functions**

Create `utils/efficiency_stats.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_efficiency_stats.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add utils/efficiency_stats.py tests/test_efficiency_stats.py
git commit -m "feat(efficiency): efficiency_factor + add_efficiency_columns"
```

---

### Task 2: `weekly_ef_trend`

**Files:**
- Modify: `utils/efficiency_stats.py`
- Modify: `tests/test_efficiency_stats.py`

**Interfaces:**
- Consumes: a DataFrame with `date` (datetime.date or datetime) and `ef` columns (e.g. from `add_efficiency_columns` filtered to easy runs).
- Produces:
  - `weekly_ef_trend(ef_df) -> DataFrame` with columns `week_start` (Monday, datetime64), `ef_median`, `n`, `ef_q25`, `ef_q75`, sorted by `week_start`. Rows with NaN `ef` are dropped before grouping. Empty input → empty frame with those columns.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_efficiency_stats.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_efficiency_stats.py::test_weekly_ef_trend_medians_and_counts -v`
Expected: FAIL — `AttributeError: module 'utils.efficiency_stats' has no attribute 'weekly_ef_trend'`.

- [ ] **Step 3: Implement `weekly_ef_trend`**

Add to `utils/efficiency_stats.py`:

```python
_WEEKLY_COLS = ["week_start", "ef_median", "n", "ef_q25", "ef_q75"]


def weekly_ef_trend(ef_df):
    """Weekly (Mon-start) median EF with IQR band and run count."""
    df = ef_df[["date", "ef"]].copy()
    df["ef"] = pd.to_numeric(df["ef"], errors="coerce")
    df = df.dropna(subset=["ef"])
    if df.empty:
        return pd.DataFrame(columns=_WEEKLY_COLS)
    df["date"] = pd.to_datetime(df["date"])
    df["week_start"] = df["date"].dt.to_period("W-SUN").dt.start_time  # Monday start
    grouped = df.groupby("week_start")["ef"]
    out = pd.DataFrame({
        "ef_median": grouped.median(),
        "n": grouped.size(),
        "ef_q25": grouped.quantile(0.25),
        "ef_q75": grouped.quantile(0.75),
    }).reset_index().sort_values("week_start").reset_index(drop=True)
    return out[_WEEKLY_COLS]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_efficiency_stats.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add utils/efficiency_stats.py tests/test_efficiency_stats.py
git commit -m "feat(efficiency): weekly_ef_trend median + IQR band"
```

---

### Task 3: `pace_at_reference_hr`

**Files:**
- Modify: `utils/efficiency_stats.py`
- Modify: `tests/test_efficiency_stats.py`

**Interfaces:**
- Consumes: DataFrame with `pace_min_per_km` and `avgHR` columns.
- Produces:
  - `pace_at_reference_hr(runs_df, ref_hr=REF_HR_DEFAULT, min_n=5, min_hr_spread=8) -> dict` with keys `pace_at_ref` (float or None), `slope`, `intercept`, `n`, `ok` (bool), `reason` (str). Fits `pace_min_per_km ~ avgHR` by least squares (`scipy.stats.linregress`). Returns `ok=False` with `pace_at_ref=None` when fewer than `min_n` valid rows or the HR range is below `min_hr_spread`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_efficiency_stats.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_efficiency_stats.py::test_pace_at_reference_hr_linear_fit -v`
Expected: FAIL — `AttributeError: module 'utils.efficiency_stats' has no attribute 'pace_at_reference_hr'`.

- [ ] **Step 3: Implement `pace_at_reference_hr`**

Add to `utils/efficiency_stats.py`:

```python
def pace_at_reference_hr(runs_df, ref_hr=REF_HR_DEFAULT, min_n=5, min_hr_spread=8):
    """Predict pace (min/km) at a reference HR from a linear pace~HR fit."""
    result = {"pace_at_ref": None, "slope": np.nan, "intercept": np.nan,
              "n": 0, "ok": False, "reason": ""}
    df = runs_df[["avgHR", "pace_min_per_km"]].apply(pd.to_numeric, errors="coerce").dropna()
    result["n"] = int(len(df))
    if len(df) < min_n:
        result["reason"] = f"need at least {min_n} runs, have {len(df)}"
        return result
    if (df["avgHR"].max() - df["avgHR"].min()) < min_hr_spread:
        result["reason"] = f"HR spread below {min_hr_spread} bpm — cannot fit a trustworthy line"
        return result
    fit = stats.linregress(df["avgHR"], df["pace_min_per_km"])
    result.update({
        "slope": float(fit.slope),
        "intercept": float(fit.intercept),
        "pace_at_ref": float(fit.intercept + fit.slope * ref_hr),
        "ok": True,
        "reason": "ok",
    })
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_efficiency_stats.py -v`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
git add utils/efficiency_stats.py tests/test_efficiency_stats.py
git commit -m "feat(efficiency): pace_at_reference_hr linear fit with guards"
```

---

### Task 4: `improvement_verdict`

**Files:**
- Modify: `utils/efficiency_stats.py`
- Modify: `tests/test_efficiency_stats.py`

**Interfaces:**
- Consumes: easy-run DataFrame with `date` and `ef` columns; an explicit `as_of` date.
- Produces:
  - `improvement_verdict(easy_ef_df, as_of, recent_weeks=6, min_n=MIN_WINDOW_N, flat_band_pct=1.5) -> dict` with keys: `direction` (`"up"`/`"flat"`/`"down"`), `pct_change` (float or None), `n_recent`, `n_prior`, `confident` (bool), `p_value` (float or None), `muted` (bool), `reason` (str).
  - Windows: recent = `(as_of - recent_weeks) .. as_of`; prior = `(as_of - 2*recent_weeks) .. (as_of - recent_weeks)`. `pct_change = (median_recent - median_prior) / median_prior * 100`. Direction: `up` if `pct_change >= flat_band_pct`, `down` if `<= -flat_band_pct`, else `flat`. `confident` = Mann-Whitney U `p < 0.05`. `muted = True` (and `confident = False`) when either window has `< min_n` runs.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_efficiency_stats.py`:

```python
from datetime import date, timedelta


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_efficiency_stats.py::test_improvement_verdict_up_and_confident -v`
Expected: FAIL — `AttributeError: module 'utils.efficiency_stats' has no attribute 'improvement_verdict'`.

- [ ] **Step 3: Implement `improvement_verdict`**

Add to `utils/efficiency_stats.py`:

```python
def improvement_verdict(easy_ef_df, as_of, recent_weeks=6, min_n=MIN_WINDOW_N,
                        flat_band_pct=1.5):
    """Compare recent vs prior EF windows into a plain-language verdict."""
    out = {"direction": "flat", "pct_change": None, "n_recent": 0, "n_prior": 0,
           "confident": False, "p_value": None, "muted": True, "reason": ""}

    df = easy_ef_df[["date", "ef"]].copy()
    df["ef"] = pd.to_numeric(df["ef"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.dropna(subset=["ef"])

    recent_start = as_of - timedelta(weeks=recent_weeks)
    prior_start = as_of - timedelta(weeks=2 * recent_weeks)
    recent = df[(df["date"] > recent_start) & (df["date"] <= as_of)]
    prior = df[(df["date"] > prior_start) & (df["date"] <= recent_start)]
    out["n_recent"], out["n_prior"] = int(len(recent)), int(len(prior))

    if len(recent) < min_n or len(prior) < min_n:
        out["reason"] = f"need >= {min_n} easy runs in each 6-week window"
        return out

    med_recent = float(recent["ef"].median())
    med_prior = float(prior["ef"].median())
    pct = (med_recent - med_prior) / med_prior * 100 if med_prior else 0.0
    _, p = stats.mannwhitneyu(recent["ef"], prior["ef"], alternative="two-sided")

    direction = "up" if pct >= flat_band_pct else "down" if pct <= -flat_band_pct else "flat"
    out.update({
        "direction": direction,
        "pct_change": float(pct),
        "confident": bool(p < 0.05),
        "p_value": float(p),
        "muted": False,
        "reason": "ok",
    })
    return out
```

Add the import at the top of `utils/efficiency_stats.py` (with the other imports):

```python
from datetime import timedelta
```

- [ ] **Step 4: Run the full efficiency test suite**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_efficiency_stats.py -v`
Expected: PASS (12 passed).

- [ ] **Step 5: Commit**

```bash
git add utils/efficiency_stats.py tests/test_efficiency_stats.py
git commit -m "feat(efficiency): improvement_verdict with Mann-Whitney confidence"
```

---

### Task 5: shared `process_running_activities_df` in `data_processing`

**Files:**
- Modify: `utils/data_processing.py`
- Create: `tests/test_data_processing_running.py`

**Interfaces:**
- Produces: `process_running_activities_df(activities_df_raw) -> DataFrame`. Given raw activities (as returned by `garmin_utils.get_activities`), returns a processed frame with at least: `activityType_key`, `date` (from `startTimeLocal`), `duration_minutes`, `distance_km`, `pace_min_per_km`, `avgHR`, `maxHR`, `avgCadence`, `vo2MaxValue_activity`, `aerobicTE`, `anaerobicTE`, and `time_in_zone{1..5}_minutes` (from `hrTimeInZone_{i}` columns), sorted by `date`. Empty input → empty DataFrame. This is the working logic currently living in P2 as `local_process_activities_df`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_data_processing_running.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_data_processing_running.py -v`
Expected: FAIL — `AttributeError: module 'utils.data_processing' has no attribute 'process_running_activities_df'`.

- [ ] **Step 3: Add `process_running_activities_df`**

Add to `utils/data_processing.py` (this is the exact logic from P2's `local_process_activities_df`):

```python
def process_running_activities_df(activities_df_raw):
    """Process raw Garmin activities into per-run running metrics.

    Shared by the Running Performance page and the Am-I-Improving page.
    """
    if activities_df_raw is None or activities_df_raw.empty:
        return pd.DataFrame()

    df = activities_df_raw.copy()
    if 'activityType' in df.columns:
        df['activityType_key'] = df['activityType'].apply(
            lambda x: x.get('typeKey') if isinstance(x, dict) else x if isinstance(x, str) else None
        )
    df['startTimeGMT_dt'] = pd.to_datetime(df['startTimeGMT'], errors='coerce')
    df['date'] = pd.to_datetime(df['startTimeLocal'], errors='coerce').dt.date

    df['duration_seconds'] = pd.to_numeric(df['duration'], errors='coerce')
    df['duration_minutes'] = df['duration_seconds'] / 60

    df['distance_meters'] = pd.to_numeric(df['distance'], errors='coerce')
    df['distance_km'] = df['distance_meters'] / 1000

    mask_pace = (df['distance_km'] > 0) & (df['duration_minutes'] > 0)
    df['pace_min_per_km'] = np.nan
    df.loc[mask_pace, 'pace_min_per_km'] = df.loc[mask_pace, 'duration_minutes'] / df.loc[mask_pace, 'distance_km']

    df['avgHR'] = pd.to_numeric(df['averageHR'], errors='coerce')
    df['maxHR'] = pd.to_numeric(df['maxHR'], errors='coerce')

    if 'averageRunningCadenceInStepsPerMinute' in df.columns:
        df['avgCadence'] = pd.to_numeric(df['averageRunningCadenceInStepsPerMinute'], errors='coerce') * 2
    if 'maxRunningCadenceInStepsPerMinute' in df.columns:
        df['maxCadence'] = pd.to_numeric(df['maxRunningCadenceInStepsPerMinute'], errors='coerce') * 2

    if 'vO2MaxValue' in df.columns:
        df['vo2MaxValue_activity'] = pd.to_numeric(df['vO2MaxValue'], errors='coerce')

    df['aerobicTE'] = pd.to_numeric(df['aerobicTrainingEffect'], errors='coerce')
    df['anaerobicTE'] = pd.to_numeric(df['anaerobicTrainingEffect'], errors='coerce')

    for i in range(1, 6):
        col_name = f'hrTimeInZone_{i}'
        if col_name in df.columns:
            df[f'time_in_zone{i}_seconds'] = pd.to_numeric(df[col_name], errors='coerce').fillna(0)
            df[f'time_in_zone{i}_minutes'] = df[f'time_in_zone{i}_seconds'] / 60
        else:
            df[f'time_in_zone{i}_seconds'] = 0.0
            df[f'time_in_zone{i}_minutes'] = 0.0

    df = df.sort_values(by='date').reset_index(drop=True)
    return df
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv_garmin/Scripts/python.exe -m pytest tests/test_data_processing_running.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add utils/data_processing.py tests/test_data_processing_running.py
git commit -m "feat(data): shared process_running_activities_df (lifted from P2)"
```

---

### Task 6: `pages/P7_Am_I_Improving.py` — the page

**Files:**
- Create: `pages/P7_Am_I_Improving.py`

**Interfaces:**
- Consumes: `garmin_utils.get_activities`, `data_processing.process_running_activities_df` (Task 5), `data_processing.format_time_minutes_seconds`, and all of `efficiency_stats` (Tasks 1–4).
- Produces: the rendered page (no exported symbols).

Verified by **byte-compile + symbol/import checks**; live Streamlit behavior is owner-deferred.

- [ ] **Step 1: Create the page**

Create `pages/P7_Am_I_Improving.py`:

```python
import sys
import os
from datetime import date, timedelta

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils import garmin_utils, data_processing, efficiency_stats as eff

st.set_page_config(layout="wide", page_title="Am I Improving?")
st.title("📈 Am I Improving?")
st.caption("Are you doing more with less heart rate? Efficiency Factor = metres travelled per heartbeat — higher is fitter.")

if not st.session_state.get("logged_in", False):
    st.warning("Please log in first using the sidebar on the main page.")
    st.stop()

client = st.session_state.garmin_client
username = st.session_state.current_user

# --- Own lookback control (independent of the global 30-day filter) ---
st.sidebar.header("Trend window")
preset = st.sidebar.radio("Lookback", ["3 months", "6 months", "1 year", "All (2 years)"],
                          index=1, key="improving_lookback")
months = {"3 months": 3, "6 months": 6, "1 year": 12, "All (2 years)": 24}[preset]
end_date = date.today()
start_date = end_date - timedelta(days=int(months * 30.4))
ref_hr = st.sidebar.number_input("Reference HR for pace comparison (bpm)",
                                 min_value=100, max_value=200,
                                 value=eff.REF_HR_DEFAULT, key="improving_ref_hr")
force_refresh = st.session_state.get("force_refresh", False)


@st.cache_data(ttl=300)
def _load_runs(_client, _username, _start, _end, _force):
    raw = garmin_utils.get_activities(_client, _username, _start, _end, _force)
    processed = data_processing.process_running_activities_df(raw)
    if processed.empty or "activityType_key" not in processed.columns:
        return pd.DataFrame()
    runs = processed[processed["activityType_key"] == "running"].copy()
    return runs


with st.spinner("Loading your running history..."):
    runs = _load_runs(client, username, start_date, end_date, force_refresh)

if runs.empty:
    st.info("No running activities found in this window. Try a longer lookback.")
    st.stop()

runs = eff.add_efficiency_columns(runs)
runs["date"] = pd.to_datetime(runs["date"])
easy = runs[runs["is_easy"]].copy()

# --- Verdict banner ---
verdict = eff.improvement_verdict(easy, as_of=end_date)
arrow = {"up": "⬆️", "flat": "➡️", "down": "⬇️"}[verdict["direction"]]
if verdict["muted"]:
    st.info(f"Not enough easy (Zone 2) runs yet to judge a trend "
            f"(recent: {verdict['n_recent']}, prior: {verdict['n_prior']}; "
            f"need {eff.MIN_WINDOW_N} in each 6-week window).")
else:
    pct = verdict["pct_change"]
    conf = "likely real" if verdict["confident"] else "within noise — not conclusive"
    verb = {"up": "up", "flat": "unchanged", "down": "down"}[verdict["direction"]]
    msg = (f"{arrow} Over the last 6 weeks your easy-run efficiency is **{verb} "
           f"{abs(pct):.1f}%** vs the prior 6 weeks "
           f"(n = {verdict['n_recent']} recent / {verdict['n_prior']} prior — {conf}).")
    (st.success if verdict["direction"] == "up" and verdict["confident"]
     else st.warning if verdict["direction"] == "down" and verdict["confident"]
     else st.info)(msg)

st.markdown("---")

# --- EF weekly trend (easy runs) ---
st.subheader("Efficiency Factor trend (easy runs, weekly median)")
trend = eff.weekly_ef_trend(easy)
if trend.empty:
    st.info("No easy-run efficiency data to plot yet.")
else:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=trend["week_start"], y=trend["ef_q75"], mode="lines",
        line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=trend["week_start"], y=trend["ef_q25"], mode="lines", fill="tonexty",
        line=dict(width=0), fillcolor="rgba(66,135,245,0.15)",
        name="IQR (25–75%)", hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=trend["week_start"], y=trend["ef_median"], mode="lines+markers",
        name="Median EF", line=dict(color="rgb(66,135,245)")))
    fig.update_layout(xaxis_title="Week", yaxis_title="Efficiency Factor (m/beat)",
                      hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Higher is better. The line rising over time means you're covering more ground per heartbeat.")

st.markdown("---")

# --- Pace at a fixed HR (frontier) ---
st.subheader(f"Pace vs Heart Rate — are you faster at {int(ref_hr)} bpm?")
frontier = runs.dropna(subset=["pace_min_per_km", "avgHR"]).copy()
if len(frontier) >= 2:
    frontier["days_ago"] = (pd.Timestamp(end_date) - frontier["date"]).dt.days
    fig2 = px.scatter(
        frontier, x="avgHR", y="pace_min_per_km", color="days_ago",
        color_continuous_scale="Blues_r", hover_data=["date", "distance_km"],
        labels={"avgHR": "Average HR (bpm)", "pace_min_per_km": "Pace (min/km)",
                "days_ago": "Days ago"},
        title="Each dot is a run — brighter = more recent")
    fig2.update_yaxes(autorange="reversed")  # faster pace lower

    # earlier-half vs recent-half fit lines
    midpoint = frontier["date"].median()
    recent_half = frontier[frontier["date"] >= midpoint]
    earlier_half = frontier[frontier["date"] < midpoint]
    p_recent = eff.pace_at_reference_hr(recent_half, ref_hr=ref_hr)
    p_earlier = eff.pace_at_reference_hr(earlier_half, ref_hr=ref_hr)
    hr_line = pd.Series(range(int(frontier["avgHR"].min()), int(frontier["avgHR"].max()) + 1))
    for res, name, dash in [(p_earlier, "Earlier fit", "dot"), (p_recent, "Recent fit", "solid")]:
        if res["ok"]:
            fig2.add_trace(go.Scatter(
                x=hr_line, y=res["intercept"] + res["slope"] * hr_line,
                mode="lines", name=name, line=dict(dash=dash)))
    st.plotly_chart(fig2, use_container_width=True)

    if p_recent["ok"] and p_earlier["ok"]:
        now = data_processing.format_time_minutes_seconds(p_recent["pace_at_ref"])
        then = data_processing.format_time_minutes_seconds(p_earlier["pace_at_ref"])
        st.success(f"At {int(ref_hr)} bpm you now run **{now}/km** — vs **{then}/km** earlier in this window.")
    else:
        st.info("Not enough spread in HR/pace to estimate pace-at-HR reliably yet.")
else:
    st.info("Not enough runs with pace and HR to draw the frontier.")

st.markdown("---")

# --- Hard-effort pace trend ---
st.subheader("Hard-effort speed (weekly best pace on harder runs)")
hard = runs.copy()
if "avgHR" in hard.columns and not easy.empty:
    hard = hard[~hard["is_easy"]].dropna(subset=["pace_min_per_km", "date"])
    if not hard.empty:
        hard_weekly = (hard.set_index("date")
                       .resample("W-MON", label="left", closed="left")["pace_min_per_km"]
                       .min().reset_index().dropna(subset=["pace_min_per_km"]))
        fig3 = px.line(hard_weekly, x="date", y="pace_min_per_km", markers=True,
                       labels={"date": "Week", "pace_min_per_km": "Best pace (min/km)"},
                       title="Fastest pace among harder runs, per week")
        fig3.update_yaxes(autorange="reversed")
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("No harder (non-easy) runs in this window yet.")
else:
    st.info("No harder-run data to show.")

st.markdown("---")

# --- VO2 max reference ---
with st.expander("VO2 max (Garmin's own estimate — for reference)"):
    if "vo2MaxValue_activity" in runs.columns and runs["vo2MaxValue_activity"].notna().any():
        vo2 = runs[["date", "vo2MaxValue_activity"]].dropna().sort_values("date")
        fig4 = px.line(vo2, x="date", y="vo2MaxValue_activity", markers=True,
                       labels={"vo2MaxValue_activity": "VO2 max"})
        st.plotly_chart(fig4, use_container_width=True)
    else:
        st.info("No VO2 max values recorded in this window.")
```

- [ ] **Step 2: Byte-compile and import/symbol checks**

Run: `venv_garmin/Scripts/python.exe -m py_compile pages/P7_Am_I_Improving.py`
Expected: exit 0.
Run: `venv_garmin/Scripts/python.exe -c "from utils import efficiency_stats as e; [getattr(e, n) for n in ('efficiency_factor','add_efficiency_columns','weekly_ef_trend','pace_at_reference_hr','improvement_verdict')]; print('efficiency symbols OK')"`
Expected: prints `efficiency symbols OK`.
Run: `venv_garmin/Scripts/python.exe -c "from utils import data_processing as d; d.process_running_activities_df; d.format_time_minutes_seconds; print('data_processing symbols OK')"`
Expected: prints `data_processing symbols OK`. (The page depends on `process_running_activities_df` emitting `activityType_key` / `time_in_zone2_minutes` / `vo2MaxValue_activity` / `pace_min_per_km` / `avgHR` / `distance_km` / `duration_minutes` — all covered by Task 5's test.)

- [ ] **Step 3: Manual verification (owner, deferred)**

Locally: `venv_garmin/Scripts/streamlit run app.py`, open **Am I Improving?** in the page list, pick a 6-month lookback, and confirm the verdict banner, EF trend, pace-vs-HR frontier with fit lines, hard-effort trend, and VO2 expander all render (or show their friendly empty states).

- [ ] **Step 4: Commit**

```bash
git add pages/P7_Am_I_Improving.py
git commit -m "feat(page): Am I Improving running-efficiency page"
```

---

### Task 7: Prune the two misleading charts from P2 and adopt the shared processor

**Files:**
- Modify: `pages/P2_Running_performance.py`

**Interfaces:**
- Consumes: `data_processing.process_running_activities_df` (Task 5).
- Produces: a slimmer P2 (no exported symbols).

Verified by **byte-compile + grep checks**; live behavior owner-deferred.

- [ ] **Step 1: Remove the "Selected Running Metrics Over Time" block**

In `pages/P2_Running_performance.py`, delete the block that begins with the
`metrics_to_plot = { ... }` dictionary and its `st.multiselect(...)` through the
`st.plotly_chart(fig_trends, use_container_width=True)` call and the
`st.markdown("---")` that closes that section (the multi-line "Selected Running
Metrics Over Time" chart described in the header `st.header("Running Activity Trends")`).
Keep the `st.header("Running Activity Trends")` line only if a chart still
follows it; otherwise remove that header too. Do not touch the HR-zone
distribution section that follows.

- [ ] **Step 2: Remove the two-axis "Easy Run Pace and Average HR" chart**

Delete the "**2. Aerobic Efficiency (Easy Run Pace - Zone 2)**" section: the
`st.subheader("Aerobic Efficiency (Easy Runs - Zone 2)")` line, its caption, the
local `identify_easy_runs` function, the `easy_runs_df = identify_easy_runs(...)`
call, the whole `fig_aerobic_eff` construction and its `st.plotly_chart`, the
follow-up `st.info("Consider tracking Aerobic Decoupling ...")`, the `else`
branch's `st.info`, and the trailing `st.markdown("---")` for that section.
Leave the neighboring "Pace Improvement Trends by Dominant Heart Rate Zone"
and "Long Run Progression" sections intact.

- [ ] **Step 3: Replace P2's local processor with the shared one**

Delete the entire in-file `def local_process_activities_df(activities_df_raw):`
definition (and its surrounding explanatory comments). Then change its single
call site inside `load_activity_data`:

```python
    activities_processed = local_process_activities_df(activities_raw)
```

to:

```python
    activities_processed = data_processing.process_running_activities_df(activities_raw)
```

`data_processing` is already imported at the top of P2 (`from utils import garmin_utils, data_processing, plotting_utils`). The shared function (Task 5) is byte-for-byte the same logic, so P2's behavior is unchanged.

- [ ] **Step 4: Byte-compile and confirm removals**

Run: `venv_garmin/Scripts/python.exe -m py_compile pages/P2_Running_performance.py`
Expected: exit 0.
Run: `venv_garmin/Scripts/python.exe -c "s=open('pages/P2_Running_performance.py').read(); assert 'Selected Running Metrics Over Time' not in s and 'metrics_to_plot' not in s, 'metrics-over-time chart still present'; assert 'fig_aerobic_eff' not in s, 'two-axis aerobic efficiency chart still present'; assert 'def local_process_activities_df' not in s, 'local processor still present'; assert 'process_running_activities_df' in s, 'shared processor not adopted'; print('P2 prune OK')"`
Expected: prints `P2 prune OK`.

- [ ] **Step 5: Confirm the rest of P2 still parses and key sections remain**

Run: `venv_garmin/Scripts/python.exe -c "s=open('pages/P2_Running_performance.py').read(); assert 'Long Run Progression' in s and 'Time in HR Zones Distribution' in s and 'Pace vs. Average Heart Rate' in s, 'unintended removal'; print('P2 sections intact')"`
Expected: prints `P2 sections intact`.

- [ ] **Step 6: Commit**

```bash
git add pages/P2_Running_performance.py
git commit -m "refactor(P2): drop misleading charts, adopt shared running processor"
```

---

## Self-Review

**Spec coverage:**
- Efficiency Factor (speed per heartbeat), summaries-only → Task 1. ✓
- Weekly median + IQR band → Task 2. ✓
- Pace-at-reference-HR linear fit with guards → Task 3. ✓
- Improvement verdict (6wk vs 6wk, Mann-Whitney, muted<4) → Task 4. ✓
- Shared, tested per-run processor (fixes the unusable `process_activities_df`) → Task 5. ✓
- New page with own lookback (default 6m), verdict banner, EF trend, recency-coloured frontier + fit lines + "now vs then" callout, hard-effort trend, VO2 reference → Task 6. ✓
- Prune the two misleading P2 charts + adopt shared processor → Task 7. ✓
- Pure module + processor unit-tested; page browser-verified → Tasks 1–5 pytest, Task 6 manual. ✓
- No new API calls / decoupling deferred → enforced by using only `get_activities`; noted in Global Constraints. ✓

**Placeholder scan:** No TBD/TODO; every code step has runnable code or an exact command. ✓

**Type consistency:** `efficiency_factor`, `add_efficiency_columns` (`ef`, `is_easy`), `weekly_ef_trend` (`week_start`, `ef_median`, `n`, `ef_q25`, `ef_q75`), `pace_at_reference_hr` (dict with `pace_at_ref`/`slope`/`intercept`/`n`/`ok`/`reason`), `improvement_verdict` (dict with `direction`/`pct_change`/`n_recent`/`n_prior`/`confident`/`p_value`/`muted`/`reason`), and `REF_HR_DEFAULT`/`MIN_WINDOW_N` are used identically in the page (Task 5) as defined in Tasks 1–4. ✓

**Note for executor:** The page (Task 6) depends on `data_processing.process_running_activities_df` (Task 5) producing `activityType_key`, `distance_km`, `duration_minutes`, `avgHR`, `pace_min_per_km`, `time_in_zone2_minutes`, and `vo2MaxValue_activity`. Task 5's test asserts these, so Tasks 1–5 must be green before Task 6 renders. Do **not** substitute the older `process_activities_df` — it is buggy for this purpose (see the "Why a shared processor" note above).
