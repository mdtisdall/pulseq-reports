import re
from pathlib import Path

import numpy as np
import pytest
from pulseq_analysis.series import Series, SeriesKind
from pulseq_checks import (
    AnalysisResult,
    AnalysisState,
    Result,
    ResultMatrix,
    State,
    TargetInfo,
    read_profile,
    run_checks,
)
from synthetic import empty_sequence, spin_echo_sequence

from pulseq_reports import page
from pulseq_reports.cards.spectrum import spectrum_card
from pulseq_reports.registry import build_cards
from pulseq_reports.targets import report_targets

PROFILES = Path(__file__).parent / "profiles"
GAMMA_1H = 42.576e6
STEP_HZ = 500.0  # the frequency step of the series below: 0, 500, ..., 2000 Hz
CHECK_ID = "acoustic.resonance-energy"


def _series(scale: float = 1.0, *, window_s: float = 0.05, max_frequency_hz: float = 2000.0):
    """A `gradient_spectrum` series of 5 frequencies, in Hz/m/√Hz. `scale` 1 gives 1 to 5 mT/m/√Hz
    on x for the proton gamma."""
    k = np.arange(1, 6, dtype=np.float64)
    x = scale * GAMMA_1H * 1e-3 * k
    y = 0.5 * x
    z = 0.25 * x
    return Series(
        name="gradient_spectrum",
        kind=SeriesKind.SAMPLES,
        unit="Hz/m/sqrt(Hz)",
        coord_unit="Hz",
        arrays={"value": np.sqrt(x**2 + y**2 + z**2), "x": x, "y": y, "z": z},
        coord_start=0.0,
        coord_step=STEP_HZ,
        meta={
            "max_frequency_hz": max_frequency_hz,
            "window_s": window_s,
            "frequency_oversampling": 1,
        },
    )


def _done(name: str, series: Series | None) -> AnalysisResult:
    return AnalysisResult(
        "gradient.spectrum",
        1,
        name,
        AnalysisState.DONE,
        None,
        () if series is None else (series,),
    )


def _not_done(name: str, state: AnalysisState, reason: str) -> AnalysisResult:
    return AnalysisResult("gradient.spectrum", 1, name, state, reason, ())


def _check(name: str, state: State, value=None, limit=None, unit="%", reason=None) -> Result:
    return Result(CHECK_ID, 1, name, state, value, limit, unit, reason=reason)


def _matrix(names, analyses=(), results=()) -> ResultMatrix:
    targets = tuple(TargetInfo(name=n, sources={}, unused_sections=()) for n in names)
    return ResultMatrix("x.seq", "0", targets, tuple(results), tuple(analyses))


@pytest.fixture(scope="module")
def default_seq():
    return spin_echo_sequence()


@pytest.fixture
def make_targets(make_profile):
    """`make_targets(*gammas)` is the `ReportTarget` of a profile named `t1`, `t2`, ... for each
    gamma (Hz/T). The profiles have no resonances."""

    def make(*gammas):
        return report_targets(
            [make_profile(f"t{k}", f"gamma = {gamma!r}") for k, gamma in enumerate(gammas, 1)]
        )

    return make


@pytest.fixture(scope="module")
def target_a():
    return report_targets([read_profile(PROFILES / "example_a.toml")])[0]


def _muted_notes(card) -> list[str]:
    return re.findall(r'<p class="muted">(.*?)</p>', card.body_html)


def _line(card, name: str) -> str:
    """The check line (`<li>`) of the target `name` in the body of `card`."""
    (line,) = [m for m in re.findall(r"<li>.*?</li>", card.body_html) if name in m]
    return line


