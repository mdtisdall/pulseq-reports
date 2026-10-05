import json
from pathlib import Path

import pypulseq as pp
import pytest
from pulseq_analysis import pns
from pulseq_analysis.seq_index import sequence_index
from pulseq_checks import read_profile, run_checks
from synthetic import SYSTEM, empty_sequence, spin_echo_sequence

from pulseq_reports import page
from pulseq_reports.cards.pns import _pns_data, pns_card, pns_series
from pulseq_reports.targets import report_targets

PROFILES = Path(__file__).parent / "profiles"
A = read_profile(PROFILES / "example_a.toml")
B = read_profile(PROFILES / "example_b.toml")
C = read_profile(PROFILES / "example_c.toml")  # a negative gamma


@pytest.fixture(scope="module")
def default_seq():
    return spin_echo_sequence()


def forbid_safe_model(monkeypatch):
    """Make the SAFE model of pulseq-analysis (the chunk function that each of its PNS
    functions calls) raise `AssertionError`, so a test shows that a card does not run it.
    Call it after the result matrix is made: `run_checks` runs the model."""

    def raise_error(*args, **kwargs):
        raise AssertionError("the SAFE model ran")

    monkeypatch.setattr("pulseq_analysis.pns_levels._safe_gwf_to_pns_chunk", raise_error)


def _matrix(seq, profiles, tmp_path):
    """The result matrix of the analysis `pns.safe.levels` for `profiles`. One target runs on
    the sequence object, several on a file in `tmp_path`."""
    if len(profiles) == 1:
        sequence = seq
    else:
        sequence = str(tmp_path / "seq.seq")
        seq.write(sequence)
    return run_checks(sequence, list(profiles), select=[], analyses=["pns.safe.levels"])


def _card(seq, profiles, tmp_path, **kwargs):
    return pns_card(
        seq,
        targets=report_targets(profiles),
        check_results=_matrix(seq, profiles, tmp_path),
        **kwargs,
    )


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


def test_pns_data_is_the_percent_of_the_threshold_of_the_result(default_seq, tmp_path):
    """`_pns_data` gives the peak, the time of the peak and the axis peaks of `pns_total` in
    percent: `100 * v / meta["threshold"]` of `pns_above_0` (P38), and the time in ms."""
    matrix = _matrix(default_seq, [A], tmp_path)
    (total, above), reason = pns_series(matrix, A.name)
    assert reason is None
    data = _pns_data(total, above)
    threshold = above.meta["threshold"]
    assert threshold == abs(A.make_opts().gamma)
    assert data["peak_percent"] == pytest.approx(100 * total.meta["peak"] / threshold, rel=1e-12)
    assert 0 < data["peak_percent"] < 100
    assert data["peak_time_ms"] == pytest.approx(1e3 * total.meta["peak_time_s"], rel=1e-12)
    for axis in "xyz":
        assert data["axis_peaks_percent"][axis] == pytest.approx(
            100 * total.meta[f"axis_peaks_{axis}"] / threshold, rel=1e-12
        )
    assert data["hardware"] == total.meta["hardware"]
    assert data["asc_file"] is None
    assert data["peak_percent"] >= max(data["axis_peaks_percent"].values())


def test_the_percent_of_a_negative_gamma_target_uses_its_magnitude(default_seq, tmp_path):
    """The PNS values of pulseq-analysis are in Hz/T from samples in Hz/m, so the same sequence
    and the same SAFE parameters give the same value for a target with the gamma of the proton
    (A) and for one with a negative gamma (C). Their thresholds are the magnitudes of their
    gammas, so the percent of C is the percent of A times the ratio of the magnitudes."""
    matrix = _matrix(default_seq, [A, C], tmp_path)
    (total_a, above_a), _ = pns_series(matrix, A.name)
    (total_c, above_c), _ = pns_series(matrix, C.name)
    assert A.make_opts().gamma > 0 > C.make_opts().gamma
    assert above_c.meta["threshold"] == abs(C.make_opts().gamma)
    assert total_c.meta["peak"] == pytest.approx(total_a.meta["peak"], rel=1e-12)
    percent_a = _pns_data(total_a, above_a)["peak_percent"]
    percent_c = _pns_data(total_c, above_c)["peak_percent"]
    assert percent_c > 0
    assert percent_c == pytest.approx(percent_a * abs(A.make_opts().gamma / C.make_opts().gamma))


