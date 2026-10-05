"""Gradient spectrum card: the axis and RSS spectra of a sequence for the targets of a report,
from the analysis `gradient.spectrum` of the result matrix, with the acoustic resonance bands
of each target and its result of the check `acoustic.resonance-energy`."""

import html
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pypulseq as pp
from pulseq_analysis.extensions import refuse_rotations
from pulseq_analysis.series import Series
from pulseq_checks import AnalysisState, Result, ResultMatrix

from pulseq_reports.markup import (
    _AXIS_COLOR,
    Lane,
    _sig,
    fmt,
    lanes_json,
    zoom_controls,
)
from pulseq_reports.page import Card, card_asset
from pulseq_reports.registry import CardSpec, ReportContext
from pulseq_reports.targets import ReportTarget
from pulseq_reports.units import gamma_magnitude, hz_per_m_to_mt_per_m

_ANALYSIS_ID = "gradient.spectrum"
_SERIES_NAME = "gradient_spectrum"
_CHECK_ID = "acoustic.resonance-energy"
_COMPARED_ARRAYS = ("value", "x", "y", "z")  # the arrays of a series, in Hz/m/√Hz
_SPECTRUM_UNIT = "mT/m/√Hz"
_SPECTRUM_DB_FLOOR = -80  # the lowest value drawn on the spectrum's dB scale
_NO_GRADIENTS = "no gradients"


@dataclass
class _Group:
    """The targets that have one |γ| and one series: `gamma` is the magnitude (Hz/T),
    `names` the names of the targets in their order, and `color` the color of the first."""

    gamma: float
    series: Series
    names: list[str]
    color: str


def _same_series(a: Series, b: Series) -> bool:
    """True when the arrays `value`, `x`, `y` and `z`, `coord_start` and `coord_step` of `a`
    and `b` are equal, exactly."""
    return (
        a.coord_start == b.coord_start
        and a.coord_step == b.coord_step
        and all(np.array_equal(a.arrays[k], b.arrays[k]) for k in _COMPARED_ARRAYS)
    )


def _groups(
    targets: Sequence[ReportTarget], check_results: ResultMatrix | None
) -> tuple[list[_Group], list[str], str | None]:
    """The groups of the targets whose `gradient.spectrum` result is done and has a series,
    in the order of the first target of each group; the text of a problem for each target whose
    result is not done or is missing (the result matrix has some other result); and the reason
    that the card has no chart (None when there is a group)."""
    groups: list[_Group] = []
    problems: list[str] = []
    missing: list[str] = []
    no_gradient = False
    for target in targets:
        name = target.profile.name
        result = None if check_results is None else check_results.analysis(name, _ANALYSIS_ID)
        if result is None:
            missing.append(name)
        elif result.state is not AnalysisState.DONE:
            problems.append(
                f"{name}: no gradient spectrum ({result.reason or 'no reason is given'})."
            )
        else:
            series = next((s for s in result.series if s.name == _SERIES_NAME), None)
            if series is None:  # a done result with no series: no gradient event
                no_gradient = True
                continue
            gamma = gamma_magnitude(target.gamma)
            for group in groups:
                if group.gamma == gamma and _same_series(group.series, series):
                    group.names.append(name)
                    break
            else:
                groups.append(_Group(gamma, series, [name], target.color))

    if groups:
        reason = None
    elif not targets:
        reason = "no target (the spectrum is for the targets of the report)"
    elif check_results is None:
        reason = f"no result matrix (run the checks with the analysis {_ANALYSIS_ID})"
    elif no_gradient:
        reason = _NO_GRADIENTS
    elif len(missing) == len(targets):
        reason = f"the result matrix has no {_ANALYSIS_ID} result"
    else:
        reason = "no target has a gradient spectrum"
    if len(missing) < len(targets):
        problems += [f"{name}: the result matrix has no {_ANALYSIS_ID} result." for name in missing]
    return groups, problems, reason


def _label(group: _Group) -> str:
    return f"{', '.join(group.names)} (|γ| {group.gamma / 1e6:g} MHz/T)"


