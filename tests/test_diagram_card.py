import numpy as np
import pytest
from synthetic import gre_sequence, spin_echo_sequence

from pulseq_reports import page
from pulseq_reports.cards.diagram import diagram_card
from pulseq_reports.diagram_data import decode_tables, diagram_tables, lane_meta
from pulseq_reports.markup import _zoom_controls
from pulseq_reports.seq_utils import NamedSequence
from pulseq_reports.waveforms import TimeWindow, duration_s, first_adc_window, full_window


def _named(seq, name: str = "seq") -> NamedSequence:
    return NamedSequence(name, seq)


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
    assert result.count(_ZOOM_HELP_SENTENCE) == 1
