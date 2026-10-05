"""Sequence diagram card: RF, ADC and gradient waveforms against time, with one button
for each time window that the caller gives, and an optional PNS lane.

The card sends the compressed block and event tables of the sequence
(`diagram_data.diagram_tables`, `encode_array`), not expanded points. The
browser (`assets/cards/diagram.js`, `assets/seq_lanes.js`) decodes them and draws the
exact waveform when a view has few enough points, or the minimum and the maximum of
each lane in each of the plot's time bins otherwise, so the card works for a file of up
to 10^7 blocks (`docs/plans/diagram-event-table.md`).

With `pns_lane`, a sequence that has a gradient event also gets a `"pns"` key in
the card's `"file"` entry (`docs/plans/pulseq-checks-implementation.md`, section 4.7): a
list with one entry for each target whose analysis result `pns.safe.levels` in the result
matrix is "done" and has the series `pns_total` and `pns_above_0`. An entry has the target
name and color, the SAFE parameters of the target, the gradient raster, the stimulation
limit `threshold`, the summary, the stored minimum/maximum levels of `pns_total` (Hz/T,
unchanged) and the runs of `pns_above_0`. The PNS of a target comes only from the matrix
(principle 9 of `docs/plans/pulseq-checks.md`): the card does not run the SAFE model. The
browser (`assets/pns_lanes.js`) decodes the list into the PNS lane. `pns_lane` is False by
default. For a target without an entry (no matrix, no result, another state) the
explanation paragraph says why.
"""

import html
from collections.abc import Sequence

import pypulseq as pp
from pulseq_analysis.extensions import refuse_rotations
from pulseq_analysis.series import Series, encode_array
from pulseq_checks import ResultMatrix

from .. import options
from ..diagram_data import diagram_tables, lane_meta
from ..markup import zoom_controls
from ..page import Card, card_asset
from ..registry import CardSpec, ReportContext
from ..targets import ReportTarget
from ..waveforms import TimeWindow, _check_windows, duration_s
from .pns import pns_series

PUBLISHES = ("sequence", "cursor", "anchor", "view")
SUBSCRIBES = ("goto",)


def _ms(t_s: float) -> float:
    return round(t_s * 1e3, 4)


_HW_KEYS = ("tau1", "tau2", "tau3", "a1", "a2", "a3", "stim_limit", "g_scale")


def _pns_entry(target: ReportTarget, total: Series, above: Series) -> dict:
    """The entry of `target` in the `"pns"` list of the `"file"` entry
    (`docs/plans/pulseq-checks-implementation.md`, section 4.7), from the series `pns_total`
    and `pns_above_0` of its analysis result `pns.safe.levels`: the target name and color
    token, the hardware name and `.asc` file name, the SAFE parameters `hw` of the target
    (the keys that `assets/pns_lanes.js` reads), the gradient raster `dtS`, the samples in
    each bin of the levels `binSamples`, the stimulation limit `threshold` (Hz/T), the
    summary (the peak, its time and the axis peaks, Hz/T), the stored `levels` (`min` and
    `max` of `pns_total`, Hz/T, float32) and the `runs` (`start` and `end` of `pns_above_0`,
    s), the arrays encoded with `encode_array`. No value is divided here: the browser makes
    a percent as `100 * v / threshold`."""
    meta = total.meta
    safe = target.profile.models["pns.safe"]
    return {
        "target": target.profile.name,
        "color": target.color,
        "hardware": meta["hardware"],
        "asc_file": meta["asc_file"],
        "hw": {axis: {key: safe[axis][key] for key in _HW_KEYS} for axis in "xyz"},
        "dtS": meta["dt_s"],
        "binSamples": int(meta["bin_samples"]),
        "threshold": above.meta["threshold"],
        "summary": {
            "peak": meta["peak"],
            "peak_time_s": meta["peak_time_s"],
            "axis_peaks": {axis: meta[f"axis_peaks_{axis}"] for axis in "xyz"},
        },
        "levels": {
            "min": encode_array(total.arrays["min"]),
            "max": encode_array(total.arrays["max"]),
        },
        "runs": {
            "start": encode_array(above.arrays["start"]),
            "end": encode_array(above.arrays["end"]),
        },
    }


