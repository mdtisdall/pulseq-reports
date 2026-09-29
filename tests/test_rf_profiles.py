"""Tests for `pulseq_reports.rf_profiles` (docs/plans/rf-profiles.md, sections 4.2 and
4.3; task 2.5, items 1 to 14).

Each test builds its sequence here with pypulseq. The RF raster is 5 µs (3 µs in the
interval test), so each pulse has a few hundred samples and each test is fast. The
expected values come from closed forms (trapezoid areas and means), from
`rf_sim.spin_domain` called directly on points made in the test, or from the
definitions of the plan (section 4.3) written out with numpy. Each test gives its
tolerance and the reason for it.
"""

import copy
import math

import numpy as np
import pypulseq as pp
import pytest
from pypulseq.event_lib import EventLibrary

from pulseq_reports import profile_metrics
from pulseq_reports import rf_profiles as rp
from pulseq_reports.rf_sim import magnetization, spin_domain

SYSTEM = pp.Opts(
    max_grad=30,
    grad_unit="mT/m",
    max_slew=150,
    slew_unit="T/m/s",
    rf_dead_time=100e-6,
    rf_ringdown_time=30e-6,
    adc_dead_time=10e-6,
    rf_raster_time=5e-6,
)
W = 5e-3  # m, the SliceThickness definition
CRUSHER_AREA = 4 / W  # 1/m: four cycles across W
REPHASING_TOL = 1e-9  # relative to the moment that the rephasing cancels (plan, task 2.5)


# ---- Sequence helpers ----


def _sinc(use, flip=math.pi / 2, thickness=W, system=SYSTEM, **kwargs):
    """A 1.5 ms sinc (300 samples at 5 µs) with its select gradient on z and rephaser."""
    return pp.make_sinc_pulse(
        flip_angle=flip,
        duration=1.5e-3,
        slice_thickness=thickness,
        system=system,
        return_gz=True,
        delay=system.rf_dead_time,
        use=use,
        **kwargs,
    )


def _hard(use, flip=math.pi / 2, duration=0.5e-3, system=SYSTEM, **kwargs):
    return pp.make_block_pulse(
        flip_angle=flip,
        duration=duration,
        delay=system.rf_dead_time,
        system=system,
        use=use,
        **kwargs,
    )


def _on_axis(g, channel, scale=1.0):
    """A copy of the gradient `g` on `channel`, times `scale`."""
    moved = pp.scale_grad(g, scale) if scale != 1.0 else copy.copy(g)
    moved.channel = channel
    return moved


def _readout():
    """A readout trapezoid on x with its ADC on the flat top, and the area from the
    gradient start to the ADC centre."""
    gx = pp.make_trapezoid("x", flat_area=250, flat_time=0.64e-3, system=SYSTEM)
    adc = pp.make_adc(num_samples=32, duration=gx.flat_time, delay=gx.rise_time, system=SYSTEM)
    return gx, adc, gx.amplitude * (gx.rise_time + gx.flat_time) / 2


def _trap(axis, area):
    return pp.make_trapezoid(axis, area=area, system=SYSTEM)


def _new(thickness=W, system=SYSTEM):
    seq = pp.Sequence(system)
    if thickness is not None:
        seq.set_definition("SliceThickness", thickness)
    return seq


def _half_moment(rf, g):
    """The moment (1/m) from the RF centre to the RF end on a select trapezoid whose flat
    top holds the whole RF: the dephasing that the rephasing must cancel."""
    return g.amplitude * rf.shape_dur / 2


def _turning_gradients(duration=1e-3, amplitude=2e5):
    """Arbitrary gradients on x and y whose direction turns one time during `duration`."""
    n = round(duration / SYSTEM.grad_raster_time)
    t = (np.arange(n) + 0.5) * SYSTEM.grad_raster_time
    envelope = amplitude * np.sin(np.pi * t / duration)
    angle = 2 * np.pi * t / duration
    gx = pp.make_arbitrary_grad("x", envelope * np.cos(angle), first=0, last=0, system=SYSTEM)
    gy = pp.make_arbitrary_grad("y", envelope * np.sin(angle), first=0, last=0, system=SYSTEM)
    return gx, gy


def _gre(num_trs=3, *, rf_spoiling=False, slices=(0.0,), dummies=0):
    """A GRE: [RF + gz, rephaser + readout prephaser, readout + ADC, spoiler] for each
    slice of each TR. `dummies` TRs before them have no ADC."""
    rf, gz, gzr = _sinc("excitation")
    gx, adc, to_centre = _readout()
    prephaser = _trap("x", -to_centre)
    spoiler = _trap("z", CRUSHER_AREA)
    seq = _new()
    count = 0
    for tr in range(dummies + num_trs):
        for position in slices:
            rf.freq_offset = gz.amplitude * position
            rf.phase_offset = (
                math.radians((117 * count * (count + 1) / 2) % 360) if rf_spoiling else 0
            )
            count += 1
            seq.add_block(rf, gz)
            seq.add_block(gzr, prephaser)
            seq.add_block(gx, adc) if tr >= dummies else seq.add_block(gx)
            seq.add_block(spoiler)
    return seq


def _spin_echo(
    ref_axis="y", ref_thickness=W, *, hard_ref=False, num_ref=1, before=(), exc_axis="z"
):
    """Excitation (sinc on `exc_axis`), rephaser and readout prephaser, then for each
    refocusing pulse a crusher, the pulse (sinc on `ref_axis`, or a hard pulse) and a
    crusher, then the readout. `before` are blocks before the excitation. Play indexes
    for num_ref=1 and no `before`: 0 excitation, 1 rephaser, 2 crusher, 3 refocusing,
    4 crusher, 5 readout."""
    rf_ex, gz_ex, gzr = _sinc("excitation")
    gx, adc, to_centre = _readout()
    seq = _new()
    for block in before:
        seq.add_block(*block)
    seq.add_block(rf_ex, _on_axis(gz_ex, exc_axis))
    # The prephaser has the sign of the readout: one refocusing pulse changes its sign.
    seq.add_block(_on_axis(gzr, exc_axis), _trap("x", to_centre))
    for _ in range(num_ref):
        seq.add_block(_trap(ref_axis, CRUSHER_AREA))
        if hard_ref:
            seq.add_block(_hard("refocusing", math.pi, phase_offset=math.pi / 2))
        else:
            rf_ref, gz_ref, _ = _sinc(
                "refocusing", math.pi, ref_thickness, phase_offset=math.pi / 2
            )
            seq.add_block(rf_ref, _on_axis(gz_ref, ref_axis))
        seq.add_block(_trap(ref_axis, CRUSHER_AREA))
    seq.add_block(gx, adc)
    return seq


def _profile(pulse, n=None):
    spec, reason = rp.view_spec(pulse, "profile", n=n)
    assert reason is None
    return rp.simulate(pulse, spec)


def _values_at(pulse, positions):
    """|Mxy| of an excitation or |beta|^2 of a refocusing pulse at 3D points, from
    `rf_sim.spin_domain` directly."""
    a, b = spin_domain(pulse.signal_hz, pulse.dt_s, pulse.grad_hz_per_m, positions)
    return np.abs(magnetization(a, b)[0]) if pulse.use == "excitation" else np.abs(b) ** 2


# ---- 1. The gradient kinds ----


def test_gradient_kind_none_for_a_block_pulse():
    """A block pulse without a gradient: kind "none", no select coordinate, and its
    "profile" view is df around the frequency offset."""
    seq = _new()
    seq.add_block(_hard("excitation", freq_offset=150.0))
    pulse = rp.block_pulse(seq, 0)
    assert pulse.gradient_kind == "none"
    assert pulse.select_kind is None and pulse.direction is None
    assert pulse.select_gradient_hz_per_m is None and pulse.slice_centre_m is None
    assert pulse.constant_gradient is False
    assert not np.any(pulse.grad_hz_per_m)
    spec, reason = rp.view_spec(pulse)
    assert reason is None
    (axis,) = spec.axes
    assert axis.kind == "df" and axis.n == rp.NUM_POSITIONS
    # Exact: the range is f - 2B to f + 2B, so its middle is f within float rounding.
    assert (axis.lo + axis.hi) / 2 == pytest.approx(150.0, rel=1e-12)


