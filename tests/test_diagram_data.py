"""Tests for `diagram_data.py` (task 1.3 of `docs/plans/diagram-event-table.md`).

`waveforms._events_in_range` is the reference for exact values (section 3.5 of the
plan): a later phase rebuilds these same numbers in JavaScript, and a golden test there
compares them with `==` and no tolerance, so a test here that lets a real regression
through by using a tolerance where the plan says exact would defeat that later check.
`_rebuild_lane_polylines` below rebuilds each lane's whole-file polyline from the
decoded tables with the time formulas of section 4.3, entirely independently of
`waveforms.py`, so the comparison is a real check of the tables' content, not a
tautology.
"""

import math

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

from pulseq_reports import diagram_data, waveforms
from pulseq_reports.diagram_data import CHECKPOINT_BLOCKS

LANE_IDS = ("rf_mag", "rf_phase", "gx", "gy", "gz", "adc")
_GRAD_AXES = ("gx", "gy", "gz")


def _block_starts(tables: dict[str, np.ndarray]) -> np.ndarray:
    """The start time (s) of every block, in play order, from the checkpoints and the
    durations (section 4.3): from the checkpoint at or before the block, add the
    durations of the blocks before it, one at a time."""
    duration_index = tables["duration_index"].astype(np.int64)
    durations = tables["durations"]
    checkpoints = tables["checkpoints"]
    n = duration_index.size
    starts = np.empty(n, dtype=np.float64)
    for c in range(checkpoints.size):
        i0 = c * CHECKPOINT_BLOCKS
        i1 = min(i0 + CHECKPOINT_BLOCKS, n)
        t = checkpoints[c]
        for j in range(i0, i1):
            starts[j] = t
            t += durations[duration_index[j]]
    return starts


