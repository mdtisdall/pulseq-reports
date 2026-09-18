import math

import numpy as np
import pypulseq as pp
import pytest
from synthetic import SYSTEM, gre_sequence, spin_echo_sequence

from pulseq_reports import grad_spectrum

# A Hann window's amplitude spectral density of a 1 mT/m sine on a frequency bin:
# A/2 * sum(w) / sqrt(fs * sum(w^2)), with 5000 samples at 100 kHz.
SINE_1MT_PEAK = 0.5 * 0.5 / math.sqrt(1e5 * 0.375 / 5000)


def _sine_sequence(frequency_hz: float, duration_s: float = 0.5, delay_s: float = 0.0):
    seq = pp.Sequence(SYSTEM)
    t = np.arange(round(duration_s / SYSTEM.grad_raster_time)) * SYSTEM.grad_raster_time
    waveform = 1e-3 * SYSTEM.gamma * np.sin(2 * np.pi * frequency_hz * t)  # 1 mT/m
    seq.add_block(
        pp.make_arbitrary_grad("x", waveform, first=0, last=0, delay=delay_s, system=SYSTEM)
    )
    return seq


def _assert_same_spectrum(a, b):
    np.testing.assert_array_equal(a.frequency_hz, b.frequency_hz)
    assert list(a.axes) == list(b.axes)
    for axis in a.axes:
        np.testing.assert_allclose(a.axes[axis], b.axes[axis], rtol=1e-12, atol=0)
    np.testing.assert_allclose(a.rss, b.rss, rtol=1e-12, atol=0)
    assert [(p.resonance, p.frequency_hz) for p in a.band_peaks] == [
        (p.resonance, p.frequency_hz) for p in b.band_peaks
    ]


def test_prisma_as82_resonances():
    bands = [(r.low_hz, r.high_hz) for r in grad_spectrum.PRISMA_AS82_RESONANCES]
    assert bands == [(540, 640), (1030, 1250)]


def test_spin_echo_spectrum():
    s = grad_spectrum.gradient_spectrum(spin_echo_sequence())
    assert s.reason is None
    assert s.frequency_hz[0] == 0
    assert s.frequency_hz[-1] == pytest.approx(grad_spectrum.MAX_FREQUENCY_HZ)
    assert list(s.axes) == ["x", "y", "z"]
    for axis in ("x", "y"):
        assert s.axes[axis].max() > 0
    for spectrum in s.axes.values():
        assert spectrum.shape == s.frequency_hz.shape
        assert np.all(s.rss >= spectrum - 1e-12)
    assert [b.resonance for b in s.band_peaks] == list(grad_spectrum.PRISMA_AS82_RESONANCES)
    for b in s.band_peaks:
        assert b.resonance.low_hz <= b.frequency_hz <= b.resonance.high_hz
        assert 0 <= b.relative <= 1


def test_sine_in_the_first_band():
    s = grad_spectrum.gradient_spectrum(_sine_sequence(600))
    assert s.frequency_hz[np.argmax(s.rss)] == pytest.approx(600)
    assert s.rss.max() == pytest.approx(SINE_1MT_PEAK, rel=0.01)
    first, second = s.band_peaks
    assert first.relative == pytest.approx(1)
    # The windows that hold the abrupt start and end of the sine leak about 1% into the
    # second band.
    assert second.relative < 0.05


def test_sine_outside_the_bands():
    s = grad_spectrum.gradient_spectrum(_sine_sequence(300))
    assert all(b.relative < 0.05 for b in s.band_peaks)  # about 2% from the start and end


def test_short_sequence_is_padded_to_one_window():
    s = grad_spectrum.gradient_spectrum(_sine_sequence(600, duration_s=0.02))
    assert s.reason is None
    assert abs(s.frequency_hz[np.argmax(s.rss)] - 600) <= 20


def test_gradients_at_the_end_are_not_attenuated():
    # 60 ms of sine after 440 ms of nothing: the last sample is at the sequence end.
    s = grad_spectrum.gradient_spectrum(_sine_sequence(600, duration_s=0.06, delay_s=0.44))
    assert s.rss.max() == pytest.approx(SINE_1MT_PEAK, rel=0.02)


def test_no_gradients():
    seq = pp.Sequence(SYSTEM)
    seq.add_block(
        pp.make_block_pulse(
            flip_angle=math.pi / 2, duration=1e-3, delay=SYSTEM.rf_dead_time, system=SYSTEM
        )
    )
    s = grad_spectrum.gradient_spectrum(seq)
    assert s.reason == grad_spectrum.NO_GRADIENTS
    assert s.band_peaks == ()


def test_chunks_give_the_same_spectrum_as_one_chunk(monkeypatch):
    # 30 TRs of 20 ms: 600 ms, 25 windows of 50 ms with a 25 ms hop, so chunks of 4
    # windows make 7 chunks, and the last chunk is shorter than the others.
    seq = gre_sequence(num_trs=30)
    monkeypatch.setattr(grad_spectrum, "CHUNK_WINDOWS", 1_000_000)
    whole = grad_spectrum.gradient_spectrum(seq)
    monkeypatch.setattr(grad_spectrum, "CHUNK_WINDOWS", 4)
    chunked = grad_spectrum.gradient_spectrum(seq)
    _assert_same_spectrum(chunked, whole)


def test_combine_is_the_maximum_over_the_files():
    in_band = grad_spectrum.gradient_spectrum(_sine_sequence(600, duration_s=0.2))
    outside = grad_spectrum.gradient_spectrum(_sine_sequence(300, duration_s=0.2))
    combined = grad_spectrum.combine([in_band, outside])
    assert combined.reason is None
    np.testing.assert_array_equal(combined.frequency_hz, in_band.frequency_hz)
    for axis in "xyz":
        np.testing.assert_array_equal(
            combined.axes[axis], np.maximum(in_band.axes[axis], outside.axes[axis])
        )
    np.testing.assert_array_equal(combined.rss, np.maximum(in_band.rss, outside.rss))
    # The band peaks are recomputed from the combined RSS: the 600 Hz sine is in the
    # first band, and both sines have about the same peak.
    first, _ = combined.band_peaks
    assert first.frequency_hz == pytest.approx(600)
    assert first.peak == pytest.approx(in_band.band_peaks[0].peak)
    assert first.relative == pytest.approx(first.peak / combined.rss.max())


def test_combine_skips_files_without_gradients():
    empty = pp.Sequence(SYSTEM)
    empty.add_block(pp.make_delay(1e-3))
    no_gradients = grad_spectrum.gradient_spectrum(empty)
    sine = grad_spectrum.gradient_spectrum(_sine_sequence(600, duration_s=0.1))
    _assert_same_spectrum(grad_spectrum.combine([no_gradients, sine]), sine)
    assert grad_spectrum.combine([no_gradients]).reason == grad_spectrum.NO_GRADIENTS
    with pytest.raises(ValueError, match="at least one"):
        grad_spectrum.combine([])
