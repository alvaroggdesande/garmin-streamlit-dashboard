# "Am I Improving?" — Running Efficiency Trend Page (Design Spec)

**Date:** 2026-07-31
**Status:** Approved design, pending spec review → implementation plan.

## Problem

The dashboard shows running data but does not answer the runner's actual
questions: *am I improving?* and *can I do more work at a lower heart rate?*
The current Running Performance page (`pages/P2_Running_performance.py`) has
seven charts that display raw per-run series without baselines, trend lines,
or significance — the user must eyeball wiggly lines and guess. Two charts are
actively misleading (see Pruning below).

Target user: a runner training a mix of **aerobic base (easy/Z2)** and **some
speed/race work**, running a few times per week.

## Goal

A new, focused page — **`pages/P7_Am_I_Improving.py`** — that answers the
fitness-trend question directly, using an **Efficiency Factor** trend with a
plain-language verdict, a "pace at a fixed heart rate" comparison, and the
project's established statistical-honesty treatment (n, confidence, muted
states when data is thin). Plus targeted pruning of the two misleading P2
charts.

## Key constraint: data availability & the 429 risk

- The page uses **only per-run activity summaries** we already fetch
  (`distance`, `duration`, `avgHR`, time-in-HR-zone, VO2max, cadence). **No
  new API calls.**
- Activities fetch is a **single range call** (`get_activities_by_date`), so a
  long lookback (6 months) costs **one request** — cheap and safe. The
  fetch-volume 429 risk lives only in the per-day-looping *health* fetchers
  (HRV/RHR/body-battery), which this page does not use.
- Auth is fully decoupled from the date range: the token only replaces the
  login handshake; the resulting client fetches any range identically to a
  credential login. A 6-month lookback is therefore an auth non-issue.
- **Deferred (out of scope):** within-run **aerobic decoupling** (Pa:HR drift
  first-half vs second-half of a run). It requires per-activity HR/pace
  *streams* — one extra API call per run — which reintroduces fetch-volume
  throttling. Revisit as its own feature if wanted.

## Core metric definitions

### Efficiency Factor (EF)
`EF = speed / avgHR`, where `speed = distance_metres / duration_minutes`
(metres per minute). EF ≈ metres travelled per heartbeat; **higher is fitter**.
Standard, validated running metric (Friel). Computable from summaries alone.

Honesty rules:
- Computed **per run**, filtered to valid rows (`distance > 0`, `duration > 0`,
  `avgHR > 0`).
- Headline trend restricted to **easy/aerobic runs** — Z2-dominant, reusing
  P2's existing time-in-zone logic (a run counts as easy when
  `time_in_zone2_minutes / duration_minutes >= 0.60`; fall back to an avg-HR
  band if zone data is absent). Interval sessions corrupt EF and are excluded
  from the base signal.
- Aggregated **weekly (median)** — median because a few runs/week means one
  outlier (hilly grind, hot day) shouldn't swing the trend.

### Pace at a reference HR
Fit a simple linear relationship `pace ~ avgHR` across easy+moderate runs
within a period, then report **predicted pace at a reference HR** (default
145 bpm, adjustable). Comparing an earlier period's fit to a recent period's
fit yields the literal answer to "more with less HR":
> "At 145 bpm you now run 5:20/km — vs 5:38/km three months ago."

Guard: require a minimum number of runs and a minimum HR spread before fitting;
otherwise show a muted "not enough spread to estimate" state rather than a
garbage line.

### Improvement verdict
Compare a **recent trailing window (last 6 weeks)** against the **prior 6-week
window** on easy-run EF. Report:
- direction (↑ improving / → flat / ↓ declining) with the **% change**,
- **n** (runs in each window),
- a **confidence flag** — whether the difference is distinguishable from noise
  via **Mann-Whitney U** on the two windows' per-run EF values (non-parametric,
  robust for small n, consistent with median aggregation); "confident" when
  p < 0.05,
