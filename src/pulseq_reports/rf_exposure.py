"""RF exposure of a Pulseq sequence: peak B1, RF energy and B1+rms.

The values come only from the RF amplitudes in the sequence, so they do not
depend on the scanner, the transmit coil or the patient. They are not SAR: the
scanner computes SAR in W/kg itself. With `periodic=True` (the default), the
sequence is taken as one period that repeats, for example one TR. With
`periodic=False`, the sequence plays one time only.

The RF samples of each unique RF event are computed one time (`seq_index.rf_events`),
and the pulses in play order come from the sequence index, so the time and the memory
grow with the number of pulses and with the samples of the unique events, not with
every sample of every pulse (section 4.5 of docs/plans/cards-at-scale.md). The times of
the samples are the same float values as the time of each sample in play order,
`(block start + delay) + i * dt`, so the highest-window search makes the same
comparisons as a search over every sample.
"""

import math
from dataclasses import dataclass

import numpy as np
import pypulseq as pp

from pulseq_reports.seq_index import rf_events, sequence_index
from pulseq_reports.seq_utils import GAMMA, hold_samples

WINDOW_S = 10.0  # averaging window (s) for the highest B1+rms

# The number of candidate window starts that the highest-window search handles at one
# time. It bounds the memory of the search.
_CANDIDATE_CHUNK = 1 << 21


@dataclass(frozen=True)
class RfExposure:
    duration_s: float  # one period of the sequence
    num_pulses: int
    peak_b1_ut: float
    peak_block: int | None  # the first block with the peak B1
    energy_ut2_s: float  # integral of B1^2 over one period
    b1rms_ut: float  # sqrt(energy / duration): over the repeated sequence, or the one play
    window_s: float
    b1rms_window_ut: float  # the highest over any window (see window_used_s)
    window_used_s: float  # the real length (s) of the window that b1rms_window_ut covers


@dataclass(frozen=True)
class _PulseTrain:
    """The RF pulses of one or more sequences in play order, and the samples of their
    unique events. Sample `i` of pulse `j` is at the time `(base[j] + i * dt) + add[j]`
    (s), and it holds the energy `cum[i + 1] - cum[i]` (µT²·s) of the pulse's event."""

    event: np.ndarray  # int64, M: the pulse's unique event (0-based)
    base: np.ndarray  # float64, M: block start + RF delay (s)
    add: np.ndarray  # float64, M: added after base + i * dt: the file offset, 0 for one file
    block_id: np.ndarray  # int64, M: the pypulseq block id of the pulse
    ev_n: np.ndarray  # int64, K: the number of samples of each event
    ev_dt: np.ndarray  # float64, K: the sample duration of each event (s)
    ev_at: np.ndarray  # int64, K: where each event's cumulative energies start in `cum`
    cum: np.ndarray  # float64: for each event, [0, e0, e0 + e1, ...] (n + 1 values)
    ev_total: np.ndarray  # float64, K: the energy of each event (µT²·s)
    ev_peak: np.ndarray  # float64, K: the peak B1 of each event (µT)

    @property
    def num_pulses(self) -> int:
        return int(self.event.size)


def _pulse_train(seq: pp.Sequence) -> tuple[_PulseTrain, float]:
    """The pulse train of `seq`, and the duration of `seq` (s): the sum of the block
    durations in play order, as the block starts are summed."""
    index = sequence_index(seq)
    raster = seq.system.rf_raster_time
    ev_n, ev_dt, ev_delay, ev_total, ev_peak, cums = [], [], [], [], [], []
    for _, rf in rf_events(seq, index):
        signal, dt = hold_samples(rf, raster)
        b1_ut = np.abs(signal) / GAMMA * 1e6
        energy = b1_ut**2 * dt
        cum = np.concatenate([[0.0], np.cumsum(energy)])
        ev_n.append(b1_ut.size)
        ev_dt.append(float(dt))
        ev_delay.append(float(rf.delay))
        ev_total.append(float(cum[-1]))
        ev_peak.append(float(b1_ut.max()))
        cums.append(cum)

    blocks = np.flatnonzero(index.rf)
    event = index.rf[blocks].astype(np.int64) - 1
    delay = np.asarray(ev_delay, dtype=np.float64)
    n = np.asarray(ev_n, dtype=np.int64)
    at = np.cumsum(n + 1) - (n + 1)
    train = _PulseTrain(
        event=event,
        base=index.start_s[blocks] + delay[event] if blocks.size else np.empty(0),
        add=np.zeros(blocks.size),
        block_id=index.block_id[blocks].astype(np.int64),
        ev_n=n,
        ev_dt=np.asarray(ev_dt, dtype=np.float64),
        ev_at=at.astype(np.int64),
        cum=np.concatenate(cums) if cums else np.zeros(0),
        ev_total=np.asarray(ev_total, dtype=np.float64),
        ev_peak=np.asarray(ev_peak, dtype=np.float64),
    )
    return train, index.end_s


