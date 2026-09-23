import math

import pypulseq as pp
import pytest
from synthetic import DWELL, NUM_SAMPLES, SYSTEM, gre_sequence, spin_echo_sequence

from pulseq_reports import waveforms
from pulseq_reports.seq_utils import GAMMA, NamedSequence, iter_blocks


@pytest.fixture(scope="module")
def spin_echo():
    """A synthetic spin echo sequence and its exact lanes by id (vb-pulseq
    `test_spin_echo_lanes`'s `lanes` fixture, adapted to `tests/synthetic.py`)."""
    seq = spin_echo_sequence()
    return seq, {lane["id"]: lane for lane in waveforms.file_lanes(seq)}


def test_spin_echo_lanes(spin_echo):
    seq, by_id = spin_echo
    max_grad_mt = SYSTEM.max_grad / GAMMA * 1e3
    # Block pulses have no slice-select gradient, so only Gx (prephaser, readout) and
    # Gy (the two crushers) carry events; Gz stays empty.
    for axis in ("gx", "gy"):
        assert not by_id[axis]["empty"]
        assert max(abs(v) for _, v in by_id[axis]["segments"][0]) <= max_grad_mt + 1e-3
    assert by_id["gz"]["empty"]
    (window,) = by_id["adc"]["windows"]
    assert window[1] - window[0] == pytest.approx(NUM_SAMPLES * DWELL * 1e3, abs=0.01)
    assert len(by_id["rf_phase"]["segments"]) == 2  # excitation and refocusing
    first_adc = waveforms.first_adc_window([NamedSequence("se", seq)])
    assert first_adc.end_s * 1e3 > window[1]


def test_block_table(spin_echo):
    seq, _ = spin_echo
    rows, total = waveforms.block_rows(seq)
    events = [r["events"] for r in rows]
    assert total == len(rows) == 6
    assert events[0] == "RF (excitation)"
    assert any(e == "RF (refocusing)" for e in events)
    assert events.count("Gy trap") == 2  # the two crushers
    assert any("Gx trap" in e and f"ADC {NUM_SAMPLES} × " in e for e in events)


def test_zero_phase_rf_and_zero_gradient_are_events():
    seq = pp.Sequence(SYSTEM)
    rf = pp.make_block_pulse(flip_angle=math.pi / 2, duration=1e-3, system=SYSTEM)
    seq.add_block(rf, pp.make_trapezoid("x", amplitude=0, duration=1e-3, system=SYSTEM))
    by_id = {lane["id"]: lane for lane in waveforms.file_lanes(seq)}
    assert not by_id["rf_phase"]["empty"]
    assert not by_id["gx"]["empty"]
    assert by_id["gy"]["empty"]


def test_multi_tr_lanes_span_the_whole_sequence():
    """Adapted from vb-pulseq's `report_at_tr` tests (the lane and duration parts of
    `test_report_at_tr_plots_the_whole_sequence`), with a synthetic multi-TR gradient
    echo sequence instead of vb's spin echo. The PNS, page and timing-check parts of
    that vb test belong to other cards and are dropped here."""
    num_trs = 10
    seq = gre_sequence(num_trs=num_trs, tr=20e-3)
    duration_ms = waveforms.duration_s(seq) * 1e3
    by_id = {lane["id"]: lane for lane in waveforms.file_lanes(seq)}
    for lane_id in ("rf_mag", "gx", "gy", "gz"):
        (segment,) = by_id[lane_id]["segments"]
        assert segment[0][0] == 0
        assert segment[-1][0] == pytest.approx(duration_ms, abs=1e-3)
    windows = by_id["adc"]["windows"]
    assert len(windows) == num_trs
    tr_ms = duration_ms / num_trs  # each TR has the same duration by construction
    for k, (start, end) in enumerate(windows):
        assert k * tr_ms < start < end < (k + 1) * tr_ms


def test_multi_tr_excitations_start_every_tr():
    """Adapted from vb-pulseq's `test_report_at_tr_excitations_start_every_tr`, with a
    synthetic gradient echo sequence: each TR's excitation RF starts at exactly the
    real TR period, counted from the block timing, not from the nominal parameter."""
    num_trs = 10
    seq = gre_sequence(num_trs=num_trs, tr=20e-3)
    duration_ms = waveforms.duration_s(seq) * 1e3
    tr_ms = duration_ms / num_trs
    rows, _ = waveforms.block_rows(seq)
    starts = [r["start_ms"] for r in rows if r["events"].startswith("RF (excitation)")]
    expected = [k * tr_ms for k in range(num_trs)]
    assert starts == pytest.approx(expected, rel=0, abs=1e-3)


