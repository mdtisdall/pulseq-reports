from pathlib import Path

import numpy as np
import pytest
from pulseq_analysis.series import decode_array
from pulseq_checks import read_profile, run_checks
from synthetic import empty_sequence, gre_sequence, spin_echo_sequence

from pulseq_reports import page
from pulseq_reports.cards.diagram import diagram_card
from pulseq_reports.diagram_data import diagram_tables, lane_meta
from pulseq_reports.markup import zoom_controls
from pulseq_reports.targets import report_targets
from pulseq_reports.waveforms import TimeWindow, duration_s, first_adc_window, full_window

PROFILES = Path(__file__).parent / "profiles"
A = read_profile(PROFILES / "example_a.toml")
B = read_profile(PROFILES / "example_b.toml")
C = read_profile(PROFILES / "example_c.toml")  # a negative gamma


def _matrix(seq, profiles, tmp_path):
    """The result matrix of the analysis `pns.safe.levels` for `profiles`. One target runs on
    the sequence object, several on a file in `tmp_path`."""
    if len(profiles) == 1:
        sequence = seq
    else:
        sequence = str(tmp_path / "seq.seq")
        seq.write(sequence)
    return run_checks(sequence, list(profiles), select=[], analyses=["pns.safe.levels"])


def _pns_card(seq, profiles, tmp_path, **kwargs):
    return diagram_card(
        seq,
        [full_window(seq)],
        pns_lane=True,
        targets=report_targets(profiles),
        check_results=_matrix(seq, profiles, tmp_path),
        **kwargs,
    )


def test_data_has_format_3_with_file_and_window_keys():
    seq = spin_echo_sequence()
    card = diagram_card(seq, [first_adc_window(seq), full_window(seq)])
    data = card.data

    assert set(data) == {"format", "file", "windows"}
    assert data["format"] == 3
    file_entry = data["file"]
    assert set(file_entry) == {"duration_s", "num_blocks", "lanes", "tables"}
    assert file_entry["lanes"] == lane_meta(seq)
    assert file_entry["duration_s"] == duration_s(seq)
    assert file_entry["num_blocks"] == len(seq.block_events)
    for name, entry in file_entry["tables"].items():
        assert set(entry) == {"dtype", "length", "data"}, name

    assert len(data["windows"]) == 2
    for window in data["windows"]:
        assert set(window) == {"label", "view_ms"}


def test_tables_decode_to_diagram_tables():
    seq = gre_sequence(num_trs=3)
    card = diagram_card(seq, [full_window(seq)])
    file_entry = card.data["file"]

    decoded = {name: decode_array(d) for name, d in file_entry["tables"].items()}
    expected = diagram_tables(seq)
    assert set(decoded) == set(expected)
    for key in expected:
        assert decoded[key].dtype == expected[key].dtype, key
        assert np.array_equal(decoded[key], expected[key]), key


def test_ids_start_with_the_given_card_id():
    seq = spin_echo_sequence()
    card = diagram_card(seq, [full_window(seq)], card_id="my-diagram")
    assert card.id == "my-diagram"
    assert 'id="my-diagram-diagram"' in card.body_html
    assert 'id="my-diagram-chart"' in card.body_html
    assert 'id="my-diagram-tip"' in card.body_html
    assert 'id="my-diagram-mode"' in card.body_html


def test_no_windows_raises():
    with pytest.raises(ValueError):
        diagram_card(spin_echo_sequence(), [])


@pytest.mark.parametrize(
    "window",
    [
        TimeWindow("past the end", 0.0, 1e6),
        TimeWindow("before the start", -0.5, 0.001),
    ],
    ids=["past_the_end", "before_the_start"],
)
def test_a_window_outside_the_sequence_raises(window):
    with pytest.raises(ValueError, match=window.label):
        diagram_card(spin_echo_sequence(), [window])


def test_end_before_start_raises():
    bad = TimeWindow("bad", 1.0, 0.5)
    with pytest.raises(ValueError, match="bad"):
        diagram_card(spin_echo_sequence(), [bad])


def test_render_page_includes_diagram_and_seq_lanes_scripts_once():
    seq = spin_echo_sequence()
    card = diagram_card(seq, [full_window(seq)])
    result = page.render_page("t", "s", [card])
    assert result.count('PulseqReport.registerCard("diagram"') == 1
    assert result.count("const SeqLanes") == 1


def test_no_envelope_note_and_status_line_is_present():
    seq = spin_echo_sequence()
    card = diagram_card(seq, [full_window(seq)])
    assert "too many" not in card.body_html
    assert "envelope" not in card.body_html
    assert 'id="diagram-mode"' in card.body_html
    assert 'aria-live="polite"' in card.body_html


def test_diagram_card_has_zoom_controls_directly_before_its_chart():
    """Adapted from vb-pulseq's `test_report_has_zoom_controls_on_each_line_chart`."""
    seq = spin_echo_sequence()
    card = diagram_card(seq, [full_window(seq)], card_id="diagram")
    result = page.render_page("t", "s", [card])

    controls = zoom_controls("diagram-diagram")
    assert result.count(controls) == 1
    after = result[result.index(controls) + len(controls) :].removeprefix("\n")
    assert after.startswith('<div class="chart"')
    assert 'id="diagram-diagram"' in after[:400]


