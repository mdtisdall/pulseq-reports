import math
import re

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


def _error_count(body_html: str) -> int:
    """The number that the first sentence of the body gives for the errors."""
    return int(re.search(r"gave (\d+) error", body_html).group(1))


def test_timing_card_for_one_sequence_matches_timing_html():
    seq = spin_echo_sequence()
    card = timing.timing_card(seq)
    assert card.id == "timing"
    assert card.title == "Timing check"
    assert card.body_html == timing._timing_html(timing._timing_errors(seq))
    assert card.data is None
    assert card.script is None


def test_timing_card_of_a_sequence_without_timing_errors_has_no_error_table():
    card = timing.timing_card(spin_echo_sequence())

    assert _error_count(card.body_html) == 0
    assert "<table" not in card.body_html


def test_timing_card_lists_timing_errors_for_one_sequence():
    seq = _bad_sequence()
    errors = timing._timing_errors(seq)
    assert any(e.get("error_type") == "RF_DEAD_TIME" for e in errors)
    card = timing.timing_card(seq)
    assert _error_count(card.body_html) == len(errors) >= 1
    # The header row, and one row for each error.
    assert card.body_html.count("<tr>") == 1 + len(errors)
    assert "RF_DEAD_TIME" in card.body_html


def test_timing_card_has_no_verdict():
    for seq in (spin_echo_sequence(), _bad_sequence()):
        card = timing.timing_card(seq)

        assert "status good" not in card.body_html
        assert "status bad" not in card.body_html


def test_render_page_accepts_timing_card():
    card = timing.timing_card(spin_echo_sequence())
    result = page.render_page("t", "s", [card])
    assert "<h2>Timing check</h2>" in result
