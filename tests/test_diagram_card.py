import numpy as np
import pypulseq as pp
import pytest
from pypulseq.utils.safe_pns_prediction import safe_example_hw
from synthetic import empty_sequence, gre_sequence, spin_echo_sequence

from pulseq_reports import page
from pulseq_reports.cards.diagram import diagram_card
from pulseq_reports.diagram_data import decode_tables, diagram_tables, lane_meta
from pulseq_reports.markup import _zoom_controls
from pulseq_reports.pns import EXAMPLE_HARDWARE, pns_levels_for
from pulseq_reports.seq_utils import GAMMA, NamedSequence
from pulseq_reports.waveforms import TimeWindow, duration_s, first_adc_window, full_window


def _named(seq, name: str = "seq") -> NamedSequence:
    return NamedSequence(name, seq)


def _write_gradient_asc(tmp_path, name: str = "MP_GPA_TEST"):
    """A minimal gradient .asc file with the PNS parameters of pypulseq's example
    hardware (the same technique as `test_pns.py`'s `write_gradient_asc` fixture: the
    real files are confidential, so this one is built from pypulseq's own public
    example hardware)."""
    hw = safe_example_hw()
    lines = [f'asCOMP.tName = "{name}"']
    for axis in "xyz":
        a, suffix = getattr(hw, axis), axis.upper()
        lines += [f"flGSWDTau{suffix}[{i}] = {getattr(a, f'tau{i + 1}')!r}" for i in range(3)]
        lines += [f"flGSWDA{suffix}[{i}] = {getattr(a, f'a{i + 1}')!r}" for i in range(3)]
        lines += [
            f"flGSWDStimulationLimit{suffix} = {a.stim_limit!r}",
            f"flGSWDStimulationThreshold{suffix} = {a.stim_thresh!r}",
        ]
        lines.append(f"asGPAParameters[0].sGCParameters.flGScaleFactor{suffix} = {a.g_scale!r}")
    path = tmp_path / f"{name}.asc"
    path.write_text("\n".join(lines) + "\n")
    return path


def _sodium_gradient_sequence() -> pp.Sequence:
    """A one-block x trapezoid on a system with the gyromagnetic ratio of sodium
    (11.262e6 Hz/T), so `gradScale = seq_utils.GAMMA / seq.system.gamma` (decision 14
    of `docs/plans/diagram-lanes.md`) is not 1.0."""
    system = pp.Opts(
        max_grad=28,
        grad_unit="mT/m",
        max_slew=150,
        slew_unit="T/m/s",
        rf_ringdown_time=20e-6,
        rf_dead_time=100e-6,
        adc_dead_time=10e-6,
        gamma=11.262e6,
    )
    seq = pp.Sequence(system)
    seq.add_block(pp.make_trapezoid(channel="x", area=1000, system=system))
    return seq


def test_data_has_format_1_with_file_and_window_keys():
    seq = spin_echo_sequence()
    named = _named(seq)
    card = diagram_card([named], [first_adc_window([named]), full_window([named])])
    data = card.data

    assert set(data) == {"format", "files", "windows"}
    assert data["format"] == 1
    assert len(data["files"]) == 1
    (file_entry,) = data["files"]
    assert set(file_entry) == {"name", "duration_s", "num_blocks", "lanes", "tables"}
    assert file_entry["lanes"] == lane_meta(seq)
    assert file_entry["duration_s"] == duration_s(seq)
    assert file_entry["num_blocks"] == len(seq.block_events)
    for name, entry in file_entry["tables"].items():
        assert set(entry) == {"dtype", "length", "data"}, name

    for window in data["windows"]:
        assert set(window) == {"label", "file", "view_ms"}


def test_tables_decode_to_diagram_tables():
    seq = gre_sequence(num_trs=3)
    named = _named(seq)
    card = diagram_card([named], [full_window([named])])
    (file_entry,) = card.data["files"]

    decoded = decode_tables(file_entry["tables"])
    expected = diagram_tables(seq)
    assert set(decoded) == set(expected)
    for key in expected:
        assert decoded[key].dtype == expected[key].dtype, key
        assert np.array_equal(decoded[key], expected[key]), key


