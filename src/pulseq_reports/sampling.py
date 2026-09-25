"""The gradient waveform of one axis at given times, from the sequence index.

The waveform is the polyline of pypulseq's `Sequence.get_gradients()`, in Hz/m:

1. The points. For each block, in play order, that has an event on the axis: the
   corner or sample points of that event (`seq_utils.gradient_offsets`), at the times
   `(block start + delay) + offsets`, with the event's amplitudes.
2. The join. The points of all these blocks make one list. A point whose time is not
   more than `pypulseq.eps` (1e-9 s) after the time of the point before it in the list
   is left out. pypulseq's `waveforms()` leaves out the first point of an event at the
   time of the last point of the event before it, so the step at such a junction takes
   the value of the earlier event. The same rule removes the repeated points that
   `gradient_offsets` gives inside some events (for example a trapezoid without a flat
   time), which have the same value.
3. The values. Straight lines between consecutive points, also across a gap between
   two events. 0 before the first point and after the last point.
"""

import numpy as np
import pypulseq as pp

from .seq_index import SequenceIndex, grad_events
from .seq_utils import gradient_offsets

_AXES = ("gx", "gy", "gz")


class GradientSampler:
    """The waveform of each axis of one sequence, sampled at any sorted times.

    The unique gradient events are read one time (`seq_index.grad_events`). A call to
    `sample` costs O(samples + blocks between the first and the last sample), not
    O(all blocks).
    """

    def __init__(self, seq: pp.Sequence, index: SequenceIndex) -> None:
        delays: list[float] = []
        counts: list[int] = []
        offset_chunks: list[np.ndarray] = []
        amp_chunks: list[np.ndarray] = []
        for _, g in grad_events(seq, index):
            delay, offsets, amp = gradient_offsets(g)
            offsets = np.asarray(offsets, dtype=np.float64)
            amp = np.asarray(amp, dtype=np.float64)
            delays.append(float(delay))
            counts.append(offsets.size)
            offset_chunks.append(offsets)
            amp_chunks.append(amp)

        self._index = index
        self._delay = np.asarray(delays, dtype=np.float64)
        self._n = np.asarray(counts, dtype=np.int64)
        # The exclusive prefix sum: the start position of each event's points in the
        # pooled `_offsets`/`_amp` arrays.
        self._at = np.cumsum(self._n, dtype=np.int64) - self._n
        self._offsets = (
            np.concatenate(offset_chunks) if offset_chunks else np.empty(0, dtype=np.float64)
        )
        self._amp = np.concatenate(amp_chunks) if amp_chunks else np.empty(0, dtype=np.float64)
        # Filled lazily, one time for each axis that `sample` is called with.
        self._axis_blocks: dict[str, np.ndarray] = {}

    def _event_blocks(self, axis: str) -> np.ndarray:
        """The play indexes that have an event on `axis`, sorted, computed one time and
        kept for later calls."""
        blocks = self._axis_blocks.get(axis)
        if blocks is None:
            blocks = np.flatnonzero(getattr(self._index, axis))
            self._axis_blocks[axis] = blocks
        return blocks

    def _points(self, axis: str, blocks: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Times (s) and values (Hz/m) of the corner or sample points of the gradient
        events of `axis` at the play indexes `blocks` (sorted, each with an event on
        `axis`), in block order, before the join rule is applied."""
        col = getattr(self._index, axis)
        k = col[blocks].astype(np.int64) - 1  # 0-based event index
        counts = self._n[k]
        total = int(counts.sum())
        if total == 0:
            return np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64)
        base = np.repeat(self._index.start_s[blocks] + self._delay[k], counts)
        group_start = np.cumsum(counts) - counts
        local = np.arange(total, dtype=np.int64) - np.repeat(group_start, counts)
        pool_index = np.repeat(self._at[k], counts) + local
        times = base + self._offsets[pool_index]
        values = self._amp[pool_index]
        return times, values

    def sample(self, axis: str, t: np.ndarray) -> np.ndarray:
        """The waveform of `axis` ("gx", "gy" or "gz") in Hz/m at the times `t` (s),
        which must be sorted in increasing order."""
        if axis not in _AXES:
            raise ValueError(f"axis must be one of {_AXES}: {axis!r}")
        t = np.asarray(t, dtype=np.float64)
        if t.size == 0:
            return np.empty(0, dtype=np.float64)

        event_blocks = self._event_blocks(axis)
        if event_blocks.size == 0:
            return np.zeros(t.size, dtype=np.float64)

        # The block that contains (or, past the sequence end, precedes) each end of the
        # sample range: the last block whose start is not after that time.
        start_s = self._index.start_s
        lo_block = max(int(np.searchsorted(start_s, t[0], side="right")) - 1, 0)
        hi_block = max(int(np.searchsorted(start_s, t[-1], side="right")) - 1, 0)

        # The events of `axis` in that block range, plus the nearest one before it and
        # the nearest one after it, so that a gap at the edge of the range interpolates
        # correctly (section 4.3 of docs/plans/cards-at-scale.md).
        lo_pos = int(np.searchsorted(event_blocks, lo_block, side="left"))
        hi_pos = int(np.searchsorted(event_blocks, hi_block, side="right"))
        blocks = event_blocks[max(lo_pos - 1, 0) : min(hi_pos + 1, event_blocks.size)]

        times, values = self._points(axis, blocks)
        if times.size == 0:
            return np.zeros(t.size, dtype=np.float64)

        keep = np.ones(times.size, dtype=bool)
        if times.size > 1:
            keep[1:] = times[1:] > times[:-1] + pp.eps
        times = times[keep]
        values = values[keep]

        return np.interp(t, times, values, left=0.0, right=0.0)
