"""The golden test of task 4.4 of `docs/plans/diagram-event-table.md`: the browser
module `SeqLanes` (`src/pulseq_reports/assets/seq_lanes.js`) must give exactly the same
lanes as the Python reference, for the exact view (bit for bit) and for the min/max
view (exact for a value that comes from a raw point, a tight tolerance for a value that
comes from linear interpolation at a bin edge).

`_run_golden` writes one file's encoded tables and lane metadata, plus a list of
queries, to a JSON file; runs `tests/js/golden_seq_lanes.js` with Node on it; and reads
back the JSON result. `tests/js/golden_seq_lanes.js` decodes the tables, calls
`SeqLanes.decode` once, and answers each query with `SeqLanes.exactLanes` or
`SeqLanes.minMaxLanes`.

The reference for both views is built independently of `diagram_data.py` and
`seq_lanes.js`, straight from `waveforms._events_in_range`'s unrounded per-block
arrays (section 3.5 of the plan: `waveforms.file_lanes` is the reference the browser
must match), so a bug shared between the tables and the JavaScript would not pass this
test by accident.

This file does not soften a real mismatch: no tolerance beyond what the plan states
(1e-12 relative, only for an interpolated edge value), no `xfail`, no `skip`. If
`SeqLanes` and the reference disagree, this file is expected to fail and to say, in the
assertion message, which sequence, query, lane and bin (or point) disagreed and with
what values.
"""

import itertools
import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from synthetic import (
    arbitrary_gradient_sequence,
    empty_sequence,
    gre_sequence,
    spin_echo_sequence,
)

from pulseq_reports import diagram_data, waveforms

_GOLDEN_SCRIPT = Path(__file__).parent / "js" / "golden_seq_lanes.js"

_LINE_LANE_IDS = ("rf_mag", "gx", "gy", "gz")


# ---- Running the Node half ------------------------------------------------------


def _run_golden(seq, queries: list[dict], tmp_path: Path) -> tuple[dict, dict]:
    """Writes `seq`'s tables and lane metadata plus `queries` to a JSON file in
    `tmp_path`, runs `golden_seq_lanes.js` on it with Node, and returns
    `(json.loads(OUT.json), diagram_tables(seq))`.

    Fails the test, with a clear message, when `node` is not on `PATH`: the plan
    requires this (both devShells have Node), not a silent skip.
    """
    if shutil.which("node") is None:
        pytest.fail(
            "node is required to run tests/js/golden_seq_lanes.js (the golden test of "
            "SeqLanes against the Python reference), but it was not found on PATH"
        )
    tables = diagram_data.diagram_tables(seq)
    payload = {
        "format": 1,
        "tables": diagram_data.encode_tables(tables),
        "lanes": diagram_data.lane_meta(seq, tables=tables),
        "queries": queries,
    }
    in_path = tmp_path / "in.json"
    out_path = tmp_path / "out.json"
    in_path.write_text(json.dumps(payload))
    subprocess.run(["node", str(_GOLDEN_SCRIPT), str(in_path), str(out_path)], check=True)
    return json.loads(out_path.read_text()), tables


# ---- The Python reference (independent of diagram_data.py and seq_lanes.js) -----


def _reference_data(seq, duration: float):
    """`(line_pts, phase_pulses, adc_windows)`, built directly from
    `waveforms._events_in_range(seq, None, None)`'s unrounded per-block arrays, in play
    order:

    - `line_pts[lane_id]`: the whole-file polyline P_L of one line lane (`rf_mag`,
      `gx`, `gy`, `gz`), as `[(0.0, 0.0), *event points, (duration, 0.0)]` (section 2.7
      item 6 and section 4.4 item 1 of the plan).
    - `phase_pulses`: one list of `(t, v)` points for each block whose RF event has at
      least one kept phase point (section 4.4 item 1: a pulse with none gives no
      segment).
    - `adc_windows`: `(a0, a1)` for each block with an ADC.
    """
    line_pts = {lane_id: [(0.0, 0.0)] for lane_id in _LINE_LANE_IDS}
    phase_pulses: list[list[tuple[float, float]]] = []
    adc_windows: list[tuple[float, float]] = []
    for e in waveforms._events_in_range(seq, None, None):
        if e.rf_mag is not None:
            ts, vs = e.rf_mag
            line_pts["rf_mag"].extend((float(t), float(v)) for t, v in zip(ts, vs))
        for axis, (ts, vs) in e.grads.items():
            line_pts[axis].extend((float(t), float(v)) for t, v in zip(ts, vs))
        if e.rf_phase is not None:
            ts, vs = e.rf_phase
            if len(ts):
                phase_pulses.append([(float(t), float(v)) for t, v in zip(ts, vs)])
        if e.adc is not None:
            adc_windows.append((float(e.adc[0]), float(e.adc[1])))
    for lane_id in _LINE_LANE_IDS:
        line_pts[lane_id].append((duration, 0.0))
    return line_pts, phase_pulses, adc_windows