# ---- `pns_lane`, the targets and the result matrix (docs/plans/pulseq-checks-implementation.md,
# section 4.7) ----


def test_pns_false_by_default_adds_no_pns_key():
    seq = spin_echo_sequence()
    card = diagram_card(seq, [full_window(seq)])
    file_entry = card.data["file"]
    assert "pns" not in file_entry


def test_targets_and_a_matrix_without_pns_lane_add_no_pns_key(tmp_path):
    seq = spin_echo_sequence()
    card = diagram_card(
        seq,
        [full_window(seq)],
        targets=report_targets([A]),
        check_results=_matrix(seq, [A], tmp_path),
    )
    assert "pns" not in card.data["file"]


def test_one_target_gives_one_pns_entry_from_its_series(tmp_path):
    seq = spin_echo_sequence()
    matrix = _matrix(seq, [A], tmp_path)
    card = diagram_card(
        seq,
        [full_window(seq)],
        pns_lane=True,
        targets=report_targets([A]),
        check_results=matrix,
    )
    file_entry = card.data["file"]

    assert isinstance(file_entry["pns"], list)
    (entry,) = file_entry["pns"]
    assert set(entry) == {
        "target",
        "color",
        "hardware",
        "asc_file",
        "hw",
        "dtS",
        "binSamples",
        "threshold",
        "summary",
        "levels",
        "runs",
    }
    total, above = matrix.analysis(A.name, "pns.safe.levels").series
    assert entry["target"] == A.name
    assert entry["color"] == "target-1"
    assert entry["hardware"] == total.meta["hardware"]
    assert entry["asc_file"] is None
    assert set(entry["hw"]) == {"x", "y", "z"}
    for axis, axis_hw in entry["hw"].items():
        assert set(axis_hw) == {"tau1", "tau2", "tau3", "a1", "a2", "a3", "stim_limit", "g_scale"}
        for key, value in axis_hw.items():
            assert value == A.models["pns.safe"][axis][key]
    assert entry["dtS"] == seq.grad_raster_time == total.meta["dt_s"]
    assert entry["binSamples"] == total.meta["bin_samples"] > 0
    assert entry["threshold"] == above.meta["threshold"] == abs(A.make_opts().gamma)

    # The values are Hz/T as the series gives them: nothing is divided.
    assert entry["summary"] == {
        "peak": total.meta["peak"],
        "peak_time_s": total.meta["peak_time_s"],
        "axis_peaks": {axis: total.meta[f"axis_peaks_{axis}"] for axis in "xyz"},
    }
    assert 0 < entry["summary"]["peak"] < entry["threshold"]
    assert set(entry["levels"]) == {"min", "max"}
    for key, table in entry["levels"].items():
        assert set(table) == {"dtype", "length", "data"}
        assert table["dtype"] == "float32"
        decoded = decode_array(table)
        assert decoded.dtype == np.float32
        assert np.array_equal(decoded, total.arrays[key])
    assert set(entry["runs"]) == {"start", "end"}
    for key, table in entry["runs"].items():
        assert table["dtype"] == "float64"
        assert np.array_equal(decode_array(table), above.arrays[key])


def test_two_targets_give_two_entries_in_order_with_their_own_thresholds(tmp_path):
    """The levels are in Hz/T of samples in Hz/m, so two targets with the same SAFE
    parameters have the same levels, and the thresholds are the magnitudes of their gammas,
    also for a negative gamma."""
    seq = gre_sequence(num_trs=3)
    card = _pns_card(seq, [C, A], tmp_path)
    first, second = card.data["file"]["pns"]

    assert [first["target"], second["target"]] == [C.name, A.name]
    assert [first["color"], second["color"]] == ["target-1", "target-2"]
    assert first["threshold"] == abs(C.make_opts().gamma) == 11.777e6
    assert second["threshold"] == abs(A.make_opts().gamma)
    assert C.make_opts().gamma < 0
    for key in ("min", "max"):
        assert first["levels"][key] == second["levels"][key]
    assert first["summary"] == second["summary"]


def test_a_target_that_is_not_evaluated_has_no_entry_and_is_named_with_its_reason(
    make_profile, tmp_path
):
    seq = spin_echo_sequence()
    no_safe = make_profile("no <safe>")
    card = _pns_card(seq, [no_safe, A], tmp_path)

    (entry,) = card.data["file"]["pns"]
    assert entry["target"] == A.name
    assert entry["color"] == "target-2"  # the color of its place in the report
    assert "no &lt;safe&gt;" in card.body_html
    assert "model pns.safe" in card.body_html  # a part of the reason of pulseq-checks
    assert A.name not in card.body_html.split('<p class="muted" id="diagram-mode"')[1]


