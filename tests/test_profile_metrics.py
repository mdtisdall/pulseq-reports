"""Tests for pulseq_reports.profile_metrics, on synthetic profiles with known values.

Every expected value here is derived from the shape of the synthetic profile
itself (a rectangle, a trapezoid, a cosine ripple, a spike, a linear phase),
not from the functions under test.
"""

import numpy as np
import pytest

from pulseq_reports import profile_metrics as pm


def _grid(half_width, dx):
    """A symmetric, sorted position grid from -half_width to +half_width."""
    n = round(half_width / dx)
    return np.arange(-n, n + 1) * dx


def test_rectangle_edge_width_is_zero():
    dx = 1e-4
    a = 0.006  # rectangle half-width
    x = _grid(0.015, dx)
    profile = np.where(np.abs(x) <= a, 1.0, 0.0)

    assert pm.edge_width(x, profile) == pytest.approx(0.0, abs=1e-12)


def test_rectangle_passband_ripple_is_zero():
    dx = 1e-4
    a = 0.006  # rectangle half-width, wider than the 0.4 * nominal region
    nominal = 0.01
    x = _grid(0.015, dx)
    profile = np.where(np.abs(x) <= a, 1.0, 0.0)

    assert pm.passband_ripple(x, profile, nominal) == pytest.approx(0.0, abs=1e-12)


def test_rectangle_stopband_level_is_zero():
    dx = 1e-4
    a = 0.006  # rectangle half-width, narrower than nominal on each side
    nominal = 0.01
    x = _grid(0.015, dx)
    profile = np.where(np.abs(x) <= a, 1.0, 0.0)

    assert pm.stopband_level(x, profile, nominal) == pytest.approx(0.0, abs=1e-12)


def test_rectangle_fwhm_equals_width():
    dx = 1e-4
    a = 0.005  # a is an exact multiple of dx
    x = _grid(0.01, dx)
    profile = np.where(np.abs(x) <= a, 1.0, 0.0)

    assert pm.fwhm(x, profile) == pytest.approx(2 * a, abs=1e-12)


def test_trapezoid_edge_width_matches_ramp():
    dx = 1e-5
    plateau = 0.003  # half-width of the flat top
    ramp = 0.004  # R, the width of each linear edge
    x = _grid(0.01, dx)
    ax = np.abs(x)
    profile = np.clip(1.0 - (ax - plateau) / ramp, 0.0, 1.0)

    assert pm.edge_width(x, profile) == pytest.approx(0.8 * ramp, abs=dx)


def test_passband_ripple_known_cosine():
    dx = 1e-4
    nominal = 0.01
    w = 0.4 * nominal  # 0.004, the passband half-width
    x = _grid(2 * w, dx)
    # k is chosen so that cos(k * x) sweeps from +1 at x=0 to -1 exactly at the
    # passband edge x = +/- w, so the region maximum and minimum are known.
    k = np.pi / w
    profile = 1 + 0.1 * np.cos(k * x)

    expected = (1.1 - 0.9) / 1.1
    assert pm.passband_ripple(x, profile, nominal) == pytest.approx(expected, abs=1e-6)


def test_stopband_level_known_spike():
    dx = 1e-4
    nominal = 0.005
    x = _grid(0.01, dx)
    profile = np.where(np.abs(x) <= 0.6 * nominal, 1.0, 0.0)
    h = 0.2
    spike_index = np.argmin(np.abs(x - 0.007))  # |x| = 0.007 >= nominal
    profile[spike_index] = h

    assert pm.stopband_level(x, profile, nominal) == pytest.approx(h, abs=1e-12)


def test_phase_peak_to_peak_linear_phase():
    dx = 1e-4
    nominal = 0.01
    w = 0.4 * nominal
    x = _grid(2 * w, dx)
    s = 2000.0  # rad/m; s * (2 * w) is well over 2*pi, so the phase wraps
    mxy = np.exp(1j * s * x)

    expected = s * (2 * w)
    assert pm.phase_peak_to_peak(x, mxy, nominal) == pytest.approx(expected, rel=1e-6)


def test_phase_peak_to_peak_constant_phase_is_zero():
    dx = 1e-4
    nominal = 0.01
    x = _grid(2 * 0.4 * nominal, dx)
    mxy = np.exp(1j * 0.7) * np.ones_like(x, dtype=complex)

    assert pm.phase_peak_to_peak(x, mxy, nominal) == pytest.approx(0.0, abs=1e-12)


def test_passband_ripple_empty_region_raises():
    x = np.array([1.0, 2.0, 3.0])
    profile = np.array([1.0, 1.0, 1.0])
    with pytest.raises(ValueError):
        pm.passband_ripple(x, profile, nominal=0.001)


def test_stopband_level_empty_region_raises():
    x = np.array([0.0, 0.001, -0.001])
    profile = np.array([1.0, 0.5, 0.5])
    with pytest.raises(ValueError):
        pm.stopband_level(x, profile, nominal=10.0)


def test_phase_peak_to_peak_empty_region_raises():
    x = np.array([1.0, 2.0, 3.0])
    mxy = np.array([1.0, 1.0, 1.0], dtype=complex)
    with pytest.raises(ValueError):
        pm.phase_peak_to_peak(x, mxy, nominal=0.001)


def test_fwhm_triangle_known_width():
    dx = 1e-4
    width = 0.02  # full base width
    x = _grid(width, dx)
    profile = np.clip(1.0 - np.abs(x) / (width / 2), 0.0, None)

    # A triangle's FWHM is half its base width.
    assert pm.fwhm(x, profile) == pytest.approx(width / 2, abs=2 * dx)
