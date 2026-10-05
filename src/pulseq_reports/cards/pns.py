"""PNS prediction summary card: for each target, the table of peaks and a button that shows
the peak in the diagram, and the note about the model. The PNS chart is the PNS lane of the
sequence diagram (`cards.diagram.diagram_card(..., pns_lane=True)`), not this card
(`docs/plans/diagram-lanes.md`, section 4.6).

The PNS of a target comes only from the analysis result `pns.safe.levels` of the result
matrix (principle 9 of `docs/plans/pulseq-checks.md`): the card does not run the SAFE model.
Without targets, or without a result matrix, the card has a note and no PNS.
"""

import html
from collections.abc import Sequence

import numpy as np
import pypulseq as pp
from pulseq_analysis.extensions import refuse_rotations
from pulseq_analysis.pns import peak_tr_window
from pulseq_analysis.seq_index import sequence_index
from pulseq_analysis.series import Series
from pulseq_checks import AnalysisState, ResultMatrix

from pulseq_reports.markup import html_table, target_legend_html
from pulseq_reports.page import Card, card_asset
from pulseq_reports.registry import CardSpec, ReportContext
from pulseq_reports.targets import ReportTarget

PUBLISHES = ("goto",)

ANALYSIS_ID = "pns.safe.levels"

_GOTO_TR_TEXT = "Show the peak's TR in the diagram"
_GOTO_BLOCK_TEXT = "Show the peak's block in the diagram"
_NO_TARGETS_HTML = (
    '<p class="muted">No PNS prediction: the report has no target. The PNS of a target '
    "comes from its analysis result <code>pns.safe.levels</code>, and a target needs "
    "SAFE parameters for it.</p>"
)
_NO_MATRIX_HTML = (
    '<p class="muted">No PNS prediction: no analysis results were given. The PNS of a '
    "target comes from its analysis result <code>pns.safe.levels</code>.</p>"
)


def pns_series(
    check_results: ResultMatrix, name: str
) -> tuple[tuple[Series, Series] | None, str | None]:
    """The series `pns_total` and `pns_above_0` of the analysis result `pns.safe.levels` of
    the target `name`, and `None`; or `None` and the reason (plain text) that the target has
    no PNS: the matrix has no such result, the state of the result is not "done" (the reason
    of the result), or the result has no series (a sequence with no gradient event)."""
    result = check_results.analysis(name, ANALYSIS_ID)
    if result is None:
        return None, f"the result matrix has no {ANALYSIS_ID} analysis result for it"
    if result.state is not AnalysisState.DONE:
        return None, result.reason or result.state.value
    if not result.series:
        return None, "the sequence has no gradient event"
    by_name = {series.name: series for series in result.series}
    if "pns_total" not in by_name or "pns_above_0" not in by_name:
        return None, f"the result has the series {sorted(by_name)}, not pns_total and pns_above_0"
    return (by_name["pns_total"], by_name["pns_above_0"]), None


def _pns_data(total: Series, above: Series) -> dict:
    """The PNS summary of `pns_total` as a dict, in percent of the stimulation limit
    (`100 * v / meta["threshold"]` of `pns_above_0`, decision P38 of
    `docs/plans/pulseq-checks.md`) and in ms. The card's body is written from it; it is not
    the card's own data (`_goto_data`)."""
    meta = total.meta
    threshold = above.meta["threshold"]
    return {
        "hardware": meta["hardware"],
        "asc_file": meta["asc_file"],
        "peak_percent": 100 * meta["peak"] / threshold,
        "peak_time_ms": meta["peak_time_s"] * 1e3,
        "axis_peaks_percent": {
            axis: 100 * meta[f"axis_peaks_{axis}"] / threshold for axis in "xyz"
        },
    }


def _goto_data(seq: pp.Sequence, peak_time_s: float) -> dict:
    """What the button of `pns.js` sends as a `goto` message, for the peak at `peak_time_s`.
    With a `TR` definition, it is `{"t0S", "t1S", "anchorS"}`: the TR that holds the peak
    (`pns.peak_tr_window`) and the peak time. Without one, it is `{"block": k}`: the play
    index of the block that holds the peak time."""
    window = peak_tr_window(seq, peak_time_s)
    if window is not None:
        return {"t0S": float(window[0]), "t1S": float(window[1]), "anchorS": float(peak_time_s)}
    index = sequence_index(seq)
    # The first block that ends after the peak time (the ends do not decrease), so a
    # block of zero duration is never chosen; the last block when the time is at the end.
    ends = index.start_s + index.duration_s
    block = min(int(np.searchsorted(ends, peak_time_s, side="right")), index.num_blocks - 1)
    return {"block": block}


