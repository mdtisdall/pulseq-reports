import math

import numpy as np
import pypulseq as pp
import pytest
from oracles import grad_spectrum as oracle
from synthetic import (
    SYSTEM,
    arbitrary_gradient_sequence,
    empty_sequence,
    gre_sequence,
    load_diagram_scale,
    spin_echo_sequence,
)

from pulseq_reports import grad_spectrum

RESONANCES = ((590.0, 100.0), (1140.0, 220.0))  # (frequency_hz, bandwidth_hz)

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


def test_spin_echo_spectrum():
    s = grad_spectrum.gradient_spectrum(spin_echo_sequence(), resonances=RESONANCES)
    assert s.reason is None
    assert s.frequency_hz[0] == 0
    assert s.frequency_hz[-1] == pytest.approx(grad_spectrum.MAX_FREQUENCY_HZ)
    assert list(s.axes) == ["x", "y", "z"]
    for axis in ("x", "y"):
        assert s.axes[axis].max() > 0
    for spectrum in s.axes.values():
        assert spectrum.shape == s.frequency_hz.shape
        assert np.all(s.rss >= spectrum - 1e-12)
    assert [b.resonance for b in s.band_peaks] == list(RESONANCES)
    for b in s.band_peaks:
        frequency_hz, bandwidth_hz = b.resonance
        assert frequency_hz - bandwidth_hz / 2 <= b.frequency_hz <= frequency_hz + bandwidth_hz / 2
        assert 0 <= b.relative <= 1


def test_sine_in_the_first_band():
    s = grad_spectrum.gradient_spectrum(_sine_sequence(600), resonances=RESONANCES)
    assert s.frequency_hz[np.argmax(s.rss)] == pytest.approx(600)
    assert s.rss.max() == pytest.approx(SINE_1MT_PEAK, rel=0.01)
    first, second = s.band_peaks
    assert first.relative == pytest.approx(1)
    # The windows that hold the abrupt start and end of the sine leak about 1% into the
    # second band.
    assert second.relative < 0.05


def test_sine_outside_the_bands():
    s = grad_spectrum.gradient_spectrum(_sine_sequence(300), resonances=RESONANCES)
    assert all(b.relative < 0.05 for b in s.band_peaks)  # about 2% from the start and end


def test_short_sequence_is_padded_to_one_window():
    s = grad_spectrum.gradient_spectrum(_sine_sequence(600, duration_s=0.02))
    assert s.reason is None
    assert abs(s.frequency_hz[np.argmax(s.rss)] - 600) <= 20


def test_gradients_at_the_end_are_not_attenuated():
    # 60 ms of sine after 440 ms of nothing: the last sample is at the sequence end.
    s = grad_spectrum.gradient_spectrum(_sine_sequence(600, duration_s=0.06, delay_s=0.44))
    assert s.rss.max() == pytest.approx(SINE_1MT_PEAK, rel=0.02)


def test_without_resonances_there_are_no_band_peaks():
    s = grad_spectrum.gradient_spectrum(spin_echo_sequence())
    assert s.reason is None
    assert s.resonances == ()
    assert s.band_peaks == ()


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
    whole = grad_spectrum.gradient_spectrum(seq, resonances=RESONANCES)
    monkeypatch.setattr(grad_spectrum, "CHUNK_WINDOWS", 4)
    chunked = grad_spectrum.gradient_spectrum(seq, resonances=RESONANCES)
    _assert_same_spectrum(chunked, whole)


def _assert_matches_oracle(got: grad_spectrum.GradientSpectrum, ref, tol: float = 1e-12) -> None:
    """`got` (this module, the sampler-based implementation) equals `ref`
    (`tests/oracles/grad_spectrum.py`, the implementation before phase 5, which samples
    through `Sequence.get_gradients()`) within the tolerance of section 3.5, item 2 of
    `docs/plans/cards-at-scale.md`: the sampler builds the waveform from each block's own
    corner points and `numpy.interp`, in a different order of float operations than
    `Sequence.get_gradients()`'s one whole-axis `scipy.interpolate.PPoly`, so the tests
    allow a relative difference of 1e-12, or an absolute difference of 1e-12 times the
    largest value of the same array. `tol` replaces 1e-12 for a long sequence (see
    `test_matches_oracle_on_long_sequences`).
    """
    assert got.reason == ref.reason
    if ref.reason is not None:
        return
    np.testing.assert_array_equal(got.frequency_hz, ref.frequency_hz)
    assert list(got.axes) == list(ref.axes)
    for axis in ref.axes:
        r = ref.axes[axis]
        peak = float(r.max()) if r.size else 0.0
        np.testing.assert_allclose(got.axes[axis], r, rtol=tol, atol=tol * peak)
    rss_peak = float(ref.rss.max()) if ref.rss.size else 0.0
    np.testing.assert_allclose(got.rss, ref.rss, rtol=tol, atol=tol * rss_peak)
    assert len(got.band_peaks) == len(ref.band_peaks)
    for g, r in zip(got.band_peaks, ref.band_peaks):
        assert g.resonance == r.resonance
        assert g.peak == pytest.approx(r.peak, rel=tol, abs=tol * rss_peak)
        assert g.frequency_hz == pytest.approx(r.frequency_hz, rel=tol, abs=tol)
        assert g.relative == pytest.approx(r.relative, rel=tol, abs=tol)


@pytest.mark.parametrize(
    "seq",
    [
        spin_echo_sequence(),
        gre_sequence(),
        arbitrary_gradient_sequence(),
        empty_sequence(),
        _sine_sequence(600),
    ],
    ids=["spin_echo", "gre", "arbitrary_gradient", "empty", "sine"],
)
def test_matches_oracle_on_synthetic_sequences(seq):
    _assert_matches_oracle(
        grad_spectrum.gradient_spectrum(seq, resonances=RESONANCES),
        oracle.gradient_spectrum(seq, RESONANCES),
    )


@pytest.mark.parametrize("case", ["repeating", "worst"])
def test_matches_oracle_on_long_sequences(case):
    """The builders of `scripts/diagram_scale.py` at 10^4 blocks (task 5.3 of
    docs/plans/cards-at-scale.md). The tolerance is `1e-12 * max(1, duration in s)`, not
    1e-12 (the user, 2026-09-28). Both implementations place each gradient corner at an
    absolute time with float rounding, in a different order of additions: the sampler
    adds `(block start + delay) + offset`, and pypulseq's `get_gradients()` adds the
    segment durations one at a time. The rounding of an absolute time grows with the
    time, and a gradient ramp turns it into a value difference, so the difference grows
    with the duration of the sequence. Measured: 2.5e-12 of the peak at 10^4 repeating
    blocks (12 s), 3.6e-12 at 10^5 blocks. Neither is more correct than the other."""
    diagram_scale = load_diagram_scale()
    n_trs = 10_000 // diagram_scale.TR_BLOCKS
    build = diagram_scale.build_repeating if case == "repeating" else diagram_scale.build_worst
    seq = build(n_trs)
    tol = 1e-12 * max(1.0, seq.duration()[0])
    _assert_matches_oracle(
        grad_spectrum.gradient_spectrum(seq, resonances=RESONANCES),
        oracle.gradient_spectrum(seq, RESONANCES),
        tol=tol,
    )
