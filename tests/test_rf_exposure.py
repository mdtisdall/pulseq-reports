import math

import numpy as np
import pypulseq as pp
import pytest
from oracles import rf_exposure as oracle
from synthetic import GAMMA_1H, SYSTEM, empty_sequence, gre_sequence, spin_echo_sequence

from pulseq_reports import rf_exposure


def _b1_ut(flip_rad: float, duration_s: float) -> float:
    """The constant B1 (µT) of a block pulse with this flip angle and duration."""
    return (flip_rad / (2 * math.pi)) / duration_s / GAMMA_1H * 1e6


# B1 (µT) of a 1 ms 90° block pulse, and its ∫B1² dt (µT²·s).
B1_UT = _b1_ut(math.pi / 2, 1e-3)
PULSE_ENERGY = B1_UT**2 * 1e-3


def _pulse_train(gaps_s: list[float]) -> pp.Sequence:
    """For each gap (s): a 1 ms 90° block pulse, then a delay of that gap."""
    seq = pp.Sequence(SYSTEM)
    rf = pp.make_block_pulse(
        flip_angle=math.pi / 2, duration=1e-3, delay=SYSTEM.rf_dead_time, system=SYSTEM
    )
    for gap in gaps_s:
        seq.add_block(rf)
        seq.add_block(pp.make_delay(gap))
    return seq


def test_block_pulse_train():
    e = rf_exposure.rf_exposure(_pulse_train([3.0, 17.0]), GAMMA_1H)
    assert e.num_pulses == 2
    assert e.duration_s == pytest.approx(20, abs=0.01)
    assert e.peak_b1_ut == pytest.approx(B1_UT, rel=1e-6)
    assert e.peak_block == 1
    assert e.energy_ut2_s == pytest.approx(2 * PULSE_ENERGY, rel=1e-6)
    assert e.b1rms_ut == pytest.approx(math.sqrt(2 * PULSE_ENERGY / e.duration_s), rel=1e-6)
    assert e.b1rms_window_used_s == e.b1rms_window_s


@pytest.mark.parametrize(
    ("gaps_s", "pulses_in_window"),
    [
        ([3.0, 17.0], 2),  # both pulses are in one 10 s window
        ([15.0, 5.0], 2),  # the window goes into the next repetition
        ([11.0, 11.0], 1),  # the pulses are more than 10 s apart in both directions
    ],
)
def test_highest_window(gaps_s, pulses_in_window):
    e = rf_exposure.rf_exposure(_pulse_train(gaps_s), GAMMA_1H)
    assert e.b1rms_window_s == 10
    assert e.b1rms_window_used_s == 10
    assert e.b1rms_window_ut == pytest.approx(
        math.sqrt(pulses_in_window * PULSE_ENERGY / 10), rel=1e-6
    )


def test_short_sequence_window():
    # A 10 s window holds 33 repetitions of the 0.3 s sequence, and a part of about 60 ms
    # that can hold one more pulse.
    e = rf_exposure.rf_exposure(_pulse_train([0.3]), GAMMA_1H)
    repeats = math.floor(10 / e.duration_s)
    assert repeats == 33
    assert e.b1rms_window_ut == pytest.approx(
        math.sqrt((repeats + 1) * PULSE_ENERGY / 10), rel=1e-6
    )
    assert e.b1rms_window_ut > e.b1rms_ut


def test_a_negative_gamma_gives_the_values_of_its_magnitude():
    seq = _pulse_train([3.0, 17.0])
    assert rf_exposure.rf_exposure(seq, -GAMMA_1H) == rf_exposure.rf_exposure(seq, GAMMA_1H)


def test_the_values_follow_the_magnitude_of_the_gamma():
    """B1 is the amplitude in Hz over |gamma|, so a gamma of half the size doubles the peak,
    the energy is 4 times as large and B1+rms doubles."""
    seq = _pulse_train([3.0, 17.0])
    full = rf_exposure.rf_exposure(seq, GAMMA_1H)
    half = rf_exposure.rf_exposure(seq, -GAMMA_1H / 2)
    assert half.peak_b1_ut == pytest.approx(2 * full.peak_b1_ut, rel=1e-12)
    assert half.energy_ut2_s == pytest.approx(4 * full.energy_ut2_s, rel=1e-12)
    assert half.b1rms_ut == pytest.approx(2 * full.b1rms_ut, rel=1e-12)
    assert half.b1rms_window_ut == pytest.approx(2 * full.b1rms_window_ut, rel=1e-12)