def _target_html(
    target: ReportTarget, p: dict | None, reason: str | None, goto_text: str | None, button_id: str
) -> str:
    """The part of one target: its name after a swatch of its color, then the table of
    peaks `p` (`_pns_data`) and the button with the text `goto_text` (none when it is None),
    or the `reason` that the target has no PNS."""
    heading = target_legend_html([target])
    if p is None:
        return f'<div>{heading}<p class="muted">No PNS prediction: {html.escape(reason)}.</p></div>'
    hardware = p["hardware"] if p["asc_file"] is None else f"{p['hardware']} ({p['asc_file']})"
    axes = p["axis_peaks_percent"]
    table = html_table(
        ["Quantity", "Value"],
        [
            ["Hardware", hardware],
            ["Peak, all axes (%)", f"{p['peak_percent']:.1f} at {p['peak_time_ms']:.3f} ms"],
            *[[f"Peak, G{a} (%)", f"{axes[a]:.1f}"] for a in "xyz"],
        ],
    )
    button = (
        ""
        if goto_text is None
        else f'<p><button type="button" id="{button_id}" hidden>{goto_text}</button></p>'
    )
    return f"<div>{heading}{table}{button}</div>"


_NOTE_HTML = (
    '<p class="muted">The prediction is the SAFE model (Hebrank and Gebhardt), from the '
    "pinned pypulseq fork's chunked SAFE recursion. Each axis is its predicted "
    "stimulation as a percent of that axis's stimulation limit. All axes is the "
    "root-sum-of-squares of the three. The stimulation over time is the PNS lane of the "
    "sequence diagram, not a chart on this card. The model can be inaccurate, and the "
    "scanner's own stimulation monitor decides: record the PNS level that the scanner "
    "reports.</p>"
)


def pns_card(
    seq: pp.Sequence,
    *,
    targets: Sequence[ReportTarget] = (),
    check_results: ResultMatrix | None = None,
    card_id: str = "pns",
) -> Card:
    """The "PNS prediction" card for one sequence: for each of `targets`, in order, its name
    after a swatch of its color, and the PNS summary of its analysis result
    `pns.safe.levels` in `check_results`: a table of the hardware and the peak percent of the
    stimulation limit for all axes, Gx, Gy and Gz, and a button. The note about the model
    follows.

    The percent of a value `v` is `100 * v / meta["threshold"]` of the series `pns_above_0`
    (decision P38 of `docs/plans/pulseq-checks.md`). A target whose result is not "done"
    (for example a target without SAFE parameters) has its reason in place of the table,
    and a target that the matrix has no result for says so. The card runs no SAFE model.
    Without `targets`, or with `check_results=None`, the card has one muted note, no table,
    no button, no script and no data.

    The card has no chart: the stimulation over time is the PNS lane of the sequence
    diagram (`cards.diagram.diagram_card(..., pns_lane=True)`).

    The button of target `k` (id `{card_id}-goto-{k}`) shows its peak in the diagram: the TR
    that holds the peak, or, when the sequence has no `TR` definition, the block that holds
    it. The card data is `{"format": 2, "goto": [...]}`, with one entry for each target: the
    payload of the `goto` message of its button (`_goto_data`), or `None` for a target with
    no button. Its script (`assets/cards/pns.js`) sends a `goto` message, and shows a button
    only while a card (the diagram) acts on `goto`. A card with no button has no script and
    no data.

    The card gives no verdict. It publishes `PUBLISHES` (`goto`), as its spec says, and a
    card with a button has `scripts` with `assets/cards/pns.js`.

    Raises `NotImplementedError` for a sequence with the rotation extension
    (`extensions.refuse_rotations`).
    """
    refuse_rotations(seq)
    title = "PNS prediction"
    if not targets or check_results is None:
        note = _NO_TARGETS_HTML if not targets else _NO_MATRIX_HTML
        return Card(id=card_id, title=title, body_html=note, publishes=PUBLISHES)
    parts = []
    goto = []
    for k, target in enumerate(targets):
        found, reason = pns_series(check_results, target.profile.name)
        if found is None:
            parts.append(_target_html(target, None, reason, None, ""))
            goto.append(None)
            continue
        total, above = found
        payload = _goto_data(seq, total.meta["peak_time_s"])
        goto_text = _GOTO_BLOCK_TEXT if "block" in payload else _GOTO_TR_TEXT
        parts.append(
            _target_html(target, _pns_data(total, above), None, goto_text, f"{card_id}-goto-{k}")
        )
        goto.append(payload)
    if not any(payload is not None for payload in goto):
        return Card(id=card_id, title=title, body_html="".join(parts), publishes=PUBLISHES)
    return Card(
        id=card_id,
        title=title,
        body_html="".join(parts) + _NOTE_HTML,
        data={"format": 2, "goto": goto},
        script="pns",
        scripts=(card_asset("pns"),),
        publishes=PUBLISHES,
    )


def _build(ctx: ReportContext) -> Card:
    return pns_card(
        ctx.seq, targets=ctx.targets, check_results=ctx.check_results, card_id=SPEC.name
    )


SPEC = CardSpec("pns", 60, _build, publishes=PUBLISHES)