def test_range_that_cuts_a_block_includes_it_whole_and_pads_at_its_own_edges():
    """A range whose edges fall inside blocks still includes each such block whole, and
    the zero pad points are at the included block's own start and end, not at the
    range's requested edges (`waveforms.file_lanes` docstring)."""
    seq = spin_echo_sequence()
    blocks = list(iter_blocks(seq))
    refocus = blocks[3]  # the RF refocusing block
    crusher2 = blocks[4]  # the gy crusher block right after it
    assert refocus.block.rf is not None
    assert crusher2.block.gy is not None

    start_s = refocus.start_s + refocus.duration_s / 2  # inside the RF block
    end_s = crusher2.start_s + crusher2.duration_s / 2  # inside the crusher block
    by_id = {lane["id"]: lane for lane in waveforms.file_lanes(seq, start_s, end_s)}

    (rf_segment,) = by_id["rf_mag"]["segments"]
    assert rf_segment[0][0] == pytest.approx(refocus.start_s * 1e3, abs=1e-4)
    assert rf_segment[0][0] < start_s * 1e3
    assert rf_segment[0][1] == 0.0

    (gy_segment,) = by_id["gy"]["segments"]
    crusher_end_ms = (crusher2.start_s + crusher2.duration_s) * 1e3
    assert gy_segment[-1][0] == pytest.approx(crusher_end_ms, abs=1e-4)
    assert gy_segment[-1][0] > end_s * 1e3
    assert gy_segment[-1][1] == 0.0


def test_first_adc_window_label_and_times():
    seq = gre_sequence(num_trs=3, tr=8e-3)
    exact_windows = [
        w for lane in waveforms.file_lanes(seq) if lane["id"] == "adc" for w in lane["windows"]
    ]
    duration_ms = round(waveforms.duration_s(seq) * 1e3, 4)
    expected_end_ms = round(min(duration_ms, 1.1 * exact_windows[0][1]), 4)

    w = waveforms.first_adc_window([NamedSequence("g", seq)])
    assert w.file_index == 0
    assert w.start_s == 0.0
    assert w.end_s * 1e3 == pytest.approx(expected_end_ms, abs=1e-4)
    assert w.label == f"First ADC (0–{expected_end_ms:.3g} ms)"


def test_first_adc_window_with_no_adc_is_the_whole_file():
    seq_no_adc = pp.Sequence(SYSTEM)
    seq_no_adc.add_block(pp.make_delay(2e-3))
    duration_ms = round(waveforms.duration_s(seq_no_adc) * 1e3, 4)
    w = waveforms.first_adc_window([NamedSequence("g", seq_no_adc)])
    assert w.end_s * 1e3 == pytest.approx(duration_ms, abs=1e-4)
    assert w.label == f"First ADC (0–{duration_ms:.3g} ms)"


def test_full_window_label_and_times():
    seq = gre_sequence(num_trs=2, tr=20e-3)
    duration_ms = round(waveforms.duration_s(seq) * 1e3, 4)
    w = waveforms.full_window([NamedSequence("g", seq)], file_index=0)
    assert w.file_index == 0
    assert w.start_s == 0.0
    assert w.end_s * 1e3 == pytest.approx(duration_ms, abs=1e-4)
    assert w.label == f"Full sequence (0–{duration_ms:g} ms)"


def test_block_rows_with_max_rows_and_range():
    num_trs = 5
    seq = gre_sequence(num_trs=num_trs, tr=20e-3)
    all_rows, total = waveforms.block_rows(seq)
    assert total == len(all_rows)

    limited_rows, limited_total = waveforms.block_rows(seq, max_rows=3)
    assert limited_total == total
    assert len(limited_rows) == 3
    assert limited_rows == all_rows[:3]

    # A range keeps only the blocks that overlap it: one whole TR out of five.
    period = waveforms.duration_s(seq) / num_trs
    start_s, end_s = 2 * period, 3 * period
    ranged_rows, ranged_total = waveforms.block_rows(seq, start_s, end_s)
    assert 0 < ranged_total < total
    ranged_limited_rows, ranged_limited_total = waveforms.block_rows(
        seq, start_s, end_s, max_rows=2
    )
    assert ranged_limited_total == ranged_total
    assert len(ranged_limited_rows) == 2
    assert ranged_limited_rows == ranged_rows[:2]