# ---- Building the queries for one sequence ---------------------------------------
#
# `waveforms._timed_blocks(seq)` is the same sequential sum, in play order, that the
# plan requires for a block's start time (section 2.7 item 3), so it is used directly
# here, the same way `tests/test_diagram_data.py` uses it as a reference.


def _event_block_indices(seq, timed: list[tuple[int, float, float]]) -> list[int]:
    """The indexes (into `timed`) of every block that has an RF, gradient or ADC
    event (`seq.block_events` columns 1 to 5; section 2.4 of the plan)."""
    idx = []
    for i, (block_id, _start, _duration) in enumerate(timed):
        ev = seq.block_events[block_id]
        if any(int(ev[c]) for c in (1, 2, 3, 4, 5)):
            idx.append(i)
    return idx


def _cuts_blocks_range(timed, event_idx: list[int]):
    """`(t0, t1)` that cuts from 0.3 of the way through the first event block into
    0.6 of the way through a later block (task 4.4: `[start_i + 0.3*dur_i, start_j +
    0.6*dur_j]` with `j > i`). Prefers a second event block for `j`; falls back to the
    very next block. `None` when the sequence has only one block."""
    i = event_idx[0]
    if len(event_idx) > 1:
        j = event_idx[1]
    elif i + 1 < len(timed):
        j = i + 1
    else:
        return None
    _, start_i, duration_i = timed[i]
    _, start_j, duration_j = timed[j]
    return start_i + 0.3 * duration_i, start_j + 0.6 * duration_j


def _no_event_range(seq, timed, line_pts):
    """A range inside a block with no RF, gradient or ADC event, when the sequence has
    one (a pure delay block); otherwise a range strictly between two consecutive
    points of some line lane's whole-file polyline (a "gap between events" on that
    lane: no lane has a point there, only interpolated values, task 4.4's fallback for
    a sequence with no pure delay block, for example `spin_echo_sequence`, whose six
    blocks all carry an event)."""
    for block_id, start, duration in timed:
        if duration <= 0:
            continue
        ev = seq.block_events[block_id]
        if not any(int(ev[c]) for c in (1, 2, 3, 4, 5)):
            return start + 0.2 * duration, start + 0.8 * duration
    best = None
    for pts in line_pts.values():
        times = sorted({t for t, _ in pts})
        for a, b in itertools.pairwise(times):
            gap = b - a
            if gap > 0 and (best is None or gap > best[0]):
                best = (gap, a, b)
    if best is None:
        return None
    _, a, b = best
    return a + 0.2 * (b - a), a + 0.8 * (b - a)


def _short_range(seq, timed):
    """One RF pulse's span (its block's `[start, start + duration]`), or, for a
    sequence with no RF (for example `arbitrary_gradient_sequence`), the first block
    with any event, or else the first block. Used for the fine-bin min/max query that
    is meant to leave many bins with no point (task 4.4, item 2)."""
    for block_id, start, duration in timed:
        if int(seq.block_events[block_id][1]):
            return start, start + duration
    event_idx = _event_block_indices(seq, timed)
    if event_idx:
        _, start, duration = timed[event_idx[0]]
        return start, start + duration
    _, start, duration = timed[0]
    return start, start + duration


# ---- Exact-view reference (task 4.4, item 1) --------------------------------------