def test_the_card_shows_the_percent_of_each_target(default_seq, tmp_path):
    """The table of a target shows its own peak percent (to one decimal), so two targets with
    thresholds that differ show different numbers."""
    card = _card(default_seq, [A, C], tmp_path)
    matrix = _matrix(default_seq, [A, C], tmp_path)
    body = card.body_html
    for profile in (A, C):
        (total, above), _ = pns_series(matrix, profile.name)
        data = _pns_data(total, above)
        assert f"{data['peak_percent']:.1f} at {data['peak_time_ms']:.3f} ms" in body
        for axis in "xyz":
            assert f"<td>{data['axis_peaks_percent'][axis]:.1f}</td>" in body
        assert f"<td>{data['hardware']}</td>" in body


def test_report_has_pns_card(default_seq, tmp_path):
    card = _card(default_seq, [A], tmp_path)
    assert card.id == "pns"
    assert card.title == "PNS prediction"
    assert card.script == "pns"

    body = card.body_html
    for label in ("Peak, all axes (%)", "Peak, Gx (%)", "Peak, Gy (%)", "Peak, Gz (%)"):
        assert f"<td>{label}</td>" in body
    assert A.name in body
    assert "var(--target-1)" in body
    # No chart: it is the PNS lane of the diagram.
    assert '<div class="chart"' not in body
    assert "<svg" not in body
    # No verdict.
    assert "status good" not in body
    assert "status bad" not in body

    # render_page accepts the card, with its script: the section tag has the
    # "data-card-script" attribute (page.py adds it when Card.script is not None).
    result = page.render_page("Title", "Subtitle", [card])
    assert '<section class="card" id="pns" data-card-script="pns">' in result
    assert "<h2>PNS prediction</h2>" in result


def test_two_targets_have_one_part_each_in_order(default_seq, tmp_path):
    card = _card(default_seq, [C, A], tmp_path)
    body = card.body_html
    assert body.index(C.name) < body.index(A.name)
    assert body.index("var(--target-1)") < body.index(C.name)
    assert body.index("var(--target-2)") < body.index(A.name)
    assert body.count("<table>") == 2
    assert body.count("<button") == 2
    assert 'id="pns-goto-0"' in body
    assert 'id="pns-goto-1"' in body
    assert body.index('id="pns-goto-0"') < body.index(A.name)


def test_the_goto_list_has_one_entry_for_each_target(default_seq, make_profile, tmp_path):
    """A target with a PNS result has the payload of its button, and a target without SAFE
    parameters has `None` and no button."""
    no_safe = make_profile("no safe")
    card = _card(default_seq, [A, no_safe, C], tmp_path)
    assert card.data["format"] == 2
    goto = card.data["goto"]
    assert len(goto) == 3
    assert goto[0] is not None and goto[2] is not None
    assert goto[1] is None
    assert goto[0] == goto[2]  # the same sequence and the same Hz/T model: the same peak
    body = card.body_html
    assert 'id="pns-goto-0"' in body
    assert 'id="pns-goto-1"' not in body
    assert 'id="pns-goto-2"' in body


def test_a_target_that_is_not_evaluated_has_its_reason_and_no_table(
    default_seq, make_profile, tmp_path
):
    no_safe = make_profile("no safe")
    matrix = _matrix(default_seq, [no_safe], tmp_path)
    reason = matrix.analysis("no safe", "pns.safe.levels").reason
    assert reason
    card = pns_card(default_seq, targets=report_targets([no_safe]), check_results=matrix)

    assert "no safe" in card.body_html
    assert "model pns.safe" in card.body_html  # a part of the reason of pulseq-checks
    assert "<table" not in card.body_html
    assert "<button" not in card.body_html
    assert card.data is None
    assert card.script is None
    assert card.scripts == ()


def test_a_target_name_and_a_reason_are_escaped(default_seq, make_profile, tmp_path):
    profile = make_profile("a<b>&")
    matrix = _matrix(default_seq, [profile], tmp_path)
    card = pns_card(default_seq, targets=report_targets([profile]), check_results=matrix)

    assert "a&lt;b&gt;&amp;" in card.body_html
    assert "a<b>" not in card.body_html


def test_a_target_without_a_result_in_the_matrix_says_so(default_seq, make_profile, make_matrix):
    profile = make_profile("no result")
    card = pns_card(
        default_seq, targets=report_targets([profile]), check_results=make_matrix(["no result"])
    )

    assert "no result" in card.body_html
    assert "pns.safe.levels" in card.body_html
    assert "<table" not in card.body_html
    assert card.data is None
    assert card.script is None


def test_without_targets_the_card_has_a_note_and_no_pns(default_seq, tmp_path, monkeypatch):
    matrix = _matrix(default_seq, [A], tmp_path)
    forbid_safe_model(monkeypatch)
    card = pns_card(default_seq, targets=(), check_results=matrix)

    assert card.id == "pns"
    assert card.data is None
    assert card.script is None
    assert card.scripts == ()
    assert "<table" not in card.body_html
    assert "<button" not in card.body_html
    assert card.body_html.startswith('<p class="muted">')
    assert card.error is None
    page.render_page("Title", "Subtitle", [card])


