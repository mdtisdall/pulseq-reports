import numpy as np
import pypulseq as pp
import pytest
from synthetic import (
    SYSTEM,
    arbitrary_gradient_sequence,
    empty_sequence,
    gre_sequence,
    spin_echo_sequence,
)

from pulseq_reports.sampling import GradientSampler
from pulseq_reports.seq_index import sequence_index

_AXES = ("gx", "gy", "gz")


def _raster_centers(duration_s: float, raster: float = SYSTEM.grad_raster_time) -> np.ndarray:
    """`(k + 0.5) * raster` for `k` in `range(ceil(duration_s / raster))`."""
    n = int(np.ceil(duration_s / raster)) if duration_s > 0 else 0
    return (np.arange(n) + 0.5) * raster


def _assert_matches_pypulseq(seq: pp.Sequence, t: np.ndarray) -> None:
    """`GradientSampler.sample(axis, t)` equals `seq.get_gradients()[axis](t)` within
    the exactness rule of section 3.5, item 2 of `docs/plans/cards-at-scale.md`: a
    relative 1e-12 and an absolute 1e-12 times the largest |value| of that axis's
    reference at `t`.

    Not bit-exact: `seq_utils.gradient_offsets` adds a trapezoid's corner times in a
    different order than pypulseq's `waveforms()` (`start + (rise + flat)` against
    `(start + rise) + flat`), and scipy's `PPoly` evaluates a line segment with its own
    formula (`c[0] * (t - x[i]) + c[1]`), not `numpy.interp`'s. Both differ by float
    rounding only.
    """
    index = sequence_index(seq)
    sampler = GradientSampler(seq, index)
    pp_gradients = seq.get_gradients()
    for axis_index, axis in enumerate(_AXES):
        ppoly = pp_gradients[axis_index]
        ref = np.zeros(t.shape, dtype=np.float64) if ppoly is None else ppoly(t)
        got = sampler.sample(axis, t)
        assert got.dtype == np.float64
        assert got.shape == t.shape
        peak = float(np.max(np.abs(ref))) if ref.size else 0.0
        np.testing.assert_allclose(got, ref, rtol=1e-12, atol=1e-12 * peak)


def _triangle_sequence() -> pp.Sequence:
    """One trapezoid on x with an area small enough that `make_trapezoid` gives it no
    flat time (a triangle): `gradient_offsets` then gives two points at the same middle
    time (both with the peak amplitude), which the join rule must remove one of."""
    seq = pp.Sequence(SYSTEM)
    g = pp.make_trapezoid(channel="x", area=10.0, system=SYSTEM)
    assert g.flat_time == 0.0
    seq.add_block(g)
    return seq


def _gap_sequence() -> pp.Sequence:
    """A trapezoid on x, a delay block with no gradient on x, and a second trapezoid on
    x: the gap between the two events."""
    seq = pp.Sequence(SYSTEM)
    seq.add_block(pp.make_trapezoid(channel="x", area=500, system=SYSTEM))
    seq.add_block(pp.make_delay(2e-3))
    seq.add_block(pp.make_trapezoid(channel="x", area=-500, system=SYSTEM))
    return seq


def _delay_padded_sequence() -> pp.Sequence:
    """A delay block, a trapezoid on x, and a second delay block: a leading and a
    trailing gap with no gradient event at all."""
    seq = pp.Sequence(SYSTEM)
    seq.add_block(pp.make_delay(1e-3))
    seq.add_block(pp.make_trapezoid(channel="x", area=500, system=SYSTEM))
    seq.add_block(pp.make_delay(1e-3))
    return seq


def _junction_sequence(step_hz_per_m: float) -> tuple[pp.Sequence, float]:
    """Two extended trapezoids on x that together make one ordinary trapezoid (the
    rise, flat and fall of an area-1000 trapezoid), split into two blocks at the middle
    of the flat top. The second block's first value is `step_hz_per_m` less than the
    first block's last value: 0 gives an amplitude that exactly continues into the next
    block, and a value up to `max_slew * grad_raster_time` is a step that pypulseq's
    `add_block` still accepts. Returns the sequence and the junction time (s)."""
    base = pp.make_trapezoid(channel="x", area=1000, system=SYSTEM)
    raster = SYSTEM.grad_raster_time
    half_flat = round((base.flat_time / 2) / raster) * raster
    amp = base.amplitude
    seq = pp.Sequence(SYSTEM)
    g1 = pp.make_extended_trapezoid(
        channel="x",
        amplitudes=np.array([0.0, amp, amp]),
        times=np.array([0.0, base.rise_time, base.rise_time + half_flat]),
        system=SYSTEM,
    )
    g2 = pp.make_extended_trapezoid(
        channel="x",
        amplitudes=np.array([amp - step_hz_per_m, amp - step_hz_per_m, 0.0]),
        times=np.array(
            [0.0, base.flat_time - half_flat, base.flat_time - half_flat + base.fall_time]
        ),
        system=SYSTEM,
    )
    seq.add_block(g1)
    seq.add_block(g2)
    return seq, base.rise_time + half_flat