def test_gradient_kind_one_on_a_logical_axis():
    """A sinc with its trapezoid on z (the RF inside the flat top): kind "one", select
    coordinate "z", G the flat-top amplitude, constant."""
    rf, gz, _ = _sinc("excitation")
    seq = _new()
    seq.add_block(rf, gz)
    pulse = rp.block_pulse(seq, 0)
    assert pulse.gradient_kind == "one" and pulse.select_kind == "z"
    np.testing.assert_array_equal(pulse.direction, [0.0, 0.0, 1.0])
    assert pulse.constant_gradient is True
    # Exact inside: an interval inside the flat top has the value at its middle, the
    # amplitude. The RF end and the flat-top end are one time from two float sums, so
    # the last interval can cross that corner by 1e-19 s: relative 1e-14 there.
    np.testing.assert_array_equal(pulse.grad_hz_per_m[:-1, 2], gz.amplitude)
    assert pulse.grad_hz_per_m[-1, 2] == pytest.approx(gz.amplitude, rel=1e-14)
    assert pulse.select_gradient_hz_per_m == pytest.approx(gz.amplitude, rel=1e-14)
    assert pulse.slice_centre_m == 0.0


def test_gradient_kind_one_oblique_on_two_axes():
    """The same trapezoid on x and y with one timing (30 degrees from x): kind "one",
    select coordinate "select", direction the unit vector (cos 30, sin 30, 0) and G the
    amplitude, within 1e-12 (the float rounding of the two scaled amplitudes)."""
    rf, gz, _ = _sinc("excitation")
    angle = math.radians(30)
    seq = _new()
    seq.add_block(rf, _on_axis(gz, "x", math.cos(angle)), _on_axis(gz, "y", math.sin(angle)))
    pulse = rp.block_pulse(seq, 0)
    assert pulse.gradient_kind == "one" and pulse.select_kind == "select"
    np.testing.assert_allclose(pulse.direction, [math.cos(angle), math.sin(angle), 0], atol=1e-12)
    assert pulse.select_gradient_hz_per_m == pytest.approx(gz.amplitude, rel=1e-12)
    assert pulse.constant_gradient is True


def test_gradient_kind_changing_for_a_turning_gradient():
    """Arbitrary gradients on x and y whose direction turns during the RF: kind
    "changing", no "profile" view, and the reason of decision 12."""
    gx, gy = _turning_gradients()
    seq = _new()
    seq.add_block(_hard("excitation", duration=0.8e-3), gx, gy)
    pulse = rp.block_pulse(seq, 0)
    assert pulse.gradient_kind == "changing"
    assert pulse.select_kind is None and pulse.direction is None
    assert rp.view_spec(pulse, "profile") == (None, rp.DIRECTION_CHANGES)
    assert rp.view_spec(pulse, "z_df") == (None, rp.DIRECTION_CHANGES)


# ---- 2. Interval values ----


def test_interval_values_of_a_trapezoid_equal_the_hand_means():
    """The value of each hold interval is the mean of the trapezoid over it: on a ramp,
    across a corner, on the flat top, on the fall, across the end, and after the end.
    The RF raster is 3 µs, so gradient corners (on the 10 µs raster) fall inside hold
    intervals. The RF is longer than the flat top: kind "one", not constant."""
    system = pp.Opts(
        max_grad=30, grad_unit="mT/m", max_slew=150, slew_unit="T/m/s", rf_raster_time=3e-6
    )
    amplitude, rise, flat = 2e5, 100e-6, 500e-6
    g = pp.make_trapezoid(
        "z", amplitude=amplitude, rise_time=rise, flat_time=flat, fall_time=rise, system=system
    )
    rf = pp.make_block_pulse(
        flip_angle=0.5, duration=900e-6, delay=60e-6, system=system, use="excitation"
    )
    seq = _new(system=system)
    seq.add_block(rf, g)
    pulse = rp.block_pulse(seq, 0)
    dt = pulse.dt_s
    assert dt == pytest.approx(3e-6, rel=1e-12)
    values = pulse.grad_hz_per_m[:, 2]

    def interval(k):  # [start, end] in block time
        return 60e-6 + k * dt, 60e-6 + (k + 1) * dt

    def ramp_up(t):
        return amplitude * t / rise

    def fall(t):
        return amplitude * (rise + flat + rise - t) / rise

    # The mean of a linear piece is its value at the middle; across a corner, the two
    # parts are added. Relative 1e-12: float rounding of the interval ends (~1e-16 s
    # against a 3 µs interval), far below any modelling difference.
    a, b = interval(0)  # [60, 63] µs on the ramp
    assert values[0] == pytest.approx(ramp_up((a + b) / 2), rel=1e-12)
    a, b = interval(13)  # [99, 102] µs: the corner at 100 µs
    across = (100e-6 - a) * (ramp_up(a) + amplitude) / 2 + (b - 100e-6) * amplitude
    assert values[13] == pytest.approx(across / dt, rel=1e-12)
    assert values[80] == amplitude  # [300, 303] µs: flat top, exact (midpoint value)
    a, b = interval(180)  # [600, 603] µs on the fall
    assert values[180] == pytest.approx(fall((a + b) / 2), rel=1e-12)
    a, b = interval(213)  # [699, 702] µs: the end at 700 µs
    assert values[213] == pytest.approx((700e-6 - a) * fall(a) / 2 / dt, rel=1e-12)
    np.testing.assert_array_equal(values[214:], 0.0)
    np.testing.assert_array_equal(pulse.grad_hz_per_m[:, :2], 0.0)
    assert pulse.gradient_kind == "one" and pulse.select_kind == "z"
    assert pulse.constant_gradient is False


# ---- 3. As played ----


def _moved_and_plain_difference(raster, centre_m):
    """The largest difference of |Mxy|, Mz and |beta|^2 between a sinc played with the
    frequency offset f = G * c and the same sinc without it moved by f / G, at the RF
    raster `raster`; and the difference when the plain profile is not moved."""
    system = pp.Opts(
        max_grad=30,
        grad_unit="mT/m",
        max_slew=150,
        slew_unit="T/m/s",
        rf_dead_time=100e-6,
        rf_ringdown_time=30e-6,
        rf_raster_time=raster,
    )
    rf, gz, _ = _sinc("excitation", system=system)
    moved, plain = _new(system=system), _new(system=system)
    rf.freq_offset = gz.amplitude * centre_m
    moved.add_block(rf, gz)
    rf.freq_offset = 0.0
    plain.add_block(rf, gz)
    p_moved, p_plain = rp.block_pulse(moved, 0), rp.block_pulse(plain, 0)
    assert p_moved.freq_offset_hz == gz.amplitude * centre_m
    assert p_moved.slice_centre_m == pytest.approx(centre_m, rel=1e-12)
    spec, _ = rp.view_spec(p_moved, "profile", n=81)
    (axis,) = spec.axes
    c = p_moved.slice_centre_m
    assert (axis.lo, axis.hi) == (c - 2 * W, c + 2 * W)
    shifted = rp.ProfileSpec((rp.ProfileAxis("z", axis.lo - c, axis.hi - c, axis.n),))
    a = rp.simulate(p_moved, spec)
    b = rp.simulate(p_plain, shifted)
    not_moved = rp.simulate(p_plain, spec)
    difference = max(
        np.max(np.abs(rp.quantity(a, name) - rp.quantity(b, name)))
        for name in ("mxy_abs", "mz", "beta_sq")
    )
    wrong = np.max(np.abs(rp.quantity(a, "mxy_abs") - rp.quantity(not_moved, "mxy_abs")))
    return difference, wrong


def test_as_played_profile_is_the_profile_moved_by_f_over_g():
    """A block with the frequency offset f = G * c (c = 1.5 mm) and a constant gradient G
    has the profile of the same block without the offset, moved by f / G (|Mxy|, Mz,
    |beta|^2), up to the error of the hold model.

    Tolerance: the hold model keeps the offset phase of each RF sample constant over its
    hold interval (its value at the centre), a midpoint rule. Its error is second order
    in dt and first order in f (measured: 1.4e-4 at a 5 µs raster, 3.5e-5 at 2.5 µs, for
    f = 800 Hz). So the test checks that the difference is small (below 1e-3, where a
    profile that is not moved differs by about 1) and that it falls by 4 +- 1 when dt
    halves. The plan's 1e-9 is not reached for any useful shift (2.6e-7 at f = 2 Hz)."""
    coarse, wrong = _moved_and_plain_difference(5e-6, 1.5e-3)
    fine, _ = _moved_and_plain_difference(2.5e-6, 1.5e-3)
    assert coarse < 1e-3 < wrong
    assert 3 <= coarse / fine <= 5


