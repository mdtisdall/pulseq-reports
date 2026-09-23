"""Waveform data for the sequence diagram and the block table.

`file_lanes` gives the exact chart lanes of a sequence, or of the blocks in a time
range: RF magnitude and phase, the ADC gate and the three gradient axes, in ms, µT,
rad and mT/m. It is the reference for the browser's `SeqLanes` (`assets/seq_lanes.js`),
which draws the diagram from the tables of `diagram_data`. `block_rows` gives the rows
of the block table from the same description of each block.

Each function reads one block at a time. A range reads only the blocks that overlap it.
"""

import dataclasses
import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

import numpy as np
import pypulseq as pp

from .markup import Lane, _fmt, _lanes_json, _points
from .seq_utils import GAMMA, NamedSequence, gradient_points

_AXES = ("gx", "gy", "gz")


@dataclass(frozen=True)
class TimeWindow:
    """A named time range in one file of a list of sequences, for example one TR."""

    label: str  # the button text
    file_index: int  # the index in the list of sequences
    start_s: float
    end_s: float


@dataclass(frozen=True)
class _BlockEvents:
    """The diagram content of one block, as arrays in ms and display units."""

    block_id: int
    start_s: float
    duration_s: float
    rf_mag: tuple[np.ndarray, np.ndarray] | None  # times (s), µT, with the zero ends
    rf_phase: tuple[np.ndarray, np.ndarray] | None  # times (s), rad, where |B1| > 1% peak
    grads: dict[str, tuple[np.ndarray, np.ndarray]]  # "gx": times (s), mT/m
    adc: tuple[float, float] | None  # start and end (s)
    events: str  # the text of the block table's Events column


def _timed_blocks(seq: pp.Sequence) -> Iterator[tuple[int, float, float]]:
    """(block id, start (s), duration (s)) of each block in play order, without reading
    the block. The start times are added as in `seq_utils.iter_blocks`."""
    start = 0.0
    for block_id in seq.block_events:
        duration = seq.block_durations[block_id]
        yield int(block_id), start, duration
        start += duration


def _in_range(start: float, duration: float, lo: float | None, hi: float | None) -> bool:
    """True when the block [start, start + duration] overlaps the range [lo, hi]. A
    `None` end is open. A block that only touches the range at one point is out of it,
    except a block of zero duration inside the range."""
    end = start + duration
    if duration == 0:
        return (lo is None or start >= lo) and (hi is None or start <= hi)
    return (lo is None or end > lo) and (hi is None or start < hi)


