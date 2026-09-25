import numpy as np
import pypulseq as pp
import pytest
from pypulseq.utils.safe_pns_prediction import safe_example_hw
from synthetic import SYSTEM, block_pulse, empty_sequence, spin_echo_sequence

from pulseq_reports import pns


@pytest.fixture
def write_gradient_asc(tmp_path):
    """A function that writes a gradient .asc file with the PNS parameters of pypulseq's
    example hardware, with the stimulation limits and thresholds multiplied by
    `limit_scale`, and returns its path. The real .asc files are confidential.

    With `split`, it writes the layout of a scanner file: an `ASCCONV` block with CRLF line
    ends and `asCOMP[0].tName`, which includes a `_GSWD_SAFETY.asc` file with the SAFE
    parameters under `GradPatSup.Phys.PNS`."""

    def write(limit_scale: float = 1.0, name: str = "MP_GPA_TEST", split: bool = False):
        hw = safe_example_hw()
        prefix = "GradPatSup.Phys.PNS." if split else ""
        pns_lines, scale_lines = [], []
        for axis in "xyz":
            a, suffix = getattr(hw, axis), axis.upper()
            pns_lines += [
                f"{prefix}flGSWDTau{suffix}[{i}] = {getattr(a, f'tau{i + 1}')!r}" for i in range(3)
            ]
            pns_lines += [
                f"{prefix}flGSWDA{suffix}[{i}] = {getattr(a, f'a{i + 1}')!r}" for i in range(3)
            ]
            pns_lines += [
                f"{prefix}flGSWDStimulationLimit{suffix} = {a.stim_limit * limit_scale!r}",
                f"{prefix}flGSWDStimulationThreshold{suffix} = {a.stim_thresh * limit_scale!r}",
            ]
            scale_lines.append(
                f"asGPAParameters[0].sGCParameters.flGScaleFactor{suffix} = {a.g_scale!r}"
            )
        path = tmp_path / f"{name}_{limit_scale:g}.asc"
        if not split:
            path.write_text(
                "\n".join([f'asCOMP.tName = "{name}"', *pns_lines, *scale_lines]) + "\n"
            )
            return path

        def ascconv(lines):
            block = ["### ASCCONV BEGIN @Checksum=mp2:0 ###", "", *lines, "", "### ASCCONV END ###"]
            return "\r\n".join(block) + "\r\n"

        safety = path.with_name(f"{path.stem}_GSWD_SAFETY.asc")
        safety.write_bytes(ascconv(pns_lines).encode())
        main = [f'asCOMP[0].tName = "{name}"', *scale_lines, f"$INCLUDE {safety.name}"]
        path.write_bytes(ascconv(main).encode())
        return path

    return write


@pytest.fixture(scope="module")
def default_seq():
    return spin_echo_sequence()


@pytest.fixture(scope="module")
def example(default_seq):
    return pns.pns_prediction(default_seq)


def test_example_hardware_for_spin_echo(example):
    assert example.reason is None
    assert example.hardware == pns.EXAMPLE_HARDWARE
    assert example.asc_file is None
    assert list(example.axes) == ["x", "y", "z"]
    assert 0 < example.peak < 1
    assert max(example.axis_peaks, key=example.axis_peaks.get) == "y"  # the crushers
    for values in example.axes.values():
        assert values.shape == example.norm.shape
        assert np.all(example.norm >= values - 1e-12)
    assert example.t_s[0] <= example.peak_time_s <= example.t_s[-1]


def test_asc_file_with_the_example_parameters(default_seq, example, write_gradient_asc):
    path = write_gradient_asc()
    p = pns.pns_prediction(default_seq, path)
    assert p.reason is None
    assert p.hardware == "MP_GPA_TEST"
    assert p.asc_file == path.name
    np.testing.assert_allclose(p.norm, example.norm, rtol=1e-9)


def test_asc_file_that_includes_the_pns_parameters(default_seq, example, write_gradient_asc):
    path = write_gradient_asc(split=True)
    p = pns.pns_prediction(default_seq, path)
    assert p.reason is None
    assert p.hardware == "MP_GPA_TEST"
    assert p.asc_file == path.name
    np.testing.assert_allclose(p.norm, example.norm, rtol=1e-9)


def test_asc_file_with_a_missing_include(write_gradient_asc):
    path = write_gradient_asc(split=True)
    safety = path.with_name(f"{path.stem}_GSWD_SAFETY.asc")
    safety.unlink()
    with pytest.raises(FileNotFoundError, match=f"{path.name} includes {safety.name}"):
        pns.read_gradient_asc(path)


def test_included_fields_replace_fields_with_the_same_name(tmp_path):
    (tmp_path / "inc.asc").write_text('a.b[1] = 3\nc = "new"\n')
    main = tmp_path / "main.asc"
    main.write_text('a.b[0] = 1\na.b[1] = 2\nc = "old"\n$INCLUDE inc.asc\n')
    assert pns.read_gradient_asc(main) == {"a": {"b": {0: 1, 1: 3}}, "c": "new"}


def test_hardware_name():
    assert pns.hardware_name({"asCOMP": {0: {"tName": "GPAK2309"}}}) == "GPAK2309"
    assert pns.hardware_name({"asCOMP": {"tName": "MP_GPA_TEST"}}) == "MP_GPA_TEST"
    assert pns.hardware_name({}) == "unknown"