def _rebuild_lane_polylines(
    tables: dict[str, np.ndarray],
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Each lane's whole-file polyline (times (s), values), rebuilt from the decoded
    `tables` with the section 4.3 formulas: point time = (block start + event delay) +
    the event's own offset. The ADC lane's "values" are dummy zeros; only its times (the
    window starts and ends) mean anything.

    Independent of `waveforms.py`, so comparing this against `_events_in_range` is a
    real check of the tables, not a tautology.
    """
    starts = _block_starts(tables)
    n = starts.size
    parts: dict[str, tuple[list[np.ndarray], list[np.ndarray]]] = {
        lane_id: ([], []) for lane_id in LANE_IDS
    }

    rf_index = tables["rf"]
    for i in range(n):
        k = int(rf_index[i])
        if not k:
            continue
        k -= 1
        t0 = starts[i] + tables["rf_delay"][k]
        for kind in ("mag", "phase"):
            length = int(tables[f"rf_{kind}_n"][k])
            offset_at = int(tables[f"rf_{kind}_offset_at"][k])
            value_at = int(tables[f"rf_{kind}_at"][k])
            offsets = tables[f"rf_{kind}_offset"][offset_at : offset_at + length]
            values = tables[f"rf_{kind}"][value_at : value_at + length]
            lane_id = "rf_mag" if kind == "mag" else "rf_phase"
            parts[lane_id][0].append(t0 + offsets)
            parts[lane_id][1].append(values)

    for axis in _GRAD_AXES:
        axis_index = tables[axis]
        for i in range(n):
            k = int(axis_index[i])
            if not k:
                continue
            k -= 1
            t0 = starts[i] + tables["grad_delay"][k]
            length = int(tables["grad_n"][k])
            offset_at = int(tables["grad_offset_at"][k])
            value_at = int(tables["grad_at"][k])
            offsets = tables["grad_offset"][offset_at : offset_at + length]
            values = tables["grad_value"][value_at : value_at + length]
            parts[axis][0].append(t0 + offsets)
            parts[axis][1].append(values)

    adc_index = tables["adc"]
    for i in range(n):
        k = int(adc_index[i])
        if not k:
            continue
        k -= 1
        a0 = starts[i] + tables["adc_delay"][k]
        a1 = a0 + tables["adc_length"][k]
        parts["adc"][0].append(np.array([a0, a1]))
        parts["adc"][1].append(np.array([0.0, 0.0]))

    polylines: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for lane_id, (ts, vs) in parts.items():
        t = np.concatenate(ts) if ts else np.empty(0, dtype=np.float64)
        v = np.concatenate(vs) if vs else np.empty(0, dtype=np.float64)
        polylines[lane_id] = (t, v)
    return polylines


def _reference_lane_polylines(seq: pp.Sequence) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Each lane's whole-file polyline (times (s), values), built directly from
    `waveforms._events_in_range(seq, None, None)`'s unrounded per-block arrays, in the
    same play order as `_rebuild_lane_polylines`. This is the reference of section 3.5."""
    parts: dict[str, tuple[list[np.ndarray], list[np.ndarray]]] = {
        lane_id: ([], []) for lane_id in LANE_IDS
    }
    for e in waveforms._events_in_range(seq, None, None):
        if e.rf_mag is not None:
            parts["rf_mag"][0].append(e.rf_mag[0])
            parts["rf_mag"][1].append(e.rf_mag[1])
            parts["rf_phase"][0].append(e.rf_phase[0])
            parts["rf_phase"][1].append(e.rf_phase[1])
        for axis, (t, v) in e.grads.items():
            parts[axis][0].append(t)
            parts[axis][1].append(v)
        if e.adc is not None:
            parts["adc"][0].append(np.array([e.adc[0], e.adc[1]]))
            parts["adc"][1].append(np.array([0.0, 0.0]))

    polylines: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for lane_id, (ts, vs) in parts.items():
        t = np.concatenate(ts) if ts else np.empty(0, dtype=np.float64)
        v = np.concatenate(vs) if vs else np.empty(0, dtype=np.float64)
        polylines[lane_id] = (t, v)
    return polylines


@pytest.mark.parametrize(
    "builder",
    [spin_echo_sequence, gre_sequence, arbitrary_gradient_sequence, empty_sequence],
    ids=["spin_echo", "gre", "arbitrary_gradient", "empty"],
)
def test_rebuilt_polylines_exactly_match_events_in_range(builder):
    """The section 4.3 formulas, applied to the decoded tables, give exactly (bit for
    bit) the same per-lane points as `waveforms._events_in_range`'s unrounded output, for
    every kind of synthetic sequence, including one with no RF, gradient or ADC event."""
    seq = builder()
    tables = diagram_data.decode_tables(
        diagram_data.encode_tables(diagram_data.diagram_tables(seq))
    )
    rebuilt = _rebuild_lane_polylines(tables)
    reference = _reference_lane_polylines(seq)
    for lane_id in LANE_IDS:
        got_t, got_v = rebuilt[lane_id]
        want_t, want_v = reference[lane_id]
        assert np.array_equal(got_t, want_t), lane_id
        assert np.array_equal(got_v, want_v), lane_id


def test_encode_then_decode_gives_the_same_arrays_and_dtypes():
    seq = gre_sequence(num_trs=5)
    tables = diagram_data.diagram_tables(seq)
    decoded = diagram_data.decode_tables(diagram_data.encode_tables(tables))
    assert decoded.keys() == tables.keys()
    for name, arr in tables.items():
        assert decoded[name].dtype == arr.dtype, name
        assert np.array_equal(decoded[name], arr), name


@pytest.mark.parametrize(
    "max_value, expected_dtype",
    [(0, np.uint8), (255, np.uint8), (256, np.uint16), (65535, np.uint16), (65536, np.uint32)],
    ids=["zero", "uint8_max", "uint8_overflow", "uint16_max", "uint16_overflow"],
)
def test_index_dtype_widths(max_value, expected_dtype):
    # A small made-up array whose maximum is the boundary value, as `diagram_tables`
    # builds one of its index columns from a maximum library id count.
    arr = np.array([0, 1, max_value], dtype=np.uint32)
    dtype = diagram_data._index_dtype(int(arr.max()))
    assert dtype is expected_dtype
    assert arr.astype(dtype).dtype == np.dtype(expected_dtype)


def test_checkpoints_match_the_sequential_sum_at_blocks_0_1024_2048():
    """`gre_sequence(num_trs=600)` (3000 blocks) is large enough to have all three
    checkpoints this plan lists (blocks 0, 1024 and 2048), and building its tables is
    fast: well under a second in a `uv run pytest` run, so it belongs in the suite."""
    seq = gre_sequence(num_trs=600)
    assert len(seq.block_events) > 2 * CHECKPOINT_BLOCKS
    tables = diagram_data.diagram_tables(seq)
    assert tables["checkpoints"].size == 3

    timed_blocks = list(waveforms._timed_blocks(seq))
    for c, block_index in enumerate((0, CHECKPOINT_BLOCKS, 2 * CHECKPOINT_BLOCKS)):
        expected_start = timed_blocks[block_index][1]
        assert tables["checkpoints"][c] == expected_start


def test_lane_meta_matches_file_lanes_without_segments_and_windows():
    seq = spin_echo_sequence()
    expected = [
        {k: v for k, v in lane.items() if k not in ("segments", "windows")}
        for lane in waveforms.file_lanes(seq)
    ]
    assert diagram_data.lane_meta(seq) == expected

    # Passing prebuilt tables gives the same result, without rebuilding them.
    tables = diagram_data.diagram_tables(seq)
    assert diagram_data.lane_meta(seq, tables=tables) == expected


def test_read_back_sequence_rebuilds_exactly_and_matches_the_original_within_tolerance(tmp_path):
    """A sequence written with `seq.write` and read back with `pp.Sequence.read`: the
    read sequence's own tables still rebuild its own `_events_in_range` polylines
    exactly, because the section 4.3 formulas do not depend on where the numbers came
    from. The read sequence's polylines are also close to the original's, but not
    bit-for-bit equal: pypulseq's own `.seq` writer (`Sequence/write_seq.py`) formats
    block durations as raster sample counts (exact) but RF and gradient event values,
    including a `[TRAP]` gradient's amplitude, as decimal text with Python's default
    `%g` precision (6 significant digits: `'{:12g}'` for `[TRAP]`). That is a much
    coarser round trip than "differ in the last few bits": measured on these synthetic
    sequences, times agree to within double-precision rounding (0 to a few ULP, far
    inside 1e-9 s), but values can differ by up to about 1e-6 relative (for example
    about 3.6e-6 for a Gx trapezoid amplitude here). The plan's stated tolerance for
    this test (1e-9 s absolute, 1e-9 relative on values) holds for times but not for
    values; this test uses 1e-9 for times and a wider, measured tolerance for values
    (1e-6 absolute, 1e-5 relative) instead. This is the one test in this file, and the
    only one the plan allows, that compares with a tolerance rather than exactly."""
    seq = spin_echo_sequence()
    path = tmp_path / "roundtrip.seq"
    seq.write(str(path))
    read_seq = pp.Sequence(SYSTEM)
    read_seq.read(str(path))

    read_tables = diagram_data.diagram_tables(read_seq)
    rebuilt = _rebuild_lane_polylines(read_tables)
    read_reference = _reference_lane_polylines(read_seq)
    for lane_id in LANE_IDS:
        got_t, got_v = rebuilt[lane_id]
        want_t, want_v = read_reference[lane_id]
        assert np.array_equal(got_t, want_t), lane_id
        assert np.array_equal(got_v, want_v), lane_id

    original_reference = _reference_lane_polylines(seq)
    for lane_id in LANE_IDS:
        orig_t, orig_v = original_reference[lane_id]
        read_t, read_v = read_reference[lane_id]
        assert orig_t == pytest.approx(read_t, abs=1e-9, rel=1e-9), lane_id
        assert orig_v == pytest.approx(read_v, abs=1e-6, rel=1e-5), lane_id


def test_two_rf_events_that_differ_only_in_phase_offset_share_their_offset_pools():
    """Two RF events built from the same flip angle, duration and delay, differing only
    in `phase_offset`, have identical magnitude points (`|signal|` does not depend on
    `phase_offset`) and identical kept-phase-point offsets (the 1%-of-peak threshold is a
    function of the magnitude only), so the pool must store each offset array one time
    and point both events at the same position. Their phase values differ, so the phase
    value pool must not merge them."""
    seq = pp.Sequence(SYSTEM)
    rf1 = pp.make_block_pulse(
        flip_angle=math.pi / 2,
        duration=1e-3,
        delay=SYSTEM.rf_dead_time,
        phase_offset=0.0,
        system=SYSTEM,
    )
    rf2 = pp.make_block_pulse(
        flip_angle=math.pi / 2,
        duration=1e-3,
        delay=SYSTEM.rf_dead_time,
        phase_offset=math.pi / 3,
        system=SYSTEM,
    )
    seq.add_block(rf1)
    seq.add_block(rf2)

    tables = diagram_data.diagram_tables(seq)
    assert tables["rf"].tolist() == [1, 2]  # two distinct dense RF events
    assert tables["rf_mag_offset_at"][0] == tables["rf_mag_offset_at"][1]
    assert tables["rf_mag_at"][0] == tables["rf_mag_at"][1]
    assert tables["rf_phase_offset_at"][0] == tables["rf_phase_offset_at"][1]
    # Sanity: the phase offset actually changes the phase values, so this is a real
    # positive-and-negative check, not one where every pool happens to collapse.
    assert tables["rf_phase_at"][0] != tables["rf_phase_at"][1]
