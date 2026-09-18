import numpy as np
import pypulseq as pp
import pytest
from synthetic import SYSTEM, empty_sequence, spin_echo_sequence

from pulseq_reports import page, pns
from pulseq_reports.cards.pns import _active_samples, _max_envelope, pns_card, pns_data
from pulseq_reports.seq_utils import NamedSequence

_PNS_MAX_POINTS = 100_000
_PNS_ZERO_PERCENT = 0.01


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
    data = pns_data(default_seq)
    assert data["reason"] is None
    assert data["example"] is True
    assert data["asc_file"] is None
    assert data["hardware"] == pns.EXAMPLE_HARDWARE
    assert 0 < data["peak_percent"] < 100
    assert data["peak_percent"] >= max(data["axis_peaks_percent"].values())
    assert [lane["id"] for lane in data["lanes"]] == ["pns", "gx", "gy", "gz"]
    for lane in data["lanes"]:
        assert lane["unit"] == "%"
        assert lane["domain"] == [0.0, pytest.approx(110)]
        assert 0 < len(lane["segments"][0]) <= _PNS_MAX_POINTS
    all_axes = data["lanes"][0]["segments"][0]
    assert max(v for _, v in all_axes) == pytest.approx(data["peak_percent"], abs=0.01)
    assert all_axes[-1][0] == data["end_ms"]
    # One TR, and no TR definition: nothing to zoom to.
    assert data["peak_tr_ms"] is None


def test_max_envelope_keeps_the_maximum_of_each_run():
    t = np.arange(10_001) * 1e-5
    values = np.zeros(10_001)
    values[7_777] = 3.0
    et, ev = _max_envelope(t, values, 4000)
    assert len(ev) == len(et) <= 4000
    assert ev.max() == 3.0
    assert et[0] == 0


@pytest.mark.parametrize("peak_tr", [0, 1, 2])
def test_pns_data_zooms_to_the_tr_with_the_highest_pns(peak_tr):
    data = pns_data(_three_trs(peak_tr))
    lo, hi = 50 * peak_tr, 50 * (peak_tr + 1)
    assert data["peak_tr_ms"] == pytest.approx([lo, hi])
    assert lo <= data["peak_time_ms"] <= hi


def test_pns_data_without_a_tr_definition_has_no_zoom():
    seq = _three_trs(1)
    del seq.definitions["TR"]
    data = pns_data(seq)
    assert data["peak_tr_ms"] is None


def test_pns_lanes_keep_every_sample_above_the_floor():
    seq = _three_trs(1)
    p = pns.pns_prediction(seq)
    data = pns_data(seq)
    by_id = {lane["id"]: lane for lane in data["lanes"]}
    lane_values = {"pns": p.norm, "gx": p.axes["x"], "gy": p.axes["y"], "gz": p.axes["z"]}
    for lane_id, values in lane_values.items():
        lane_points = set(map(tuple, by_id[lane_id]["segments"][0]))
        expected = {
            (round(float(t) * 1e3, 4), round(float(100 * v), 2))
            for t, v in zip(p.t_s, values)
            if 100 * v > _PNS_ZERO_PERCENT
        }
        assert expected <= lane_points
        assert len(lane_points) < p.t_s.size


def test_active_samples_keep_the_ends_of_zero_runs():
    t = np.arange(10.0)
    values = np.array([0, 0, 0, 1, 2, 0, 0, 0, 0, 0.0])
    kept_t, kept_v = _active_samples(t, values, 0.01)
    assert list(kept_t) == [0, 2, 3, 4, 5, 9]
    assert list(kept_v) == [0, 0, 1, 2, 0, 0]


def test_report_has_peak_tr_buttons():
    card = pns_card(NamedSequence("three-trs", _three_trs(1)))
    body = card.body_html
    label = "TR with the highest PNS (50–100 ms)</button>"
    assert '<button type="button" data-pns-view="full" aria-pressed="true">' in body
    assert f'<button type="button" data-pns-view="peak-tr" aria-pressed="false">{label}' in body
    assert "counted from the sequence start in steps of the TR definition" in body


def test_report_has_pns_card(default_seq):
    card = pns_card(NamedSequence("vb-spin-echo", default_seq))
    assert card.id == "pns"
    assert card.title == "PNS prediction"
    assert card.script == "pns"

    body = card.body_html
    assert "is below the 100 % limit" in body
    assert "Example hardware, not a real scanner." in body
    assert f"<td>{pns.EXAMPLE_HARDWARE}</td>" in body
    for label in ("Peak, all axes (%)", "Peak, Gx (%)", "Peak, Gy (%)", "Peak, Gz (%)"):
        assert f"<td>{label}</td>" in body
    assert 'id="pns-diagram"' in body
    assert "data-pns-view" not in body  # one TR, no TR definition

    # render_page accepts the card, with its title and the id that the script and the
    # data element key on.
    result = page.render_page("Title", "Subtitle", [card])
    assert '<section class="card" id="pns" data-card-script="pns">' in result
    assert "<h2>PNS prediction</h2>" in result


def test_report_without_gradients_has_no_pns_chart():
    card = pns_card(NamedSequence("no-gradients", empty_sequence()))
    result = page.render_page("Title", "Subtitle", [card])
    assert '<p class="muted">No PNS prediction: no gradients.</p>' in result
    assert 'id="pns-diagram"' not in result


def test_card_ids_start_with_card_id(default_seq):
    """With a non-default `card_id`, every id in the card's body starts with it, so two
    PNS cards can be on one page."""
    card = pns_card(NamedSequence("vb-spin-echo", default_seq), card_id="pns-b")
    assert card.id == "pns-b"
    assert card.script == "pns"
    for element_id in ("pns-b-diagram", "pns-b-chart", "pns-b-tip"):
        assert f'id="{element_id}"' in card.body_html
    assert 'data-zoom-for="pns-b-diagram"' in card.body_html
    # No id from the default card_id leaks in.
    assert "pns-diagram" not in card.body_html.replace("pns-b-diagram", "")


def test_render_page_includes_pns_script_once(default_seq):
    card = pns_card(NamedSequence("vb-spin-echo", default_seq))
    result = page.render_page("Title", "Subtitle", [card])
    assert result.count(page.card_asset("pns")) == 1