def test_no_rf():
    e = rf_exposure.rf_exposure(empty_sequence(), GAMMA_1H)
    assert e.num_pulses == 0
    assert e.peak_block is None
    assert e.energy_ut2_s == 0
    assert e.b1rms_ut == 0
    assert e.b1rms_window_ut == 0
    assert e.b1rms_window_used_s == e.b1rms_window_s


def test_periodic_false_does_not_wrap():
    # With the window (15 s, 5 s) gap pattern, a periodic search finds a 10 s window that
    # wraps past the end of one repetition into the start of the next, catching 2 pulses
    # (see test_highest_window). A one-time play has no next repetition to wrap into, so
    # the highest 10 s window can catch only 1 pulse: the two pulses are 15 s apart, more
    # than the 10 s window, in both directions within the single play.
    seq = _pulse_train([15.0, 5.0])
    e_periodic = rf_exposure.rf_exposure(seq, GAMMA_1H, periodic=True)
    assert e_periodic.b1rms_window_ut == pytest.approx(math.sqrt(2 * PULSE_ENERGY / 10), rel=1e-6)

    e = rf_exposure.rf_exposure(seq, GAMMA_1H, periodic=False)
    assert e.duration_s > e.b1rms_window_s
    assert e.b1rms_window_used_s == e.b1rms_window_s
    assert e.b1rms_window_ut == pytest.approx(math.sqrt(1 * PULSE_ENERGY / 10), rel=1e-6)


def test_periodic_false_window_is_whole_sequence_when_shorter_than_window():
    # The 0.3 s pulse train is much shorter than the 10 s window, so with periodic=False the
    # highest window is the whole sequence: its real length is the sequence duration, and its
    # B1+rms equals the plain (non-windowed) B1+rms, both from the sequence's one pulse.
    seq = _pulse_train([0.3])
    e = rf_exposure.rf_exposure(seq, GAMMA_1H, periodic=False)
    assert e.duration_s < e.b1rms_window_s
    assert e.b1rms_window_used_s == pytest.approx(e.duration_s)
    assert e.b1rms_ut == pytest.approx(math.sqrt(PULSE_ENERGY / e.duration_s), rel=1e-6)
    assert e.b1rms_window_ut == pytest.approx(e.b1rms_ut, rel=1e-9)


def test_periodic_false_no_rf():
    e = rf_exposure.rf_exposure(empty_sequence(), GAMMA_1H, periodic=False)
    assert e.num_pulses == 0
    assert e.b1rms_window_ut == 0
    assert e.b1rms_window_used_s == e.duration_s


# ---- Comparisons with the oracle (task 3.5) ----
#
# `tests/oracles/rf_exposure.py` is the implementation from before phase 3 of
# docs/plans/cards-at-scale.md: it sums and searches over every RF sample, in play order.
# The new code sums the energy once for each unique RF event (`_pulse_train`) and once for
# each pulse in play order (`_Search`), not over every sample in play order, so the float
# additions run in a different order and can differ from the oracle's sums by float
# rounding (section 3.5, item 2 of the plan). `_assert_matches_oracle` therefore requires
# exact equality only for the fields both implementations compute the same way
# (`num_pulses`, `peak_block`, `b1rms_window_s`, `b1rms_window_used_s`), and a relative difference of
# at most 1e-12 for the summed float fields (`duration_s`, `peak_b1_ut`, `energy_ut2_s`,
# `b1rms_ut`, `b1rms_window_ut`).


def _assert_matches_oracle(ours: rf_exposure.RfExposure, theirs: oracle.RfExposure) -> None:
    assert ours.num_pulses == theirs.num_pulses
    assert ours.peak_block == theirs.peak_block
    assert ours.b1rms_window_s == theirs.window_s
    assert ours.b1rms_window_used_s == theirs.window_used_s
    for field in ("duration_s", "peak_b1_ut", "energy_ut2_s", "b1rms_ut", "b1rms_window_ut"):
        a, b = getattr(ours, field), getattr(theirs, field)
        bound = max(abs(a), abs(b)) * 1e-12
        assert abs(a - b) <= bound, f"{field}: {a!r} != {b!r} (bound {bound!r})"


@pytest.mark.parametrize(
    "make_seq",
    [spin_echo_sequence, gre_sequence, empty_sequence],
    ids=["spin_echo", "gre", "empty"],
)
@pytest.mark.parametrize("periodic", [True, False])
def test_matches_oracle_on_synthetic_sequences(make_seq, periodic):
    """`rf_exposure` matches the oracle (within the tolerance above) on each of
    `tests/synthetic.py`'s sequences, for both `periodic` values and several window
    lengths."""
    seq = make_seq()
    for window_s in (1e-3, 10.0, 100.0):
        ours = rf_exposure.rf_exposure(seq, GAMMA_1H, periodic=periodic, b1rms_window_s=window_s)
        theirs = oracle.rf_exposure(seq, window_s=window_s, periodic=periodic)
        _assert_matches_oracle(ours, theirs)