@pytest.mark.parametrize(
    "case",
    ["no target", "no matrix", "no analysis result", "not evaluated", "error", "no gradient"],
)
def test_without_a_chart_the_data_has_a_reason_and_no_lanes(default_seq, make_targets, case):
    (a,) = make_targets(GAMMA_1H)
    name = a.profile.name
    targets, matrix = {
        "no target": ((), _matrix([])),
        "no matrix": ((a,), None),
        "no analysis result": ((a,), _matrix([name])),
        "not evaluated": (
            (a,),
            _matrix([name], [_not_done(name, AnalysisState.NOT_EVALUATED, "no raster")]),
        ),
        "error": ((a,), _matrix([name], [_not_done(name, AnalysisState.ERROR, "it raised")])),
        "no gradient": ((a,), _matrix([name], [_done(name, None)])),
    }[case]

    card = spectrum_card(default_seq, targets=targets, check_results=matrix)

    assert card.data["reason"] is not None
    assert card.data["lanes"] == []
    assert card.data["max_frequency_hz"] is None
    assert card.script == "spectrum"
    assert f'id="{card.id}-diagram"' not in card.body_html
    assert "data-scale" not in card.body_html


def test_a_result_that_is_not_done_gives_its_reason_in_the_body_escaped(default_seq, make_targets):
    a, b = make_targets(GAMMA_1H, GAMMA_1H)
    matrix = _matrix(
        ["t1", "t2"],
        [
            _not_done("t1", AnalysisState.ERROR, "bad <b>value</b> & more"),
            _not_done("t2", AnalysisState.NOT_EVALUATED, "no raster"),
        ],
    )

    card = spectrum_card(default_seq, targets=(a, b), check_results=matrix)

    notes = " ".join(_muted_notes(card))
    assert "bad &lt;b&gt;value&lt;/b&gt; &amp; more" in notes
    assert "no raster" in notes
    assert "<b>" not in card.body_html


def test_a_not_done_target_is_named_next_to_a_target_that_is_drawn(default_seq, make_targets):
    a, b = make_targets(GAMMA_1H, GAMMA_1H)
    matrix = _matrix(
        ["t1", "t2"],
        [_done("t1", _series()), _not_done("t2", AnalysisState.ERROR, "it raised")],
    )

    card = spectrum_card(default_seq, targets=(a, b), check_results=matrix)

    assert card.data["reason"] is None
    assert [lane["id"] for lane in card.data["lanes"]] == ["gx", "gy", "gz", "rss"]
    assert any("t2" in note and "it raised" in note for note in _muted_notes(card))


def test_one_target_gives_four_lanes_of_the_series_in_mt_per_m(default_seq, make_targets):
    (a,) = make_targets(GAMMA_1H)
    series = _series()

    card = spectrum_card(
        default_seq, targets=(a,), check_results=_matrix(["t1"], [_done("t1", series)])
    )

    data = card.data
    assert data["reason"] is None
    assert data["max_frequency_hz"] == 2000.0
    assert data["db_floor"] == -80
    assert [lane["id"] for lane in data["lanes"]] == ["gx", "gy", "gz", "rss"]
    assert [lane["color"] for lane in data["lanes"]] == ["gx", "gy", "gz", "ink-2"]
    arrays = [series.arrays[k] for k in ("x", "y", "z", "value")]
    for lane, array in zip(data["lanes"], arrays):
        assert "series" not in lane
        assert lane["unit"] == "mT/m/√Hz"
        (points,) = lane["segments"]
        assert [f for f, _ in points] == [0.0, 500.0, 1000.0, 1500.0, 2000.0]
        # mT/m/√Hz: the value in Hz/m/√Hz times 1e3 / |γ|
        assert [v for _, v in points] == pytest.approx(array * 1e3 / GAMMA_1H, rel=1e-3)
    peak = float(series.arrays["value"].max()) * 1e3 / GAMMA_1H
    for lane in data["lanes"]:
        assert lane["domain"] == pytest.approx([0.0, 1.1 * peak])
        assert lane["ticks"] == pytest.approx([0.0, peak])


