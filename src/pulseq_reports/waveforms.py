"""Waveform data for the sequence diagram and the block table.

`file_lanes` gives the exact chart lanes of a sequence, or of the blocks in a time
range: RF magnitude and phase, the ADC gate and the three gradient axes, in ms, µT,
rad and mT/m. `file_envelope` gives the minimum and the maximum of each waveform in
equal time bins, for a view that has too many points to send. `point_count` counts the
points of `file_lanes` without building them, so a caller can choose between the two.
`block_rows` gives the rows of the block table from the same description of each block.

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

DIAGRAM_POINT_BUDGET = 200_000  # points for all lanes of one file

_AXES = ("gx", "gy", "gz")
# The joined line lanes (RF magnitude and the three gradient axes) each get two zero
# points, one at each end of the range.
_PAD_POINTS = 2 * (1 + len(_AXES))


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


def _block_events(block_id: int, t: float, duration: float, block) -> _BlockEvents:
    """The diagram content of one block that starts at `t` (s). The same computation as
    vb-pulseq `report/diagram.py::sequence_data` for one block."""
    events = []
    rf_mag = rf_phase = None
    rf = getattr(block, "rf", None)
    if rf is not None:
        rt = np.asarray(rf.t, dtype=float)
        signal = np.asarray(rf.signal, dtype=complex)
        mag = np.abs(signal) / GAMMA * 1e6
        phase = np.angle(signal * np.exp(1j * (rf.phase_offset + 2 * np.pi * rf.freq_offset * rt)))
        start = t + rf.delay
        rf_mag = (
            np.concatenate([[start], start + rt, [start + rt[-1]]]),
            np.concatenate([[0.0], mag, [0.0]]),
        )
        keep = mag > 0.01 * mag.max() if mag.max() > 0 else np.zeros_like(mag, bool)
        rf_phase = (start + rt[keep], phase[keep])
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


def point_count(seq: pp.Sequence, start_s: float | None = None, end_s: float | None = None) -> int:
    """The number of points that `file_lanes(seq, start_s, end_s)` gives, over all its
    lanes (an ADC window counts as two points), computed without building the lanes."""
    count = _PAD_POINTS
    for e in _events_in_range(seq, start_s, end_s):
        if e.rf_mag is not None:
            count += e.rf_mag[0].size + e.rf_phase[0].size
        count += sum(t.size for t, _ in e.grads.values())
        if e.adc is not None:
            count += 2
    return count


def _value_lane(lane_id, title, unit, color, segments, symmetric, has_events, fill=0.0) -> Lane:
    values = [abs(v) for seg in segments for _, v in seg]
    peak = max(values, default=0.0)
    if peak == 0.0:
        domain, ticks, labels = [-1.0, 1.0], [0.0], ["0"]
    elif symmetric:
        domain, ticks, labels = (
            [-1.1 * peak, 1.1 * peak],
            [-peak, 0.0, peak],
            [
                _fmt(-peak),
                "0",
                _fmt(peak),
            ],
        )
    else:
        domain, ticks, labels = [0.0, 1.1 * peak], [0.0, peak], ["0", _fmt(peak)]
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


class _Envelope:
    """The running minimum and maximum of one piecewise-linear waveform in equal time
    bins. Where no event covers part of a bin, the waveform is zero there."""

    def __init__(self, edges: np.ndarray) -> None:
        self.edges = edges
        n = edges.size - 1
        self.low = np.full(n, np.inf)
        self.high = np.full(n, -np.inf)
        self.covered = np.zeros(n)  # the time in each bin that an event covers
        self.has_event = False

    def add(self, t: np.ndarray, v: np.ndarray) -> None:
        """Add one event: the polyline through (t, v), zero outside [t[0], t[-1]]."""
        edges, n = self.edges, self.edges.size - 1
        t0, t1 = max(t[0], edges[0]), min(t[-1], edges[-1])
        if t1 < t0:
            return
        self.has_event = True
        # The extremes of a polyline in a bin are at its points in the bin or at the
        # bin edges.
        inside = (t >= edges[0]) & (t <= edges[-1])
        bins = np.clip(np.searchsorted(edges, t[inside], side="right") - 1, 0, n - 1)
        np.minimum.at(self.low, bins, v[inside])
        np.maximum.at(self.high, bins, v[inside])
        first = max(int(np.searchsorted(edges, t0, side="right")) - 1, 0)
        last = min(int(np.searchsorted(edges, t1, side="left")), n)
        # The bin edges inside the event, and the range ends where the event crosses
        # them. Each value belongs to the bins on both sides of its edge.
        k = np.arange(first, min(last, n) + 1)
        k = k[(edges[k] > t[0]) & (edges[k] < t[-1])]
        if k.size:
            at = np.interp(edges[k], t, v)
            for b in (k - 1, k):
                ok = (b >= 0) & (b < n)
                np.minimum.at(self.low, b[ok], at[ok])
                np.maximum.at(self.high, b[ok], at[ok])
        for b in range(first, min(last, n)):
            lo, hi = max(edges[b], t0), min(edges[b + 1], t1)
            if hi > lo:
                self.covered[b] += hi - lo

    def points(self, width: float) -> list[list[float]]:
        """(bin start, minimum), (bin centre, maximum) for each bin, rounded like
        `markup._points`. A bin that events do not cover fully includes zero."""
        uncovered = self.covered < width * (1 - 1e-9)
        low = np.where(uncovered, np.minimum(self.low, 0.0), self.low)
        high = np.where(uncovered, np.maximum(self.high, 0.0), self.high)
        starts, centres = self.edges[:-1], self.edges[:-1] + width / 2
        t = np.column_stack([starts, centres]).ravel()
        v = np.column_stack([low, high]).ravel()
        return [[round(float(a), 4), round(float(b), 4)] for a, b in zip(t, v)]


def file_envelope(
    seq: pp.Sequence, bins: int, start_s: float | None = None, end_s: float | None = None
) -> list[dict]:
    """The lanes of `file_lanes` as a minimum/maximum envelope in `bins` equal time bins
    over [start_s, end_s] (the whole sequence by default), with times in ms.

    Each line lane (RF |B1|, Gx, Gy, Gz) is one segment through (bin start, minimum) and
    (bin centre, maximum) for each bin. The ADC gate lane merges windows that are closer
    than one bin. There is no RF phase lane. Each lane has a `note` field that says it
    is an envelope; the RF |B1| note also says that the RF phase is not shown.
    """
    if bins < 1:
        raise ValueError(f"bins must be at least 1, not {bins}")
    lo = 0.0 if start_s is None else start_s
    hi = duration_s(seq) if end_s is None else end_s
    lo_ms, hi_ms = lo * 1e3, hi * 1e3
    if not hi_ms > lo_ms:
        raise ValueError(f"the range ({lo}, {hi}) s is empty")
    edges = np.linspace(lo_ms, hi_ms, bins + 1)
    width = (hi_ms - lo_ms) / bins

    envelopes = {lane: _Envelope(edges) for lane in ("rf_mag", *_AXES)}
    adc_windows: list[list[float]] = []
    for e in _events_in_range(seq, lo, hi):
        if e.rf_mag is not None:
            t, v = e.rf_mag
            envelopes["rf_mag"].add(t * 1e3, v)
        for axis, (t, v) in e.grads.items():
            envelopes[axis].add(t * 1e3, v)
        if e.adc is not None:
            a0, a1 = e.adc[0] * 1e3, e.adc[1] * 1e3
            if adc_windows and a0 - adc_windows[-1][1] < width:
                adc_windows[-1][1] = max(adc_windows[-1][1], a1)
            else:
                adc_windows.append([a0, a1])

    def joined(envelope: _Envelope) -> list:
        return [envelope.points(width)] if envelope.has_event else []

    note = f"Minimum and maximum in each of {bins} time bins of {width:.4g} ms."
    lanes = []
    for lane_id, title, unit, color, symmetric in (
        ("rf_mag", "RF |B1|", "µT", "rf", False),
        *((axis, f"G{axis[1]}", "mT/m", axis, True) for axis in _AXES),
    ):
        envelope = envelopes[lane_id]
        lane = dataclasses.asdict(
            _value_lane(
                lane_id,
                title,
                unit,
                color,
                joined(envelope),
                symmetric=symmetric,
                has_events=envelope.has_event,
            )
        )
        lane["note"] = note + (" RF phase is not shown." if lane_id == "rf_mag" else "")
        lanes.append(lane)
    adc = _adc_lane([[round(a, 4), round(b, 4)] for a, b in adc_windows])
    adc["note"] = f"ADC windows closer than one bin ({width:.4g} ms) are merged."
    return [lanes[0], adc, *lanes[1:]]


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