def _exact_line_segment(P_L, t0: float, t1: float) -> list[list[float]]:
    """The one segment of a line lane's exact view: the points of `P_L` with
    `t0 <= t <= t1`, preceded by the last point (by index) with `t < t0` when one
    exists, and followed by the first point with `t > t1` when one exists, times in
    ms. `P_L`'s times are non-decreasing (play order), so one forward pass finds the
    last "before" point (each new match overwrites the last) and the first "after"
    point (the first match is kept) at once.
    """
    before = None
    in_range: list[tuple[float, float]] = []
    after = None
    for t, v in P_L:
        if t < t0:
            before = (t, v)
        elif t <= t1:
            in_range.append((t, v))
        elif after is None:
            after = (t, v)
    pts = (
        ([before] if before is not None else []) + in_range + ([after] if after is not None else [])
    )
    return [[t * 1000, v] for t, v in pts]


def _exact_phase_segments(phase_pulses, t0: float, t1: float) -> list[list[list[float]]]:
    """One segment per pulse that has a point in `[t0, t1]`, with all of that pulse's
    points, times in ms (task 4.4, item 1)."""
    return [
        [[t * 1000, v] for t, v in pulse]
        for pulse in phase_pulses
        if any(t0 <= t <= t1 for t, _ in pulse)
    ]


def _exact_adc_windows(adc_windows, t0: float, t1: float) -> list[list[float]]:
    """The ADC windows that overlap `[t0, t1]`, as `[a0 * 1000, a1 * 1000]`."""
    return [[a0 * 1000, a1 * 1000] for a0, a1 in adc_windows if a1 >= t0 and a0 <= t1]


def _assert_exact_lanes(js_lanes, meta_list, t0, t1, line_pts, phase_pulses, adc_windows, label):
    assert len(js_lanes) == len(meta_list), label
    for js_lane, meta in zip(js_lanes, meta_list):
        lane_id = meta["id"]
        for key, value in meta.items():
            assert js_lane[key] == value, f"{label}: {lane_id}.{key} does not match lane_meta"
        if lane_id == "adc":
            expected = _exact_adc_windows(adc_windows, t0, t1)
            assert js_lane["windows"] == expected, (
                f"{label}: adc windows: js={js_lane['windows']!r} ref={expected!r}"
            )
        elif lane_id == "rf_phase":
            expected = _exact_phase_segments(phase_pulses, t0, t1)
            assert js_lane["segments"] == expected, (
                f"{label}: rf_phase segments: js={js_lane['segments']!r} ref={expected!r}"
            )
        else:
            expected = [_exact_line_segment(line_pts[lane_id], t0, t1)]
            assert js_lane["segments"] == expected, (
                f"{label}: {lane_id} segments: js={js_lane['segments']!r} ref={expected!r}"
            )


# ---- Min/max-view reference (task 4.4, item 2) ------------------------------------
#
# For each bin, the reference minimum and maximum come from the points of the
# whole-file polyline (or, for the phase lane, the pulses' own points) that fall in
# the bin, and the linear interpolation (`numpy.interp`'s own formula, called
# directly, not reimplemented) at the bin's two edges. Section 4.4, item 2 of the plan
# says which comparison to use: a value that a raw point already reaches (it is
# <= every edge value, for the minimum; >= every edge value, for the maximum) must
# match exactly; a value that only an edge reaches gets `math.isclose` at 1e-12.


def _bin_edges(t0: float, t1: float, bins: int) -> list[float]:
    span = t1 - t0
    return [t0 + span * k / bins for k in range(bins + 1)]


def _reference_minmax_line(P_L, t0: float, t1: float, bins: int):
    """`[(time_ms, value, is_exact), ...]`, two entries per bin (the bin's minimum at
    its start edge, its maximum at its centre), for one line lane's whole-file
    polyline `P_L`."""
    xp = np.array([t for t, _ in P_L], dtype=np.float64)
    fp = np.array([v for _, v in P_L], dtype=np.float64)
    edges = np.array(_bin_edges(t0, t1, bins), dtype=np.float64)
    edge_values = np.interp(edges, xp, fp)
    out = []
    for k in range(bins):
        e0, e1 = edges[k], edges[k + 1]
        last = k == bins - 1
        lo = int(np.searchsorted(xp, e0, side="left"))
        hi = int(np.searchsorted(xp, e1, side="right" if last else "left"))
        pts_in_bin = fp[lo:hi]
        ev0, ev1 = float(edge_values[k]), float(edge_values[k + 1])
        edge_min, edge_max = (ev0, ev1) if ev0 <= ev1 else (ev1, ev0)
        point_min = float(pts_in_bin.min()) if pts_in_bin.size else math.inf
        point_max = float(pts_in_bin.max()) if pts_in_bin.size else -math.inf
        min_exact = point_min <= edge_min
        max_exact = point_max >= edge_max
        ref_min = point_min if min_exact else edge_min
        ref_max = point_max if max_exact else edge_max
        centre = e0 + (e1 - e0) / 2
        out.append((e0 * 1000, ref_min, min_exact))
        out.append((centre * 1000, ref_max, max_exact))
    return out