- **muted/grey** when either window has too few runs (threshold, e.g. < 4) —
  no confident verdict from thin data.

## Page layout (`pages/P7_Am_I_Improving.py`)

1. **Own lookback control** (independent of the global 30-day filter, since
   trends need months). Preset buttons — **3m / 6m / 1y / All** — default
   **6 months**, with an optional custom range. (An improvement over the global
   two-date picker; the user explicitly wanted the selector improved.)
2. **Verdict banner** — the one-sentence, colour-coded ↑/→/↓ verdict with n and
   confidence; muted when thin.
3. **EF weekly trend** — median EF line + shaded **IQR band (25th–75th
   percentile)** + baseline marker. Weeks with < 2 runs rendered muted (marker
   only, no band).
4. **Pace-at-fixed-HR frontier** — the Pace-vs-HR scatter, points **coloured by
   recency** (old faded → recent bright), with **earlier-period vs
   recent-period fit lines** overlaid and the numeric "at 145 bpm: now vs then"
   callout.
5. **Hard-effort pace trend** (the speed/"b" side) — weekly best pace among
   harder (Z3+) runs, so speed progress is visible alongside efficiency.
6. **VO2max** — small, muted, "for reference" (Garmin's own smoothed estimate;
   corroborating, not the headline).

Every section degrades gracefully: empty/short-data states rather than
exceptions, consistent with the untested-6-month-load caveat.

## Pruning P2 (approved)

- **Remove** "Selected Running Metrics Over Time" — the multi-line chart that
  connects per-run pace/HR/distance in sequence, implying continuity between
  runs of different types (tempo → long run → recovery). Misleading.
- **Remove** the two-axis "Easy Run Pace and Average HR Over Time" chart —
  it forces the reader to mentally divide two wiggling lines; superseded by the
  EF trend on the new page.
- **Keep** HR-zone distribution, pace-per-zone trend, long-run progression,
  VO2max trend, Pace-vs-HR scatter, and the details table.

## Code structure

- **New pure module `utils/efficiency_stats.py`** — no Streamlit, no Garmin,
  unit-tested with pytest (mirrors `utils/analysis_stats.py`). Functions:
  - `efficiency_factor(distance_m, duration_min, avg_hr) -> float | nan`
  - `add_efficiency_columns(runs_df) -> DataFrame` (EF + is_easy flags)
  - `weekly_ef_trend(easy_runs_df) -> DataFrame` (week, median EF, n, band)
  - `pace_at_reference_hr(runs_df, ref_hr) -> float | None` (linear fit;
    None when insufficient data/spread)
  - `improvement_verdict(easy_runs_df, recent_weeks=6) -> dict`
    (direction, pct_change, n_recent, n_prior, confident: bool, reason)
- **New page `pages/P7_Am_I_Improving.py`** — renders the above; owns its
  lookback control; reuses `garmin_utils.get_activities` + P2's activity
  processing (extract the shared `local_process_activities_df` into
  `data_processing` if it isn't already there, so the new page and P2 share
  one processor rather than duplicating it).
- **P2 edits** — remove the two charts above.
- **Tests `tests/test_efficiency_stats.py`** — pure unit tests for every
  `efficiency_stats` function, including thin-data / muted-state paths.

## Testing strategy

- Pure helpers (`efficiency_stats`) fully unit-tested with pytest, including
  edge cases: zero/NaN inputs, thin windows (muted verdict), insufficient HR
  spread (no pace-at-HR line), single-run weeks.
- The Streamlit page is browser-verified by the owner (no automated UI test),
  consistent with repo convention.
- Run: `venv_garmin/Scripts/python.exe -m pytest -q` from repo root.

## Non-goals / deferred

- Within-run aerobic decoupling (needs streams; new API calls).
- Cycling / multi-sport efficiency (running only for now).
- Any change to the health/HRV/readiness fetchers or their 429 exposure.