def test_prediction_scales_with_the_stimulation_limit(default_seq, example, write_gradient_asc):
    p = pns.pns_prediction(default_seq, write_gradient_asc(limit_scale=0.1))
    assert p.peak == pytest.approx(10 * example.peak, rel=1e-9)
    assert p.peak > 1


def test_peak_time_is_the_first_sample_at_the_peak_within_rounding():
    t = np.arange(5) * 1e-3
    norm = np.array([0.0, 0.5 * (1 - 1e-12), 0.1, 0.5, 0.2])
    p = pns.PnsPrediction(None, pns.EXAMPLE_HARDWARE, None, t, norm)
    assert p.peak == 0.5
    assert p.peak_time_s == pytest.approx(1e-3)
    # A real increase, larger than the tolerance, moves the peak time.
    norm[3] = 0.5 * (1 + 1e-3)
    assert p.peak_time_s == pytest.approx(3e-3)


def test_no_gradients():
    p = pns.pns_prediction(empty_sequence())
    assert p.reason == pns.NO_GRADIENTS
    assert p.hardware == pns.EXAMPLE_HARDWARE
    assert p.peak == 0
    assert p.peak_time_s is None


def test_no_gradients_with_rf_and_adc():
    seq = pp.Sequence(SYSTEM)
    seq.add_block(block_pulse("excitation", np.pi / 2))
    seq.add_block(
        pp.make_adc(num_samples=64, dwell=20e-6, delay=SYSTEM.adc_dead_time, system=SYSTEM)
    )
    assert pns.pns_prediction(seq).reason == pns.NO_GRADIENTS


@pytest.mark.parametrize("channel", ["x", "y", "z"])
def test_a_gradient_on_one_axis_has_a_prediction(channel):
    seq = pp.Sequence(SYSTEM)
    seq.add_block(pp.make_delay(1e-3))
    seq.add_block(pp.make_trapezoid(channel=channel, area=1000, system=SYSTEM))
    p = pns.pns_prediction(seq)
    assert p.reason is None
    assert p.peak > 0


def test_prediction_builds_the_gradients_one_time(monkeypatch):
    seq = spin_echo_sequence()
    calls = []
    get_gradients = seq.get_gradients

    def counted(*args, **kwargs):
        calls.append(1)
        return get_gradients(*args, **kwargs)

    monkeypatch.setattr(seq, "get_gradients", counted)
    pns.pns_prediction(seq)
    assert len(calls) == 1  # the one in calculate_pns


@pytest.mark.parametrize("use_block_cache", [True, False])
def test_prediction_keeps_no_blocks_and_gives_back_the_cache_setting(use_block_cache):
    seq = spin_echo_sequence()
    seq.use_block_cache = use_block_cache
    seq.block_cache.clear()
    pns.pns_prediction(seq)
    assert seq.use_block_cache is use_block_cache
    assert not seq.block_cache


def test_prediction_gives_back_the_cache_setting_after_an_error(monkeypatch):
    seq = spin_echo_sequence()
    seq.use_block_cache = True
    seen = []

    def fail(*args, **kwargs):
        seen.append(seq.use_block_cache)
        raise RuntimeError("calculate_pns failed")

    monkeypatch.setattr(seq, "calculate_pns", fail)
    with pytest.raises(RuntimeError, match="calculate_pns failed"):
        pns.pns_prediction(seq)
    assert seen == [False]
    assert seq.use_block_cache is True


def _three_trs(peak_tr: int) -> pp.Sequence:
    """Three 50 ms TRs on the synthetic system, each a Gy trapezoid and a delay. TR
    `peak_tr` has the fastest slew (0.1 ms rise/fall instead of 0.4 ms), so its PNS is the
    highest."""
    seq = pp.Sequence(SYSTEM)
    for i in range(3):
        g = pp.make_trapezoid(
            channel="y",
            amplitude=0.3 * SYSTEM.max_grad,
            rise_time=0.1e-3 if i == peak_tr else 0.4e-3,
            flat_time=2e-3,
            system=SYSTEM,
        )
        seq.add_block(g)
        seq.add_block(pp.make_delay(50e-3 - pp.calc_duration(g)))
    seq.set_definition("TR", 50e-3)
    return seq


@pytest.mark.parametrize("peak_tr", [0, 1, 2])
def test_peak_tr_window_finds_the_tr_with_the_peak(peak_tr):
    seq = _three_trs(peak_tr)
    p = pns.pns_prediction(seq)
    window = pns.peak_tr_window(seq, p.peak_time_s)
    lo, hi = 50e-3 * peak_tr, 50e-3 * (peak_tr + 1)
    assert window == pytest.approx((lo, hi))
    assert lo <= p.peak_time_s <= hi


def test_peak_tr_window_without_a_tr_definition_is_none():
    seq = _three_trs(1)
    del seq.definitions["TR"]
    p = pns.pns_prediction(seq)
    assert pns.peak_tr_window(seq, p.peak_time_s) is None


def test_peak_tr_window_with_one_tr_is_none():
    seq = spin_echo_sequence()  # much shorter than a TR, and no TR definition
    seq.set_definition("TR", seq.duration()[0])
    assert pns.peak_tr_window(seq, 0.0) is None


def test_peak_tr_window_without_a_peak_time_is_none():
    seq = _three_trs(1)
    assert pns.peak_tr_window(seq, None) is None
