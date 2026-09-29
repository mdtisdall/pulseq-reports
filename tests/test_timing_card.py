import math

import pypulseq as pp
from synthetic import SYSTEM, spin_echo_sequence

from pulseq_reports import page
from pulseq_reports.cards import timing


def _bad_sequence() -> pp.Sequence:
    """A single RF block whose delay is below the RF dead time, so `check_timing` fails."""
    seq = pp.Sequence(SYSTEM)
    rf = pp.make_block_pulse(flip_angle=math.pi / 2, duration=1e-3, system=SYSTEM)
    rf.delay = 0
    seq.add_block(rf)
    return seq


def test_timing_card_for_one_sequence_matches_timing_html():
    seq = spin_echo_sequence()
    card = timing.timing_card(seq)
    assert card.id == "timing"
    assert card.title == "Timing check"
    assert card.body_html == timing._timing_html(timing._timing_errors(seq))
    assert "Timing check passed" in card.body_html
    assert card.data is None
    assert card.script is None


def test_timing_card_lists_timing_errors_for_one_sequence():
    seq = _bad_sequence()
    errors = timing._timing_errors(seq)
    assert any(e.get("error_type") == "RF_DEAD_TIME" for e in errors)
    card = timing.timing_card(seq)
    assert "Timing check failed" in card.body_html
    assert "RF_DEAD_TIME" in card.body_html


def test_render_page_accepts_timing_card():
    card = timing.timing_card(spin_echo_sequence())
    result = page.render_page("t", "s", [card])
    assert "<h2>Timing check</h2>" in result
