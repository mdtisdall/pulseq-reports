"""Numbers that describe a 1D slice profile.

A copy of vb-pulseq `profile_metrics.py` at commit 3a1c7dd.
"""

import numpy as np


def fwhm(x, profile):
    """Full width at half maximum: the distance between the outermost positions
    where the profile is at or above half its maximum."""
    above = x[profile >= profile.max() / 2]
    return above.max() - above.min()


def edge_width(x, profile):
    """Mean width of the two edges from 10% to 90% of the profile maximum, on the
    sample grid, in meters.

    Left edge: (outermost left position at or above 90% of max) minus (outermost
    left position at or above 10% of max). Right edge: the mirror image. Returns
    the mean of the two.
    """
    max_val = profile.max()
    at_10 = x[profile >= 0.1 * max_val]
    at_90 = x[profile >= 0.9 * max_val]
    left_edge = at_90.min() - at_10.min()
    right_edge = at_10.max() - at_90.max()
    return (left_edge + right_edge) / 2


def passband_ripple(x, profile, nominal):
    """Passband ripple, (max - min) / max, over samples with |x| <= 0.4 * nominal.
    Unitless."""
    region = profile[np.abs(x) <= 0.4 * nominal]
    if region.size == 0:
        raise ValueError("passband_ripple: no samples with |x| <= 0.4 * nominal")
    return (region.max() - region.min()) / region.max()


def stopband_level(x, profile, nominal):
    """Stopband level: the maximum of the profile over samples with |x| >= nominal,
    divided by the maximum of the whole profile. Unitless."""
    region = profile[np.abs(x) >= nominal]
    if region.size == 0:
        raise ValueError("stopband_level: no samples with |x| >= nominal")
    return region.max() / profile.max()


def phase_peak_to_peak(x, mxy, nominal):
    """Peak-to-peak unwrapped phase of mxy over samples with |x| <= 0.4 * nominal,
    in rad."""
    region = mxy[np.abs(x) <= 0.4 * nominal]
    if region.size == 0:
        raise ValueError("phase_peak_to_peak: no samples with |x| <= 0.4 * nominal")
    phase = np.unwrap(np.angle(region))
    return phase.max() - phase.min()