def test_two_files_give_two_file_entries_and_names_in_button_texts():
    named_a = _named(spin_echo_sequence(), "a.seq")
    named_b = _named(gre_sequence(num_trs=2), "b.seq")
    seqs = [named_a, named_b]
    windows = [full_window(seqs, 0), full_window(seqs, 1)]
    card = diagram_card(seqs, windows)
    data = card.data

    assert len(data["files"]) == 2
    assert [f["name"] for f in data["files"]] == ["a.seq", "b.seq"]
    assert "a.seq: Full sequence" in card.body_html
    assert "b.seq: Full sequence" in card.body_html


def test_a_window_of_a_file_with_no_other_window_adds_that_file():
    """A file in `seqs` with no window is not in `files`; a window of a file with no
    other window still adds it, and each window's `file` index points at the right
    entry (checked by name, since a file's position in `files` is its order of first
    use, not its position in `seqs`)."""
    named_a = _named(spin_echo_sequence(), "a.seq")
    named_b = _named(gre_sequence(num_trs=2), "b.seq")
    named_c = _named(gre_sequence(num_trs=1), "c.seq")
    seqs = [named_a, named_b, named_c]
    windows = [full_window(seqs, 2), full_window(seqs, 0)]
    card = diagram_card(seqs, windows)
    data = card.data

    assert len(data["files"]) == 2
    names_by_index = [f["name"] for f in data["files"]]
    assert set(names_by_index) == {"a.seq", "c.seq"}

    def file_of(name_prefix: str) -> str:
        (window,) = [w for w in data["windows"] if w["label"].startswith(name_prefix)]
        return names_by_index[window["file"]]

    assert file_of("c.seq:") == "c.seq"
    assert file_of("a.seq:") == "a.seq"


def test_ids_start_with_the_given_card_id():
    named = _named(spin_echo_sequence())
    card = diagram_card([named], [full_window([named])], card_id="my-diagram")
    assert card.id == "my-diagram"
    assert 'id="my-diagram-diagram"' in card.body_html
    assert 'id="my-diagram-chart"' in card.body_html
    assert 'id="my-diagram-tip"' in card.body_html
    assert 'id="my-diagram-mode"' in card.body_html


def test_no_windows_raises():
    with pytest.raises(ValueError):
        diagram_card([_named(spin_echo_sequence())], [])


def test_bad_file_index_raises():
    named = _named(spin_echo_sequence())
    bad = TimeWindow("bad", 1, 0.0, 1.0)  # only file 0 exists
    with pytest.raises(ValueError):
        diagram_card([named], [bad])


def test_end_before_start_raises():
    named = _named(spin_echo_sequence())
    bad = TimeWindow("bad", 0, 1.0, 0.5)
    with pytest.raises(ValueError):
        diagram_card([named], [bad])


def test_render_page_includes_diagram_and_seq_lanes_scripts_once():
    named = _named(spin_echo_sequence())
    card = diagram_card([named], [full_window([named])])
    result = page.render_page("t", "s", [card])
    assert result.count('PulseqReport.registerCard("diagram"') == 1
    assert result.count("const SeqLanes") == 1


def test_no_envelope_note_and_status_line_is_present():
    named = _named(spin_echo_sequence())
    card = diagram_card([named], [full_window([named])])
    assert "too many" not in card.body_html
    assert "envelope" not in card.body_html
    assert 'id="diagram-mode"' in card.body_html
    assert 'aria-live="polite"' in card.body_html


_ZOOM_HELP_SENTENCE = (
    "Click the chart to mark the centre for the zoom buttons. Drag across the chart to zoom to "
    "that range. Hold Shift and drag, or scroll sideways, to pan."
)


def test_diagram_card_has_zoom_controls_before_its_chart_and_the_help_sentence_once():
    """Adapted from vb-pulseq's `test_report_has_zoom_controls_on_each_line_chart`.
    Phases 4 (gradient spectrum) and 5 (PNS) are not merged into this branch, so only
    the diagram card's own zoom controls and help text are checked, not a page with
    every line chart."""
    named = _named(spin_echo_sequence())
    card = diagram_card([named], [full_window([named])], card_id="diagram")
    result = page.render_page("t", "s", [card])

    controls = _zoom_controls("diagram-diagram")
    assert result.count(controls) == 1
    after = result[result.index(controls) + len(controls) :].removeprefix("\n")
    assert after.startswith('<div class="chart"')
    assert 'id="diagram-diagram"' in after[:400]


