import numpy as np
import pypulseq as pp
import pytest
from pypulseq.utils.safe_pns_prediction import safe_example_hw
from synthetic import SYSTEM, block_pulse, empty_sequence, spin_echo_sequence

from pulseq_reports import pns
from pulseq_reports import pns_levels as pns_levels_module
from pulseq_reports.cards.diagram import diagram_card
from pulseq_reports.cards.pns import pns_data
from pulseq_reports.pns import pns_levels_for
from pulseq_reports.waveforms import full_window


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


def test_example_hardware_for_spin_echo(example, default_seq):
    """The summary equals `pns_levels.pns_levels` of the same sequence and hardware
    (task 4.4 of `docs/plans/diagram-lanes.md`: `PnsPrediction` is now built from
    `PnsLevels`)."""
    ref = pns_levels_module.pns_levels(default_seq)
    assert example.reason is None
    assert example.hardware == pns.EXAMPLE_HARDWARE
    assert example.asc_file is None
    assert list(example.axis_peaks) == ["x", "y", "z"]
    assert 0 < example.peak < 1
    assert max(example.axis_peaks, key=example.axis_peaks.get) == "y"  # the crushers
    assert example.peak == ref.peak
    assert example.peak_time_s == ref.peak_time_s
    assert example.axis_peaks == ref.axis_peaks


def test_asc_file_with_the_example_parameters(default_seq, example, write_gradient_asc):
    path = write_gradient_asc()
    p = pns.pns_prediction(default_seq, path)
    assert p.reason is None
    assert p.hardware == "MP_GPA_TEST"
    assert p.asc_file == path.name
    assert p.peak == pytest.approx(example.peak, rel=1e-9)
    assert p.peak_time_s == pytest.approx(example.peak_time_s, rel=1e-9)
    for axis in "xyz":
        assert p.axis_peaks[axis] == pytest.approx(example.axis_peaks[axis], rel=1e-9)


def test_asc_file_that_includes_the_pns_parameters(default_seq, example, write_gradient_asc):
    path = write_gradient_asc(split=True)
    p = pns.pns_prediction(default_seq, path)
    assert p.reason is None
    assert p.hardware == "MP_GPA_TEST"
    assert p.asc_file == path.name
    assert p.peak == pytest.approx(example.peak, rel=1e-9)
    assert p.peak_time_s == pytest.approx(example.peak_time_s, rel=1e-9)
    for axis in "xyz":
        assert p.axis_peaks[axis] == pytest.approx(example.axis_peaks[axis], rel=1e-9)


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


def test_prediction_does_not_build_the_gradients_for_an_on_raster_sequence(monkeypatch):
    """`pns_prediction` (`pns_levels.pns_levels`) samples an on-raster sequence with
    `GradientSampler.block_samples`, not `seq.get_gradients()` (unlike the old
    `seq.calculate_pns`-based prediction), so `get_gradients` is never called."""
    seq = spin_echo_sequence()
    calls = []
    get_gradients = seq.get_gradients

    def counted(*args, **kwargs):
        calls.append(1)
        return get_gradients(*args, **kwargs)

    monkeypatch.setattr(seq, "get_gradients", counted)
    pns.pns_prediction(seq)
    assert calls == []


@pytest.mark.parametrize("use_block_cache", [True, False])
def test_prediction_keeps_no_blocks_and_gives_back_the_cache_setting(use_block_cache):
    seq = spin_echo_sequence()
    seq.use_block_cache = use_block_cache
    seq.block_cache.clear()
    pns.pns_prediction(seq)
    assert seq.use_block_cache is use_block_cache
    assert not seq.block_cache


def test_prediction_propagates_an_error_and_keeps_the_cache_setting(monkeypatch):
    """An error deep inside the SAFE model (the pinned fork's chunk function)
    propagates out of `pns_prediction`, and the sequence's block-cache setting and
    contents are unaffected: the block cache is only ever touched inside
    `seq_index.block_cache_off`'s own `try`/`finally`, which has already restored it
    by the time the chunk function runs (`GradientSampler` is built first)."""
    seq = spin_echo_sequence()
    seq.use_block_cache = True

    def fail(*args, **kwargs):
        raise RuntimeError("chunk failed")

    monkeypatch.setattr(pns_levels_module, "_safe_gwf_to_pns_chunk", fail)
    with pytest.raises(RuntimeError, match="chunk failed"):
        pns.pns_prediction(seq)
    assert seq.use_block_cache is True
    assert not seq.block_cache


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


def _count_pns_levels_calls(monkeypatch) -> list:
    """Patches `pns_levels.pns_levels` (as `pns.pns_levels_for` imports it, one time for
    each call) with a wrapper that records one entry for each call, and returns the
    list. `pns.pns_levels_for` looks up the current module attribute on every call (a
    local import inside the function, to avoid a circular import with `pns_levels.py`),
    so patching the module attribute here reaches it."""
    calls: list = []
    original = pns_levels_module.pns_levels

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(pns_levels_module, "pns_levels", counted)
    return calls


def test_pns_levels_for_shares_one_computation_with_the_pns_card_and_the_diagram(
    monkeypatch,
):
    """The PNS summary card (`cards.pns.pns_data`) and the diagram's PNS lane
    (`cards.diagram.diagram_card(..., pns=True)`) both read `pns.pns_levels_for`, so
    for one sequence the SAFE model runs once, not twice (`docs/plans/diagram-lanes.md`,
    section 4.6). Adding a block changes the sequence, so the next call recomputes."""
    calls = _count_pns_levels_calls(monkeypatch)
    seq = spin_echo_sequence()

    pns_data(seq)
    diagram_card(seq, [full_window(seq)], pns=True)
    assert len(calls) == 1

    seq.add_block(pp.make_delay(1e-3))
    pns_data(seq)
    assert len(calls) == 2


def test_pns_levels_for_recomputes_for_a_different_asc_path(monkeypatch, write_gradient_asc):
    """`pns_levels_for` keeps one result for each (sequence, asc path): calling it again
    for the same sequence with a different `.asc` file recomputes, and going back to the
    first path recomputes again (the kept result is only the most recent one)."""
    calls = _count_pns_levels_calls(monkeypatch)
    seq = spin_echo_sequence()
    path_a = write_gradient_asc(name="MP_GPA_A")
    path_b = write_gradient_asc(name="MP_GPA_B")

    pns_levels_for(seq, path_a)
    assert len(calls) == 1
    pns_levels_for(seq, path_a)  # same sequence, same path: cached
    assert len(calls) == 1
    pns_levels_for(seq, path_b)  # a different path: recomputes
    assert len(calls) == 2
    pns_levels_for(seq, path_a)  # back to path_a: recomputes again (not a 2-entry cache)
    assert len(calls) == 3
