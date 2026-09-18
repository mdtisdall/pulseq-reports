import html

from synthetic import gre_sequence, spin_echo_sequence

from pulseq_reports import page
from pulseq_reports.cards.blocks import blocks_card
from pulseq_reports.markup import _table
from pulseq_reports.seq_utils import NamedSequence
from pulseq_reports.waveforms import TimeWindow, block_rows, duration_s


def _named(seq, name: str = "seq.seq") -> NamedSequence:
    return NamedSequence(name, seq)


def _expected_table(rows: list[dict]) -> str:
    """The block table HTML that vb-pulseq's own `block_table` builds, via
    `markup._table`, from `waveforms.block_rows`' rows."""
    return _table(
        ["Block", "Start (ms)", "Duration (ms)", "Events"],
        [[r["block"], f"{r['start_ms']:g}", f"{r['duration_ms']:g}", r["events"]] for r in rows],
    )


def test_one_file_note_and_table_match_vb_parity_when_rows_are_cut():
    seq = gre_sequence(num_trs=5, tr=20e-3)
    max_rows = 10
    card = blocks_card([_named(seq)], max_rows=max_rows)
    rows, total = block_rows(seq, max_rows=max_rows)
    assert total > max_rows  # the note is present only when rows are cut

    expected_note = f'<p class="muted">First {max_rows} of {total} blocks.</p>'
    expected_table = _expected_table(rows)
    # vb-pulseq's own template has "__BLOCK_NOTE__\n__BLOCKS__" between the
    # <summary> and </details>; `body_html` is exactly that text (parity).
    assert card.body_html == f"{expected_note}\n{expected_table}"
    assert card.id == "blocks"
    assert card.title == "Blocks (table view)"
    assert card.collapsed is True
    assert card.data is None
    assert card.script is None


def test_no_note_when_all_rows_fit():
    seq = gre_sequence(num_trs=2, tr=20e-3)
    card = blocks_card([_named(seq)])  # default max_rows=500, well above the block count
    rows, total = block_rows(seq)
    assert total <= 500
    assert card.body_html == f"\n{_expected_table(rows)}"
    assert "muted" not in card.body_html


def test_two_files_have_an_h3_with_each_escaped_file_name():
    seq_a, seq_b = gre_sequence(num_trs=1, tr=20e-3), gre_sequence(num_trs=1, tr=25e-3)
    card = blocks_card([_named(seq_a, "a<b>.seq"), _named(seq_b, "b.seq")])
    assert f"<h3>{html.escape('a<b>.seq')}</h3>" in card.body_html
    assert "<h3>b.seq</h3>" in card.body_html
    assert card.body_html.index("a&lt;b&gt;.seq") < card.body_html.index("<h3>b.seq</h3>")


def test_windows_give_one_table_each_headed_by_the_window_label():
    seq = gre_sequence(num_trs=3, tr=20e-3)
    tr = duration_s(seq) / 3
    windows = [TimeWindow(f"TR {k}", 0, k * tr, (k + 1) * tr) for k in range(3)]
    card = blocks_card([_named(seq)], windows=windows)
    assert card.body_html.count("<h3>") == 3
    for k, w in enumerate(windows):
        assert f"<h3>TR {k}</h3>" in card.body_html
        rows, _ = block_rows(seq, w.start_s, w.end_s)
        assert _expected_table(rows) in card.body_html


def test_windows_with_two_files_prefix_the_heading_with_the_file_name():
    seq_a, seq_b = gre_sequence(num_trs=2, tr=20e-3), gre_sequence(num_trs=2, tr=30e-3)
    tr_a, tr_b = duration_s(seq_a) / 2, duration_s(seq_b) / 2
    windows = [
        TimeWindow("TR 0", 0, 0.0, tr_a),
        TimeWindow("TR 0", 1, 0.0, tr_b),
    ]
    card = blocks_card([_named(seq_a, "a.seq"), _named(seq_b, "b.seq")], windows=windows)
    assert "<h3>a.seq: TR 0</h3>" in card.body_html
    assert "<h3>b.seq: TR 0</h3>" in card.body_html


def test_windows_note_when_a_window_has_more_blocks_than_max_rows():
    seq = gre_sequence(num_trs=1, tr=20e-3)
    w = TimeWindow("whole", 0, 0.0, duration_s(seq))
    _, total = block_rows(seq, w.start_s, w.end_s, max_rows=2)
    assert total > 2

    card = blocks_card([_named(seq)], windows=[w], max_rows=2)
    assert f'<p class="muted">First 2 of {total} blocks.</p>' in card.body_html


def test_render_page_accepts_blocks_card():
    card = blocks_card([_named(spin_echo_sequence())])
    result = page.render_page("t", "s", [card])
    assert "<summary>Blocks (table view)</summary>" in result
