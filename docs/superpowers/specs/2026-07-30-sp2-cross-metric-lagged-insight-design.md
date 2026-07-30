# SP2 — Cross-Metric & Lagged Insight (Design)

**Date:** 2026-07-30
**Status:** Approved design, ready for implementation planning
**Sub-project:** SP2 of the Garmin dashboard roadmap (SP1 training analytics and SP3 polish are separate, later cycles)

## Context

The Garmin dashboard logs into Garmin Connect with email + password via the unofficial
`garminconnect` library (Option A, kept as-is — the app is used by the author and a few
trusted people, so the hosted-password concern does not apply). SP2 does **not** touch data
access, auth, or add new data sources.

The existing Correlations page (`pages/P4_Correlations.py`) is the starting point. Today it:

- loads **only** daily-summary data (RHR, stress, steps, body battery, `sleepingHours`,
  calories, intensity, respiration);
- draws same-day scatter plots with an OLS trendline and a raw Pearson coefficient;
- supports a hardcoded `shift(-1)` for a few "next day" pairs, and a custom explorer offering
  exactly lag-0 or lag-1;
- does not load HRV or activities, so it cannot relate recovery to actual training outcomes.

### Weaknesses SP2 addresses

1. **Only lag 0 or 1.** No way to ask or discover whether a driver 2–3+ days ago matters.
2. **Statistically naïve.** Reports e.g. "Pearson 0.20 on 12 points" with no n-awareness,
   no significance, no confidence interval, no rank-correlation option, no small-sample guard.
3. **P-hacking wide open.** The custom explorer invites fishing across many metrics × lags with
   no multiple-comparison caveat.
4. **Activities not merged.** "Readiness → realized performance" is impossible because run
   performance lives only on the Running page (`P2`).

## Guiding principle

**Statistical honesty is the feature.** The differentiator over the native Garmin app is not
more scatter plots — it is that every relationship is reported with sample size, significance,
and an explicit "real signal vs noise" verdict, plus rank-correlation and small-sample guards.
This is also what makes the sub-project portfolio-grade.

## Scope

### In scope

- **Feature 1 — Lagged Correlation Explorer** (reworks `P4`).
- **Feature 2 — Readiness → Realized Performance** (new page `P6`).
- **Feature 3 — Correlation heatmap** (optional; include only if it does not stretch the plan).
- **New pure-Python analytics module** `utils/analysis_stats.py` with unit tests.
- **Daily activity aggregation** merged into a unified daily frame (the one new bit of plumbing).

### Out of scope (YAGNI)

- No ML / forecasting / prediction.
- No causal-inference claims — correlation reported honestly, never as causation.
- No new data sources, no auth changes, no export/GDPR path.
- SP1 (training analytics) and SP3 (polish) are not implemented here.

## Architecture

### Page structure

- **`pages/P4_Correlations.py`** — reworked into the **Lagged Correlation Explorer** (+ optional
  heatmap). The curated fixed same-day/next-day plots are replaced by the lag explorer; a small
  set of sensible default driver/outcome pairs is preserved as presets.
- **`pages/P6_Readiness_and_Performance.py`** — new page for the readiness composite and its
  relationship to realized training performance.

### New module: `utils/analysis_stats.py` (pure, no Streamlit, no Garmin)

All statistics and framing live here so they are unit-testable with small fixture DataFrames.
Proposed functions (names indicative; finalize in the plan):

- `corr_with_significance(x, y, method="pearson") -> {r, p, n, ci_low, ci_high}`
  - Supports `"pearson"` and `"spearman"`.
  - Returns n, coefficient, p-value, and 95% CI (Fisher z-transform for the CI).
  - Handles n < 3 gracefully (returns NaNs / a `too_few` flag rather than raising).
- `lagged_correlation(df, x_col, y_col, lags=range(0, 8), method="pearson") -> DataFrame`
  - For each lag k, shift `y` by −k (outcome k days after driver) and compute
    `corr_with_significance`. Returns tidy rows: lag, r, p, n, ci_low, ci_high, significant.
  - "significant" uses a stated alpha (default 0.05) and a minimum-n threshold.