@pytest.mark.parametrize(
    "window_s",
    [0.3e-3, 5.0, 50.0],
    ids=[
        "shorter_than_one_pulse",
        "between_one_pulse_and_the_sequence",
        "longer_than_the_sequence",
    ],
)
@pytest.mark.parametrize("periodic", [True, False])
def test_matches_oracle_for_window_length_categories(window_s, periodic):
    """`rf_exposure` matches the oracle for a window shorter than one pulse (the pulses
    are 1 ms), a window between one pulse and the whole sequence, and a window longer
    than the whole sequence (about 20 s, from two 1 ms pulses and 3 s and 17 s gaps),
    for both `periodic` values."""
    seq = _pulse_train([3.0, 17.0])
    ours = rf_exposure.rf_exposure(seq, GAMMA_1H, periodic=periodic, b1rms_window_s=window_s)
    theirs = oracle.rf_exposure(seq, window_s=window_s, periodic=periodic)
    _assert_matches_oracle(ours, theirs)


def _random_pulse_train(rng: np.random.Generator) -> pp.Sequence:
    """A random train of 1 to 11 blocks on the synthetic system: about 70% of them a
    block or a sinc RF pulse, with a random flip angle and a random duration on the
    10 us raster, each followed by a random gap (`make_delay`), also on the 10 us
    raster."""
    seq = pp.Sequence(SYSTEM)
    for _ in range(rng.integers(1, 12)):
        if rng.random() < 0.7:
            dur = round(rng.uniform(0.1e-3, 2e-3) / 1e-5) * 1e-5
            if rng.random() < 0.5:
                rf = pp.make_block_pulse(
                    flip_angle=rng.uniform(0.1, 3), duration=dur, system=SYSTEM
                )
            else:
                rf = pp.make_sinc_pulse(flip_angle=rng.uniform(0.1, 3), duration=dur, system=SYSTEM)
            seq.add_block(rf)
        seq.add_block(pp.make_delay(round(rng.uniform(1e-4, 20e-3) / 1e-5) * 1e-5))
    return seq


@pytest.mark.parametrize("seed", range(200))
def test_matches_oracle_on_random_pulse_trains(seed):
    """200 seeded random pulse trains (`_random_pulse_train`), each with several random
    window lengths (well under the sequence, about half of it, well over it, and the
    default 10 s), for both `periodic` values: `rf_exposure` matches the oracle within
    the tolerance above."""
    rng = np.random.default_rng(seed)
    seq = _random_pulse_train(rng)
    duration = sum(seq.block_durations.values())
    windows = (
        duration * rng.uniform(0.001, 0.3),
        duration * 0.5,
        duration * rng.uniform(1.5, 3.0),
        10.0,
    )
    for window_s in windows:
        for periodic in (True, False):
            ours = rf_exposure.rf_exposure(
                seq, GAMMA_1H, periodic=periodic, b1rms_window_s=window_s
            )
            theirs = oracle.rf_exposure(seq, window_s=window_s, periodic=periodic)
            _assert_matches_oracle(ours, theirs)


def test_tie_at_window_end_matches_oracle_exactly():
    """Equal pulses at a regular spacing, with a window length that is a whole number of
    that spacing (1), put the window end exactly on the next pulse's first sample: a tie
    between "in the window" and "not in the window". The module docstring says the
    highest-window search uses the same float sample times and the same float
    comparisons as a search over every sample, so this tie must exclude the next pulse
    the same way in both implementations, and each window can then hold only one pulse.

    The first pulse has a larger flip angle than the rest (which are equal to each
    other), so it alone has the highest one-pulse energy and the search picks it as the
    peak window without a further tie among equal candidates. Its own window energy is
    then an isolated sum, from the same per-sample energies in the same order, in both
    implementations (the oracle's cumulative sum over every sample starts at this first
    pulse, and the new code's `energy_before` for its own first pulse is exactly 0): the
    window value must equal the oracle's exactly, not just within the tolerance above."""
    gap = 2e-3
    peak_rf = pp.make_block_pulse(
        flip_angle=math.pi, duration=1e-3, delay=SYSTEM.rf_dead_time, system=SYSTEM
    )
    rest_rf = pp.make_block_pulse(
        flip_angle=math.pi / 4, duration=1e-3, delay=SYSTEM.rf_dead_time, system=SYSTEM
    )
    seq = pp.Sequence(SYSTEM)
    seq.add_block(peak_rf)
    seq.add_block(pp.make_delay(gap))
    for _ in range(4):
        seq.add_block(rest_rf)
        seq.add_block(pp.make_delay(gap))

    durations = list(seq.block_durations.values())
    spacing = durations[0] + durations[1]  # one pulse block, then one delay block
    window_s = spacing  # a whole number (1) of the spacing

    for periodic in (True, False):
        ours = rf_exposure.rf_exposure(seq, GAMMA_1H, periodic=periodic, b1rms_window_s=window_s)
        theirs = oracle.rf_exposure(seq, window_s=window_s, periodic=periodic)
        assert ours.b1rms_window_used_s == theirs.window_used_s
        assert ours.b1rms_window_ut == theirs.b1rms_window_ut