def _pns_entries(
    targets: Sequence[ReportTarget], check_results: ResultMatrix | None
) -> tuple[list[dict], str | None]:
    """The `"pns"` list of the `"file"` entry for `targets` (`_pns_entry`, one for each target
    that has the series, in the order of `targets`), and the explanation of the targets that
    have no entry: the HTML (escaped) that names each with its reason, or why there is no
    matrix or no target; `None` when every target has an entry."""
    if not targets:
        return [], "the report has no target"
    if check_results is None:
        return [], "no analysis results were given"
    entries = []
    missing = []
    for target in targets:
        found, reason = pns_series(check_results, target.profile.name)
        if found is None:
            missing.append(f"{html.escape(target.profile.name)} ({html.escape(reason)})")
        else:
            entries.append(_pns_entry(target, *found))
    return entries, "; ".join(missing) if missing else None


def _validate(seq: pp.Sequence, windows: Sequence[TimeWindow]) -> None:
    if not windows:
        raise ValueError("the diagram card needs at least one time window")
    _check_windows(seq, windows)


def _diagram_data(seq: pp.Sequence, windows: Sequence[TimeWindow], pns: list[dict]) -> dict:
    """The card data (section 4.1 of `docs/plans/diagram-event-table.md`, plus the
    `"pns"` key of section 4.7 of `docs/plans/pulseq-checks-implementation.md`):
    `{"format": 3, "file": {...}, "windows": [...]}`.

    `file` has `duration_s`, `num_blocks`, `lanes` (`lane_meta`) and `tables`
    (`encode_array` of each table of `diagram_tables(seq)`). `diagram_tables(seq)` is built once and
    passed to `lane_meta` so it is not built twice. When `pns` (the list of `_pns_entry`) is
    not empty, `file` also gets it as the `"pns"` key. `windows` has one entry for each of
    `windows`: `label` and `view_ms`.
    """
    tables = diagram_tables(seq)
    file = {
        "duration_s": duration_s(seq),
        "num_blocks": len(seq.block_events),
        "lanes": lane_meta(seq, tables=tables),
        "tables": {name: encode_array(array) for name, array in tables.items()},
    }
    if pns:
        file["pns"] = pns
    out_windows = [{"label": w.label, "view_ms": [_ms(w.start_s), _ms(w.end_s)]} for w in windows]
    return {"format": 3, "file": file, "windows": out_windows}