def test_freq_ppm_adds_to_the_total_frequency_offset():
    """The total offsets are freq_offset + freq_ppm * 1e-6 * |gamma| * B0 (and the same
    for the phase), and the RF as played is the baseband times exp(1j * (phase + 2*pi*f
    * t)) with t at the centre of each hold interval. Relative 1e-12: the same formula,
    so only float rounding."""
    system = pp.Opts(rf_raster_time=5e-6, rf_dead_time=100e-6, B0=2.89)
    rf = _hard(
        "saturation",
        system=system,
        freq_offset=100.0,
        freq_ppm=-3.45,
        phase_offset=0.3,
        phase_ppm=0.7,
    )
    seq = _new(system=system)
    seq.add_block(rf)
    pulse = rp.block_pulse(seq, 0)
    ppm_hz = 1e-6 * abs(system.gamma) * 2.89
    f = 100.0 - 3.45 * ppm_hz
    assert pulse.freq_offset_hz == pytest.approx(f, rel=1e-12)
    n = pulse.signal_hz.size
    t = (np.arange(n) + 0.5) * pulse.dt_s
    amplitude = (math.pi / 2) / (2 * math.pi * 0.5e-3)
    expected = amplitude * np.exp(1j * (0.3 + 0.7 * ppm_hz + 2 * np.pi * f * t))
    np.testing.assert_allclose(pulse.signal_hz, expected, rtol=1e-12, atol=0)


# ---- 4. The pulse key ----


def _mprage_like(after_rf=False):
    """Blocks with one RF and a different phase-encode gradient in each: before the RF
    (ending where the RF starts, as pypulseq's MPRAGE) or after it. Then a block with the
    RF alone. Each RF block is followed by a readout."""
    rf = _hard("excitation", math.radians(8), duration=0.2e-3)
    spoiler = pp.make_trapezoid("x", area=300, duration=0.6e-3, system=SYSTEM)
    rf.delay = 0.6e-3
    gx, adc, _ = _readout()
    seq = _new()
    for k in range(4):
        pe = pp.make_trapezoid("y", area=50.0 * (k + 1), duration=0.6e-3, system=SYSTEM)
        if after_rf:
            pe.delay = rf.delay + rf.shape_dur + SYSTEM.rf_ringdown_time
            seq.add_block(rf, pe)
        else:
            seq.add_block(rf, spoiler, pe)
        seq.add_block(gx, adc)
    seq.add_block(rf)
    seq.add_block(gx, adc)
    return seq


@pytest.mark.parametrize("after_rf", [False, True], ids=["before", "after"])
def test_pulse_key_ignores_gradients_outside_the_rf(after_rf, tmp_path):
    """MPRAGE-like blocks, each with a different phase-encode gradient before or after
    the RF, have the key of the block with the RF alone, and kind "none". Also after a
    write and read of the file (times in µs: a spoiler that ends at the RF start then
    ends 1e-19 s after it, which the TIME_TOLERANCE rule of `block_pulse` ignores)."""
    seq = _mprage_like(after_rf)
    path = tmp_path / "mprage_like.seq"
    seq.write(str(path))
    read = pp.Sequence(SYSTEM)
    read.read(str(path))
    for s in (seq, read):
        pulses = [rp.block_pulse(s, i) for i in range(0, 10, 2)]
        assert len({p.key for p in pulses}) == 1
        assert all(p.gradient_kind == "none" for p in pulses)


def test_pulse_key_ignores_the_phase_offset():
    """The blocks of an RF-spoiled GRE (a new phase offset in each TR, so a new RF event)
    have one key, and one distinct pulse in each period."""
    seq = _gre(4, rf_spoiling=True)
    assert len({seq.block_events[b][1] for b in (1, 5, 9, 13)}) == 4  # four RF events
    keys = {rp.block_pulse(seq, i).key for i in (0, 4, 8, 12)}
    assert len(keys) == 1


def test_pulse_key_differs_for_different_frequency_offsets():
    """Blocks with different frequency offsets (three slices) have different keys."""
    seq = _gre(1, slices=(-5e-3, 0.0, 5e-3))
    keys = [rp.block_pulse(seq, i).key for i in (0, 4, 8)]
    assert len(set(keys)) == 3


# ---- 5. The echo pathway ----


def test_echo_pathway_of_a_gre():
    """A GRE (the rephaser in the next block): the pathway ends at the ADC of the same
    TR, sign +1, and the moment cancels the dephasing of the pulse on z and the readout
    moment on x (REPHASING_TOL of the moment each cancels)."""
    seq = _gre(2)
    rf, gz, _ = _sinc("excitation")
    _, _, to_centre = _readout()
    pulse = rp.block_pulse(seq, 4)
    assert pulse.echo_reason is None
    echo = pulse.echo
    assert echo.adc_block == 6 and echo.sign == 1
    half = _half_moment(rf, gz)
    assert abs(echo.moment_per_m[2] + half) <= REPHASING_TOL * half
    assert abs(echo.moment_per_m[0]) <= REPHASING_TOL * to_centre
    assert echo.moment_per_m[1] == 0.0


def test_echo_pathway_of_a_spin_echo_with_crushers():
    """A spin echo with crushers around the refocusing pulse (on y): sign -1, and the
    residual moment is 0 on each axis within REPHASING_TOL of the moment it cancels (z:
    the dephasing of the pulse, which the conjugation turns; y: the crusher; x: the
    readout)."""
    seq = _spin_echo("y")
    rf, gz, _ = _sinc("excitation")
    _, _, to_centre = _readout()
    echo = rp.block_pulse(seq, 0).echo
    assert echo.adc_block == 5 and echo.sign == -1
    half = _half_moment(rf, gz)
    # With the sign -1, the echo phase is -(dephasing) + moment: the moment must be +half.
    assert abs(echo.moment_per_m[2] - half) <= REPHASING_TOL * half
    assert abs(echo.moment_per_m[1]) <= REPHASING_TOL * CRUSHER_AREA
    assert abs(echo.moment_per_m[0]) <= REPHASING_TOL * to_centre


def test_echo_pathway_without_an_adc():
    """No ADC before the next excitation (a dummy TR), no ADC before the end of the
    file, and a walk longer than `max_blocks`: no pathway, reason NO_ADC. The pathway of
    the last excitation before the ADC is found."""
    seq = _gre(1, dummies=1)
    dummy = rp.block_pulse(seq, 0)
    assert dummy.echo is None and dummy.echo_reason == rp.NO_ADC
    assert rp.block_pulse(seq, 4).echo.adc_block == 6
    assert rp.block_pulse(seq, 4, max_blocks=1).echo_reason == rp.NO_ADC

    end = _new()
    rf, gz, gzr = _sinc("excitation")
    end.add_block(rf, gz)
    end.add_block(gzr)
    last = rp.block_pulse(end, 0)
    assert last.echo is None and last.echo_reason == rp.NO_ADC
    # Only excitation pulses get a pathway.
    refocusing = rp.block_pulse(_spin_echo("y"), 3)
    assert refocusing.echo is None and refocusing.echo_reason is None


def test_echo_pathway_of_a_tse_like_merged_rephaser_and_crusher():
    """A TSE-like start (as pypulseq's write_tse): the slice rephaser and the first
    crusher are one gradient in the next block. The echo rule gives a residual moment of
    0 (REPHASING_TOL of the moment it cancels). A next-block rule (the select area from
    the RF end to the end of the next block, sign +1; section 2.3 of the plan, item 1 of
    the survey) leaves the crusher area."""
    rf, gz, gzr = _sinc("excitation")
    rf_ref, gz_ref, _ = _sinc("refocusing", math.pi, phase_offset=math.pi / 2)
    gx, adc, to_centre = _readout()
    merged = _trap("z", gzr.area + CRUSHER_AREA)
    seq = _new()
    seq.add_block(rf, gz)
    seq.add_block(merged, _trap("x", to_centre))
    seq.add_block(rf_ref, gz_ref)
    seq.add_block(_trap("z", CRUSHER_AREA))
    seq.add_block(gx, adc)
    echo = rp.block_pulse(seq, 0).echo
    half = _half_moment(rf, gz)
    assert echo.sign == -1
    assert abs(echo.moment_per_m[2] - half) <= REPHASING_TOL * half

    ramp_after_rf = gz.amplitude * gz.fall_time / 2
    next_block_residual = ramp_after_rf + merged.area + half  # +1 * (moment) + dephasing
    assert next_block_residual == pytest.approx(CRUSHER_AREA, rel=1e-9)
    assert abs(next_block_residual) / half > 1