def _reference_minmax_phase(phase_pulses, t0: float, t1: float, bins: int):
    """The RF phase lane's min/max segments: like `_reference_minmax_line`, but the
    points of all pulses are pooled for "a point in the bin", an edge value exists
    only when the edge falls within one pulse's own span (`numpy.interp` over that
    pulse's points, not the whole file), and a bin with neither a point nor an edge
    value ends the current segment (task 4.4, item 2)."""
    pulse_arrays = [
        (
            np.asarray([t for t, _ in pulse], dtype=np.float64),
            np.asarray([v for _, v in pulse], dtype=np.float64),
        )
        for pulse in phase_pulses
    ]
    if pulse_arrays:
        all_t = np.concatenate([xp for xp, _ in pulse_arrays])
        all_v = np.concatenate([fp for _, fp in pulse_arrays])
        pulse_starts = np.array([xp[0] for xp, _ in pulse_arrays])
        pulse_ends = np.array([xp[-1] for xp, _ in pulse_arrays])
    else:
        all_t = all_v = pulse_starts = pulse_ends = np.empty(0, dtype=np.float64)

    def edge_value(e: float):
        if pulse_starts.size == 0:
            return None
        idx = int(np.searchsorted(pulse_starts, e, side="right")) - 1
        if idx < 0 or pulse_ends[idx] < e:
            return None
        xp, fp = pulse_arrays[idx]
        return float(np.interp(e, xp, fp))

    edges = _bin_edges(t0, t1, bins)
    edge_values = [edge_value(e) for e in edges]

    segments: list[list[tuple[float, float, bool]]] = []
    current: list[tuple[float, float, bool]] | None = None
    for k in range(bins):
        e0, e1 = edges[k], edges[k + 1]
        last = k == bins - 1
        lo = int(np.searchsorted(all_t, e0, side="left"))
        hi = int(np.searchsorted(all_t, e1, side="right" if last else "left"))
        pts_in_bin = all_v[lo:hi]
        ev0, ev1 = edge_values[k], edge_values[k + 1]
        edges_present = [v for v in (ev0, ev1) if v is not None]
        if pts_in_bin.size == 0 and not edges_present:
            if current is not None:
                segments.append(current)
                current = None
            continue
        point_min = float(pts_in_bin.min()) if pts_in_bin.size else math.inf
        point_max = float(pts_in_bin.max()) if pts_in_bin.size else -math.inf
        edge_min = min(edges_present) if edges_present else math.inf
        edge_max = max(edges_present) if edges_present else -math.inf
        min_exact = point_min <= edge_min
        max_exact = point_max >= edge_max
        ref_min = point_min if min_exact else edge_min
        ref_max = point_max if max_exact else edge_max
        centre = e0 + (e1 - e0) / 2
        if current is None:
            current = []
        current.append((e0 * 1000, ref_min, min_exact))
        current.append((centre * 1000, ref_max, max_exact))
    if current is not None:
        segments.append(current)
    return segments


def _reference_minmax_adc(adc_windows, t0: float, t1: float, bins: int) -> list[list[float]]:
    """One window `[first_on_edge_ms, last_on_edge_plus_one_ms]` for each run of bins
    that an ADC window overlaps (task 4.4, item 2)."""
    edges = _bin_edges(t0, t1, bins)
    on = []
    for k in range(bins):
        e0, e1 = edges[k], edges[k + 1]
        last = k == bins - 1
        on.append(any(a1 >= e0 and (a0 <= e1 if last else a0 < e1) for a0, a1 in adc_windows))
    windows = []
    run_start = None
    for k in range(bins):
        if on[k] and run_start is None:
            run_start = k
        if not on[k] and run_start is not None:
            windows.append([edges[run_start] * 1000, edges[k] * 1000])
            run_start = None
    if run_start is not None:
        windows.append([edges[run_start] * 1000, edges[bins] * 1000])
    return windows


