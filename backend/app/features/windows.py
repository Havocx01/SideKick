"""Vectorised trailing-window primitives."""

from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


def _slope_weights(window: int) -> np.ndarray:
    """OLS slope weights for equally spaced points, scaled so a dot product gives the slope."""
    positions = np.arange(window, dtype=np.float64)
    centred = positions - positions.mean()
    return centred / np.square(centred).sum()


def rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    out = np.full(values.shape[0], np.nan, dtype=np.float64)
    if values.shape[0] < window:
        return out
    out[window - 1 :] = sliding_window_view(values, window).mean(axis=-1)
    return out


def rolling_slope(values: np.ndarray, window: int) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    out = np.full(values.shape[0], np.nan, dtype=np.float64)
    if values.shape[0] < window:
        return out
    out[window - 1 :] = sliding_window_view(values, window) @ _slope_weights(window)
    return out


def rolling_mean_2d(matrix: np.ndarray, window: int) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float64)
    out = np.full(matrix.shape, np.nan, dtype=np.float64)
    if matrix.shape[0] < window:
        return out
    # sliding_window_view over axis 0 yields (n - w + 1, n_channels, w).
    out[window - 1 :, :] = sliding_window_view(matrix, window, axis=0).mean(axis=-1)
    return out


def rolling_slope_2d(matrix: np.ndarray, window: int) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float64)
    out = np.full(matrix.shape, np.nan, dtype=np.float64)
    if matrix.shape[0] < window:
        return out
    out[window - 1 :, :] = sliding_window_view(matrix, window, axis=0) @ _slope_weights(window)
    return out