def test_echo_pathway_stops_at_a_saturation_pulse():
    """A saturation pulse between an excitation and its ADC: no pathway, reason
    OTHER_RF_BEFORE_ADC."""
    rf, gz, gzr = _sinc("excitation")
    gx, adc, _ = _readout()
    seq = _new()
    seq.add_block(rf, gz)
    seq.add_block(gzr)
    seq.add_block(_hard("saturation"))
    seq.add_block(gx, adc)
    pulse = rp.block_pulse(seq, 0)
    assert pulse.echo is None and pulse.echo_reason == rp.OTHER_RF_BEFORE_ADC


# ---- 6. The period ----


def test_period_of_a_gre_is_one_tr():
    """A GRE: the period of a block of the second TR is that TR (blocks 4 to 7), with
    one excitation, count 1, and its ADC block. The last TR ends at the end of the
    file."""
    seq = _gre(3)
    per = rp.period(seq, 5)
    assert (per.first_block, per.last_block, per.first_adc_block) == (4, 7, 6)
    assert not per.truncated
    (pulse,) = per.pulses
    assert (pulse.use, pulse.first_block, pulse.last_block, pulse.count) == (
        "excitation",
        4,
        4,
        1,
    )
    assert pulse.key == rp.block_pulse(seq, 4).key
    assert (rp.period(seq, 11).first_block, rp.period(seq, 11).last_block) == (8, 11)


def test_period_of_a_spin_echo():
    """A spin echo: one period with the excitation and the refocusing pulse, in the
    order of their first block."""
    seq = _spin_echo("y")
    per = rp.period(seq, 3)
    assert (per.first_block, per.last_block, per.first_adc_block) == (0, 5, 5)
    assert [(p.use, p.first_block, p.count) for p in per.pulses] == [
        ("excitation", 0, 1),
        ("refocusing", 3, 1),
    ]


def test_period_counts_repeated_refocusing_pulses():
    """Two refocusing pulses before one ADC (a double spin echo): one distinct
    refocusing pulse with count 2, first block 3 and last block 6."""
    seq = _spin_echo("y", num_ref=2)
    per = rp.period(seq, 0)
    assert [(p.use, p.first_block, p.last_block, p.count) for p in per.pulses] == [
        ("excitation", 0, 0, 1),
        ("refocusing", 3, 6, 2),
    ]


def test_period_of_a_tse_like_train_is_one_echo_train():
    """A TSE-like train (excitation, then [refocusing, crusher, readout] three times),
    twice: refocusing pulses never start a period (decision 20), so each train is one
    period, with one distinct refocusing pulse counted three times, and the next
    excitation (after an ADC) starts the next period."""
    rf, gz, gzr = _sinc("excitation")
    rf_ref, gz_ref, _ = _sinc("refocusing", math.pi, phase_offset=math.pi / 2)
    gx, adc, _ = _readout()
    seq = _new()
    for _ in range(2):
        seq.add_block(rf, gz)
        seq.add_block(_trap("z", gzr.area + CRUSHER_AREA))
        for _ in range(3):
            seq.add_block(rf_ref, gz_ref)
            seq.add_block(_trap("z", CRUSHER_AREA))
            seq.add_block(gx, adc)
    for block in (0, 1, 6, 10):
        per = rp.period(seq, block)
        assert (per.first_block, per.last_block, per.first_adc_block) == (0, 10, 4), block
        assert [(p.use, p.count) for p in per.pulses] == [("excitation", 1), ("refocusing", 3)]
    second = rp.period(seq, 13)
    assert (second.first_block, second.last_block, second.first_adc_block) == (11, 21, 15)


def test_period_with_fat_saturation_before_the_excitation():
    """A fat saturation (and its spoiler) before each excitation is in the period of
    that excitation: it is the period start, and the excitation after it is not."""
    rf, gz, gzr = _sinc("excitation")
    gx, adc, _ = _readout()
    seq = _new()
    for _ in range(2):
        seq.add_block(_hard("saturation", freq_ppm=-3.45))
        seq.add_block(_trap("z", CRUSHER_AREA))
        seq.add_block(rf, gz)
        seq.add_block(gzr)
        seq.add_block(gx, adc)
    per = rp.period(seq, 7)
    assert (per.first_block, per.last_block, per.first_adc_block) == (5, 9, 9)
    assert [(p.use, p.first_block) for p in per.pulses] == [("saturation", 5), ("excitation", 7)]


def test_period_joins_dummy_scans_to_the_first_adc():
    """Dummy TRs without an ADC are in the period of the first ADC after them: one
    distinct excitation with the count of all its blocks."""
    seq = _gre(2, dummies=3)
    per = rp.period(seq, 2)
    assert (per.first_block, per.last_block, per.first_adc_block) == (0, 15, 14)
    (pulse,) = per.pulses
    assert (pulse.first_block, pulse.last_block, pulse.count) == (0, 12, 4)


def test_period_before_the_first_rf_is_the_first_period():
    """A block before the first RF block belongs to no period: `period` gives the first
    period."""
    rf, gz, gzr = _sinc("excitation")
    gx, adc, _ = _readout()
    seq = _new()
    seq.add_block(pp.make_delay(1e-3))
    seq.add_block(_trap("x", 500))
    for _ in range(2):
        seq.add_block(rf, gz)
        seq.add_block(gzr)
        seq.add_block(gx, adc)
    per = rp.period(seq, 0)
    assert (per.first_block, per.last_block) == (2, 4)
    assert rp.period(seq, 1) == per


def test_period_is_the_same_for_each_of_its_blocks():
    """Each block of a period gives the same period (dataclass equality: blocks, pulses
    with their keys, ADC block and flag)."""
    seq = _gre(3, dummies=1)
    per = rp.period(seq, 6)
    for block in range(per.first_block, per.last_block + 1):
        assert rp.period(seq, block) == per


def test_period_truncated_after_max_blocks():
    """An excitation, 30 gradient blocks, then the ADC: with `max_blocks` = 10 the
    period of block 15 is cut 10 blocks each way and is `truncated`; with the default it
    is the whole period."""
    rf, gz, gzr = _sinc("excitation")
    gx, adc, _ = _readout()
    seq = _new()
    seq.add_block(rf, gz)
    for _ in range(30):
        seq.add_block(gzr)
    seq.add_block(gx, adc)
    short = rp.period(seq, 15, max_blocks=10)
    assert (short.first_block, short.last_block, short.truncated) == (5, 25, True)
    assert short.pulses == () and short.first_adc_block is None
    full = rp.period(seq, 15)
    assert (full.first_block, full.last_block, full.truncated) == (0, 31, False)


# ---- 7. The labels ----


def test_rf_uses_labeled_and_unlabeled_sequences():
    """`rf_uses_labeled` is True for the test sequences and a file without RF, and False
    when one RF event has the use "undefined". Then `block_pulse`, `period`,
    `combined_profile` and `pulse_list` raise ValueError."""
    for seq in (_gre(1), _spin_echo("y"), _mprage_like(), _new()):
        assert rp.rf_uses_labeled(seq)
    seq = _gre(1)
    unlabeled = pp.make_block_pulse(
        flip_angle=0.1, duration=0.2e-3, delay=SYSTEM.rf_dead_time, system=SYSTEM
    )
    seq.add_block(unlabeled)
    assert not rp.rf_uses_labeled(seq)
    per = rp.Period(0, 3, (), 2, False)
    for call in (
        lambda: rp.block_pulse(seq, 0),
        lambda: rp.period(seq, 0),
        lambda: rp.combined_profile(seq, per),
        lambda: rp.pulse_list(seq),
    ):
        with pytest.raises(ValueError, match="rf_uses_labeled"):
            call()


# ---- 8. The combined profile ----


