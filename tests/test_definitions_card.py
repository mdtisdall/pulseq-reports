from synthetic import gre_sequence, spin_echo_sequence

from pulseq_reports import page
from pulseq_reports.cards import definitions
from pulseq_reports.markup import html_table


def test_definitions_card_for_one_sequence_matches_the_vb_table():
    seq = gre_sequence()
    card = definitions.definitions_card(seq)
    assert card.id == "definitions"
    assert card.title == "Definitions"
    expected_rows = [
        [k, " ".join(map(str, v)) if isinstance(v, (list, tuple)) else v]
        for k, v in seq.definitions.items()
    ]
    assert card.body_html == html_table(["Definition", "Value"], expected_rows)
    assert card.data is None
    assert card.script is None


def test_definitions_card_for_one_sequence_with_no_definitions_is_an_empty_table():
    seq = spin_echo_sequence()
    seq.definitions.clear()
    card = definitions.definitions_card(seq)
    assert card.body_html == html_table(["Definition", "Value"], [])


def test_render_page_accepts_definitions_card():
    card = definitions.definitions_card(gre_sequence())
    result = page.render_page("t", "s", [card])
    assert "<h2>Definitions</h2>" in result