# ---- the `pns` argument (docs/plans/diagram-lanes.md, section 4.7) ----


def test_pns_false_by_default_adds_no_pns_key():
    named = _named(spin_echo_sequence())
    card = diagram_card([named], [full_window([named])])
    (file_entry,) = card.data["files"]
    assert "pns" not in file_entry


def test_pns_true_adds_the_pns_key_with_the_example_hardware():
    named = _named(spin_echo_sequence())
    card = diagram_card([named], [full_window([named])], pns=True)
    (file_entry,) = card.data["files"]

    assert "pns" in file_entry
    pns_entry = file_entry["pns"]
    assert set(pns_entry) == {
        "hardware",
        "example",
        "asc_file",
        "hw",
        "dtS",
        "gradScale",
        "binSamples",
        "summary",
        "levels",
    }
    assert pns_entry["hardware"] == EXAMPLE_HARDWARE
    assert pns_entry["example"] is True
    assert pns_entry["asc_file"] is None
    assert set(pns_entry["hw"]) == {"x", "y", "z"}
    for axis_hw in pns_entry["hw"].values():
        assert set(axis_hw) == {
            "tau1",
            "tau2",
            "tau3",
            "a1",
            "a2",
            "a3",
            "stim_limit",
            "g_scale",
        }
    assert pns_entry["dtS"] == spin_echo_sequence().grad_raster_time
    assert pns_entry["gradScale"] == 1.0  # a proton sequence (decision 14)
    assert pns_entry["binSamples"] > 0

    summary = pns_entry["summary"]
    assert set(summary) == {"peak", "peak_time_s", "axis_peaks"}
    assert 0 < summary["peak"] < 1
    assert summary["peak_time_s"] is not None
    assert set(summary["axis_peaks"]) == {"x", "y", "z"}

    assert set(pns_entry["levels"]) == {"min", "max"}
    for table in pns_entry["levels"].values():
        assert set(table) == {"dtype", "length", "data"}
        assert table["dtype"] == "float32"


def test_pns_asc_path_uses_the_gradient_asc_hardware(tmp_path):
    named = _named(spin_echo_sequence())
    path = _write_gradient_asc(tmp_path)
    card = diagram_card([named], [full_window([named])], pns=path)
    (file_entry,) = card.data["files"]
    pns_entry = file_entry["pns"]
    assert pns_entry["hardware"] == "MP_GPA_TEST"
    assert pns_entry["example"] is False
    assert pns_entry["asc_file"] == path.name


def test_pns_grad_scale_for_a_sequence_with_another_gyromagnetic_ratio():
    """`gradScale = seq_utils.GAMMA / seq.system.gamma` (decision 14): not 1.0 for a
    sequence built with a non-proton gyromagnetic ratio (here sodium, 11.262e6 Hz/T, as
    in the golden test of task 4.5)."""
    seq = _sodium_gradient_sequence()
    named = _named(seq)
    card = diagram_card([named], [full_window([named])], pns=True)
    (file_entry,) = card.data["files"]
    assert file_entry["pns"]["gradScale"] == pytest.approx(GAMMA / seq.system.gamma)
    assert file_entry["pns"]["gradScale"] != 1.0


def test_pns_without_gradients_adds_no_pns_key():
    named = _named(empty_sequence())
    card = diagram_card([named], [full_window([named])], pns=True)
    (file_entry,) = card.data["files"]
    assert "pns" not in file_entry


def test_pns_levels_decode_back_to_pns_levels_for_exactly():
    """The `"levels"` key of the `"pns"` entry, decoded, equals the `level_min`/
    `level_max` of `pns.pns_levels_for(seq)` exactly (the same values, encoded and
    decoded with `diagram_data.encode_tables`/`decode_tables`)."""
    seq = spin_echo_sequence()
    named = _named(seq)
    card = diagram_card([named], [full_window([named])], pns=True)
    (file_entry,) = card.data["files"]

    decoded = decode_tables(file_entry["pns"]["levels"])
    levels = pns_levels_for(seq)
    assert decoded["min"].dtype == np.float32
    assert decoded["max"].dtype == np.float32
    assert np.array_equal(decoded["min"], levels.level_min)
    assert np.array_equal(decoded["max"], levels.level_max)