def test_the_frequency_of_a_sample_follows_coord_start_and_coord_step(default_seq, make_targets):
    (a,) = make_targets(GAMMA_1H)
    series = _series()
    shifted = Series(
        name=series.name,
        kind=series.kind,
        unit=series.unit,
        coord_unit=series.coord_unit,
        arrays=dict(series.arrays),
        coord_start=10.0,
        coord_step=25.0,
        meta=dict(series.meta),
    )

    card = spectrum_card(
        default_seq, targets=(a,), check_results=_matrix(["t1"], [_done("t1", shifted)])
    )

    (points,) = card.data["lanes"][0]["segments"]
    assert [f for f, _ in points] == [10.0, 35.0, 60.0, 85.0, 110.0]


def test_targets_with_the_same_spectrum_and_gamma_are_one_group(default_seq, make_targets):
    (a,) = make_targets(GAMMA_1H)
    a2, b2 = make_targets(GAMMA_1H, GAMMA_1H)
    one = spectrum_card(
        default_seq, targets=(a,), check_results=_matrix(["t1"], [_done("t1", _series())])
    )

    two = spectrum_card(
        default_seq,
        targets=(a2, b2),
        check_results=_matrix(["t1", "t2"], [_done("t1", _series()), _done("t2", _series())]),
    )

    assert two.data["lanes"] == one.data["lanes"]
    assert all("series" not in lane for lane in two.data["lanes"])


def test_a_negative_gamma_is_in_the_group_of_its_magnitude(default_seq, make_targets):
    a, b = make_targets(GAMMA_1H, -GAMMA_1H)
    matrix = _matrix(["t1", "t2"], [_done("t1", _series()), _done("t2", _series())])

    card = spectrum_card(default_seq, targets=(a, b), check_results=matrix)

    assert all("series" not in lane for lane in card.data["lanes"])
    assert card.data["lanes"][3]["segments"][0][-1][1] == pytest.approx(
        5 * np.sqrt(1 + 0.25 + 0.0625), rel=1e-3
    )


def test_targets_with_different_magnitudes_give_a_series_each_in_their_colors(
    default_seq, make_targets
):
    a, b = make_targets(GAMMA_1H, GAMMA_1H / 2)
    series = _series()
    matrix = _matrix(["t1", "t2"], [_done("t1", series), _done("t2", series)])

    card = spectrum_card(default_seq, targets=(a, b), check_results=matrix)

    lanes = card.data["lanes"]
    assert [lane["id"] for lane in lanes] == ["gx", "gy", "gz", "rss"]
    for lane, key in zip(lanes, ("x", "y", "z", "value")):
        assert lane["segments"] == []
        first, second = lane["series"]
        assert [first["color"], second["color"]] == ["target-1", "target-2"]
        assert "t1" in first["label"] and "t2" not in first["label"]
        assert "t2" in second["label"] and "t1" not in second["label"]
        array = series.arrays[key]
        # series k has the |γ| of group k: the value times 1e3 / |γ|
        (points_1,) = first["segments"]
        (points_2,) = second["segments"]
        assert [v for _, v in points_1] == pytest.approx(array * 1e3 / GAMMA_1H, rel=1e-3)
        assert [v for _, v in points_2] == pytest.approx(array * 1e3 / (GAMMA_1H / 2), rel=1e-3)
    # one value range for every lane and series: 1.1 times the largest RSS of all groups
    peak = float(series.arrays["value"].max()) * 1e3 / (GAMMA_1H / 2)
    for lane in lanes:
        assert lane["domain"] == pytest.approx([0.0, 1.1 * peak])
        assert lane["ticks"] == pytest.approx([0.0, peak])


def test_targets_with_one_gamma_and_different_spectra_give_a_series_each(default_seq, make_targets):
    a, b, c = make_targets(GAMMA_1H, GAMMA_1H, GAMMA_1H)
    matrix = _matrix(
        ["t1", "t2", "t3"],
        [_done("t1", _series()), _done("t2", _series(2.0)), _done("t3", _series())],
    )

    card = spectrum_card(default_seq, targets=(a, b, c), check_results=matrix)

    for lane in card.data["lanes"]:
        first, second = lane["series"]  # t1 and t3 share the first
        assert "t1" in first["label"] and "t3" in first["label"] and "t2" not in first["label"]
        assert "t2" in second["label"]
        assert [first["color"], second["color"]] == ["target-1", "target-2"]
        ratio = [v2 / v1 for (_, v1), (_, v2) in zip(first["segments"][0], second["segments"][0])]
        assert ratio == pytest.approx([2.0] * 5, rel=1e-3)