def diagram_card(
    seq: pp.Sequence,
    windows: Sequence[TimeWindow],
    *,
    pns_lane: bool = False,
    targets: Sequence[ReportTarget] = (),
    check_results: ResultMatrix | None = None,
    card_id: str = "diagram",
) -> Card:
    """The "Sequence diagram" card: one button for each of `windows`, in the given
    order. The first window is the initial view.

    The sequence's block and event tables are sent to the browser once (see
    `_diagram_data`); the browser decodes them and draws the waveform. A status line
    under the chart (`{card_id}-mode`) says whether the current view is exact or a
    minimum/maximum of time bins.

    `pns_lane` (`docs/plans/diagram-lanes.md`, section 4.7) adds a PNS lane: `False` (the
    default) adds no `"pns"` key. With `pns_lane`, the `"pns"` key is the list of
    `_pns_entry`, one for each of `targets` (`targets.ReportTarget`, in order) whose analysis
    result `pns.safe.levels` in `check_results` (the `ResultMatrix` of a run, or `None`) is
    "done" and has the series `pns_total` and `pns_above_0`. The card runs no SAFE model:
    the PNS of a target comes only from the matrix. Without targets, without a matrix, or
    when no target has the series (for example a sequence with no gradient event), the card
    has no `"pns"` key, and the explanation paragraph says why; for a target that has no
    entry while another has one, it names the target and the reason (escaped).

    A group-controls container (`{card_id}-groups`) sits above the chart, after the
    window buttons: the card script (`assets/cards/diagram.js`) fills it with one
    toggle button for each lane group (RF, ADC, Gradients, and PNS when the card has
    PNS data), so any of them can be hidden. The Gradients group also has a
    |G| lane (`docs/plans/diagram-lanes.md`, phase 5): the exact minimum and maximum of
    the gradient vector's magnitude in each time bin, computed in the browser
    (`assets/g_lanes.js`) from the same tables as Gx, Gy and Gz, no extra data from this
    function. The explanation paragraph under the chart always gets one sentence about
    the |G| lane, and one more about the PNS lane when the card has PNS data, or, when
    `pns_lane` is true without PNS data, one that says why there is no PNS lane.

    The card's `scripts` has `assets/cards/diagram.js`. It publishes `PUBLISHES` (the
    topics `sequence`, `cursor`, `anchor` and `view`) and subscribes to `SUBSCRIBES`
    (`goto`).

    Raises `TypeError` when `pns_lane` is not a `bool`. Raises `ValueError` when `windows` is
    empty, or when a window is not inside the sequence or does not end after its start (the
    message names the window's label). Raises
    `NotImplementedError` (`extensions.refuse_rotations`) for a sequence that uses the
    Pulseq rotation extension: this card shows unrotated gradient events, which would
    be wrong for such a sequence.
    """
    if not isinstance(pns_lane, bool):
        raise TypeError(f"pns_lane must be a bool, not {type(pns_lane).__name__}")
    _validate(seq, windows)
    refuse_rotations(seq)
    pns, pns_missing = _pns_entries(targets, check_results) if pns_lane else ([], None)
    data = _diagram_data(seq, windows, pns)
    has_pns = "pns" in data["file"]
    buttons = "".join(
        f'<button type="button" data-window="{i}" aria-pressed="{str(i == 0).lower()}">'
        f"{html.escape(w['label'])}</button>"
        for i, w in enumerate(data["windows"])
    )
    svg_id = f"{card_id}-diagram"
    lanes_after_adc = "Gx, Gy, Gz, |G| and PNS" if has_pns else "Gx, Gy, Gz and |G|"
    g_note = (
        " The |G| lane shows the magnitude of the gradient vector (the root-sum-of-squares "
        "of Gx, Gy and Gz), as the exact minimum and maximum in each time bin."
    )
    pns_note = ""
    if has_pns:
        pns_note = (
            " The PNS lane shows the total predicted stimulation (the root-sum-of-squares "
            "of the three axes) as a percent of the SAFE stimulation limit, one line for "
            "each target in its color, and marks the runs at or above the limit. It is exact "
            "for a view of 10 s or less; a longer view shows the minimum and the maximum "
            "in time bins."
        )
        if pns_missing is not None:
            pns_note += f" No PNS for: {pns_missing}."
    elif pns_missing is not None:
        pns_note = f" There is no PNS lane: {pns_missing}."
    body = (
        f'<div class="controls" role="group" aria-label="Time window">{buttons}</div>\n'
        f'<div class="controls" role="group" aria-label="Lanes" id="{card_id}-groups">'
        "</div>\n" + zoom_controls(svg_id) + f'\n<div class="chart" id="{card_id}-chart">\n'
        f'<svg id="{svg_id}" tabindex="0" role="img"\n'
        f'  aria-label="Sequence diagram: RF magnitude and phase, ADC, {lanes_after_adc} '
        'against time"></svg>\n'
        f'<div class="tip" id="{card_id}-tip" hidden></div>\n'
        "</div>\n"
        f'<p class="muted" id="{card_id}-mode" aria-live="polite">Loading…</p>\n'
        '<p class="muted">Hover the diagram, or focus it and use the arrow keys, to read '
        "values.\nRF phase is drawn where |B1| is above 1% of that pulse's peak.\n"
        "Click the chart to mark the centre for the zoom buttons. Drag across the chart to "
        f"zoom to that range. Hold Shift and drag, or scroll sideways, to pan.{g_note}"
        f"{pns_note}</p>"
    )
    return Card(
        id=card_id,
        title="Sequence diagram",
        body_html=body,
        data=data,
        script="diagram",
        scripts=(card_asset("diagram"),),
        publishes=PUBLISHES,
        subscribes=SUBSCRIBES,
    )


def _build(ctx: ReportContext) -> Card:
    return diagram_card(
        ctx.seq,
        ctx.windows(),
        pns_lane=ctx.option(options.pns_lane),
        targets=ctx.targets,
        check_results=ctx.check_results,
        card_id=SPEC.name,
    )


SPEC = CardSpec(
    "diagram",
    30,
    _build,
    (options.pns_lane,),
    publishes=PUBLISHES,
    subscribes=SUBSCRIBES,
)