def test_combined_profile_one_direction():
    """A spin echo with the refocusing pulse on z, 1.5 times as wide as the excitation:
    one direction, and the combined line equals the product of the two "profile" views
    at the same points (exact: the same points and the same simulation). `line_pulses`
    holds each pulse's block and those same values (exact). The signal kept is below 1,
    and the numbers follow their definitions (exact or 1e-15: the same formulas)."""
    seq = _spin_echo("z", 1.5 * W)
    combined = rp.combined_profile(seq, rp.period(seq, 0))
    assert combined.reason is None
    assert (combined.excitation_block, combined.refocusing_blocks) == (0, (3,))
    assert combined.directions == ("z",) and combined.maps == ()
    exc, ref = rp.block_pulse(seq, 0), rp.block_pulse(seq, 3)
    exc_profile, ref_profile = _profile(exc), _profile(ref)
    np.testing.assert_array_equal(exc_profile.grid[0], ref_profile.grid[0])
    mxy = rp.quantity(exc_profile, "mxy_abs")
    product = mxy * rp.quantity(ref_profile, "beta_sq")
    u, values = combined.line
    np.testing.assert_array_equal(u, exc_profile.grid[0])
    np.testing.assert_array_equal(values, product)
    assert [block for block, _ in combined.line_pulses] == [0, 3]
    np.testing.assert_array_equal(combined.line_pulses[0][1], mxy)
    np.testing.assert_array_equal(combined.line_pulses[1][1], rp.quantity(ref_profile, "beta_sq"))
    numbers = combined.numbers
    kept = np.trapezoid(product, u) / np.trapezoid(mxy, u)
    assert numbers["signal_kept"] == pytest.approx(kept, rel=1e-15)
    assert numbers["signal_kept"] < 1
    assert numbers["fwhm_m"] == profile_metrics.fwhm(u, product)
    assert numbers["edge_width_m"] == profile_metrics.edge_width(u, product)
    inside = np.abs(u) <= W / 2
    assert numbers["fraction_inside"] == pytest.approx(
        product[inside].sum() / product.sum(), rel=1e-15
    )
    assert numbers["centre_signal"] == pytest.approx(np.interp(0.0, u, product), rel=1e-15)


def test_combined_profile_two_logical_directions():
    """Excitation on z, refocusing on y, each over +-2W with 401 points (a column spin
    echo). `fraction_inside` and `centre_signal` equal the definitions of plan section
    4.3, item 7, computed here by hand on the "profile" views: the product over the two
    directions of the sum inside |u - c| <= W / 2 over the sum on the grid, and of each
    profile interpolated at c = 0 (relative 1e-12: the same simulation, only the order of
    float sums). The "2d" map is the outer product of the two direction products on the
    MAP_POINTS map axes (exact)."""
    seq = _spin_echo("y")
    per = rp.period(seq, 0)
    combined = rp.combined_profile(seq, per, view="2d")
    assert combined.reason is None and combined.line is None
    assert combined.line_pulses == ()
    assert combined.directions == ("z", "y")
    exc, ref = rp.block_pulse(seq, 0), rp.block_pulse(seq, 3)
    z_profile, y_profile = _profile(exc), _profile(ref)
    assert z_profile.grid[0].size == 401
    z, mxy = z_profile.grid[0], rp.quantity(z_profile, "mxy_abs")
    y, beta_sq = y_profile.grid[0], rp.quantity(y_profile, "beta_sq")

    def fraction_inside(x, profile):
        return profile[np.abs(x) <= W / 2].sum() / profile.sum()

    fraction = fraction_inside(z, mxy) * fraction_inside(y, beta_sq)
    centre = np.interp(0, z, mxy) * np.interp(0, y, beta_sq)
    assert combined.numbers["fraction_inside"] == pytest.approx(fraction, rel=1e-12)
    assert combined.numbers["centre_signal"] == pytest.approx(centre, rel=1e-12)

    (cmap,) = combined.maps
    y_axis, z_axis = cmap.axes
    assert (y_axis.kind, z_axis.kind) == ("y", "z")
    assert y_axis.n == z_axis.n == rp.MAP_POINTS
    y_map = rp.simulate(ref, rp.ProfileSpec((y_axis,)))
    z_map = rp.simulate(exc, rp.ProfileSpec((z_axis,)))
    expected = np.outer(rp.quantity(y_map, "beta_sq"), rp.quantity(z_map, "mxy_abs"))
    np.testing.assert_array_equal(cmap.values, expected)


def test_combined_profile_three_directions():
    """PRESS-like: excitation on x, refocusing on y and on z. The numbers are products
    over the three directions; with "2d", three maps (x-y, x-z, y-z), each the outer
    product of two direction lines times the third at its slice centre. Relative 1e-12
    (the same simulations; the third value is a one-point simulation)."""
    n = 41
    rf_ex, gz_ex, gzr = _sinc("excitation")
    gx, adc, _ = _readout()
    seq = _new()
    seq.add_block(rf_ex, _on_axis(gz_ex, "x"))
    seq.add_block(_on_axis(gzr, "x"))
    for axis in ("y", "z"):
        rf_ref, gz_ref, _ = _sinc("refocusing", math.pi, phase_offset=math.pi / 2)
        seq.add_block(_trap(axis, CRUSHER_AREA))
        seq.add_block(rf_ref, _on_axis(gz_ref, axis))
        seq.add_block(_trap(axis, CRUSHER_AREA))
    seq.add_block(gx, adc)
    combined = rp.combined_profile(seq, rp.period(seq, 0), view="2d", n=n)
    assert combined.reason is None
    assert combined.directions == ("x", "y", "z")
    pulses = [rp.block_pulse(seq, i) for i in (0, 3, 6)]
    lines = []
    for p in pulses:
        prof = _profile(p, n)
        name = "mxy_abs" if p.use == "excitation" else "beta_sq"
        lines.append((prof.grid[0], rp.quantity(prof, name)))
    fraction = math.prod(v[np.abs(u) <= W / 2].sum() / v.sum() for u, v in lines)
    centre = math.prod(np.interp(0.0, u, v) for u, v in lines)
    assert combined.numbers["fraction_inside"] == pytest.approx(fraction, rel=1e-12)
    assert combined.numbers["centre_signal"] == pytest.approx(centre, rel=1e-12)

    at_centre = []
    for p in pulses:  # each pulse at its slice centre (0), a spec without axes
        point = rp.simulate(p, rp.ProfileSpec(()))
        at_centre.append(
            float(rp.quantity(point, "mxy_abs" if p.use == "excitation" else "beta_sq"))
        )
    assert [tuple(a.kind for a in m.axes) for m in combined.maps] == [
        ("x", "y"),
        ("x", "z"),
        ("y", "z"),
    ]
    for cmap, (i, j, k) in zip(combined.maps, ((0, 1, 2), (0, 2, 1), (1, 2, 0)), strict=True):
        expected = np.outer(lines[i][1], lines[j][1]) * at_centre[k]
        np.testing.assert_allclose(cmap.values, expected, rtol=1e-12, atol=0)


def test_combined_profile_oblique_direction():
    """Excitation on x, refocusing oblique in the x-y plane (60 degrees from x): two
    directions ("x", "select"), and the "2d" map has the in-plane axes "s1" (x) and
    "s2" (y, perpendicular to x in that plane). Each value equals the excitation |Mxy|
    times the refocusing |beta|^2 from `spin_domain` at the 3D grid point, within 1e-12
    (the same simulation; the oblique gradient is parallel to its direction only within
    float rounding). The "s2" range puts the range of the refocusing pulse on the line
    s1 = 0."""
    n = 21
    angle = math.radians(60)
    rf_ex, gz_ex, gzr = _sinc("excitation")
    rf_ref, gz_ref, _ = _sinc("refocusing", math.pi, phase_offset=math.pi / 2)
    gx, adc, _ = _readout()
    seq = _new()
    seq.add_block(rf_ex, _on_axis(gz_ex, "x"))
    seq.add_block(_on_axis(gzr, "x"))
    seq.add_block(
        rf_ref, _on_axis(gz_ref, "x", math.cos(angle)), _on_axis(gz_ref, "y", math.sin(angle))
    )
    seq.add_block(gx, adc)
    combined = rp.combined_profile(seq, rp.period(seq, 0), view="2d", n=n)
    assert combined.reason is None
    assert combined.directions == ("x", "select")
    (cmap,) = combined.maps
    s1_axis, s2_axis = cmap.axes
    assert (s1_axis.kind, s2_axis.kind, s1_axis.n, s2_axis.n) == ("s1", "s2", n, n)
    exc, ref = rp.block_pulse(seq, 0), rp.block_pulse(seq, 2)
    ref_axis = rp.view_spec(ref, "profile", n=n)[0].axes[0]
    # On s1 = 0 the coordinate along the refocusing direction is s2 * sin(60 degrees).
    assert s2_axis.lo * math.sin(angle) == pytest.approx(ref_axis.lo, rel=1e-12)
    assert s2_axis.hi * math.sin(angle) == pytest.approx(ref_axis.hi, rel=1e-12)
    s1 = np.linspace(s1_axis.lo, s1_axis.hi, n)
    s2 = np.linspace(s2_axis.lo, s2_axis.hi, n)
    g1, g2 = np.meshgrid(s1, s2, indexing="ij")
    points = np.stack([g1.ravel(), g2.ravel(), np.zeros(n * n)], axis=1)
    expected = (_values_at(exc, points) * _values_at(ref, points)).reshape(n, n)
    np.testing.assert_allclose(cmap.values, expected, rtol=0, atol=1e-12)