def test_the_window_and_the_frequency_come_from_the_series(default_seq, make_targets):
    (a,) = make_targets(GAMMA_1H)
    series = _series(window_s=0.02, max_frequency_hz=1000.0)

    card = spectrum_card(
        default_seq, targets=(a,), check_results=_matrix(["t1"], [_done("t1", series)])
    )

    assert card.data["max_frequency_hz"] == 1000.0
    method = _muted_notes(card)[-1]
    assert "20 ms" in method and "1000 Hz" in method
    assert "50 ms" not in method and "2000 Hz" not in method


def test_each_target_with_resonances_has_its_bands_in_its_color(default_seq, make_profile):
    plain = make_profile("plain")
    a, b = (read_profile(PROFILES / f"example_{k}.toml") for k in "ab")
    targets = report_targets([a, plain, b])
    names = [t.profile.name for t in targets]
    matrix = _matrix(names, [_done(n, _series()) for n in names])

    card = spectrum_card(default_seq, targets=targets, check_results=matrix)

    assert card.data["resonances"] == [
        {"lo": 640.0, "hi": 760.0, "color": "target-1", "target": a.name},
        {"lo": 1200.0, "hi": 1400.0, "color": "target-1", "target": a.name},
        {"lo": 760.0, "hi": 840.0, "color": "target-3", "target": b.name},
        {"lo": 1375.0, "hi": 1625.0, "color": "target-3", "target": b.name},
    ]
    assert "bands" not in card.data


def test_the_bands_are_in_the_data_without_a_chart(default_seq, target_a):
    card = spectrum_card(default_seq, targets=(target_a,))

    assert card.data["reason"] is not None
    assert [(r["lo"], r["hi"]) for r in card.data["resonances"]] == [(640, 760), (1200, 1400)]


def test_a_target_without_resonances_is_named_in_a_note(default_seq, make_profile, target_a):
    plain = report_targets([make_profile("Plain target")])[0]
    targets = (target_a, plain)
    names = [t.profile.name for t in targets]
    matrix = _matrix(names, [_done(n, _series()) for n in names])

    card = spectrum_card(default_seq, targets=targets, check_results=matrix)

    notes = _muted_notes(card)
    assert any("Plain target" in note for note in notes)
    assert not any(target_a.profile.name in note for note in notes)


def test_each_target_has_a_check_line_with_its_state_and_value(default_seq, make_targets):
    a, b, c, d = make_targets(GAMMA_1H, GAMMA_1H, GAMMA_1H, GAMMA_1H)
    results = [
        _check("t1", State.PASS, 12.3, 30.0),
        _check("t2", State.FAIL, 45.6, 30.0),
        _check("t3", State.NOT_EVALUATED, reason="a <band> over the spectrum"),
    ]  # t4 has no result of the check; the result of another check does not count
    results.append(Result("timing.rasters", 1, "t4", State.PASS))
    names = ["t1", "t2", "t3", "t4"]
    matrix = _matrix(names, [_done(n, _series()) for n in names], results)

    card = spectrum_card(default_seq, targets=(a, b, c, d), check_results=matrix)

    first = _line(card, "t1")
    assert "pass" in first and "12.3" in first and "30" in first and "%" in first
    assert 'style="background: var(--target-1)"' in first
    second = _line(card, "t2")
    assert "fail" in second and "45.6" in second and "var(--target-2)" in second
    third = _line(card, "t3")
    assert "not evaluated" in third and "a &lt;band&gt; over the spectrum" in third
    assert "<band>" not in card.body_html
    fourth = _line(card, "t4")
    assert "var(--target-4)" in fourth
    assert not any(word in fourth for word in ("pass", "fail", "%"))
    assert "<table" not in card.body_html


