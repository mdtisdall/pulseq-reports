"""RF exposure of a Pulseq sequence: peak B1, RF energy and B1+rms.

The values come only from the RF amplitudes in the sequence, so they do not
depend on the scanner, the transmit coil or the patient. They are not SAR: the
scanner computes SAR in W/kg itself. With `periodic=True` (the default), the
sequence is taken as one period that repeats, for example one TR. With
`periodic=False`, the sequence plays one time only.
"""

import math
from dataclasses import dataclass

import numpy as np
import pypulseq as pp

from pulseq_reports.seq_utils import GAMMA, hold_samples, iter_blocks

WINDOW_S = 10.0  # averaging window (s) for the highest B1+rms


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


def _rf_samples(
    seq: pp.Sequence, raster: float
) -> tuple[list[np.ndarray], list[np.ndarray], float, float, int | None, int]:
    """The RF sample times (s) and B1² energy contributions (µT²·s) of every pulse in
    `seq`, in play order, together with the sequence duration, the peak B1 (µT), the id
    of the first block with that peak, and the number of pulses."""
    times: list[np.ndarray] = []
    energies: list[np.ndarray] = []
    peak_b1, peak_block, num_pulses = 0.0, None, 0

    duration = 0.0
    for block_id, t, block_duration, block in iter_blocks(seq):
        rf = getattr(block, "rf", None)
        if rf is not None:
            signal, dt = hold_samples(rf, raster)
            b1_ut = np.abs(signal) / GAMMA * 1e6
            times.append(t + rf.delay + np.arange(b1_ut.size) * dt)
            energies.append(b1_ut**2 * dt)
            num_pulses += 1
            if b1_ut.max() > peak_b1:
                peak_b1, peak_block = float(b1_ut.max()), block_id
        duration = t + block_duration

    return times, energies, duration, peak_b1, peak_block, num_pulses


def _max_window_energy(
    times: np.ndarray, energy: np.ndarray, period: float, length: float
) -> float:
    """The largest energy in a window of `length` (s, less than `period`) that starts at a
    sample, with the sequence repeated. Each sample counts at its start time."""
    if length <= 0 or times.size == 0:
        return 0.0
    t = np.concatenate([times, times + period])
    cumulative = np.concatenate([[0.0], np.cumsum(np.concatenate([energy, energy]))])
    end = np.searchsorted(t, times + length, side="left")
    return float(np.max(cumulative[end] - cumulative[: times.size]))


def _max_window_energy_no_wrap(times: np.ndarray, energy: np.ndarray, length: float) -> float:
    """The largest energy in a window of `length` (s) that starts at a sample, without
    wrapping past the last sample. Each sample counts at its start time."""
    if length <= 0 or times.size == 0:
        return 0.0
    cumulative = np.concatenate([[0.0], np.cumsum(energy)])
    end = np.searchsorted(times, times + length, side="left")
    return float(np.max(cumulative[end] - cumulative[: times.size]))


def _windowed_energy(
    times: np.ndarray, energy: np.ndarray, duration: float, window_s: float, periodic: bool
) -> tuple[float, float]:
    """The real window length (s) and the energy (µT²·s) in the highest window of that
    length, for one sequence of `duration` (s) whose RF samples are `times`/`energy`.

    With `periodic=True`, the window is exactly `window_s`, the sequence repeats, and the
    search wraps past the end into the next repetition. With `periodic=False`, the sequence
    plays once: when `duration` is at least `window_s`, the window is `window_s` and the
    search does not wrap; when `duration` is shorter than `window_s`, the window is the
    whole sequence.
    """
    if duration <= 0 or times.size == 0:
        return (window_s if periodic else duration), 0.0
    if periodic:
        repeats, rest = divmod(window_s, duration)
        total = float(energy.sum())
        window_energy = repeats * total + _max_window_energy(times, energy, duration, rest)
        return window_s, window_energy
    if duration <= window_s:
        return duration, float(energy.sum())
    return window_s, _max_window_energy_no_wrap(times, energy, window_s)


def rf_exposure(seq: pp.Sequence, window_s: float = WINDOW_S, periodic: bool = True) -> RfExposure:
    """Peak B1, ∫B1² dt and B1+rms of `seq`. With `periodic=True` (parity with vb-pulseq),
    `seq` is treated as one period that repeats. With `periodic=False`, `seq` plays once;
    see `_windowed_energy` for how that changes the highest-window search."""
    raster = seq.system.rf_raster_time
    times, energies, duration, peak_b1, peak_block, num_pulses = _rf_samples(seq, raster)

    if num_pulses == 0 or duration <= 0:
        window_used = window_s if periodic else duration
        return RfExposure(duration, num_pulses, 0.0, None, 0.0, 0.0, window_s, 0.0, window_used)

    sample_times = np.concatenate(times)
    sample_energy = np.concatenate(energies)
    total = float(sample_energy.sum())
    window_used, window_energy = _windowed_energy(
        sample_times, sample_energy, duration, window_s, periodic
    )
    return RfExposure(
        duration_s=duration,
        num_pulses=num_pulses,
        peak_b1_ut=peak_b1,
        peak_block=peak_block,
        energy_ut2_s=total,
        b1rms_ut=math.sqrt(total / duration),
        window_s=window_s,
        b1rms_window_ut=math.sqrt(window_energy / window_used) if window_used > 0 else 0.0,
        window_used_s=window_used,
    )
