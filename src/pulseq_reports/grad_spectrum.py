"""Gradient spectrum of a Pulseq sequence, and its largest values in the acoustic
resonance bands that the caller gives.

The gradient coil vibrates strongly at its mechanical resonances. Siemens
lists these in the gradient system's .asc file (aflAcousticResonanceFrequency
and aflAcousticResonanceBandwidth) and forbids protocols, such as EPI echo
spacings, that put gradient energy in those bands. A resonance is a pair
(frequency_hz, bandwidth_hz), the centre frequency and the full width of its band
in Hz. There is no default coil: the caller gives the resonances, or none.

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
from dataclasses import dataclass

import numpy as np
import pypulseq as pp
from scipy.signal import spectrogram

from .sampling import GradientSampler
from .seq_index import sequence_index

MAX_FREQUENCY_HZ = 2000.0
FFT_WINDOW_S = 0.05
FREQUENCY_OVERSAMPLING = 3
CHUNK_WINDOWS = 256  # windows in each chunk of samples

NO_GRADIENTS = "no gradients"


@dataclass(frozen=True)
class BandPeak:
    resonance: tuple[float, float]  # (frequency_hz, bandwidth_hz) of the band
    peak: float  # largest RSS spectrum value in the band, mT/m/sqrt(Hz)
    frequency_hz: float  # where that value is
    relative: float  # peak / the largest RSS spectrum value at any frequency


@dataclass(frozen=True)
class GradientSpectrum:
    reason: str | None  # why there is no spectrum, or None
    resonances: tuple[tuple[float, float], ...]  # (frequency_hz, bandwidth_hz) pairs
    frequency_hz: np.ndarray
    axes: dict[str, np.ndarray]  # "x", "y", "z": spectrum, mT/m/sqrt(Hz)
    rss: np.ndarray  # root-sum-of-squares of the axes in each window, then the maximum
    band_peaks: tuple[BandPeak, ...]


def gradient_spectrum(
    seq: pp.Sequence,
    *,
    resonances: tuple[tuple[float, float], ...] = (),
) -> GradientSpectrum:
    """The spectrum of each gradient axis up to `MAX_FREQUENCY_HZ`, and the largest
    RSS value in each resonance band. `resonances` are (frequency_hz, bandwidth_hz) pairs
    in Hz, as in `TargetProfile.acoustic_resonances`; the band of a pair is its frequency
    less and plus half its bandwidth."""
    index = sequence_index(seq)
    if not (index.gx.any() or index.gy.any() or index.gz.any()):
        empty = np.zeros(0)
        return GradientSpectrum(NO_GRADIENTS, resonances, empty, {}, empty, ())
    sampler = GradientSampler(seq, index)

    # The file's raster ([DEFINITIONS]): `Sequence.read` does not change `seq.system`.
    dt = seq.grad_raster_time
    nwin = round(FFT_WINDOW_S / dt)
    pad = nwin // 2
    # Python's `sum` is compensated (Python 3.12), so this total can differ from
    # `index.end_s`, the sequential sum, by one sample. The oracle
    # (tests/oracles/grad_spectrum.py) has the same line, and the oracle tests
    # compare the two. Do not change it to `index.end_s`.
    nt = math.ceil(sum(seq.block_durations.values()) / dt)
    to_mt = 1e3 / seq.system.gamma  # Hz/m to mT/m

    # The padded waveform has n samples: pad zeros, the nt gradient samples, pad zeros.
    # scipy's spectrogram does not pad, so window j covers samples [j * hop, j * hop + nwin).
    n = nt + 2 * pad  # n >= nwin: after the NO_GRADIENTS return, nt >= 1
    hop = nwin - nwin // 2
    num_windows = (n - nwin) // hop + 1

    axes_max: dict[str, np.ndarray] = {}
    rss_max = None
    keep = None  # the frequencies to keep: the same for each chunk
    for first in range(0, num_windows, CHUNK_WINDOWS):
        last = min(first + CHUNK_WINDOWS, num_windows)
        # The samples of windows first to last - 1.
        start = first * hop
        stop = (last - 1) * hop + nwin
        rss_sq = 0.0
        for axis in "xyz":
            freq, sxx = _chunk_spectrogram(
                sampler, f"g{axis}", start, stop, pad, nt, dt, nwin, to_mt
            )
            if keep is None:
                keep = freq <= MAX_FREQUENCY_HZ + 1e-6
            sxx = sxx[keep]
            chunk_max = sxx.max(axis=1)
            axes_max[axis] = (
                chunk_max if axis not in axes_max else np.maximum(axes_max[axis], chunk_max)
            )
            rss_sq = rss_sq + sxx**2
        chunk_rss = np.sqrt(rss_sq).max(axis=1)
        rss_max = chunk_rss if rss_max is None else np.maximum(rss_max, chunk_rss)
    freq = freq[keep]
    return GradientSpectrum(
        None, resonances, freq, axes_max, rss_max, _band_peaks(freq, rss_max, resonances)
    )


def _chunk_spectrogram(sampler, axis, start, stop, pad, nt, dt, nwin, to_mt):
    """The frequencies and the magnitude spectrogram of samples [start, stop) of one
    axis's padded waveform, with the arguments of pypulseq's
    `calculate_gradient_spectrum`. `axis` is "gx", "gy" or "gz" (`sampling.GradientSampler`'s
    axis names); `sampler` gives the axis's waveform (Hz/m), 0 before the first event and
    after the last one, so an axis with no gradient gives an all-zero chunk."""
    w = np.zeros(stop - start)
    # Sequence sample i is at (i + 0.5) * dt, and is padded sample i + pad.
    lo, hi = max(start - pad, 0), min(stop - pad, nt)
    if hi > lo:
        t = (np.arange(lo, hi) + 0.5) * dt
        w[lo + pad - start : hi + pad - start] = sampler.sample(axis, t) * to_mt
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
    freq: np.ndarray, rss: np.ndarray, resonances: tuple[tuple[float, float], ...]
) -> tuple[BandPeak, ...]:
    """The largest RSS value in each resonance band that has a frequency bin."""
    peak = float(rss.max())
    band_peaks = []
    for r in resonances:
        frequency_hz, bandwidth_hz = r
        low_hz = frequency_hz - bandwidth_hz / 2
        high_hz = frequency_hz + bandwidth_hz / 2
        inside = np.flatnonzero((freq >= low_hz) & (freq <= high_hz))
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
