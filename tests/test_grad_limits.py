import math

import numpy as np
import pypulseq as pp
import pytest
from synthetic import SYSTEM

from pulseq_reports.grad_limits import gradient_limits
from pulseq_reports.seq_utils import GAMMA


def test_trapezoid_peak_slew_and_rms_match_hand_computed_values():
    """A single x trapezoid: the peak amplitude, the peak slew and the RMS amplitude
    equal values computed by hand from the trapezoid's own rise time, flat time and
    amplitude."""
    amplitude = 0.5 * SYSTEM.max_grad  # Hz/m
    gx = pp.make_trapezoid(
        channel="x", amplitude=amplitude, rise_time=200e-6, flat_time=1e-3, system=SYSTEM
    )
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx)
    (block_id,) = seq.block_events

    result = gradient_limits(seq)

    peak_mt_per_m = amplitude / GAMMA * 1e3
    slew_t_per_m_per_s = amplitude / gx.rise_time / GAMMA
    # RMS^2 * duration is the integral of amplitude^2 dt: the rising ramp contributes
    # amplitude^2 * rise_time / 3 (the integral of (amplitude * t / rise_time)^2 from 0
    # to rise_time), the falling ramp contributes the same by symmetry, and the flat
    # top contributes amplitude^2 * flat_time.
    duration = sum(seq.block_durations.values())
    energy = 2 * (gx.rise_time * amplitude**2 / 3) + gx.flat_time * amplitude**2
    rms_mt_per_m = math.sqrt(energy / duration) / GAMMA * 1e3

    axis = result.axes["x"]
    assert result.reason is None
    assert axis.peak_mt_per_m == pytest.approx(peak_mt_per_m)
    assert axis.peak_block == block_id
    assert axis.max_slew_t_per_m_per_s == pytest.approx(slew_t_per_m_per_s)
    assert axis.slew_block == block_id
    assert axis.rms_mt_per_m == pytest.approx(rms_mt_per_m)


def test_same_trapezoid_on_x_and_y_gives_vector_peak_root_2_times_axis_peak():
    """The same trapezoid, played on x and on y at the same time: the vector peak is
    the axis peak times sqrt(2), because at every point Gx == Gy, so
    |G| = sqrt(Gx^2 + Gy^2) = sqrt(2) * |Gx|."""
    gx = pp.make_trapezoid(
        channel="x",
        amplitude=0.5 * SYSTEM.max_grad,
        rise_time=200e-6,
        flat_time=1e-3,
        system=SYSTEM,
    )
    gy = pp.make_trapezoid(
        channel="y",
        amplitude=0.5 * SYSTEM.max_grad,
        rise_time=200e-6,
        flat_time=1e-3,
        system=SYSTEM,
    )
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx, gy)

    result = gradient_limits(seq)

    assert result.vector_peak_mt_per_m == pytest.approx(
        result.axes["x"].peak_mt_per_m * math.sqrt(2)
    )
    assert result.axes["x"].peak_mt_per_m == pytest.approx(result.axes["y"].peak_mt_per_m)


def test_window_that_cuts_a_ramp_gives_hand_computed_rms():
    """A window that ends halfway up the rising ramp of a trapezoid: the RMS amplitude
    over the window equals the value computed by hand from the piece that the window
    keeps, cut at the window edge."""
    amplitude = 0.5 * SYSTEM.max_grad
    rise_time = 200e-6
    gx = pp.make_trapezoid(
        channel="x", amplitude=amplitude, rise_time=rise_time, flat_time=1e-3, system=SYSTEM
    )
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx)
    window = (0.0, gx.delay + rise_time / 2)

    result = gradient_limits(seq, window=window)

    # The window keeps the ramp from (0, 0) to (rise_time / 2, amplitude / 2), a
    # straight line, so Delta t * (a^2 + a*b + b^2) / 3 with a = 0, b = amplitude / 2.
    mid_amplitude = amplitude / 2
    length = window[1] - window[0]
    energy = (rise_time / 2) * (mid_amplitude**2) / 3
    rms_mt_per_m = math.sqrt(energy / length) / GAMMA * 1e3

    assert result.range_s == window
    assert result.axes["x"].rms_mt_per_m == pytest.approx(rms_mt_per_m)


def test_arbitrary_gradient_peak_is_the_largest_of_first_last_and_waveform():
    """An arbitrary gradient: the peak amplitude is the largest absolute value among
    the shape's `first`, `last` and interior waveform samples, since `gradient_points`
    (seq_utils) adds `first` and `last` as extra points at the shape's ends."""
    n = 40
    dt = SYSTEM.grad_raster_time
    t = (np.arange(n) + 0.5) * dt
    # A waveform that is not symmetric, so its largest magnitude is not at the center.
    waveform = 0.3 * SYSTEM.max_grad * np.sin(np.pi * t / (1.5 * n * dt))
    gx = pp.make_arbitrary_grad(channel="x", waveform=waveform, system=SYSTEM)
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx)

    result = gradient_limits(seq)

    block = seq.get_block(1)
    peak_hz_per_m = max(abs(block.gx.first), abs(block.gx.last), np.max(np.abs(waveform)))
    assert result.axes["x"].peak_mt_per_m == pytest.approx(peak_hz_per_m / GAMMA * 1e3)


def test_no_gradients_sets_reason():
    """A sequence with no gradient events at all: `reason` is set, and every numeric
    field is its zero value (0.0, or None for a block field)."""
    seq = pp.Sequence(SYSTEM)
    seq.add_block(pp.make_delay(2e-3))

    result = gradient_limits(seq)

    assert result.reason == "no gradient events in the sequence"
    assert result.vector_peak_mt_per_m == 0.0
    assert result.vector_peak_time_s == 0.0
    for axis in ("x", "y", "z"):
        a = result.axes[axis]
        assert a.peak_mt_per_m == 0.0
        assert a.peak_block is None
        assert a.max_slew_t_per_m_per_s == 0.0
        assert a.slew_block is None
        assert a.rms_mt_per_m == 0.0


def test_default_limits_come_from_seq_system():
    """With `limits=None`, the limits are `seq.system.max_grad` and
    `seq.system.max_slew`, converted from Hz/m (respectively Hz/m/s) to mT/m
    (respectively T/m/s), with the label "pypulseq system limits"."""
    gx = pp.make_trapezoid(channel="x", area=1000, system=SYSTEM)
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx)

    result = gradient_limits(seq)

    assert result.limits.label == "pypulseq system limits"
    assert result.limits.max_grad_mt_per_m == pytest.approx(seq.system.max_grad / GAMMA * 1e3)
    assert result.limits.max_slew_t_per_m_per_s == pytest.approx(seq.system.max_slew / GAMMA)