def test_without_a_matrix_the_card_has_a_note_and_no_pns(default_seq, monkeypatch):
    forbid_safe_model(monkeypatch)
    card = pns_card(default_seq, targets=report_targets([A]))

    assert card.data is None
    assert card.script is None
    assert card.scripts == ()
    assert "<table" not in card.body_html
    assert "<button" not in card.body_html
    assert A.name not in card.body_html
    assert card.body_html.startswith('<p class="muted">')


def test_the_card_runs_no_safe_model(default_seq, tmp_path, monkeypatch):
    """The card reads the matrix: with a matrix that has the result, it does not call the
    SAFE model."""
    matrix = _matrix(default_seq, [A], tmp_path)
    forbid_safe_model(monkeypatch)
    card = pns_card(default_seq, targets=report_targets([A]), check_results=matrix)
    assert card.data is not None


def test_card_without_gradients_has_no_data_and_no_script(tmp_path):
    """A sequence with no gradient event: the result is "done" with no series, so there is
    nothing for a button to show."""
    seq = empty_sequence()
    card = _card(seq, [A], tmp_path)
    assert A.name in card.body_html
    assert "<table" not in card.body_html
    assert card.data is None
    assert card.script is None
    assert "<button" not in card.body_html


def test_card_id_is_used_for_the_section_the_buttons_and_the_data_element(default_seq, tmp_path):
    """With a non-default `card_id`, the card's own id follows it (so two PNS cards can be on
    one page without an id clash), and so do the ids of its buttons and its JSON data
    element."""
    card = _card(default_seq, [A], tmp_path, card_id="pns-b")
    assert card.id == "pns-b"
    assert card.script == "pns"
    assert 'id="pns-b-goto-0"' in card.body_html
    result = page.render_page("Title", "Subtitle", [card])
    assert '<section class="card" id="pns-b" data-card-script="pns">' in result
    element = result.split('<script type="application/json" id="pns-b-data">')[1]
    assert json.loads(element.split("</script>")[0]) == card.data


def test_data_with_a_tr_definition_has_the_peak_tr_and_the_peak_time(tmp_path):
    """With a `TR` definition, `goto` is the TR that `pns.peak_tr_window` gives and the
    peak time as the anchor, and nothing else is in the data."""
    seq = _three_trs(1)
    matrix = _matrix(seq, [A], tmp_path)
    (total, _), _ = pns_series(matrix, A.name)
    peak_time_s = total.meta["peak_time_s"]
    t0, t1 = pns.peak_tr_window(seq, peak_time_s)
    data = pns_card(seq, targets=report_targets([A]), check_results=matrix).data
    assert data == {
        "format": 2,
        "goto": [{"t0S": t0, "t1S": t1, "anchorS": peak_time_s}],
    }
    assert (t0, t1) == pytest.approx((0.05, 0.10))


@pytest.mark.parametrize("peak_tr", [0, 1, 2])
def test_the_peak_is_in_the_tr_with_the_fastest_slew(peak_tr, tmp_path):
    """The card reports the right peak for a sequence whose highest PNS is in a different TR:
    the TR of its `goto` is that TR."""
    seq = _three_trs(peak_tr)
    card = _card(seq, [A], tmp_path)
    (goto,) = card.data["goto"]
    assert goto["t0S"] == pytest.approx(0.05 * peak_tr)
    assert goto["t1S"] == pytest.approx(0.05 * (peak_tr + 1))
    assert goto["t0S"] <= goto["anchorS"] <= goto["t1S"]


def test_data_without_a_tr_definition_has_the_block_of_the_peak(default_seq, tmp_path):
    """Without a `TR` definition (`pns.peak_tr_window` gives None), `goto` is the play
    index of the block that holds the peak time, and nothing else is in the data."""
    matrix = _matrix(default_seq, [A], tmp_path)
    (total, _), _ = pns_series(matrix, A.name)
    peak_time_s = total.meta["peak_time_s"]
    assert pns.peak_tr_window(default_seq, peak_time_s) is None
    data = pns_card(default_seq, targets=report_targets([A]), check_results=matrix).data
    assert set(data) == {"format", "goto"}
    assert data["format"] == 2
    (goto,) = data["goto"]
    assert set(goto) == {"block"}
    index = sequence_index(default_seq)
    block = goto["block"]
    assert index.start_s[block] <= peak_time_s <= index.start_s[block] + index.duration_s[block]
    assert index.duration_s[block] > 0
