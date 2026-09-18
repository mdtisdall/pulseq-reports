import math

import pypulseq as pp
import pytest
from synthetic import SYSTEM, empty_sequence

from pulseq_reports import rf_exposure, seq_utils


def _b1_ut(flip_rad: float, duration_s: float) -> float:
    """The constant B1 (µT) of a block pulse with this flip angle and duration."""
    return (flip_rad / (2 * math.pi)) / duration_s / seq_utils.GAMMA * 1e6


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
    e = rf_exposure.rf_exposure(_pulse_train([3.0, 17.0]))
    assert e.num_pulses == 2
    assert e.duration_s == pytest.approx(20, abs=0.01)
    assert e.peak_b1_ut == pytest.approx(B1_UT, rel=1e-6)
    assert e.peak_block == 1
    assert e.energy_ut2_s == pytest.approx(2 * PULSE_ENERGY, rel=1e-6)
    assert e.b1rms_ut == pytest.approx(math.sqrt(2 * PULSE_ENERGY / e.duration_s), rel=1e-6)
    assert e.window_used_s == e.window_s


@pytest.mark.parametrize(
    ("gaps_s", "pulses_in_window"),
    [
        ([3.0, 17.0], 2),  # both pulses are in one 10 s window
        ([15.0, 5.0], 2),  # the window goes into the next repetition
        ([11.0, 11.0], 1),  # the pulses are more than 10 s apart in both directions
    ],
)
def test_highest_window(gaps_s, pulses_in_window):
    e = rf_exposure.rf_exposure(_pulse_train(gaps_s))
    assert e.window_s == 10
    assert e.window_used_s == 10
    assert e.b1rms_window_ut == pytest.approx(
        math.sqrt(pulses_in_window * PULSE_ENERGY / 10), rel=1e-6
    )


def test_short_sequence_window():
    # A 10 s window holds 33 repetitions of the 0.3 s sequence, and a part of about 60 ms
    # that can hold one more pulse.
    e = rf_exposure.rf_exposure(_pulse_train([0.3]))
    repeats = math.floor(10 / e.duration_s)
    assert repeats == 33
    assert e.b1rms_window_ut == pytest.approx(
        math.sqrt((repeats + 1) * PULSE_ENERGY / 10), rel=1e-6
    )
    assert e.b1rms_window_ut > e.b1rms_ut


def test_no_rf():
    e = rf_exposure.rf_exposure(empty_sequence())
    assert e.num_pulses == 0
    assert e.peak_block is None
    assert e.energy_ut2_s == 0
    assert e.b1rms_ut == 0
    assert e.b1rms_window_ut == 0
    assert e.window_used_s == e.window_s


def test_periodic_false_does_not_wrap():
    # With the window (15 s, 5 s) gap pattern, a periodic search finds a 10 s window that
    # wraps past the end of one repetition into the start of the next, catching 2 pulses
    # (see test_highest_window). A one-time play has no next repetition to wrap into, so
    # the highest 10 s window can catch only 1 pulse: the two pulses are 15 s apart, more
    # than the 10 s window, in both directions within the single play.
    seq = _pulse_train([15.0, 5.0])
    e_periodic = rf_exposure.rf_exposure(seq, periodic=True)
    assert e_periodic.b1rms_window_ut == pytest.approx(math.sqrt(2 * PULSE_ENERGY / 10), rel=1e-6)

    e = rf_exposure.rf_exposure(seq, periodic=False)
    assert e.duration_s > e.window_s
    assert e.window_used_s == e.window_s
    assert e.b1rms_window_ut == pytest.approx(math.sqrt(1 * PULSE_ENERGY / 10), rel=1e-6)


def test_periodic_false_window_is_whole_sequence_when_shorter_than_window():
    # The 0.3 s pulse train is much shorter than the 10 s window, so with periodic=False the
    # highest window is the whole sequence: its real length is the sequence duration, and its
    # B1+rms equals the plain (non-windowed) B1+rms, both from the sequence's one pulse.
    seq = _pulse_train([0.3])
    e = rf_exposure.rf_exposure(seq, periodic=False)
    assert e.duration_s < e.window_s
    assert e.window_used_s == pytest.approx(e.duration_s)
    assert e.b1rms_ut == pytest.approx(math.sqrt(PULSE_ENERGY / e.duration_s), rel=1e-6)
    assert e.b1rms_window_ut == pytest.approx(e.b1rms_ut, rel=1e-9)


def test_periodic_false_no_rf():
    e = rf_exposure.rf_exposure(empty_sequence(), periodic=False)
    assert e.num_pulses == 0
    assert e.b1rms_window_ut == 0
    assert e.window_used_s == e.duration_s
