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
