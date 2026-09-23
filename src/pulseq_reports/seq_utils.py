"""Shared helpers for reading a pypulseq sequence, used by the report cards."""

from collections.abc import Iterator
from dataclasses import dataclass
from types import SimpleNamespace
from typing import NamedTuple

import numpy as np
import pypulseq as pp

GAMMA = 42.576e6  # Hz/T
TIME_TOLERANCE = 1e-9  # s


class BlockTiming(NamedTuple):
    block_id: int
    start_s: float  # sum of the durations of the blocks before this one
    duration_s: float
    block: SimpleNamespace  # from Sequence.get_block


def iter_blocks(seq: pp.Sequence) -> Iterator[BlockTiming]:
    """Each block of `seq` in play order, with its start time and duration (s).

    The start times are added in play order from 0.0, one block duration at a time,
    so they are equal to `t += seq.block_durations[block_id]` in a loop. The end of
    the sequence is `start_s + duration_s` of the last block.
    """
    start = 0.0
    for block_id in seq.block_events:
        duration = seq.block_durations[block_id]
        yield BlockTiming(int(block_id), start, duration, seq.get_block(block_id))
        start += duration


def hold_samples(rf: SimpleNamespace, raster: float) -> tuple[np.ndarray, float]:
    """RF samples (Hz, complex), each held for dt (s).

    A shape with uniform samples that fill shape_dur is used as it is. Other shapes,
    for example a block pulse with samples at its start and end, are interpolated
    linearly at the centers of raster intervals.
    """
    t = np.asarray(rf.t, dtype=float)
    signal = np.asarray(rf.signal, dtype=complex)
    if len(t) > 1:
        dt = t[1] - t[0]
        uniform = np.allclose(np.diff(t), dt, rtol=1e-6, atol=TIME_TOLERANCE)
        if uniform and abs(len(t) * dt - rf.shape_dur) <= TIME_TOLERANCE:
            return signal, dt
    n = max(1, round(rf.shape_dur / raster))
    dt = rf.shape_dur / n
    centers = (np.arange(n) + 0.5) * dt
    return np.interp(centers, t, signal.real) + 1j * np.interp(centers, t, signal.imag), dt


def gradient_offsets(g) -> tuple[float, np.ndarray, np.ndarray]:
    """The delay (s) and the offsets (s) and amplitudes (Hz/m) of one gradient event's
    corner or sample points, relative to the delay."""
    if g.type == "trap":
        offsets = np.cumsum([0.0, g.rise_time, g.flat_time, g.fall_time])
        amp = np.array([0.0, g.amplitude, g.amplitude, 0.0])
    else:
        offsets = np.asarray(g.tt, dtype=float)
        amp = np.asarray(g.waveform, dtype=float)
        if hasattr(g, "first") and hasattr(g, "shape_dur"):
            offsets = np.concatenate([[0.0], offsets, [g.shape_dur]])
            amp = np.concatenate([[g.first], amp, [g.last]])
    return g.delay, offsets, amp


def gradient_points(g, t0: float) -> tuple[np.ndarray, np.ndarray]:
    """Corner or sample times (s) and amplitudes (Hz/m) of one gradient event."""
    delay, offsets, amp = gradient_offsets(g)
    return (t0 + delay) + offsets, amp


@dataclass(frozen=True)
class NamedSequence:
    name: str  # shown in the report, for example the file name
    seq: pp.Sequence
