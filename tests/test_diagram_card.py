import pytest
from synthetic import gre_sequence, spin_echo_sequence

from pulseq_reports import page
from pulseq_reports.cards.diagram import diagram_card
from pulseq_reports.markup import _zoom_controls
from pulseq_reports.seq_utils import NamedSequence
from pulseq_reports.waveforms import (
    TimeWindow,
    duration_s,
    first_adc_window,
    full_window,
    point_count,
)


def _named(seq, name: str = "seq") -> NamedSequence:
    return NamedSequence(name, seq)


def test_small_file_has_one_lane_set_with_the_file_extent():
    seq = spin_echo_sequence()
    named = _named(seq)
    windows = [first_adc_window([named]), full_window([named])]
    card = diagram_card([named], windows)
    data = card.data

    assert len(data["lane_sets"]) == 1
    (lane_set,) = data["lane_sets"]
    assert lane_set["envelope"] is False
    end_ms = round(duration_s(seq) * 1e3, 4)
    assert lane_set["extent_ms"] == [0.0, end_ms]

    assert all(w["lane_set"] == 0 for w in data["windows"])
    assert [w["view_ms"] for w in data["windows"]] == [
        [round(w.start_s * 1e3, 4), round(w.end_s * 1e3, 4)] for w in windows
    ]


def test_over_budget_file_gets_one_lane_set_per_window():
    """A file over `point_budget` gets an envelope for a window equal to the whole
    file, and the exact lanes of just its own blocks (extent equal to the window) for
    a short window within the budget."""
    seq = gre_sequence(num_trs=5, tr=20e-3)
    named = _named(seq)
    duration_ms = round(duration_s(seq) * 1e3, 4)
    full = full_window([named])
    tr = duration_s(seq) / 5
    short = TimeWindow("TR 0", 0, 0.0, tr)
    point_budget = 50
    assert point_count(seq) > point_budget  # the whole file is over the budget
    assert point_count(seq, short.start_s, short.end_s) <= point_budget  # one TR is not

    card = diagram_card([named], [full, short], point_budget=point_budget)
    data = card.data
    assert len(data["lane_sets"]) == 2

    full_set = data["lane_sets"][data["windows"][0]["lane_set"]]
    short_set = data["lane_sets"][data["windows"][1]["lane_set"]]
    assert full_set["envelope"] is True
    assert full_set["extent_ms"] == [0.0, duration_ms]
    assert short_set["envelope"] is False
    assert short_set["extent_ms"] == [
        round(short.start_s * 1e3, 4),
        round(short.end_s * 1e3, 4),
    ]


def test_two_files_prefix_button_text_with_the_file_name():
    named_a = _named(spin_echo_sequence(), "a.seq")
    named_b = _named(gre_sequence(num_trs=2), "b.seq")
    seqs = [named_a, named_b]
    windows = [full_window(seqs, 0), full_window(seqs, 1)]
    card = diagram_card(seqs, windows)
    assert "a.seq: Full sequence" in card.body_html
    assert "b.seq: Full sequence" in card.body_html


def test_ids_start_with_the_given_card_id():
    named = _named(spin_echo_sequence())
    card = diagram_card([named], [full_window([named])], card_id="my-diagram")
    assert card.id == "my-diagram"
    assert 'id="my-diagram-diagram"' in card.body_html
    assert 'id="my-diagram-chart"' in card.body_html
    assert 'id="my-diagram-tip"' in card.body_html


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


def test_render_page_includes_diagram_script_once():
    named = _named(spin_echo_sequence())
    card = diagram_card([named], [full_window([named])])
    result = page.render_page("t", "s", [card])
    assert result.count('PulseqReport.registerCard("diagram"') == 1


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
    assert result.count(_ZOOM_HELP_SENTENCE) == 1
