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