- `aggregate_activities_daily(activities_df) -> DataFrame`
  - Collapses multiple activities per day into one row: total duration, total distance,
    mean pace, mean avgHR, aerobic efficiency proxy (pace at avg HR), summed aerobic TE, run flag.
- `readiness_score(daily_df, baseline_window=28) -> DataFrame`
  - z-scores each available recovery component against a trailing baseline window, inverts
    where higher = worse (RHR, prior-day stress), averages available components into a 0-centered
    score. Returns the score plus each component column for transparency. Missing components are
    skipped, not imputed.
- `build_unified_daily_frame(daily_df, hrv_df, sleep_df, activities_daily_df) -> DataFrame`
  - Outer-joins on date into one tidy daily frame consumed by both pages. Supersedes the current
    `merge_sleep_hrv_activity_data`, which skips activities.

Existing `merge_sleep_hrv_activity_data` is either extended or replaced by
`build_unified_daily_frame`; the plan decides which to keep to avoid duplication.

### Data flow

1. Page loads raw data via existing `garmin_utils` fetchers (daily summaries, HRV, sleep,
   activities) — unchanged.
2. Existing `data_processing` functions normalize each source (unchanged), plus new
   `aggregate_activities_daily`.
3. `build_unified_daily_frame` produces one daily frame.
4. `analysis_stats` functions compute lagged correlations / readiness on that frame.
5. Pages render Plotly charts + the significance annotations.

## Feature details

### Feature 1 — Lagged Correlation Explorer (P4)

UI:
- Two selectors: **driver** metric (X) and **outcome** metric (Y), populated from the unified
  daily frame's numeric columns (with sensible presets, e.g. sleep→next-day RHR).
- **Correlation-vs-lag chart**: bar/line of r across lags 0…N (N default 7, adjustable), with
  significant lags visually distinguished from non-significant ones (e.g. muted color / marker).
- **Scatter at the selected lag** with OLS trendline.
- Method toggle: **Pearson / Spearman**.
- Reported under each chart: **n, r, p-value, 95% CI**, and an explicit muted state when
  n is below threshold or p ≥ alpha ("not significant — likely noise").
- A persistent one-line caveat: *exploratory, not confirmatory; correlation ≠ causation;
  scanning many pairs inflates false positives.*

### Feature 2 — Readiness → Realized Performance (P6)

- **Readiness score** section: line chart of the composite over time, with an expander showing
  each z-scored component so the score is never a black box.
- **Readiness vs performance**: scatter of morning readiness vs that day's training outcome
  (aerobic efficiency / pace-at-HR / aerobic TE — user-selectable), using the same
  `corr_with_significance` reporting.
- **Dual time series**: readiness and the chosen performance metric on twin axes.
- Graceful degradation: if HRV is absent (common via the unofficial API), readiness is computed
  from the remaining components and the UI states which components were used.

### Feature 3 — Correlation heatmap (optional)

- Masked heatmap of correlations among key daily metrics at a chosen lag; non-significant cells
  greyed/blanked. Screenshot-friendly overview. Included only if it does not stretch the plan.

## Testing

- `utils/analysis_stats.py` gets unit tests (`tests/test_analysis_stats.py`) against small
  hand-built DataFrames:
  - known-correlation fixtures verify r and significance;
  - lag fixtures (signal deliberately offset by k days) verify the peak lands at lag k;
  - small-n and all-NaN inputs return the `too_few` / NaN contract without raising;
  - `readiness_score` inverts RHR/stress correctly and skips missing components.
- No Streamlit or Garmin API in tests — pure functions only.
- Page-level (Streamlit) behavior is verified manually by the author, per repo convention.

## Success criteria

- P4 lets the user pick any driver/outcome pair and see correlation across a range of lags,
  identify the strongest lag, and read n + significance for every result.
- P6 shows a transparent readiness composite and its (honestly-reported) relationship to realized
  training performance, degrading gracefully when HRV is missing.
- All statistics live in a tested, Streamlit-free module.
- No regressions to data fetching, auth, or other pages.

## Open questions for the plan

- Keep vs replace `merge_sleep_hrv_activity_data`.
- Exact readiness component list and default baseline window (28 days proposed).
- Whether Feature 3 (heatmap) makes the cut.