def _lanes(groups: list[_Group]) -> list[dict]:
    """The lanes Gx, Gy, Gz and RSS in mT/m/√Hz. One group: one line in each lane. Several
    groups: a lane has `series`, one for each group in color of its first target. All lanes
    share the value range of the largest RSS value."""
    values = []  # for each group, the arrays x, y, z and rss in mT/m/√Hz
    for group in groups:
        arrays = group.series.arrays
        values.append(
            {
                lane: hz_per_m_to_mt_per_m(np.asarray(arrays[key], dtype=np.float64), group.gamma)
                for lane, key in (("x", "x"), ("y", "y"), ("z", "z"), ("rss", "value"))
            }
        )
    peak = max(float(v["rss"].max()) for v in values)
    if peak > 0:
        domain, ticks, labels = [0.0, 1.1 * peak], [0.0, peak], ["0", fmt(peak)]
    else:
        domain, ticks, labels = [0.0, 1.0], [0.0], ["0"]

    points = []  # for each group, the segment of each lane
    for group, v in zip(groups, values):
        series = group.series
        frequency = series.coord_start + np.arange(v["rss"].size) * series.coord_step
        points.append(
            {
                lane: [[round(float(f), 3), _sig(float(a))] for f, a in zip(frequency, v[lane])]
                for lane in v
            }
        )

    several = len(groups) > 1
    lanes = []
    for lane, lane_id, title, color in [
        *((a, f"g{a}", f"G{a}", _AXIS_COLOR[a]) for a in "xyz"),
        ("rss", "rss", "RSS", "ink-2"),
    ]:
        data = lanes_json(
            [
                Lane(
                    id=lane_id,
                    title=title,
                    unit=_SPECTRUM_UNIT,
                    color=color,
                    segments=[] if several else [points[0][lane]],
                    domain=domain,
                    ticks=ticks,
                    tick_labels=labels,
                )
            ]
        )[0]
        if several:
            data["series"] = [
                {"label": f"{title}: {_label(group)}", "color": group.color, "segments": [p[lane]]}
                for group, p in zip(groups, points)
            ]
        lanes.append(data)
    return lanes


def _spectrum_data(
    groups: list[_Group], reason: str | None, targets: Sequence[ReportTarget]
) -> dict:
    """The JSON-ready data of the card, in Hz and mT/m/√Hz: `reason` (the card has no chart
    when it is not None), `max_frequency_hz` of the first series, `db_floor`, `lanes`, and
    `resonances`, the band `{lo, hi, color, target}` of each resonance of each target."""
    return {
        "reason": reason,
        "max_frequency_hz": (
            None if reason is not None else float(groups[0].series.meta["max_frequency_hz"])
        ),
        "db_floor": _SPECTRUM_DB_FLOOR,
        "lanes": [] if reason is not None else _lanes(groups),
        "resonances": [
            {
                "lo": float(frequency) - float(bandwidth) / 2,
                "hi": float(frequency) + float(bandwidth) / 2,
                "color": target.color,
                "target": target.profile.name,
            }
            for target in targets
            for frequency, bandwidth in target.profile.acoustic_resonances or ()
        ],
    }


def _check_result(check_results: ResultMatrix | None, name: str) -> Result | None:
    if check_results is None:
        return None
    return next(
        (r for r in check_results.results if r.check_id == _CHECK_ID and r.target == name), None
    )


def _check_text(result: Result | None) -> str:
    """The state of `result` with its value and limit and their unit, or its reason when it has
    no value; or the note that the check did not run for `None`."""
    if result is None:
        return "the check did not run"
    state = result.state.value
    if result.value is None:
        return f"{state}, {result.reason or 'no reason is given'}"
    unit = f" {result.unit}" if result.unit else ""
    text = f"{state}, {fmt(result.value)}{unit}"
    if result.limit is not None:
        text += f" (limit {fmt(result.limit)}{unit})"
    return text


def _check_lines_html(targets: Sequence[ReportTarget], check_results: ResultMatrix | None) -> str:
    """One line for each target: its color swatch, its name and the result of the check
    `acoustic.resonance-energy`."""
    if not targets:
        return ""
    items = [
        f'<li><span class="swatch" style="background: var(--{target.color})" '
        f'aria-hidden="true"></span>{html.escape(target.profile.name)}: '
        f"{_CHECK_ID} {html.escape(_check_text(_check_result(check_results, target.profile.name)))}"
        "</li>"
        for target in targets
    ]
    return f'<ul class="target-legend" aria-label="Acoustic resonance check">{"".join(items)}</ul>'


def _notes_html(*notes: str) -> str:
    return "".join(f'<p class="muted">{html.escape(note)}</p>' for note in notes)