def _concat_trains(trains: list[_PulseTrain], offsets: list[float]) -> _PulseTrain:
    """The trains of several files played one after another: file `f` gets `offsets[f]`
    as its `add`, and its event indexes move past the events of the files before it."""
    event_base = np.cumsum([0] + [t.ev_n.size for t in trains[:-1]])
    cum_base = np.cumsum([0] + [t.cum.size for t in trains[:-1]])
    return _PulseTrain(
        event=np.concatenate([t.event + b for t, b in zip(trains, event_base)]),
        base=np.concatenate([t.base for t in trains]),
        add=np.concatenate([np.full(t.num_pulses, off) for t, off in zip(trains, offsets)]),
        block_id=np.concatenate([t.block_id for t in trains]),
        ev_n=np.concatenate([t.ev_n for t in trains]),
        ev_dt=np.concatenate([t.ev_dt for t in trains]),
        ev_at=np.concatenate([t.ev_at + b for t, b in zip(trains, cum_base)]),
        cum=np.concatenate([t.cum for t in trains]),
        ev_total=np.concatenate([t.ev_total for t in trains]),
        ev_peak=np.concatenate([t.ev_peak for t in trains]),
    )


class _Search:
    """The highest-window search over one pulse train, with an optional second copy of
    the train shifted by `period` (for a sequence that repeats).

    The samples are point masses at their times. A window `[s, s + length)` holds the
    masses whose time is before `s + length`, from the sample at `s` on; the search tries
    every sample time as `s` and gives the largest energy. `s` is a sample of the first
    copy. The window end `fl(s + length)` is the float sum, and "before" is the float
    comparison, as a search over an array of every sample time would make them.

    While `s` moves over the samples of one pulse, masses leave the window at its start,
    and a mass comes in only when the window end passes a sample time. So the energy
    does not increase between two such events, and only these starts can give the
    largest energy: the first sample of each pulse, and, for each sample time `u` that
    comes in while `s` moves over one pulse, the first sample `s` of that pulse with
    `fl(s + length) > u`. The search evaluates only these starts.
    """

    def __init__(self, train: _PulseTrain, period: float | None) -> None:
        self.train = train
        m = train.num_pulses
        copies = 1 if period is None else 2
        self.m = m
        self.event = np.tile(train.event, copies)
        self.base = np.tile(train.base, copies)
        self.add = np.tile(train.add, copies)
        self.shift = np.concatenate([np.zeros(m)] + ([np.full(m, period)] if period else []))
        self.n = train.ev_n[self.event]
        self.dt = train.ev_dt[self.event]
        self.at = train.ev_at[self.event]
        # The time of each pulse's first sample, `((base + 0 * dt) + add) + shift`.
        self.first = self._time(np.arange(self.event.size), np.zeros(self.event.size, np.int64))
        # The number of samples and the energy before each pulse.
        self.samples_before = np.concatenate([[0], np.cumsum(self.n)[:-1]]).astype(np.int64)
        energy = train.ev_total[self.event]
        self.energy_before = np.concatenate([[0.0], np.cumsum(energy)[:-1]])

    def _time(self, pulse: np.ndarray, i: np.ndarray) -> np.ndarray:
        """The time of sample `i` of (extended) pulse `pulse`, with the float operations of
        a search over every sample: `((base + i * dt) + add) + shift`."""
        return ((self.base[pulse] + i * self.dt[pulse]) + self.add[pulse]) + self.shift[pulse]

    def _before(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """The number of samples whose time is before `x`, and their energy."""
        q = np.searchsorted(self.first, x, side="left") - 1
        none = q < 0
        q = np.maximum(q, 0)
        n = self.n[q]
        with np.errstate(invalid="ignore", divide="ignore"):
            c = np.ceil((x - self.first[q]) / self.dt[q])
        c = np.clip(np.nan_to_num(c, nan=1.0), 1, n).astype(np.int64)
        for _ in range(64):
            up = (c < n) & (self._time(q, np.minimum(c, n - 1)) < x)
            down = (c > 1) & (self._time(q, c - 1) >= x)
            if not (up.any() or down.any()):
                break
            c = c + up - down
        else:
            raise RuntimeError("rf_exposure: the sample count did not converge")
        count = np.where(none, 0, self.samples_before[q] + c)
        energy = np.where(none, 0.0, self.energy_before[q] + self.train.cum[self.at[q] + c])
        return count, energy

    def _first_start_after(self, pulse: np.ndarray, u: np.ndarray, length: float) -> np.ndarray:
        """For each first-copy `pulse` and time `u`, the smallest sample `i` (1 to n - 1)
        with `fl(time(pulse, i) + length) > u`. The caller makes sure that it exists."""
        n = self.n[pulse]
        start = self.base[pulse] + self.add[pulse]
        i = np.ceil(((u - length) - start) / self.dt[pulse])
        i = np.clip(np.nan_to_num(i, nan=1.0), 1, n - 1).astype(np.int64)
        for _ in range(64):
            up = (i < n - 1) & ~(self._time(pulse, i) + length > u)
            down = (i > 1) & (self._time(pulse, i - 1) + length > u)
            if not (up.any() or down.any()):
                break
            i = i + up - down
        else:
            raise RuntimeError("rf_exposure: the window start did not converge")
        return i

    def max_energy(self, length: float) -> float:
        if length <= 0 or self.m == 0:
            return 0.0
        pulses = np.arange(self.m)
        # The first sample of each pulse.
        _, end_energy = self._before(self.first[pulses] + length)
        best = float(np.max(end_energy - self.energy_before[pulses]))

        # The samples that come in while the start moves over each pulse: those in
        # [fl(first + length), fl(last + length)), by global sample index.
        last = self._time(pulses, self.n[pulses] - 1)
        lo, _ = self._before(self.first[pulses] + length)
        hi, _ = self._before(last + length)
        counts = np.maximum(hi - lo, 0)
        todo = np.flatnonzero(counts)
        if todo.size == 0:
            return best
        cum_counts = np.cumsum(counts[todo])
        start = 0
        while start < todo.size:
            done_before = cum_counts[start - 1] if start else 0
            stop = int(np.searchsorted(cum_counts, done_before + _CANDIDATE_CHUNK, "right"))
            stop = max(stop, start + 1)
            chunk = todo[start:stop]
            c = counts[chunk]
            pulse = np.repeat(chunk, c)
            first_offset = np.cumsum(c) - c
            g = np.repeat(lo[chunk], c) + (np.arange(int(c.sum())) - np.repeat(first_offset, c))
            q = np.searchsorted(self.samples_before, g, side="right") - 1
            u = self._time(q, g - self.samples_before[q])
            i = self._first_start_after(pulse, u, length)
            s = self._time(pulse, i)
            _, end_energy = self._before(s + length)
            start_energy = self.energy_before[pulse] + self.train.cum[self.at[pulse] + i]
            best = max(best, float(np.max(end_energy - start_energy)))
            start = stop
        return best


def _windowed_energy(
    train: _PulseTrain, duration: float, window_s: float, periodic: bool
) -> tuple[float, float]:
    """The real window length (s) and the energy (µT²·s) in the highest window of that
    length, for one pulse train of `duration` (s).

    With `periodic=True`, the window is exactly `window_s`, the sequence repeats, and the
    search wraps past the end into the next repetition. With `periodic=False`, the sequence
    plays once: when `duration` is at least `window_s`, the window is `window_s` and the
    search does not wrap; when `duration` is shorter than `window_s`, the window is the
    whole sequence.
    """
    if duration <= 0 or train.num_pulses == 0:
        return (window_s if periodic else duration), 0.0
    total = float(np.sum(train.ev_total[train.event]))
    if periodic:
        repeats, rest = divmod(window_s, duration)
        return window_s, repeats * total + _Search(train, duration).max_energy(rest)
    if duration <= window_s:
        return duration, total
    return window_s, _Search(train, None).max_energy(window_s)


def _exposure(train: _PulseTrain, duration: float, window_s: float, periodic: bool) -> RfExposure:
    """The `RfExposure` of one sequence's pulse train."""
    if train.num_pulses == 0 or duration <= 0:
        window_used = window_s if periodic else duration
        return RfExposure(
            duration, train.num_pulses, 0.0, None, 0.0, 0.0, window_s, 0.0, window_used
        )
    peaks = train.ev_peak[train.event]
    peak_b1 = float(peaks.max())
    peak_block = int(train.block_id[int(np.argmax(peaks == peak_b1))])
    total = float(np.sum(train.ev_total[train.event]))
    window_used, window_energy = _windowed_energy(train, duration, window_s, periodic)
    return RfExposure(
        duration_s=duration,
        num_pulses=train.num_pulses,
        peak_b1_ut=peak_b1,
        peak_block=peak_block,
        energy_ut2_s=total,
        b1rms_ut=math.sqrt(total / duration),
        window_s=window_s,
        b1rms_window_ut=math.sqrt(window_energy / window_used) if window_used > 0 else 0.0,
        window_used_s=window_used,
    )


def rf_exposure(seq: pp.Sequence, window_s: float = WINDOW_S, periodic: bool = True) -> RfExposure:
    """Peak B1, ∫B1² dt and B1+rms of `seq`. With `periodic=True` (parity with vb-pulseq),
    `seq` is treated as one period that repeats. With `periodic=False`, `seq` plays once;
    see `_windowed_energy` for how that changes the highest-window search."""
    train, duration = _pulse_train(seq)
    return _exposure(train, duration, window_s, periodic)
