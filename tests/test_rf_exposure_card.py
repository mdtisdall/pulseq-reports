import math

import pytest
from synthetic import empty_sequence, gre_sequence, spin_echo_sequence

from pulseq_reports import page
from pulseq_reports.cards.rf_exposure import rf_exposure_card, rf_exposure_data
from pulseq_reports.seq_utils import GAMMA, NamedSequence


def _b1_ut(flip_rad: float, duration_s: float) -> float:
    """The constant B1 (µT) of a block pulse with this flip angle and duration."""
    return (flip_rad / (2 * math.pi)) / duration_s / GAMMA * 1e6


@pytest.fixture(scope="module")
def default_seq():
    return spin_echo_sequence()


def _refocusing_block_id(seq) -> int:
    for block_id in seq.block_events:
        rf = getattr(seq.get_block(block_id), "rf", None)
        if rf is not None and rf.use == "refocusing":
            return int(block_id)
    raise AssertionError("no refocusing pulse in sequence")


def test_rf_exposure_data_for_spin_echo(default_seq):
    data = rf_exposure_data(default_seq)
    b1_ex = _b1_ut(math.pi / 2, 1e-3)
    b1_ref = _b1_ut(math.pi, 1e-3)

    assert data["num_pulses"] == 2
    assert data["duration_ms"] == pytest.approx(default_seq.duration()[0] * 1e3)
    # The refocusing pulse (180°) has twice the flip of the excitation pulse (90°) in the
    # same duration, so it has the higher B1 and is the peak.
    assert data["peak_b1_ut"] == pytest.approx(b1_ref, rel=1e-6)
    assert data["peak_block"] == _refocusing_block_id(default_seq)
    assert data["energy_ut2_ms"] == pytest.approx(b1_ex**2 + b1_ref**2, rel=1e-6)
    assert data["b1rms_ut"] == pytest.approx(
        math.sqrt(data["energy_ut2_ms"] / data["duration_ms"]), rel=1e-4
    )
    assert data["window_s"] == 10.0
    assert data["window_used_s"] == 10.0
    # The window is at least as energetic as one period, since it can include more than one
    # repetition of the (much shorter than 10 s) sequence.
    assert data["b1rms_window_ut"] >= data["b1rms_ut"]
    assert data["periodic"] is True


def test_report_has_rf_exposure_card(default_seq):
    card = rf_exposure_card([NamedSequence("vb-spin-echo", default_seq)])
    assert card.id == "rf-exposure"
    assert card.title == "RF exposure"
    assert card.data is None
    assert card.script is None

    result = page.render_page("Title", "Subtitle", [card])
    body = result[result.index('id="rf-exposure"') :]
    assert "<h2>RF exposure</h2>" in body
    for label in (
        "RF pulses",
        "Peak B1 (µT)",
        "∫B1² dt over the sequence (µT²·ms)",
        "Sequence duration (ms)",
        "B1+rms, sequence repeated (µT)",
        "B1+rms, highest 10 s window (µT)",
    ):
        assert f"<td>{label}</td>" in body


def test_rf_exposure_card_without_rf():
    card = rf_exposure_card([NamedSequence("no-rf", empty_sequence())])
    assert card.body_html == '<p class="muted">No RF pulses.</p>'
    result = page.render_page("Title", "Subtitle", [card])
    assert '<p class="muted">No RF pulses.</p>' in result


def test_rf_exposure_card_two_files():
    seqs = [
        NamedSequence("spin-echo.seq", spin_echo_sequence()),
        NamedSequence("gre.seq", gre_sequence()),
    ]
    card = rf_exposure_card(seqs)
    body = card.body_html

    assert "<h3>spin-echo.seq</h3>" in body
    assert "<h3>gre.seq</h3>" in body
    assert "<h3>All files</h3>" in body
    assert (
        body.index("<h3>spin-echo.seq</h3>")
        < body.index("<h3>gre.seq</h3>")
        < body.index("<h3>All files</h3>")
    )

    spin_echo_data = rf_exposure_data(seqs[0].seq)
    gre_data = rf_exposure_data(seqs[1].seq)
    all_files_peak_b1 = max(spin_echo_data["peak_b1_ut"], gre_data["peak_b1_ut"])
    assert f"<td>{all_files_peak_b1:.2f}</td>" in body[body.index("<h3>All files</h3>") :]
    assert "sequence repeated" in body[body.index("<h3>All files</h3>") :]

    # render_page accepts a card built for more than one file too.
    page.render_page("Title", "Subtitle", [card])


def test_rf_exposure_card_two_files_not_periodic_omits_repeated_wording():
    seqs = [
        NamedSequence("spin-echo.seq", spin_echo_sequence()),
        NamedSequence("gre.seq", gre_sequence()),
    ]
    card = rf_exposure_card(seqs, periodic=False)
    all_files_html = card.body_html[card.body_html.index("<h3>All files</h3>") :]
    assert "sequence repeated" not in all_files_html
    assert "files played once" in all_files_html