def _lane_peak(values) -> float:
    """The largest absolute value of `values`, or 1.0 when there is none (so a
    relative tolerance of an all-zero lane is not zero itself, matching the plan's
    `abs_tol=1e-12 * lane_peak`)."""
    peak = max((abs(v) for v in values), default=0.0)
    return peak or 1.0


def _compare_minmax_pairs(js_pairs, expected, peak: float, context: str):
    assert len(js_pairs) == len(expected), (
        f"{context}: {len(js_pairs)} points from JS, {len(expected)} from the reference"
    )
    for i, ((t_js, v_js), (t_ref, v_ref, exact)) in enumerate(zip(js_pairs, expected)):
        assert t_js == t_ref, f"{context}: bin-pair {i}: time js={t_js!r} ref={t_ref!r}"
        if exact:
            assert v_js == v_ref, (
                f"{context}: bin-pair {i} (from a point, exact): js={v_js!r} ref={v_ref!r}"
            )
        else:
            assert math.isclose(v_js, v_ref, rel_tol=1e-12, abs_tol=1e-12 * peak), (
                f"{context}: bin-pair {i} (from an edge interpolation): "
                f"js={v_js!r} ref={v_ref!r} diff={v_js - v_ref!r}"
            )


def _assert_minmax_lanes(
    js_lanes, meta_list, t0, t1, bins, line_pts, phase_pulses, adc_windows, label
):
    assert len(js_lanes) == len(meta_list), label
    for js_lane, meta in zip(js_lanes, meta_list):
        lane_id = meta["id"]
        context = f"{label}: {lane_id}"
        assert js_lane.get("minmax") is True, f"{context}: missing minmax:true"
        for key, value in meta.items():
            assert js_lane[key] == value, f"{context}.{key} does not match lane_meta"
        if lane_id == "adc":
            expected = _reference_minmax_adc(adc_windows, t0, t1, bins)
            assert js_lane["windows"] == expected, (
                f"{context}: windows: js={js_lane['windows']!r} ref={expected!r}"
            )
        elif lane_id == "rf_phase":
            peak = _lane_peak(v for pulse in phase_pulses for _, v in pulse)
            expected_segments = _reference_minmax_phase(phase_pulses, t0, t1, bins)
            assert len(js_lane["segments"]) == len(expected_segments), (
                f"{context}: {len(js_lane['segments'])} segments from JS, "
                f"{len(expected_segments)} from the reference"
            )
            for s, (js_seg, ref_seg) in enumerate(zip(js_lane["segments"], expected_segments)):
                _compare_minmax_pairs(js_seg, ref_seg, peak, f"{context} segment {s}")
        else:
            P_L = line_pts[lane_id]
            peak = _lane_peak(v for _, v in P_L)
            expected_segment = _reference_minmax_line(P_L, t0, t1, bins)
            assert len(js_lane["segments"]) == 1, (
                f"{context}: {len(js_lane['segments'])} segments from JS, expected 1"
            )
            _compare_minmax_pairs(js_lane["segments"][0], expected_segment, peak, context)


# ---- The whole-file link to vb-pulseq parity (task 4.4, item 2's last bullet) ----


def _assert_whole_file_matches_file_lanes(js_lanes, seq):
    """The whole-file exact lanes, rounded in Python the way `markup._points` rounds
    them, must equal `waveforms.file_lanes(seq)` once its RF phase lane's empty
    segments (one per zero-amplitude pulse) are removed: `SeqLanes.exactLanes` never
    emits one for such a pulse (task 4.4, item 1)."""
    rounded = []
    for lane in js_lanes:
        lane = dict(lane)
        if lane["id"] == "adc":
            lane["windows"] = [[round(a, 4), round(b, 4)] for a, b in lane["windows"]]
        elif lane["id"] == "rf_phase":
            lane["segments"] = [
                [[round(t, 4), round(v, 3)] for t, v in seg] for seg in lane["segments"]
            ]
        else:
            lane["segments"] = [
                [[round(t, 4), round(v, 4)] for t, v in seg] for seg in lane["segments"]
            ]
        rounded.append(lane)

    reference = []
    for lane in waveforms.file_lanes(seq):
        lane = dict(lane)
        if lane["id"] == "rf_phase":
            lane["segments"] = [seg for seg in lane["segments"] if seg]
        reference.append(lane)

    assert rounded == reference