@pytest.mark.parametrize(
    "seq",
    [spin_echo_sequence(), gre_sequence(), arbitrary_gradient_sequence(), empty_sequence()],
    ids=["spin_echo", "gre", "arbitrary_gradient", "empty"],
)
def test_whole_file_matches_pypulseq_for_synthetic_sequences(seq):
    index = sequence_index(seq)
    t = _raster_centers(index.end_s)
    _assert_matches_pypulseq(seq, t)


def test_subrange_that_cuts_blocks_matches_pypulseq():
    # gre_sequence(num_trs=1) has 5 blocks: rf, phase-encode (gy), readout (gx) with
    # ADC, spoiler (gz), delay. The middle of block 2 to the middle of block 4 cuts
    # through the gx event, includes the whole gz event, and leaves the gy event (block
    # 1) entirely before the range, so this also checks that gy is correctly 0 after
    # its one and only event.
    seq = gre_sequence(num_trs=1)
    index = sequence_index(seq)
    t0 = index.start_s[2] + index.duration_s[2] / 2
    t1 = index.start_s[4] + index.duration_s[4] / 2
    t = np.linspace(t0, t1, 500)
    _assert_matches_pypulseq(seq, t)


def test_subrange_inside_a_gap_matches_pypulseq():
    seq = _gap_sequence()
    index = sequence_index(seq)
    gap_start = index.start_s[1]
    gap_end = index.start_s[1] + index.duration_s[1]
    margin = 50e-6
    t = np.linspace(gap_start + margin, gap_end - margin, 200)
    _assert_matches_pypulseq(seq, t)


def test_single_sample_matches_pypulseq():
    seq = gre_sequence(num_trs=1)
    index = sequence_index(seq)
    t = np.array([index.start_s[2] + index.duration_s[2] / 2])
    _assert_matches_pypulseq(seq, t)


def test_amplitude_continues_across_a_block_junction():
    seq, junction_s = _junction_sequence(step_hz_per_m=0.0)
    t = np.sort(junction_s + np.linspace(-20, 20, 41) * SYSTEM.grad_raster_time)
    _assert_matches_pypulseq(seq, t)


def test_tolerated_step_at_a_block_junction_matches_pypulseq():
    step = 0.5 * SYSTEM.max_slew * SYSTEM.grad_raster_time
    seq, junction_s = _junction_sequence(step_hz_per_m=step)
    t = np.sort(junction_s + np.linspace(-20, 20, 41) * SYSTEM.grad_raster_time)
    _assert_matches_pypulseq(seq, t)


def test_triangle_trapezoid_matches_pypulseq():
    seq = _triangle_sequence()
    index = sequence_index(seq)
    t = _raster_centers(index.end_s)
    _assert_matches_pypulseq(seq, t)


def test_axis_without_events_is_zero():
    # spin_echo_sequence uses gx and gy only: gz has no event.
    seq = spin_echo_sequence()
    index = sequence_index(seq)
    assert seq.get_gradients()[2] is None
    t = _raster_centers(index.end_s)
    sampler = GradientSampler(seq, index)
    got = sampler.sample("gz", t)
    assert got.dtype == np.float64
    np.testing.assert_array_equal(got, np.zeros(t.shape, dtype=np.float64))


def test_zero_before_the_first_event_and_after_the_last():
    seq = _delay_padded_sequence()
    index = sequence_index(seq)
    sampler = GradientSampler(seq, index)
    before = np.linspace(0.0, index.start_s[1] - 1e-6, 50)
    after = np.linspace(index.start_s[2] + 1e-6, index.end_s, 50)
    got_before = sampler.sample("gx", before)
    got_after = sampler.sample("gx", after)
    np.testing.assert_array_equal(got_before, np.zeros(before.shape, dtype=np.float64))
    np.testing.assert_array_equal(got_after, np.zeros(after.shape, dtype=np.float64))


def test_empty_sequence_is_zero_for_any_t():
    seq = empty_sequence()
    index = sequence_index(seq)
    sampler = GradientSampler(seq, index)
    t = np.array([0.0, 1e-3, 5.0])  # 5.0 s is well past the sequence's own duration
    for axis in _AXES:
        got = sampler.sample(axis, t)
        assert got.dtype == np.float64
        np.testing.assert_array_equal(got, np.zeros(t.shape, dtype=np.float64))


def test_empty_times_gives_empty_output():
    seq = gre_sequence(num_trs=1)
    sampler = GradientSampler(seq, sequence_index(seq))
    got = sampler.sample("gx", np.array([]))
    assert got.dtype == np.float64
    assert got.shape == (0,)


def test_invalid_axis_name_raises_value_error():
    seq = gre_sequence(num_trs=1)
    sampler = GradientSampler(seq, sequence_index(seq))
    with pytest.raises(ValueError):
        sampler.sample("gw", np.array([0.0]))