def _small_random_pulse_train(rng: np.random.Generator) -> pp.Sequence:
    """Like `_random_pulse_train`, but 1 to 4 blocks and shorter pulses, small enough
    for a brute-force search over every sample."""
    seq = pp.Sequence(SYSTEM)
    for _ in range(rng.integers(1, 5)):
        if rng.random() < 0.8:
            dur = round(rng.uniform(0.1e-3, 0.5e-3) / 1e-5) * 1e-5
            if rng.random() < 0.5:
                rf = pp.make_block_pulse(
                    flip_angle=rng.uniform(0.1, 3), duration=dur, system=SYSTEM
                )
            else:
                rf = pp.make_sinc_pulse(flip_angle=rng.uniform(0.1, 3), duration=dur, system=SYSTEM)
            seq.add_block(rf)
        seq.add_block(pp.make_delay(round(rng.uniform(1e-4, 5e-3) / 1e-5) * 1e-5))
    return seq


def _brute_force_max_energy(search: rf_exposure._Search, length: float) -> float:
    """The highest-window energy for `length`, from every candidate start `s` that a
    search over every sample of `search` would try (every sample of the first copy),
    against every sample of `search` (both copies, when periodic) — independent of
    `_Search.max_energy`'s candidate-only search, built only from `_Search._time`, the
    per-event cumulative energies, and `np.searchsorted`."""
    times_parts, energy_parts = [], []
    for p in range(search.event.size):
        n = int(search.n[p])
        if n == 0:
            continue
        i = np.arange(n)
        times_parts.append(search._time(np.full(n, p), i))
        at = int(search.at[p])
        energy_parts.append(search.train.cum[at + i + 1] - search.train.cum[at + i])
    if not times_parts:
        return 0.0
    times = np.concatenate(times_parts)
    energy = np.concatenate(energy_parts)
    order = np.argsort(times, kind="stable")
    times = times[order]
    cumulative = np.concatenate([[0.0], np.cumsum(energy[order])])

    best = 0.0
    for p in range(search.m):
        n = int(search.n[p])
        if n == 0:
            continue
        i = np.arange(n)
        starts = search._time(np.full(n, p), i)
        lo = np.searchsorted(times, starts, side="left")
        hi = np.searchsorted(times, starts + length, side="left")
        best = max(best, float(np.max(cumulative[hi] - cumulative[lo])))
    return best


@pytest.mark.parametrize("seed", range(30))
def test_search_candidates_match_brute_force_over_every_sample(seed):
    """`_Search(train, period).max_energy(length)`, which tries only the candidate
    starts of section 4.5 item 4 of the plan, equals `_brute_force_max_energy`, a search
    over every sample start written independently in this test (all sample times from
    `_Search._time`, all window ends, `np.searchsorted`), on small random pulse trains,
    for both a wrapping (`period=duration`) and a non-wrapping (`period=None`) search
    and for several window lengths."""
    rng = np.random.default_rng(1_000_000 + seed)
    seq = _small_random_pulse_train(rng)
    train, duration = rf_exposure._pulse_train(seq, GAMMA_1H)
    if train.num_pulses == 0:
        pytest.skip("no RF pulses in this seed's train")

    lengths = (
        duration * rng.uniform(0.01, 0.3),
        duration * 0.5,
        duration * rng.uniform(1.5, 3.0),
    )
    for period in (duration, None):
        search = rf_exposure._Search(train, period)
        for length in lengths:
            fast = search.max_energy(length)
            brute = _brute_force_max_energy(search, length)
            bound = max(abs(fast), abs(brute)) * 1e-12
            assert abs(fast - brute) <= bound, (seed, period, length, fast, brute)
