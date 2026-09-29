import json

import pypulseq as pp
import pytest
from synthetic import SYSTEM, empty_sequence, spin_echo_sequence

from pulseq_reports import page, pns
from pulseq_reports.asc import EXAMPLE_HARDWARE
from pulseq_reports.cards.pns import _pns_data, pns_card
from pulseq_reports.seq_index import sequence_index

_DATA_KEYS = {
    "reason",
    "hardware",
    "asc_file",
    "example",
    "peak_percent",
    "peak_time_ms",
    "axis_peaks_percent",
}


@pytest.fixture(scope="module")
def default_seq():
    return spin_echo_sequence()


def _three_trs(peak_tr: int) -> pp.Sequence:
    """Three 50 ms TRs on the synthetic system, each a Gy trapezoid and a delay. TR
    `peak_tr` has the fastest slew (0.1 ms rise/fall instead of 0.4 ms), so its PNS is the
    highest."""
    seq = pp.Sequence(SYSTEM)
    for i in range(3):
        g = pp.make_trapezoid(
            channel="y",
            amplitude=0.3 * SYSTEM.max_grad,
            rise_time=0.1e-3 if i == peak_tr else 0.4e-3,
            flat_time=2e-3,
            system=SYSTEM,
        )
        seq.add_block(g)
        seq.add_block(pp.make_delay(50e-3 - pp.calc_duration(g)))
    seq.set_definition("TR", 50e-3)
    return seq


def test_pns_data_for_spin_echo(default_seq):
    """`_pns_data` is `pns.pns_prediction`'s summary as a JSON-ready dict: no `lanes`,
    `end_ms` or `peak_tr_ms` any more (`docs/plans/diagram-lanes.md`, section 4.6). The
    PNS chart moved into the diagram's PNS lane, which this card no longer computes."""
    data = _pns_data(default_seq)
    assert set(data) == _DATA_KEYS
    assert data["reason"] is None
    assert data["example"] is True
    assert data["asc_file"] is None
    assert data["hardware"] == EXAMPLE_HARDWARE
    assert 0 < data["peak_percent"] < 100
    assert data["peak_percent"] >= max(data["axis_peaks_percent"].values())
    assert set(data["axis_peaks_percent"]) == {"x", "y", "z"}


def test_pns_data_matches_pns_prediction(default_seq):
    """`_pns_data`'s numbers are `pns.pns_prediction`'s own fields, in percent and ms,
    rounded the same way as the old chart-bearing card rounded them."""
    p = pns.pns_prediction(default_seq)
    data = _pns_data(default_seq)
    assert data["peak_percent"] == pytest.approx(100 * p.peak, abs=0.01)
    assert data["peak_time_ms"] == pytest.approx(1e3 * p.peak_time_s, abs=1e-4)
    for axis in "xyz":
        assert data["axis_peaks_percent"][axis] == pytest.approx(100 * p.axis_peaks[axis], abs=0.01)


@pytest.mark.parametrize("peak_tr", [0, 1, 2])
def test_pns_data_for_each_tr_position(peak_tr):
    """The card still reports the right peak for a sequence whose highest PNS is in a
    different TR (the TR-zoom feature itself moved to the diagram card's windows,
    `pns.peak_tr_window`, so it is not tested here any more)."""
    seq = _three_trs(peak_tr)
    p = pns.pns_prediction(seq)
    data = _pns_data(seq)
    assert data["peak_time_ms"] == pytest.approx(1e3 * p.peak_time_s, abs=1e-4)
    lo, hi = 50 * peak_tr, 50 * (peak_tr + 1)
    assert lo <= data["peak_time_ms"] <= hi


def test_report_has_pns_card(default_seq):
    card = pns_card(default_seq)
    assert card.id == "pns"
    assert card.title == "PNS prediction"
    assert card.script == "pns"

    body = card.body_html
    assert "is below the 100 % limit" in body
    assert "Example hardware, not a real scanner." in body
    assert f"<td>{EXAMPLE_HARDWARE}</td>" in body
    for label in ("Peak, all axes (%)", "Peak, Gx (%)", "Peak, Gy (%)", "Peak, Gz (%)"):
        assert f"<td>{label}</td>" in body
    # No chart any more: it moved into the diagram's PNS lane.
    assert '<div class="chart"' not in body
    assert "<svg" not in body
    assert "data-pns-view" not in body

    # render_page accepts the card, with its script: the section tag has the
    # "data-card-script" attribute (page.py adds it when Card.script is not None).
    result = page.render_page("Title", "Subtitle", [card])
    assert '<section class="card" id="pns" data-card-script="pns">' in result
    assert "<h2>PNS prediction</h2>" in result


def test_report_without_gradients_has_no_pns_table():
    card = pns_card(empty_sequence())
    result = page.render_page("Title", "Subtitle", [card])
    assert '<p class="muted">No PNS prediction: no gradients.</p>' in result
    assert "<table>" not in result


def test_card_id_is_used_for_the_section_and_data_element():
    """With a non-default `card_id`, the card's own id follows it (so two PNS cards,
    for example for two hardware files, can be on one page without an id clash), and its
    JSON data element key is that id too, with the card's data."""
    card = pns_card(spin_echo_sequence(), card_id="pns-b")
    assert card.id == "pns-b"
    assert card.script == "pns"
    result = page.render_page("Title", "Subtitle", [card])
    assert '<section class="card" id="pns-b" data-card-script="pns">' in result
    element = result.split('<script type="application/json" id="pns-b-data">')[1]
    assert json.loads(element.split("</script>")[0]) == card.data


def test_data_with_a_tr_definition_has_the_peak_tr_and_the_peak_time():
    """With a `TR` definition, `goto` is the TR that `pns.peak_tr_window` gives and the
    peak time as the anchor, and nothing else is in the data."""
    seq = _three_trs(1)
    p = pns.pns_prediction(seq)
    t0, t1 = pns.peak_tr_window(seq, p.peak_time_s)
    data = pns_card(seq).data
    assert data == {
        "format": 1,
        "goto": {"t0S": t0, "t1S": t1, "anchorS": p.peak_time_s},
    }
    assert (t0, t1) == pytest.approx((0.05, 0.10))


def test_data_without_a_tr_definition_has_the_block_of_the_peak(default_seq):
    """Without a `TR` definition (`pns.peak_tr_window` gives None), `goto` is the play
    index of the block that holds the peak time, and nothing else is in the data."""
    seq = default_seq
    p = pns.pns_prediction(seq)
    assert pns.peak_tr_window(seq, p.peak_time_s) is None
    data = pns_card(seq).data
    assert set(data) == {"format", "goto"}
    assert data["format"] == 1
    assert set(data["goto"]) == {"block"}
    index = sequence_index(seq)
    block = data["goto"]["block"]
    assert index.start_s[block] <= p.peak_time_s <= index.start_s[block] + index.duration_s[block]
    assert index.duration_s[block] > 0


def test_card_without_gradients_has_no_data_and_no_script():
    """No prediction (no gradients): nothing for a button to show, so the card has no
    data, no script and no button."""
    card = pns_card(empty_sequence())
    assert card.data is None
    assert card.script is None
    assert "<button" not in card.body_html