# ---- The test ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "builder",
    [
        spin_echo_sequence,
        gre_sequence,
        lambda: gre_sequence(num_trs=600),
        arbitrary_gradient_sequence,
        empty_sequence,
        lambda: gre_sequence(num_trs=10),
    ],
    ids=[
        "spin_echo",
        "gre_default",
        "gre_600_trs_two_checkpoints",
        "arbitrary_gradient",
        "empty",
        "gre_10_trs_with_tr_definition",
    ],
)
def test_seq_lanes_exact_and_minmax_views_match_the_python_reference(builder, tmp_path):
    """`SeqLanes.exactLanes` and `SeqLanes.minMaxLanes`, run through Node on one
    sequence's real tables, give the same lanes as the Python reference built
    straight from `waveforms._events_in_range`: bit for bit for the exact view, and
    exact-or-1e-12-close (task 4.4, item 2) for the min/max view. One Node process
    answers every query of one sequence, so the six sequences of this test together
    stay well under pytest's per-file time budget.
    """
    seq = builder()
    timed = list(waveforms._timed_blocks(seq))
    duration = waveforms.duration_s(seq)
    event_idx = _event_block_indices(seq, timed)
    line_pts, phase_pulses, adc_windows = _reference_data(seq, duration)

    exact_specs: list[tuple[str, float, float]] = []
    minmax_specs: list[tuple[str, float, float, int]] = []

    if not event_idx:
        # No RF, gradient or ADC event anywhere (the empty sequence): the generic
        # recipe below has nothing to anchor "one block with events" or "a range that
        # cuts blocks" on, so task 4.4 lists these two ranges instead, and only one
        # min/max query. Because "the whole file" is not one of them, this test does
        # not run the vb-pulseq parity check (below) for such a sequence.
        small = min(1e-3, duration) if duration else 1e-3
        exact_specs.append(("empty_zero_width", 0.0, 0.0))
        exact_specs.append(("empty_small_range", 0.0, small))
        minmax_specs.append(("empty_small_range", 0.0, small, 3))
    else:
        exact_specs.append(("whole_file", 0.0, duration))

        i = event_idx[0]
        _, start_i, duration_i = timed[i]
        exact_specs.append(("one_block_with_events", start_i, start_i + duration_i))

        cuts = _cuts_blocks_range(timed, event_idx)
        if cuts is not None:
            exact_specs.append(("cuts_blocks", *cuts))
            minmax_specs.append(("cuts_blocks", cuts[0], cuts[1], 50))

        no_event = _no_event_range(seq, timed, line_pts)
        if no_event is not None:
            exact_specs.append(("no_event", *no_event))

        if duration > 0:
            small = max(1e-6, duration * 0.02)
            exact_specs.append(("near_end", duration - small, duration))
            exact_specs.append(("past_end", 0.9 * duration, 1.1 * duration))

        minmax_specs.append(("whole_file_1_bin", 0.0, duration, 1))
        minmax_specs.append(("whole_file_7_bins", 0.0, duration, 7))
        minmax_specs.append(("whole_file_800_bins", 0.0, duration, 800))
        short_t0, short_t1 = _short_range(seq, timed)
        minmax_specs.append(("short_range_2000_bins", short_t0, short_t1, 2000))

    queries = [{"kind": "exact", "t0": t0, "t1": t1} for _, t0, t1 in exact_specs] + [
        {"kind": "minmax", "t0": t0, "t1": t1, "bins": bins} for _, t0, t1, bins in minmax_specs
    ]
    output, tables = _run_golden(seq, queries, tmp_path)
    meta = diagram_data.lane_meta(seq, tables=tables)

    assert output["durationS"] == duration

    results = output["results"]
    exact_results = results[: len(exact_specs)]
    minmax_results = results[len(exact_specs) :]

    exact_by_label = {}
    for (label, t0, t1), js_lanes in zip(exact_specs, exact_results):
        _assert_exact_lanes(js_lanes, meta, t0, t1, line_pts, phase_pulses, adc_windows, label)
        exact_by_label[label] = js_lanes

    for (label, t0, t1, bins), js_lanes in zip(minmax_specs, minmax_results):
        _assert_minmax_lanes(
            js_lanes, meta, t0, t1, bins, line_pts, phase_pulses, adc_windows, label
        )

    if "whole_file" in exact_by_label:
        _assert_whole_file_matches_file_lanes(exact_by_label["whole_file"], seq)
