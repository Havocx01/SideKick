"""Vectorised trailing-window primitives.

Runtime is a named risk. The fault matrix rebuilds features once per
sensor-scenario, so these operate as single array expressions rather than
per-cycle Python loops. Each function returns a full-length array whose first
``window - 1`` entries are NaN, because a trailing window is undefined there.
Those rows are dropped by the scorable mask rather than filled with a guess.
"""

from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


def _slope_weights(window: int) -> np.ndarray:
    """Weights that turn a dot product into an ordinary least-squares slope.

    For a window of evenly spaced points, the OLS slope is
    ``sum((t - t_mean) * y) / sum((t - t_mean) ** 2)``, and the denominator is a
    constant, so the whole thing collapses to one fixed weight vector.
    """
    positions = np.arange(window, dtype=np.float64)
    centred = positions - positions.mean()
    return centred / np.square(centred).sum()


def rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    """Trailing mean over ``window`` cycles, inclusive of the current cycle."""
    values = np.asarray(values, dtype=np.float64)
    out = np.full(values.shape[0], np.nan, dtype=np.float64)
    if values.shape[0] < window:
        return out
    out[window - 1 :] = sliding_window_view(values, window).mean(axis=-1)
    return out


def rolling_slope(values: np.ndarray, window: int) -> np.ndarray:
    """Trailing least-squares slope per cycle, in units per cycle."""
    values = np.asarray(values, dtype=np.float64)
    out = np.full(values.shape[0], np.nan, dtype=np.float64)
    if values.shape[0] < window:
        return out
    out[window - 1 :] = sliding_window_view(values, window) @ _slope_weights(window)
    return out


def rolling_mean_2d(matrix: np.ndarray, window: int) -> np.ndarray:
    """Column-wise trailing mean for a ``(n_cycles, n_channels)`` matrix."""
    matrix = np.asarray(matrix, dtype=np.float64)
    out = np.full(matrix.shape, np.nan, dtype=np.float64)
    if matrix.shape[0] < window:
        return out
    # sliding_window_view over axis 0 yields (n - w + 1, n_channels, w).
    out[window - 1 :, :] = sliding_window_view(matrix, window, axis=0).mean(axis=-1)
    return out


def rolling_slope_2d(matrix: np.ndarray, window: int) -> np.ndarray:
    """Column-wise trailing slope for a ``(n_cycles, n_channels)`` matrix."""
    matrix = np.asarray(matrix, dtype=np.float64)
    out = np.full(matrix.shape, np.nan, dtype=np.float64)
    if matrix.shape[0] < window:
        return out
    out[window - 1 :, :] = sliding_window_view(matrix, window, axis=0) @ _slope_weights(window)
    return out