def test_combined_profile_non_selective_refocusing_is_a_factor():
    """A hard refocusing pulse (kind "none") is a factor: its |beta|^2 at r = 0, df = 0.
    The line is the excitation |Mxy| times that factor (exact: the same product), and
    `line_pulses` has the excitation only: the factor is not on the line."""
    seq = _spin_echo("y", hard_ref=True)
    combined = rp.combined_profile(seq, rp.period(seq, 0))
    assert combined.reason is None and combined.directions == ("z",)
    ref = rp.block_pulse(seq, 3)
    assert ref.gradient_kind == "none"
    factor = float(rp.quantity(rp.simulate(ref, rp.ProfileSpec(())), "beta_sq"))
    assert combined.factor == factor
    assert factor == pytest.approx(1.0, abs=1e-12)  # a hard 180 at r = 0, df = 0: sin(90)^2
    exc_profile = _profile(rp.block_pulse(seq, 0))
    _, values = combined.line
    np.testing.assert_array_equal(values, rp.quantity(exc_profile, "mxy_abs") * factor)
    ((block, exc_values),) = combined.line_pulses
    assert block == 0
    np.testing.assert_array_equal(exc_values, rp.quantity(exc_profile, "mxy_abs"))


def _gre_one_tr():
    return _gre(1)


def _without_adc():
    rf_ex, gz_ex, gzr = _sinc("excitation")
    rf_ref, gz_ref, _ = _sinc("refocusing", math.pi)
    seq = _new()
    seq.add_block(rf_ex, gz_ex)
    seq.add_block(gzr)
    seq.add_block(rf_ref, _on_axis(gz_ref, "y"))
    return seq


def _with_changing_refocusing():
    rf_ex, gz_ex, gzr = _sinc("excitation")
    gx, adc, _ = _readout()
    turn_x, turn_y = _turning_gradients()
    seq = _new()
    seq.add_block(rf_ex, gz_ex)
    seq.add_block(gzr)
    seq.add_block(_hard("refocusing", math.pi, duration=0.8e-3), turn_x, turn_y)
    seq.add_block(gx, adc)
    return seq


def _with_inversion_before_adc():
    rf_ex, gz_ex, gzr = _sinc("excitation")
    gx, adc, _ = _readout()
    seq = _new()
    seq.add_block(rf_ex, gz_ex)
    seq.add_block(gzr)
    seq.add_block(_hard("inversion", math.pi))
    seq.add_block(gx, adc)
    return seq


def _refocusing_only():
    rf_ref, gz_ref, _ = _sinc("refocusing", math.pi)
    gx, adc, _ = _readout()
    seq = _new()
    seq.add_block(rf_ref, gz_ref)
    seq.add_block(gx, adc)
    return seq


@pytest.mark.parametrize(
    ("build", "reason"),
    [
        (_gre_one_tr, "no refocusing pulse between the excitation and the ADC"),
        (_without_adc, rp.NO_ADC),
        (_with_changing_refocusing, rp.DIRECTION_CHANGES),
        (_with_inversion_before_adc, rp.OTHER_RF_BEFORE_ADC),
        (_refocusing_only, "no excitation before the first ADC of the period"),
    ],
    ids=["gre", "no_adc", "changing", "inversion", "no_excitation"],
)
def test_no_combined_profile_reasons(build, reason):
    """No combined profile, with the reason and empty fields, for: a GRE (no refocusing
    pulse), a period without an ADC, a refocusing pulse of kind "changing", an inversion
    pulse between the excitation and the ADC, and a refocusing pulse without an
    excitation before the ADC."""
    seq = build()
    combined = rp.combined_profile(seq, rp.period(seq, 0))
    assert combined.reason == reason
    assert combined.excitation_block is None and combined.refocusing_blocks == ()
    assert combined.line is None and combined.maps == () and combined.numbers == {}
    assert combined.line_pulses == ()
    assert math.isnan(combined.factor)


def test_fat_saturation_before_the_excitation_does_not_take_part():
    """A fat saturation before the excitation is in the period, but not in the combined
    profile: the excitation and the refocusing pulse only."""
    fat_sat = ((_hard("saturation", freq_ppm=-3.45),), (_trap("z", CRUSHER_AREA),))
    seq = _spin_echo("y", before=fat_sat)
    per = rp.period(seq, 2)
    assert per.first_block == 0
    combined = rp.combined_profile(seq, per)
    assert combined.reason is None
    assert (combined.excitation_block, combined.refocusing_blocks) == (2, (5,))


# ---- 9. The views ----


def test_profile_view_for_each_kind():
    """The "profile" view: kind "one" with W (c +- 2W, NUM_POSITIONS points, c = f / G);
    kind "one" without W (+- 2 times the spectrum thickness, and the note); kind "none"
    (df, f +- 2B); kind "changing" (None and the reason, in
    test_gradient_kind_changing_for_a_turning_gradient). B is the FWHM of the
    zero-padded spectrum, computed here with numpy (relative 1e-12: the same formula)."""
    rf, gz, _ = _sinc("excitation")
    rf.freq_offset = gz.amplitude * 1e-3
    with_w = _new()
    with_w.add_block(rf, gz)
    pulse = rp.block_pulse(with_w, 0)
    assert pulse.notes == ()
    (axis,) = rp.view_spec(pulse)[0].axes
    assert (axis.kind, axis.n) == ("z", rp.NUM_POSITIONS)
    assert (axis.lo, axis.hi) == (pulse.slice_centre_m - 2 * W, pulse.slice_centre_m + 2 * W)

    def spectrum_fwhm(signal, dt):
        n = rp.SPECTRUM_PADDING * signal.size
        spectrum = np.abs(np.fft.fftshift(np.fft.fft(signal, n)))
        freqs = np.fft.fftshift(np.fft.fftfreq(n, dt))
        above = freqs[spectrum >= spectrum.max() / 2]
        return above.max() - above.min()

    without_w = _new(thickness=None)
    without_w.add_block(rf, gz)
    pulse = rp.block_pulse(without_w, 0)
    assert pulse.nominal_m is None and pulse.notes == (rp.NO_SLICE_THICKNESS,)
    (axis,) = rp.view_spec(pulse, n=51)[0].axes
    half = 2 * spectrum_fwhm(pulse.signal_hz, pulse.dt_s) / abs(gz.amplitude)
    assert axis.n == 51
    assert axis.lo == pytest.approx(pulse.slice_centre_m - half, rel=1e-12)
    assert axis.hi == pytest.approx(pulse.slice_centre_m + half, rel=1e-12)

    hard = _new()
    hard.add_block(_hard("excitation", freq_offset=-200.0))
    pulse = rp.block_pulse(hard, 0)
    (axis,) = rp.view_spec(pulse)[0].axes
    b = spectrum_fwhm(pulse.signal_hz, pulse.dt_s)
    assert axis.kind == "df"
    assert axis.lo == pytest.approx(-200.0 - 2 * b, rel=1e-12)
    assert axis.hi == pytest.approx(-200.0 + 2 * b, rel=1e-12)
    assert rp.view_spec(pulse, "z_df") == (
        None,
        "no gradient: the profile against Δf is the 1D profile",
    )


