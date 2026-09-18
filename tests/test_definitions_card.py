import pypulseq as pp
from synthetic import gre_sequence, spin_echo_sequence

from pulseq_reports import page
from pulseq_reports.cards import definitions
from pulseq_reports.markup import _table
from pulseq_reports.seq_utils import NamedSequence


def test_definitions_card_for_one_sequence_matches_the_vb_table():
    seq = gre_sequence()
    card = definitions.definitions_card([NamedSequence("gre", seq)])
    assert card.id == "definitions"
    assert card.title == "Definitions"
    expected_rows = [
        [k, " ".join(map(str, v)) if isinstance(v, (list, tuple)) else v]
        for k, v in seq.definitions.items()
    ]
    assert card.body_html == _table(["Definition", "Value"], expected_rows)
    assert card.data is None
    assert card.script is None


def test_definitions_card_for_one_sequence_with_no_definitions_is_an_empty_table():
    seq = spin_echo_sequence()
    seq.definitions.clear()
    card = definitions.definitions_card([NamedSequence("se", seq)])
    assert card.body_html == _table(["Definition", "Value"], [])


def test_definitions_card_for_two_sequences_unions_keys_in_first_seen_order():
    a = pp.Sequence()
    a.set_definition("Name", "a")
    a.set_definition("TR", 20e-3)
    b = pp.Sequence()
    b.set_definition("TR", 30e-3)
    b.set_definition("FOV", [200, 200, 5])

    card = definitions.definitions_card([NamedSequence("a.seq", a), NamedSequence("b.seq", b)])

    assert "<th>Definition</th><th>a.seq</th><th>b.seq</th>" in card.body_html
    # "Name" is only in a.seq; "FOV" is only in b.seq (space-joined); "TR" differs per file.
    assert "<tr><td>Name</td><td>a</td><td></td></tr>" in card.body_html
    assert "<tr><td>TR</td><td>0.02</td><td>0.03</td></tr>" in card.body_html
    assert "<tr><td>FOV</td><td></td><td>200 200 5</td></tr>" in card.body_html
    # First-seen order: both files' shared raster keys and "Name"/"TR" (from a.seq) come
    # before "FOV" (first seen in b.seq).
    assert card.body_html.index("Name") < card.body_html.index("TR") < card.body_html.index("FOV")


def test_definitions_card_for_two_sequences_with_no_definitions_shows_a_muted_message():
    a = pp.Sequence()
    a.definitions.clear()
    b = pp.Sequence()
    b.definitions.clear()
    card = definitions.definitions_card([NamedSequence("a.seq", a), NamedSequence("b.seq", b)])
    assert card.body_html == '<p class="muted">No definitions.</p>'


def test_render_page_accepts_definitions_card():
    card = definitions.definitions_card([NamedSequence("gre", gre_sequence())])
    result = page.render_page("t", "s", [card])
    assert "<h2>Definitions</h2>" in result
