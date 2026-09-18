import math

import pypulseq as pp
from synthetic import SYSTEM, spin_echo_sequence

from pulseq_reports import page
from pulseq_reports.cards import timing
from pulseq_reports.seq_utils import NamedSequence


def _bad_sequence() -> pp.Sequence:
    """A single RF block whose delay is below the RF dead time, so `check_timing` fails."""
    seq = pp.Sequence(SYSTEM)
    rf = pp.make_block_pulse(flip_angle=math.pi / 2, duration=1e-3, system=SYSTEM)
    rf.delay = 0
    seq.add_block(rf)
    return seq


def test_timing_card_for_one_sequence_matches_timing_html():
    seq = spin_echo_sequence()
    card = timing.timing_card([NamedSequence("se", seq)])
    assert card.id == "timing"
    assert card.title == "Timing check"
    assert card.body_html == timing._timing_html(timing.timing_errors(seq))
    assert "Timing check passed" in card.body_html
    assert card.data is None
    assert card.script is None


def test_timing_card_lists_timing_errors_for_one_sequence():
    seq = _bad_sequence()
    errors = timing.timing_errors(seq)
    assert any(e.get("error_type") == "RF_DEAD_TIME" for e in errors)
    card = timing.timing_card([NamedSequence("bad", seq)])
    assert "Timing check failed" in card.body_html
    assert "RF_DEAD_TIME" in card.body_html


def test_timing_card_for_two_sequences_names_each_file_and_only_the_failing_one_has_a_table():
    good = NamedSequence("good.seq", spin_echo_sequence())
    bad = NamedSequence("bad.seq", _bad_sequence())
    card = timing.timing_card([good, bad])
    assert "good.seq" in card.body_html
    assert "bad.seq" in card.body_html
    assert card.body_html.index("good.seq") < card.body_html.index("bad.seq")
    assert "Timing check passed" in card.body_html
    assert "Timing check failed" in card.body_html
    assert card.body_html.count("<table") == 1
    good_part, bad_part = card.body_html.split("bad.seq", 1)
    assert "RF_DEAD_TIME" not in good_part
    assert "RF_DEAD_TIME" in bad_part


def test_timing_card_escapes_file_names():
    seqs = [NamedSequence("a<b>", spin_echo_sequence()), NamedSequence("c", spin_echo_sequence())]
    card = timing.timing_card(seqs)
    assert "a<b>" not in card.body_html
    assert "a&lt;b&gt;" in card.body_html


def test_render_page_accepts_timing_card():
    card = timing.timing_card([NamedSequence("se", spin_echo_sequence())])
    result = page.render_page("t", "s", [card])
    assert "<h2>Timing check</h2>" in result