def test_z_df_grid_lines_equal_1d_profiles():
    """A z x df view of a pulse whose gradient is not constant (the RF is longer than the
    flat top, so the whole grid is simulated): each row equals the 1D df profile with
    that z in `at`, and each column the 1D z profile with that df in `at` (exact: the
    same points)."""
    rf, gz, _ = _sinc("excitation")
    short = pp.make_trapezoid("z", amplitude=gz.amplitude, flat_time=1e-3, system=SYSTEM)
    seq = _new()
    seq.add_block(rf, short)
    pulse = rp.block_pulse(seq, 0)
    assert pulse.gradient_kind == "one" and not pulse.constant_gradient
    spec, _ = rp.view_spec(pulse, "z_df", n=15)
    z_axis, df_axis = spec.axes
    assert (z_axis.kind, df_axis.kind, z_axis.n, df_axis.n) == ("z", "df", 15, 15)
    step_z = (z_axis.hi - z_axis.lo) / 14
    step_df = abs(pulse.select_gradient_hz_per_m) * step_z  # G: the mean during the RF
    assert (df_axis.hi - df_axis.lo) / 14 == pytest.approx(step_df, rel=1e-12)
    assert df_axis.lo == -df_axis.hi
    full = rp.simulate(pulse, spec)
    z, df = full.grid
    for i in (0, 7, 14):
        row = rp.simulate(pulse, rp.ProfileSpec((df_axis,), {"z": float(z[i])}))
        np.testing.assert_array_equal(full.a[i], row.a)
        np.testing.assert_array_equal(full.b[i], row.b)
    for j in (0, 5, 14):
        column = rp.simulate(pulse, rp.ProfileSpec((z_axis,), {"df": float(df[j])}))
        np.testing.assert_array_equal(full.a[:, j], column.a)
        np.testing.assert_array_equal(full.b[:, j], column.b)


@pytest.mark.parametrize("sign", [1, -1], ids=["positive_g", "negative_g"])
def test_z_df_shear_equals_the_full_grid(sign):
    """With a constant gradient, the z x df view is one 1D simulation of the distinct
    values z + df / G; it equals the whole grid from `spin_domain` at each (z, df) point
    within 1e-12 (float rounding of z + df / G against G * z + df), for either sign of
    G."""
    rf, gz, _ = _sinc("excitation")
    rf.freq_offset = 300.0
    seq = _new()
    seq.add_block(rf, _on_axis(gz, "z", sign))
    pulse = rp.block_pulse(seq, 0)
    spec, _ = rp.view_spec(pulse, "z_df", n=25)
    sheared = rp.simulate(pulse, spec)
    z, df = np.meshgrid(*sheared.grid, indexing="ij")
    positions = np.zeros((z.size, 3))
    positions[:, 2] = z.ravel()
    a, b = spin_domain(pulse.signal_hz, pulse.dt_s, pulse.grad_hz_per_m, positions, df.ravel())
    np.testing.assert_allclose(sheared.a, a.reshape(z.shape), rtol=0, atol=1e-12)
    np.testing.assert_allclose(sheared.b, b.reshape(z.shape), rtol=0, atol=1e-12)


def test_2d_view():
    """The "2d" view of a pulse of kind "changing": with `plane` and `extent_m`; with the
    FOV definition (the two axes with the largest RMS gradient, x and y); with neither
    (None, NO_FOV). A pulse of kind "one" has no "2d" view."""
    gx, gy = _turning_gradients()
    seq = _new()
    seq.add_block(_hard("excitation", duration=0.8e-3), gx, gy)
    pulse = rp.block_pulse(seq, 0)
    assert rp.view_spec(pulse, "2d") == (None, rp.NO_FOV)
    spec, reason = rp.view_spec(pulse, "2d", plane=("y", "z"), extent_m=0.1)
    assert reason is None
    assert spec.axes == (
        rp.ProfileAxis("y", -0.05, 0.05, rp.MAP_POINTS),
        rp.ProfileAxis("z", -0.05, 0.05, rp.MAP_POINTS),
    )
    seq.set_definition("FOV", [0.2, 0.25, 0.005])
    pulse = rp.block_pulse(seq, 0)
    spec, reason = rp.view_spec(pulse, "2d", n=9)
    assert spec.axes == (rp.ProfileAxis("x", -0.1, 0.1, 9), rp.ProfileAxis("y", -0.125, 0.125, 9))
    assert rp.simulate(pulse, spec).a.shape == (9, 9)
    rf, gz, _ = _sinc("excitation")
    one = _new()
    one.add_block(rf, gz)
    assert rp.view_spec(rp.block_pulse(one, 0), "2d", extent_m=0.1)[0] is None


# ---- 10. The quantities and the widths ----


@pytest.mark.parametrize(
    ("use", "flip"),
    [
        ("excitation", math.pi / 2),
        ("refocusing", math.pi),
        ("inversion", math.pi),
        ("saturation", math.pi / 2),
        ("preparation", math.pi / 2),
        ("other", math.pi / 2),
    ],
)
def test_quantities_and_widths_for_each_use(use, flip):
    """For each use of section 4.3, item 2: `quantity` is |2 conj(a) b|, |a|^2 - |b|^2
    and |b|^2 (exact: the same formulas); `widths` measures the profile of the use
    (excitation, preparation, other |Mxy|; refocusing |beta|^2; inversion (1 - Mz) / 2;
    saturation 1 - Mz) at u - c (exact). Only an excitation with a pathway gets the phase
    numbers, and its echo phase is 0 at the slice centre and NaN below 10 % of max |Mxy|.
    pypulseq 1.5 stores use="other" as undefined, so the "other" case sets the letter "o"
    in `rf_library.type`, as a file with that label is read."""
    rf, gz, gzr = _sinc("preparation" if use == "other" else use, flip)
    rf.freq_offset = gz.amplitude * 0.5e-3
    gx, adc, to_centre = _readout()
    seq = _new()
    seq.add_block(rf, gz)
    seq.add_block(gzr, _trap("x", -to_centre))
    seq.add_block(gx, adc)
    if use == "other":
        seq.rf_library.type[seq.block_events[1][1]] = "o"
    pulse = rp.block_pulse(seq, 0)
    assert pulse.use == use
    profile = _profile(pulse, 201)
    a, b = profile.a, profile.b
    np.testing.assert_array_equal(rp.quantity(profile, "mxy_abs"), np.abs(2 * np.conj(a) * b))
    np.testing.assert_array_equal(rp.quantity(profile, "mz"), np.abs(a) ** 2 - np.abs(b) ** 2)
    np.testing.assert_array_equal(rp.quantity(profile, "beta_sq"), np.abs(b) ** 2)
    with pytest.raises(ValueError, match="quantity"):
        rp.quantity(profile, "phase")

    mz = np.abs(a) ** 2 - np.abs(b) ** 2
    main = {
        "refocusing": np.abs(b) ** 2,
        "inversion": (1 - mz) / 2,
        "saturation": 1 - mz,
    }.get(use, np.abs(2 * np.conj(a) * b))
    u = profile.grid[0]
    rel = u - pulse.slice_centre_m
    numbers = rp.widths(pulse, profile)
    assert numbers["fwhm"] == profile_metrics.fwhm(u, main)
    assert numbers["edge_width"] == profile_metrics.edge_width(u, main)
    assert numbers["passband_ripple"] == profile_metrics.passband_ripple(rel, main, W)
    assert numbers["stopband_level"] == profile_metrics.stopband_level(rel, main, W)
    phase_keys = {"rephasing_error_rad", "nonlinear_residual_rad", "centre_phase_rad"}
    if use == "excitation":
        assert phase_keys <= set(numbers)
        phase = rp.echo_phase(pulse, profile)
        centre = int(np.argmin(np.abs(rel)))
        assert abs(phase[centre]) <= 1e-15  # the angle of z * exp(-1j * angle(z)): rounding
        mxy = np.abs(2 * np.conj(a) * b)
        np.testing.assert_array_equal(np.isnan(phase), mxy < 0.1 * mxy.max())
    else:
        assert not phase_keys & set(numbers)
        assert rp.echo_phase(pulse, profile) is None