def _rf_offsets(rf) -> tuple[float, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """The delay (s) and the offsets and values of one RF event's magnitude (µT) and
    phase (rad) points, relative to the delay: `mag_offsets = [0, rt..., rt[-1]]` with a
    zero-padded `mag`, and `phase_offsets = rt[keep]` with `phase` there, where `keep`
    is `mag` above 1% of its peak."""
    rt = np.asarray(rf.t, dtype=float)
    signal = np.asarray(rf.signal, dtype=complex)
    mag = np.abs(signal) / GAMMA * 1e6
    phase = np.angle(signal * np.exp(1j * (rf.phase_offset + 2 * np.pi * rf.freq_offset * rt)))
    mag_offsets = np.concatenate([[0.0], rt, [rt[-1]]])
    mag_padded = np.concatenate([[0.0], mag, [0.0]])
    keep = mag > 0.01 * mag.max() if mag.max() > 0 else np.zeros_like(mag, bool)
    phase_offsets = rt[keep]
    phase = phase[keep]
    return rf.delay, mag_offsets, mag_padded, phase_offsets, phase


def _block_events(block_id: int, t: float, duration: float, block) -> _BlockEvents:
    """The diagram content of one block that starts at `t` (s). The same computation as
    vb-pulseq `report/diagram.py::sequence_data` for one block."""
    events = []
    rf_mag = rf_phase = None
    rf = getattr(block, "rf", None)
    if rf is not None:
        delay, mag_offsets, mag, phase_offsets, phase = _rf_offsets(rf)
        start = t + delay
        rf_mag = (start + mag_offsets, mag)
        rf_phase = (start + phase_offsets, phase)
        use = getattr(rf, "use", "")
        events.append(f"RF ({use})" if use else "RF")

    grads = {}
    for axis in _AXES:
        g = getattr(block, axis, None)
        if g is not None:
            gt, amp = gradient_points(g, t)
            grads[axis] = (gt, amp / GAMMA * 1e3)
            events.append(f"G{axis[1]} {g.type}")

    adc_window = None
    adc = getattr(block, "adc", None)
    if adc is not None:
        a0 = t + adc.delay
        adc_window = (a0, a0 + adc.num_samples * adc.dwell)
        events.append(f"ADC {adc.num_samples} × {adc.dwell * 1e6:g} µs")

    return _BlockEvents(
        block_id, t, duration, rf_mag, rf_phase, grads, adc_window, ", ".join(events) or "delay"
    )


def _events_in_range(
    seq: pp.Sequence, start_s: float | None, end_s: float | None
) -> Iterator[_BlockEvents]:
    """The `_BlockEvents` of each block that overlaps [start_s, end_s], in play order.
    Only those blocks are read."""
    for block_id, t, duration in _timed_blocks(seq):
        if end_s is not None and t > end_s:
            return
        if _in_range(t, duration, start_s, end_s):
            yield _block_events(block_id, t, duration, seq.get_block(block_id))


def duration_s(seq: pp.Sequence) -> float:
    """The end of the last block (s), added one block at a time as in `iter_blocks`."""
    end = 0.0
    for _, t, duration in _timed_blocks(seq):
        end = t + duration
    return end


def block_row(e: _BlockEvents) -> dict:
    """One row of the block table: block id, start (ms), duration (ms) and events."""
    return {
        "block": e.block_id,
        "start_ms": round(e.start_s * 1e3, 4),
        "duration_ms": round(e.duration_s * 1e3, 4),
        "events": e.events,
    }


def block_rows(
    seq: pp.Sequence,
    start_s: float | None = None,
    end_s: float | None = None,
    max_rows: int | None = None,
) -> tuple[list[dict], int]:
    """The block table rows of the blocks that overlap [start_s, end_s] (all blocks by
    default), at most `max_rows` of them, and the number of blocks in the range. Only
    the blocks of the rows are read."""
    rows: list[dict] = []
    total = 0
    for block_id, t, duration in _timed_blocks(seq):
        if not _in_range(t, duration, start_s, end_s):
            continue
        total += 1
        if max_rows is None or len(rows) < max_rows:
            rows.append(block_row(_block_events(block_id, t, duration, seq.get_block(block_id))))
    return rows, total


def _value_domain(peak: float, symmetric: bool) -> tuple[list[float], list[float], list[str]]:
    """The domain, ticks and tick labels of a value lane whose largest absolute rounded
    point is `peak`."""
    if peak == 0.0:
        return [-1.0, 1.0], [0.0], ["0"]
    if symmetric:
        return (
            [-1.1 * peak, 1.1 * peak],
            [-peak, 0.0, peak],
            [
                _fmt(-peak),
                "0",
                _fmt(peak),
            ],
        )
    return [0.0, 1.1 * peak], [0.0, peak], ["0", _fmt(peak)]


def _value_lane(lane_id, title, unit, color, segments, symmetric, has_events, fill=0.0) -> Lane:
    values = [abs(v) for seg in segments for _, v in seg]
    peak = max(values, default=0.0)
    domain, ticks, labels = _value_domain(peak, symmetric)
    return Lane(
        id=lane_id,
        title=title,
        unit=unit,
        color=color,
        segments=segments,
        domain=domain,
        ticks=ticks,
        tick_labels=labels,
        empty=not has_events,
        fill=fill,
    )


def _phase_lane(segments: list) -> Lane:
    return dataclasses.replace(
        _value_lane(
            "rf_phase",
            "RF phase",
            "rad",
            "rf",
            segments,
            symmetric=True,
            has_events=bool(segments),
        ),
        domain=[-1.1 * math.pi, 1.1 * math.pi],
        ticks=[-math.pi, 0.0, math.pi],
        tick_labels=["−π", "0", "π"],
        fill=None,
    )


def _adc_lane(windows: list) -> dict:
    return {
        "id": "adc",
        "title": "ADC",
        "unit": "",
        "color": "adc",
        "kind": "gate",
        "windows": windows,
        "domain": [0.0, 1.25],
        "ticks": [0.0, 1.0],
        "tick_labels": ["off", "on"],
        "empty": not windows,
    }


def _lanes(rf_mag: list, rf_phase: list, adc_windows: list, grads: dict, joined) -> list:
    """The six lanes in their page order, from the parts of each lane. `joined` makes
    the one segment of a line lane from its parts."""
    lanes = [
        _value_lane(
            "rf_mag",
            "RF |B1|",
            "µT",
            "rf",
            joined(rf_mag),
            symmetric=False,
            has_events=bool(rf_mag),
        ),
        _phase_lane(rf_phase),
        _adc_lane(adc_windows),
    ]
    for axis, parts in grads.items():
        lanes.append(
            _value_lane(
                axis,
                f"G{axis[1]}",
                "mT/m",
                axis,
                joined(parts),
                symmetric=True,
                has_events=bool(parts),
            )
        )
    return lanes


def file_lanes(
    seq: pp.Sequence, start_s: float | None = None, end_s: float | None = None
) -> list[dict]:
    """The exact chart lanes of the blocks of `seq` that overlap [start_s, end_s]: RF
    |B1| (µT), RF phase (rad), the ADC gate, and Gx, Gy, Gz (mT/m), with times in ms.

    With no range, these are the lanes of vb-pulseq `sequence_data` (parity). The line
    lanes RF |B1|, Gx, Gy and Gz are one segment each, with a zero point at the start of
    the first block in the range and at the end of the last one (0 and the sequence end
    when there is no range). A block that crosses a range edge is included whole, so
    points can be outside the range.
    """
    grads: dict[str, list] = {axis: [] for axis in _AXES}
    rf_mag: list = []
    rf_phase: list = []
    adc_windows: list = []
    first_start = last_end = None
    for e in _events_in_range(seq, start_s, end_s):
        if first_start is None:
            first_start = e.start_s
        last_end = e.start_s + e.duration_s
        if e.rf_mag is not None:
            rf_mag.append(_points(*e.rf_mag))
            rf_phase.append(_points(*e.rf_phase, digits=3))
        for axis, (t, amp) in e.grads.items():
            grads[axis].append(_points(t, amp))
        if e.adc is not None:
            a0, a1 = e.adc
            adc_windows.append([round(a0 * 1e3, 4), round(a1 * 1e3, 4)])

    if first_start is None:  # no block in the range
        first_start, last_end = start_s or 0.0, end_s or 0.0
    lo_ms, hi_ms = round(first_start * 1e3, 4), round(last_end * 1e3, 4)

    def joined(parts: list) -> list:
        # One zero-padded segment across the blocks in the range.
        return [[[lo_ms, 0.0], *[p for part in parts for p in part], [hi_ms, 0.0]]]

    return _lanes_json(_lanes(rf_mag, rf_phase, adc_windows, grads, joined))


def first_adc_window(seqs: Sequence[NamedSequence], file_index: int = 0) -> TimeWindow:
    """vb-pulseq's "First ADC" view of one file: from 0 to 1.1 times the end of the first
    ADC window, or the whole file when that is shorter or there is no ADC."""
    seq = seqs[file_index].seq
    end = duration_s(seq)
    duration_ms = round(end * 1e3, 4)
    window_ms = duration_ms
    for e in _events_in_range(seq, None, None):
        if e.adc is not None:
            window_ms = min(duration_ms, 1.1 * round(e.adc[1] * 1e3, 4))
            break
    window_ms = round(window_ms, 4)
    return TimeWindow(f"First ADC (0–{window_ms:.3g} ms)", file_index, 0.0, window_ms / 1e3)


def full_window(seqs: Sequence[NamedSequence], file_index: int = 0) -> TimeWindow:
    """vb-pulseq's "Full sequence" view of one file: from 0 to the end of the file."""
    duration_ms = round(duration_s(seqs[file_index].seq) * 1e3, 4)
    return TimeWindow(f"Full sequence (0–{duration_ms:g} ms)", file_index, 0.0, duration_ms / 1e3)