def test_the_check_line_does_not_depend_on_the_chart(default_seq, make_targets):
    a, b = make_targets(GAMMA_1H, GAMMA_1H)
    matrix = _matrix(
        ["t1", "t2"],
        [_not_done("t1", AnalysisState.ERROR, "it raised"), _done("t2", None)],
        [_check("t1", State.PASS, 1.5, 30.0)],
    )

    card = spectrum_card(default_seq, targets=(a, b), check_results=matrix)

    assert card.data["reason"] is not None
    assert "pass" in _line(card, "t1") and "1.5" in _line(card, "t1")
    assert "pass" not in _line(card, "t2")


def test_a_card_from_a_real_run_has_the_spectrum_and_the_check_result(default_seq, target_a):
    matrix = run_checks(
        default_seq,
        [target_a.profile],
        select=[CHECK_ID],
        analyses=["gradient.spectrum"],
    )
    series = matrix.analysis(target_a.profile.name, "gradient.spectrum").series[0]
    (result,) = matrix.results

    (card,) = build_cards(
        default_seq, cards=["gradient-spectrum"], targets=[target_a.profile], check_results=matrix
    )

    assert card.data["reason"] is None
    assert card.data["max_frequency_hz"] == series.meta["max_frequency_hz"]
    rss = card.data["lanes"][3]["segments"][0]
    gamma = abs(target_a.gamma)
    assert [v for _, v in rss] == pytest.approx(series.arrays["value"] * 1e3 / gamma, rel=1e-3)
    assert rss[1][0] == pytest.approx(series.coord_step, rel=1e-3)
    line = _line(card, target_a.profile.name)
    assert result.state.value in line and f"{result.value:.3g}" in line


def test_a_real_run_for_a_sequence_without_gradients_has_no_chart(target_a):
    seq = empty_sequence()
    matrix = run_checks(seq, [target_a.profile], select=[], analyses=["gradient.spectrum"])

    card = spectrum_card(seq, targets=(target_a,), check_results=matrix)

    assert card.data["reason"] == "no gradients"
    assert card.data["lanes"] == []
    assert 'id="gradient-spectrum-diagram"' not in card.body_html


def test_report_has_gradient_spectrum_card(default_seq, make_targets):
    (a,) = make_targets(GAMMA_1H)
    card = spectrum_card(
        default_seq, targets=(a,), check_results=_matrix(["t1"], [_done("t1", _series())])
    )
    result = page.render_page("Title", "Subtitle", [card])
    body = result[result.index('id="gradient-spectrum"') :]

    assert "<h2>Gradient spectrum</h2>" in body
    assert 'id="gradient-spectrum-diagram"' in body
    assert '<button type="button" data-scale="linear" aria-pressed="true">Linear</button>' in body
    assert '<button type="button" data-scale="db" aria-pressed="false">dB</button>' in body
    assert "drawn at −80 dB" in body


def test_custom_card_id_changes_element_ids(default_seq, make_targets):
    (a,) = make_targets(GAMMA_1H)
    card = spectrum_card(
        default_seq,
        targets=(a,),
        check_results=_matrix(["t1"], [_done("t1", _series())]),
        card_id="spectrum-b",
    )

    assert card.id == "spectrum-b"
    assert 'id="spectrum-b-chart"' in card.body_html
    assert 'id="spectrum-b-diagram"' in card.body_html
    assert 'id="spectrum-b-tip"' in card.body_html
    assert 'data-zoom-for="spectrum-b-diagram"' in card.body_html


def test_render_page_includes_spectrum_script_once(default_seq):
    cards = [
        spectrum_card(default_seq, card_id="spectrum-a"),
        spectrum_card(default_seq, card_id="spectrum-b"),
    ]

    result = page.render_page("Title", "Subtitle", cards)

    assert result.count('PulseqReport.registerCard("spectrum"') == 1