def _spectrum_html(
    spectrum: dict,
    card_id: str,
    *,
    problems: Sequence[str] = (),
    targets: Sequence[ReportTarget] = (),
    check_results: ResultMatrix | None = None,
    window_s: float | None = None,
    several: bool = False,
) -> str:
    """The body of the "Gradient spectrum" card: the chart, the check line of each target, the
    notes and the explanation, or the note that there is no spectrum with the notes and the
    check lines. `card_id` is used to build the chart element ids (`{card_id}-chart`,
    `{card_id}-diagram`, `{card_id}-tip`). `window_s` is the window of the method, and
    `several` is true when a lane has several lines."""
    check_lines = _check_lines_html(targets, check_results)
    if spectrum["reason"] is not None:
        return (
            f'<p class="muted">No gradient spectrum: {html.escape(spectrum["reason"])}.</p>'
            + _notes_html(*problems)
            + check_lines
        )

    controls = (
        '<div class="controls" role="group" aria-label="Spectrum scale">'
        '<button type="button" data-scale="linear" aria-pressed="true">Linear</button>'
        '<button type="button" data-scale="db" aria-pressed="false">dB</button>'
        "</div>"
    )
    diagram_id = f"{card_id}-diagram"
    chart = (
        f'<div class="chart" id="{card_id}-chart">'
        f'<svg id="{diagram_id}" tabindex="0" role="img" aria-label="'
        + html.escape(
            f"Gradient spectrum: Gx, Gy, Gz and RSS against frequency, 0 to "
            f"{spectrum['max_frequency_hz']:g} Hz"
        )
        + f'"></svg><div class="tip" id="{card_id}-tip" hidden></div></div>'
    )
    without_resonances = [
        f"{target.profile.name} has no acoustic resonances."
        for target in targets
        if not target.profile.acoustic_resonances
    ]
    method = (
        '<p class="muted">The spectra use the method of pypulseq '
        f"<code>calculate_gradient_spectrum</code> over the whole sequence, up to "
        f"{spectrum['max_frequency_hz']:g} Hz: {window_s * 1e3:g} ms "
        "Hann windows with 50% overlap, the magnitude spectrum (amplitude spectral density) of "
        "each window, and the maximum over windows. The gradients are padded with half a window "
        "of zeros at each end. RSS is the root-sum-of-squares of the three axes in each window. "
        + (
            "A line is the spectrum for the targets with one |γ| (in the tooltip). "
            if several
            else ""
        )
        + "On the dB scale, each value is 20 log10 of its ratio to the largest RSS value, and "
        "values below "
        f"{fmt(_SPECTRUM_DB_FLOOR)} dB are drawn at {fmt(_SPECTRUM_DB_FLOOR)} dB. "
        "Click the chart to mark the centre for the zoom buttons. "
        "Drag across the chart to zoom to that range. Hold Shift and drag, or scroll "
        "sideways, to pan.</p>"
    )
    return (
        controls
        + zoom_controls(diagram_id)
        + chart
        + check_lines
        + _notes_html(*without_resonances, *problems)
        + method
    )


def spectrum_card(
    seq: pp.Sequence,
    *,
    targets: Sequence[ReportTarget] = (),
    check_results: ResultMatrix | None = None,
    card_id: str = "gradient-spectrum",
) -> Card:
    """The "Gradient spectrum" card for the `targets` (`targets.report_targets`) and the
    result matrix `check_results` of a run with the analysis `gradient.spectrum`. The card
    calls no spectrum function: it draws the series `gradient_spectrum` of the result of each
    target whose result is done, in mT/m/√Hz with the |γ| of the target. Targets with one |γ|
    and the same series (equal arrays) are one group, and each group is one line in each lane,
    in the color of its first target (several groups: the `series` of the lanes, one for each
    group). The acoustic resonance bands of each target are shaded in its color, and the body
    has the result of the check `acoustic.resonance-energy` of each target.

    The card has a note and no chart when there is no target, no matrix, or no done result
    with a series. `data` is always a dict (`reason`, `max_frequency_hz`, `db_floor`, `lanes`,
    `resonances`) and `script` is always `"spectrum"`, so the card script can read
    `data.reason`. The card's `scripts` has `assets/cards/spectrum.js`.

    Raises `NotImplementedError` for a sequence with the rotation extension
    (`extensions.refuse_rotations`).
    """
    refuse_rotations(seq)
    groups, problems, reason = _groups(targets, check_results)
    data = _spectrum_data(groups, reason, targets)
    window_s = None if reason is not None else float(groups[0].series.meta["window_s"])
    body = _spectrum_html(
        data,
        card_id,
        problems=problems,
        targets=targets,
        check_results=check_results,
        window_s=window_s,
        several=len(groups) > 1,
    )
    return Card(
        id=card_id,
        title="Gradient spectrum",
        body_html=body,
        data=data,
        script="spectrum",
        scripts=(card_asset("spectrum"),),
    )


def _build(ctx: ReportContext) -> Card:
    return spectrum_card(
        ctx.seq, targets=ctx.targets, check_results=ctx.check_results, card_id=SPEC.name
    )


SPEC = CardSpec("gradient-spectrum", 50, _build)
