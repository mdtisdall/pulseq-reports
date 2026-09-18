"""Gradient spectrum of a Pulseq sequence, checked against the acoustic resonances of
a gradient coil (by default the Siemens MAGNETOM Prisma AS82).

The gradient coil vibrates strongly at its mechanical resonances. Siemens
lists these in the gradient system's .asc file (aflAcousticResonanceFrequency
and aflAcousticResonanceBandwidth) and forbids protocols, such as EPI echo
spacings, that put gradient energy in those bands.

`gradient_spectrum` uses the same method as pypulseq's
`calculate_gradient_spectrum`: 50 ms Hann windows with 50% overlap, the
magnitude spectrum of each window, and the maximum over windows. pypulseq
stops sampling at the last gradient point and starts the first window at 0.
Here the gradients are sampled to the end of the sequence and padded with half
a window of zeros at each end, so a sequence shorter than one window still has
a spectrum and gradients near either end are not attenuated by the window.

The gradients are sampled in chunks of `CHUNK_WINDOWS` windows, so the memory does not
grow with the length of the sequence. Each chunk starts at a multiple of the hop and
overlaps the next chunk by one window less one hop, so the chunks give the same windows
as one spectrogram of the whole padded waveform.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pypulseq as pp
from scipy.signal import spectrogram

MAX_FREQUENCY_HZ = 2000.0
WINDOW_S = 0.05
FREQUENCY_OVERSAMPLING = 3
CHUNK_WINDOWS = 256  # windows in each chunk of samples

NO_GRADIENTS = "no gradients"


@dataclass(frozen=True)
class AcousticResonance:
    frequency_hz: float
    bandwidth_hz: float

    @property
    def low_hz(self) -> float:
        return self.frequency_hz - self.bandwidth_hz / 2

    @property
    def high_hz(self) -> float:
        return self.frequency_hz + self.bandwidth_hz / 2


# MAGNETOM Prisma, AS82 gradient coil (MP_GPA_K2309_2250V_951A_AS82.asc). The .asc
# file is not public; these are the values in the QIS-MRI Pulseq workshop safety
# check for its Prisma. Check them against the .asc file of the scanner you use.
PRISMA_AS82_RESONANCES = (
    AcousticResonance(frequency_hz=590.0, bandwidth_hz=100.0),
    AcousticResonance(frequency_hz=1140.0, bandwidth_hz=220.0),
)


@dataclass(frozen=True)
class BandPeak:
    resonance: AcousticResonance
    peak: float  # largest RSS spectrum value in the band, mT/m/sqrt(Hz)
    frequency_hz: float  # where that value is
    relative: float  # peak / the largest RSS spectrum value at any frequency


@dataclass(frozen=True)
class GradientSpectrum:
    reason: str | None  # why there is no spectrum, or None
    resonances: tuple[AcousticResonance, ...]
    frequency_hz: np.ndarray
    axes: dict[str, np.ndarray]  # "x", "y", "z": spectrum, mT/m/sqrt(Hz)
    rss: np.ndarray  # root-sum-of-squares of the axes in each window, then the maximum
    band_peaks: tuple[BandPeak, ...]


def gradient_spectrum(
    seq: pp.Sequence,
    resonances: tuple[AcousticResonance, ...] = PRISMA_AS82_RESONANCES,
) -> GradientSpectrum:
    """The spectrum of each gradient axis up to `MAX_FREQUENCY_HZ`, and the largest
    RSS value in each resonance band."""
    gradients = seq.get_gradients()
    if all(g is None for g in gradients):
        empty = np.zeros(0)
        return GradientSpectrum(NO_GRADIENTS, resonances, empty, {}, empty, ())

    dt = seq.system.grad_raster_time
    nwin = round(WINDOW_S / dt)
    pad = nwin // 2
    nt = math.ceil(sum(seq.block_durations.values()) / dt)
    to_mt = 1e3 / seq.system.gamma  # Hz/m to mT/m

    # The padded waveform has n samples: pad zeros, the nt gradient samples, pad zeros.
    # scipy's spectrogram does not pad, so window j covers samples [j * hop, j * hop + nwin).
    n = nt + 2 * pad
    hop = nwin - nwin // 2
    num_windows = (n - nwin) // hop + 1 if n >= nwin else 1

    axes_max: dict[str, np.ndarray] = {}
    rss_max = None
    freq = None
    for first in range(0, num_windows, CHUNK_WINDOWS):
        last = min(first + CHUNK_WINDOWS, num_windows)
        # The samples of windows first to last - 1. For a waveform shorter than one
        # window, the whole waveform (scipy then shortens the window, as in one call).
        start = first * hop
        stop = n if n < nwin else (last - 1) * hop + nwin
        rss_sq = 0.0
        for axis, g in zip("xyz", gradients):
            freq, sxx = _chunk_spectrogram(g, start, stop, pad, nt, dt, nwin, to_mt)
            keep = freq <= MAX_FREQUENCY_HZ + 1e-6
            sxx = sxx[keep]
            chunk_max = sxx.max(axis=1)
            axes_max[axis] = (
                chunk_max if axis not in axes_max else np.maximum(axes_max[axis], chunk_max)
            )
            rss_sq = rss_sq + sxx**2
        chunk_rss = np.sqrt(rss_sq).max(axis=1)
        rss_max = chunk_rss if rss_max is None else np.maximum(rss_max, chunk_rss)
    freq = freq[freq <= MAX_FREQUENCY_HZ + 1e-6]
    return GradientSpectrum(
        None, resonances, freq, axes_max, rss_max, _band_peaks(freq, rss_max, resonances)
    )


def _chunk_spectrogram(g, start, stop, pad, nt, dt, nwin, to_mt):
    """The frequencies and the magnitude spectrogram of samples [start, stop) of one
    axis's padded waveform, with the arguments of pypulseq's
    `calculate_gradient_spectrum`. `g` is the axis's piecewise polynomial from
    `Sequence.get_gradients` (Hz/m), or None for an axis with no gradient."""
    w = np.zeros(stop - start)
    if g is not None:
        # Sequence sample i is at (i + 0.5) * dt, and is padded sample i + pad.
        lo, hi = max(start - pad, 0), min(stop - pad, nt)
        if hi > lo:
            t = (np.arange(lo, hi) + 0.5) * dt
            inside = (t >= g.x[0]) & (t <= g.x[-1])
            w[lo + pad - start : hi + pad - start][inside] = g(t[inside]) * to_mt
    freq, _, sxx = spectrogram(
        w,
        fs=1 / dt,
        mode="magnitude",
        nperseg=nwin,
        noverlap=nwin // 2,
        nfft=FREQUENCY_OVERSAMPLING * nwin,
        detrend="constant",
        window=("tukey", 1),
    )
    return freq, sxx


def _band_peaks(
    freq: np.ndarray, rss: np.ndarray, resonances: tuple[AcousticResonance, ...]
) -> tuple[BandPeak, ...]:
    """The largest RSS value in each resonance band that has a frequency bin."""
    peak = float(rss.max())
    band_peaks = []
    for r in resonances:
        inside = np.flatnonzero((freq >= r.low_hz) & (freq <= r.high_hz))
        if inside.size == 0:
            continue
        i = inside[np.argmax(rss[inside])]
        band_peaks.append(
            BandPeak(
                resonance=r,
                peak=float(rss[i]),
                frequency_hz=float(freq[i]),
                relative=float(rss[i]) / peak if peak > 0 else 0.0,
            )
        )
    return tuple(band_peaks)


def combine(spectra: Sequence[GradientSpectrum]) -> GradientSpectrum:
    """The spectrum of several files: the element-wise maximum of each axis and of RSS
    over the files, with the band peaks recomputed.

    Each spectrum is a maximum over windows, so the maximum over the files is the
    maximum over the windows of all the files. The windows that would cross from one
    file to the next are not included. Files with no gradients are skipped; when no
    file has gradients, the result has the reason `NO_GRADIENTS`. All the spectra must
    have the same resonances and the same frequencies (the same gradient raster), or
    this raises ValueError.
    """
    if not spectra:
        raise ValueError("combine needs at least one spectrum")
    resonances = spectra[0].resonances
    if any(s.resonances != resonances for s in spectra):
        raise ValueError("the spectra have different resonances")
    with_gradients = [s for s in spectra if s.reason is None]
    if not with_gradients:
        empty = np.zeros(0)
        return GradientSpectrum(NO_GRADIENTS, resonances, empty, {}, empty, ())
    freq = with_gradients[0].frequency_hz
    if any(not np.array_equal(s.frequency_hz, freq) for s in with_gradients):
        raise ValueError("the spectra have different frequencies (different gradient rasters)")
    axes = {
        axis: np.maximum.reduce([s.axes[axis] for s in with_gradients])
        for axis in with_gradients[0].axes
    }
    rss = np.maximum.reduce([s.rss for s in with_gradients])
    return GradientSpectrum(None, resonances, freq, axes, rss, _band_peaks(freq, rss, resonances))