# ---- lane groups (docs/plans/diagram-lanes.md, section 4.5, item 3): the
# group-controls container and the PNS explanation sentence (task 4.3) ----

_GROUP_CONTROLS = '<div class="controls" role="group" aria-label="Lanes" id="diagram-groups"></div>'


def test_group_controls_container_is_between_the_window_buttons_and_the_zoom_controls():
    """The RF/ADC/Gradients/PNS toggle buttons go above the chart, after the window
    buttons (worker spec); `_zoom_controls` must still sit directly before
    `<div class="chart"` (the existing zoom-controls test), so the group-controls
    container goes before it, not after."""
    named = _named(spin_echo_sequence())
    card = diagram_card([named], [full_window([named])], card_id="diagram")
    body = card.body_html

    window_buttons = '<div class="controls" role="group" aria-label="Time window">'
    zoom_controls = _zoom_controls("diagram-diagram")

    assert body.count(_GROUP_CONTROLS) == 1
    window_pos = body.index(window_buttons)
    group_pos = body.index(_GROUP_CONTROLS)
    zoom_pos = body.index(zoom_controls)
    assert window_pos < group_pos < zoom_pos


def test_group_controls_container_id_starts_with_the_given_card_id():
    named = _named(spin_echo_sequence())
    card = diagram_card([named], [full_window([named])], card_id="my-diagram")
    assert (
        '<div class="controls" role="group" aria-label="Lanes" id="my-diagram-groups"></div>'
        in card.body_html
    )


def test_group_controls_container_present_even_without_pns_data():
    """The RF, ADC and gradient groups can be hidden even when the card has no PNS
    lane, so the container is not conditional on `pns`: it is empty, and the card
    script (`assets/cards/diagram.js`) fills it with one button for each group that
    applies to the file's own data."""
    named = _named(spin_echo_sequence())
    card = diagram_card([named], [full_window([named])])  # pns=False (the default)
    assert _GROUP_CONTROLS in card.body_html


_PNS_EXPLANATION_PHRASES = (
    "PNS lane",
    "percent of the SAFE stimulation limit",
    "10 s or less",
)


def test_pns_explanation_sentence_present_when_the_card_has_pns_data():
    named = _named(spin_echo_sequence())
    card = diagram_card([named], [full_window([named])], pns=True)
    for phrase in _PNS_EXPLANATION_PHRASES:
        assert phrase in card.body_html, phrase


def test_pns_explanation_sentence_absent_by_default():
    named = _named(spin_echo_sequence())
    card = diagram_card([named], [full_window([named])])  # pns=False
    for phrase in _PNS_EXPLANATION_PHRASES:
        assert phrase not in card.body_html, phrase


_G_EXPLANATION_PHRASES = ("|G| lane", "magnitude of the gradient vector")


def test_g_lane_explanation_sentence_always_present():
    """The |G| lane (`docs/plans/diagram-lanes.md`, phase 5) needs no extra data from
    `diagram_card` (it is computed in the browser from the tables already sent), so its
    explanation sentence is unconditional, unlike the PNS sentence."""
    named = _named(spin_echo_sequence())
    card = diagram_card([named], [full_window([named])])  # pns=False (the default)
    for phrase in _G_EXPLANATION_PHRASES:
        assert phrase in card.body_html, phrase


def test_g_lane_explanation_sentence_present_even_without_gradients():
    named = _named(empty_sequence())
    card = diagram_card([named], [full_window([named])])
    for phrase in _G_EXPLANATION_PHRASES:
        assert phrase in card.body_html, phrase


def test_pns_explanation_sentence_absent_without_gradients_even_with_pns_true():
    """A file with no gradient event gets no `"pns"` key (`_diagram_data`) even when
    `pns` is not False, so it gets no PNS sentence either: the explanation is keyed
    on the data (`has_pns` in `diagram_card`), not on the `pns` argument alone."""
    named = _named(empty_sequence())
    card = diagram_card([named], [full_window([named])], pns=True)
    for phrase in _PNS_EXPLANATION_PHRASES:
        assert phrase not in card.body_html, phrase
