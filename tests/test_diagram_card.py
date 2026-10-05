import numpy as np
import pypulseq as pp
import pytest
from pulseq_analysis.pns import pns_levels_for
from pulseq_analysis.series import decode_array
from synthetic import GAMMA_1H, empty_sequence, gre_sequence, spin_echo_sequence

from pulseq_reports import page
from pulseq_reports.cards.diagram import diagram_card
from pulseq_reports.diagram_data import diagram_tables, lane_meta
from pulseq_reports.markup import zoom_controls
from pulseq_reports.waveforms import TimeWindow, duration_s, first_adc_window, full_window


def _sodium_gradient_sequence() -> pp.Sequence:
    """A one-block x trapezoid on a system with the gyromagnetic ratio of sodium
    (11.262e6 Hz/T), so `gradScale = the proton gamma (42.576e6) / seq.system.gamma` (decision 14
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


def test_data_has_format_2_with_file_and_window_keys():
    seq = spin_echo_sequence()
    card = diagram_card(seq, [first_adc_window(seq), full_window(seq)])
    data = card.data

    assert set(data) == {"format", "file", "windows"}
    assert data["format"] == 2
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


# ---- `pns_lane` and `gradient_asc` (docs/plans/diagram-lanes.md, section 4.7) ----


def test_pns_false_by_default_adds_no_pns_key():
    seq = spin_echo_sequence()
    card = diagram_card(seq, [full_window(seq)])
    file_entry = card.data["file"]
    assert "pns" not in file_entry


def test_pns_true_adds_the_pns_key_with_the_gradient_asc_hardware(write_gradient_asc):
    seq = spin_echo_sequence()
    path = write_gradient_asc()
    card = diagram_card(seq, [full_window(seq)], pns_lane=True, gradient_asc=path)
    file_entry = card.data["file"]

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
    assert pns_entry["hardware"] == "MP_GPA_TEST"
    assert pns_entry["example"] is False
    assert pns_entry["asc_file"] == path.name
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


def test_pns_true_without_gradient_asc_adds_no_pns_key_and_runs_no_safe_model(no_safe_model):
    seq = spin_echo_sequence()

    card = diagram_card(seq, [full_window(seq)], pns_lane=True)

    assert "pns" not in card.data["file"]
    assert card.error is None


def test_gradient_asc_without_pns_lane_raises_value_error(write_gradient_asc):
    seq = spin_echo_sequence()
    path = write_gradient_asc()
    with pytest.raises(ValueError, match="gradient_asc"):
        diagram_card(seq, [full_window(seq)], gradient_asc=path)


@pytest.mark.parametrize("pns_lane", [1, 0, "yes", None, np.True_])
def test_pns_lane_that_is_not_a_bool_raises_type_error(pns_lane):
    seq = spin_echo_sequence()
    with pytest.raises(TypeError, match="pns_lane"):
        diagram_card(seq, [full_window(seq)], pns_lane=pns_lane)


def test_pns_grad_scale_for_a_sequence_with_another_gyromagnetic_ratio(write_gradient_asc):
    """`gradScale = the proton gamma (42.576e6) / seq.system.gamma` (decision 14): not 1.0 for a
    sequence built with a non-proton gyromagnetic ratio (here sodium, 11.262e6 Hz/T, as
    in the golden test of task 4.5)."""
    seq = _sodium_gradient_sequence()
    card = diagram_card(seq, [full_window(seq)], pns_lane=True, gradient_asc=write_gradient_asc())
    file_entry = card.data["file"]
    assert file_entry["pns"]["gradScale"] == pytest.approx(GAMMA_1H / seq.system.gamma)
    assert file_entry["pns"]["gradScale"] != 1.0


def test_pns_without_gradients_adds_no_pns_key(write_gradient_asc):
    seq = empty_sequence()
    card = diagram_card(seq, [full_window(seq)], pns_lane=True, gradient_asc=write_gradient_asc())
    file_entry = card.data["file"]
    assert "pns" not in file_entry


def test_pns_levels_decode_back_to_pns_levels_for_exactly(write_gradient_asc):
    """The `"levels"` key of the `"pns"` entry, decoded, equals the `level_min_hz_per_t`/
    `level_max_hz_per_t` of `pns.pns_levels_for(seq, gradient_asc=...)`, divided by |gamma|,
    exactly (the same values, encoded and decoded with
    `pulseq_analysis.series.encode_array`/`decode_array`)."""
    seq = spin_echo_sequence()
    path = write_gradient_asc()
    card = diagram_card(seq, [full_window(seq)], pns_lane=True, gradient_asc=path)
    file_entry = card.data["file"]

    decoded = {name: decode_array(d) for name, d in file_entry["pns"]["levels"].items()}
    levels = pns_levels_for(seq, gradient_asc=path)
    assert decoded["min"].dtype == np.float32
    assert decoded["max"].dtype == np.float32
    g = abs(seq.system.gamma)
    assert np.array_equal(decoded["min"], levels.level_min_hz_per_t / g)
    assert np.array_equal(decoded["max"], levels.level_max_hz_per_t / g)


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


_PNS_EXPLANATION_PHRASES = (
    "PNS lane",
    "percent of the SAFE stimulation limit",
    "10 s or less",
)


def test_pns_explanation_sentence_present_when_the_card_has_pns_data(write_gradient_asc):
    seq = spin_echo_sequence()
    card = diagram_card(seq, [full_window(seq)], pns_lane=True, gradient_asc=write_gradient_asc())
    for phrase in _PNS_EXPLANATION_PHRASES:
        assert phrase in card.body_html, phrase


def test_pns_explanation_sentence_absent_by_default():
    seq = spin_echo_sequence()
    card = diagram_card(seq, [full_window(seq)])  # pns_lane=False
    for phrase in _PNS_EXPLANATION_PHRASES:
        assert phrase not in card.body_html, phrase


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


def test_pns_explanation_sentence_absent_without_gradients_even_with_pns_true(
    write_gradient_asc,
):
    """A file with no gradient event gets no `"pns"` key (`_diagram_data`) even when
    `pns` is not False, so it gets no PNS sentence either: the explanation is keyed
    on the data (`has_pns` in `diagram_card`), not on the `pns` argument alone."""
    seq = empty_sequence()
    card = diagram_card(seq, [full_window(seq)], pns_lane=True, gradient_asc=write_gradient_asc())
    for phrase in _PNS_EXPLANATION_PHRASES:
        assert phrase not in card.body_html, phrase