def test_rephasing_error_of_a_1_5x_rephaser():
    """A rephaser of 1.5 times the correct moment m leaves the moment 0.5 * m, a linear
    echo phase 2*pi * 0.5 * m * u: the rephasing error grows by 0.5 * 2*pi * m * W
    against the correct rephaser, within 1e-6 (the linear fit on the same weights; the
    difference is exact up to float rounding). The error of the correct rephaser is not
    0 for a 90-degree sinc (the pulse's own non-linear phase has a linear part), so the
    test compares the two sequences. `echo_moment_per_m` gives the same numbers as the
    pathway (exact)."""
    rf, gz, gzr = _sinc("excitation")
    gx, adc, to_centre = _readout()
    errors = []
    for scale in (1.0, 1.5):
        seq = _new()
        seq.add_block(rf, gz)
        seq.add_block(pp.scale_grad(gzr, scale), _trap("x", -to_centre))
        seq.add_block(gx, adc)
        pulse = rp.block_pulse(seq, 0)
        profile = _profile(pulse)
        numbers = rp.widths(pulse, profile)
        errors.append(numbers["rephasing_error_rad"])
        replaced = rp.widths(pulse, profile, echo_moment_per_m=pulse.echo.moment_per_m)
        assert replaced == numbers
    expected = 0.5 * 2 * math.pi * gzr.area * W
    assert errors[1] - errors[0] == pytest.approx(expected, abs=1e-6)


# ---- 11. Spec errors ----


def _pulse_on_z():
    rf, gz, _ = _sinc("excitation")
    seq = _new()
    seq.add_block(rf, gz)
    return rp.block_pulse(seq, 0)


def _pulse_oblique():
    rf, gz, _ = _sinc("excitation")
    seq = _new()
    seq.add_block(rf, _on_axis(gz, "x", 0.6), _on_axis(gz, "y", 0.8))
    return rp.block_pulse(seq, 0)


_Z = rp.ProfileAxis("z", -0.01, 0.01, 11)
_DF = rp.ProfileAxis("df", -1000.0, 1000.0, 11)
_SELECT = rp.ProfileAxis("select", -0.01, 0.01, 11)


@pytest.mark.parametrize(
    ("make_pulse", "spec"),
    [
        (_pulse_on_z, rp.ProfileSpec((rp.ProfileAxis("w", 0, 1, 3),))),
        (_pulse_on_z, rp.ProfileSpec((_Z, _Z))),
        (_pulse_on_z, rp.ProfileSpec((_Z,), {"z": 0.0})),
        (_pulse_oblique, rp.ProfileSpec((_SELECT,), {"z": 0.0})),
        (_pulse_on_z, rp.ProfileSpec((_SELECT,))),
        (_pulse_on_z, rp.ProfileSpec((rp.ProfileAxis("z", -0.01, 0.01, 1),))),
        (_pulse_on_z, rp.ProfileSpec((rp.ProfileAxis("z", 0.01, 0.01, 5),))),
        (
            _pulse_on_z,
            rp.ProfileSpec(
                (rp.ProfileAxis("z", 0.0, 1.0, 300), rp.ProfileAxis("df", -1.0, 1.0, 300))
            ),
        ),
    ],
    ids=[
        "unknown_kind",
        "kind_twice",
        "kind_in_axes_and_at",
        "select_with_z",
        "select_for_a_logical_pulse",
        "one_point",
        "lo_not_below_hi",
        "too_many_points",
    ],
)
def test_spec_errors(make_pulse, spec):
    """Each rule of the specs (section 4.2 of the plan): `simulate` raises ValueError."""
    with pytest.raises(ValueError):
        rp.simulate(make_pulse(), spec)


def test_argument_errors():
    """The other argument checks: a number of points that is not an int (TypeError), an
    unknown view, a plane that is not two different logical axes, n < 2, a bad
    `extent_m`, an unknown combined view (ValueError), and a play index outside the file
    (IndexError)."""
    pulse = _pulse_on_z()
    with pytest.raises(TypeError):
        rp.simulate(pulse, rp.ProfileSpec((rp.ProfileAxis("z", -0.01, 0.01, 5.0),)))
    gx, gy = _turning_gradients()
    seq = _new()
    seq.add_block(_hard("excitation", duration=0.8e-3), gx, gy)
    changing = rp.block_pulse(seq, 0)
    for kwargs in (
        {"view": "3d"},
        {"view": "2d", "plane": ("x", "x"), "extent_m": 0.1},
        {"view": "2d", "plane": ("x", "q"), "extent_m": 0.1},
        {"view": "2d", "extent_m": -0.1},
        {"view": "profile", "n": 1},
    ):
        with pytest.raises(ValueError):
            rp.view_spec(changing, **kwargs)
    spin_echo = _spin_echo("y")
    with pytest.raises(ValueError, match="view"):
        rp.combined_profile(spin_echo, rp.period(spin_echo, 0), view="z_df")
    for block in (-1, 6):
        with pytest.raises(IndexError):
            rp.block_pulse(spin_echo, block)
        with pytest.raises(IndexError):
            rp.period(spin_echo, block)


# ---- 12. The pulse list ----


def test_pulse_list_rf_spoiling_and_slices_give_one_entry():
    """An RF-spoiled GRE with three slices (a new phase offset in each block and three
    frequency offsets): one entry with all 12 RF blocks, the numbers of its first block
    (exact: the same computation)."""
    seq = _gre(4, rf_spoiling=True, slices=(-5e-3, 0.0, 5e-3))
    (entry,) = rp.pulse_list(seq)
    first = rp.block_pulse(seq, 0)
    assert (entry.first_block, entry.num_blocks, entry.use) == (0, 12, "excitation")
    assert entry.gradient_kind == "one"
    assert (entry.flip_deg, entry.peak_b1_ut, entry.energy_ut2_ms) == (
        first.flip_deg,
        first.peak_b1_ut,
        first.energy_ut2_ms,
    )
    assert entry.flip_deg == pytest.approx(90, abs=0.5)


@pytest.mark.parametrize("after_rf", [False, True], ids=["before", "after"])
def test_pulse_list_mprage_like_blocks_give_one_entry(after_rf, tmp_path):
    """MPRAGE-like blocks with a different phase-encode gradient before or after the RF
    (and a block with the RF alone): one entry of kind "none" with all 5 RF blocks, also
    after a write and read of the file. A spin echo gives two entries in block order."""
    seq = _mprage_like(after_rf)
    path = tmp_path / "mprage_like.seq"
    seq.write(str(path))
    read = pp.Sequence(SYSTEM)
    read.read(str(path))
    for s in (seq, read):
        (entry,) = rp.pulse_list(s)
        assert (entry.first_block, entry.num_blocks, entry.gradient_kind) == (0, 5, "none")
    entries = rp.pulse_list(_spin_echo("y"))
    assert [(e.first_block, e.use, e.num_blocks) for e in entries] == [
        (0, "excitation", 1),
        (3, "refocusing", 1),
    ]
    assert rp.pulse_list(_new()) == []


# ---- 13. Rotations ----


def test_rotations_are_refused():
    """A sequence with a rotation library (as pypulseq draft PR #372 stores rotations,
    see tests/test_extensions.py): `block_pulse`, `period`, `combined_profile` and
    `pulse_list` raise NotImplementedError."""
    seq = _gre(1)
    seq.rotation_library = EventLibrary()
    seq.rotation_library.insert(1, (0.9238795325112867, 0.0, 0.0, 0.3826834323650898))
    per = rp.Period(0, 3, (), 2, False)
    for call in (
        lambda: rp.block_pulse(seq, 0),
        lambda: rp.period(seq, 0),
        lambda: rp.combined_profile(seq, per),
        lambda: rp.pulse_list(seq),
    ):
        with pytest.raises(NotImplementedError, match="rotation extension"):
            call()


# ---- 14. Another nucleus ----


def test_peak_b1_of_another_nucleus():
    """With `pp.Opts(gamma=11.262e6)` (sodium), the peak B1 of a block pulse is its
    amplitude (flip / (2*pi*duration), Hz) divided by that gamma, in µT, and the energy
    follows (relative 1e-9: float rounding only)."""
    system = pp.Opts(gamma=11.262e6, rf_raster_time=5e-6, rf_dead_time=100e-6)
    seq = _new(system=system)
    seq.add_block(_hard("excitation", math.pi / 2, duration=0.5e-3, system=system))
    pulse = rp.block_pulse(seq, 0)
    b1_ut = (math.pi / 2) / (2 * math.pi * 0.5e-3) / 11.262e6 * 1e6
    assert pulse.peak_b1_ut == pytest.approx(b1_ut, rel=1e-9)
    assert pulse.energy_ut2_ms == pytest.approx(b1_ut**2 * 0.5, rel=1e-9)
    assert pulse.flip_deg == pytest.approx(90, rel=1e-9)