def test_without_a_pns_result_the_lane_has_no_entry(make_profile, make_matrix, tmp_path):
    """No targets, no matrix, no analysis result for the target and a target that is not
    evaluated each give no `"pns"` key, and the card still builds."""
    seq = spin_echo_sequence()
    window = [full_window(seq)]
    no_safe = make_profile("no safe")

    without_targets = diagram_card(
        seq, window, pns_lane=True, check_results=_matrix(seq, [A], tmp_path)
    )
    without_matrix = diagram_card(seq, window, pns_lane=True, targets=report_targets([A]))
    without_result = diagram_card(
        seq,
        window,
        pns_lane=True,
        targets=report_targets([no_safe]),
        check_results=make_matrix(["no safe"]),
    )
    not_evaluated = diagram_card(
        seq,
        window,
        pns_lane=True,
        targets=report_targets([no_safe]),
        check_results=_matrix(seq, [no_safe], tmp_path),
    )

    for card in (without_targets, without_matrix, without_result, not_evaluated):
        assert "pns" not in card.data["file"]
        assert card.error is None
    assert "no safe" in without_result.body_html
    assert "no safe" in not_evaluated.body_html


def test_a_sequence_without_gradients_has_no_pns_entry(tmp_path):
    seq = empty_sequence()
    card = _pns_card(seq, [A], tmp_path)
    assert "pns" not in card.data["file"]
    assert card.error is None


def test_the_lane_runs_no_safe_model(tmp_path, monkeypatch):
    """The card reads the matrix. It does not call the SAFE model."""
    seq = spin_echo_sequence()
    matrix = _matrix(seq, [A], tmp_path)

    def raise_error(*args, **kwargs):
        raise AssertionError("the SAFE model ran")

    monkeypatch.setattr("pulseq_analysis.pns_levels._safe_gwf_to_pns_chunk", raise_error)
    card = diagram_card(
        seq,
        [full_window(seq)],
        pns_lane=True,
        targets=report_targets([A]),
        check_results=matrix,
    )
    assert len(card.data["file"]["pns"]) == 1


@pytest.mark.parametrize("pns_lane", [1, 0, "yes", None, np.True_])
def test_pns_lane_that_is_not_a_bool_raises_type_error(pns_lane):
    seq = spin_echo_sequence()
    with pytest.raises(TypeError, match="pns_lane"):
        diagram_card(seq, [full_window(seq)], pns_lane=pns_lane)


# ---- lane groups (docs/plans/diagram-lanes.md, section 4.5, item 3): the
# group-controls container and the PNS explanation sentence (task 4.3) ----

_GROUP_CONTROLS = '<div class="controls" role="group" aria-label="Lanes" id="diagram-groups"></div>'


def test_group_controls_container_is_between_the_window_buttons_and_the_zoom_controls():
    """The RF/ADC/Gradients/PNS toggle buttons go above the chart, after the window
    buttons; `zoom_controls` must still sit directly before `<div class="chart"` (the
    existing zoom-controls test), so the group-controls container goes before it, not
    after."""
    seq = spin_echo_sequence()
    card = diagram_card(seq, [full_window(seq)], card_id="diagram")
    body = card.body_html

    window_buttons = '<div class="controls" role="group" aria-label="Time window">'
    zoom_group = zoom_controls("diagram-diagram")

    assert body.count(_GROUP_CONTROLS) == 1
    window_pos = body.index(window_buttons)
    group_pos = body.index(_GROUP_CONTROLS)
    zoom_pos = body.index(zoom_group)
    assert window_pos < group_pos < zoom_pos


def test_group_controls_container_id_starts_with_the_given_card_id():
    seq = spin_echo_sequence()
    card = diagram_card(seq, [full_window(seq)], card_id="my-diagram")
    assert (
        '<div class="controls" role="group" aria-label="Lanes" id="my-diagram-groups"></div>'
        in card.body_html
    )


def test_group_controls_container_present_even_without_pns_data():
    """The RF, ADC and gradient groups can be hidden even when the card has no PNS
    lane, so the container is not conditional on `pns`: it is empty, and the card
    script (`assets/cards/diagram.js`) fills it with one button for each group that
    applies to the file's own data."""
    seq = spin_echo_sequence()
    card = diagram_card(seq, [full_window(seq)])  # pns_lane=False (the default)
    assert _GROUP_CONTROLS in card.body_html


_G_EXPLANATION_PHRASES = ("|G| lane", "magnitude of the gradient vector")


def test_g_lane_explanation_sentence_always_present():
    """The |G| lane (`docs/plans/diagram-lanes.md`, phase 5) needs no extra data from
    `diagram_card` (it is computed in the browser from the tables already sent), so its
    explanation sentence is unconditional, unlike the PNS sentence."""
    seq = spin_echo_sequence()
    card = diagram_card(seq, [full_window(seq)])  # pns_lane=False (the default)
    for phrase in _G_EXPLANATION_PHRASES:
        assert phrase in card.body_html, phrase


def test_g_lane_explanation_sentence_present_even_without_gradients():
    seq = empty_sequence()
    card = diagram_card(seq, [full_window(seq)])
    for phrase in _G_EXPLANATION_PHRASES:
        assert phrase in card.body_html, phrase
