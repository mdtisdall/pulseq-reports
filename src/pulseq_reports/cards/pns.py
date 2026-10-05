"""PNS prediction summary card: the table of peaks, a button that shows the peak in the
diagram, and the note about the model. The PNS chart is the PNS lane of the sequence
diagram (`cards.diagram.diagram_card(..., pns_lane=True)`), not this card
(`docs/plans/diagram-lanes.md`, section 4.6). Without the gradient .asc file of the
scanner, the card has no prediction."""

import html
from pathlib import Path

import numpy as np
import pypulseq as pp
from pulseq_analysis.extensions import refuse_rotations
from pulseq_analysis.pns import peak_tr_window, pns_prediction
from pulseq_analysis.seq_index import sequence_index

from pulseq_reports import options
from pulseq_reports.markup import html_table
from pulseq_reports.page import Card, card_asset
from pulseq_reports.registry import CardSpec, ReportContext
from pulseq_reports.units import gamma_magnitude

PUBLISHES = ("goto",)

_GOTO_TR_TEXT = "Show the peak's TR in the diagram"
_GOTO_BLOCK_TEXT = "Show the peak's block in the diagram"
_NO_ASC_HTML = (
    '<p class="muted">No PNS prediction: it needs the gradient .asc file of the scanner '
    "(<code>gradient_asc</code>).</p>"
)


def _pns_data(seq: pp.Sequence, *, gradient_asc: str | Path) -> dict:
    """PNS prediction summary (`pns.pns_prediction`) as JSON-ready data, in percent of
    the stimulation limit and in ms. The card's body is written from it; it is not the
    card's own data (`_goto_data`)."""
    p = pns_prediction(seq, gradient_asc=gradient_asc)
    # The prediction gives Hz/T (the fraction of the limit times |gamma|).
    g = gamma_magnitude(seq.system.gamma)
    out = {
        "reason": p.reason,
        "hardware": p.hardware,
        "asc_file": p.asc_file,
        "peak_percent": round(100 * (p.peak_hz_per_t / g), 2),
        "peak_time_ms": round(p.peak_time_s * 1e3, 4) if p.peak_time_s is not None else None,
        "axis_peaks_percent": {
            axis: round(100 * (v / g), 2) for axis, v in p.axis_peaks_hz_per_t.items()
        },
    }
    return out


def _goto_data(seq: pp.Sequence, peak_time_s: float) -> dict:
    """The card's data (`{"format": 1, "goto": ...}`): what the button of `pns.js` sends
    as a `goto` message. With a `TR` definition, `goto` is `{"t0S", "t1S", "anchorS"}`: the
    TR that holds the peak (`pns.peak_tr_window`) and the peak time. Without one, it is
    `{"block": k}`: the play index of the block that holds the peak time."""
    window = peak_tr_window(seq, peak_time_s)
    if window is not None:
        goto = {"t0S": float(window[0]), "t1S": float(window[1]), "anchorS": float(peak_time_s)}
    else:
        index = sequence_index(seq)
        # The first block that ends after the peak time (the ends do not decrease), so a
        # block of zero duration is never chosen; the last block when the time is at the end.
        ends = index.start_s + index.duration_s
        block = min(int(np.searchsorted(ends, peak_time_s, side="right")), index.num_blocks - 1)
        goto = {"block": block}
    return {"format": 1, "goto": goto}


def _pns_html(p: dict, goto_text: str | None, card_id: str) -> str:
    """The body of the "PNS prediction" card: the table of peaks, the button with the text
    `goto_text` (none when it is None) and the note about the model, or a note that there
    is no prediction."""
    if p["reason"] is not None:
        return f'<p class="muted">No PNS prediction: {html.escape(p["reason"])}.</p>'

    peak = p["peak_percent"]
    hardware = f"{p['hardware']} ({p['asc_file']})"
    axes = p["axis_peaks_percent"]
    table = html_table(
        ["Quantity", "Value"],
        [
            ["Hardware", hardware],
            ["Peak, all axes (%)", f"{peak:.1f} at {p['peak_time_ms']:.3f} ms"],
            *[[f"Peak, G{a} (%)", f"{axes[a]:.1f}"] for a in "xyz"],
        ],
    )
    button = (
        ""
        if goto_text is None
        else f'<p><button type="button" id="{card_id}-goto" hidden>{goto_text}</button></p>'
    )
    note = (
        '<p class="muted">The prediction is the SAFE model (Hebrank and Gebhardt), from the '
        "pinned pypulseq fork's chunked SAFE recursion. Each axis is its predicted "
        "stimulation as a percent of that axis's stimulation limit. All axes is the "
        "root-sum-of-squares of the three. The stimulation over time is the PNS lane of the "
        "sequence diagram, not a chart on this card. The model can be inaccurate, and the "
        "scanner's own stimulation monitor decides: record the PNS level that the scanner "
        "reports.</p>"
    )
    return table + button + note


def pns_card(
    seq: pp.Sequence, *, gradient_asc: str | Path | None = None, card_id: str = "pns"
) -> Card:
    """The "PNS prediction" card for one sequence: the SAFE-model prediction summary
    (`_pns_data`) as a table of the peak percent of the stimulation limit for all axes,
    Gx, Gy and Gz, a button, and the note about the model.

    The card has no chart: the stimulation over time is the PNS lane of the sequence
    diagram (`cards.diagram.diagram_card(..., pns_lane=True)`). `gradient_asc` is the
    gradient .asc file of the scanner. With `gradient_asc=None`, the card has no
    prediction: it runs no SAFE model, has a muted note that a PNS prediction needs
    `gradient_asc`, and has no button, no script and no data. The card shares its
    `PnsLevels` computation with the diagram's lane (`pns.pns_levels_for`) when both are
    given the same `gradient_asc`, so a page with both cards for one sequence runs the
    SAFE model once.

    The button shows the peak in the diagram: the TR that holds the peak, or, when the
    sequence has no `TR` definition, the block that holds it. Its script
    (`assets/cards/pns.js`) sends a `goto` message, and shows the button only while a
    card (the diagram) acts on `goto`. A sequence with no gradients has no prediction:
    then the card has no button, no script and no data.

    The card gives no verdict. It publishes `PUBLISHES` (`goto`), as its spec says, and a
    card with a button has `scripts` with `assets/cards/pns.js`.

    Raises `NotImplementedError` for a sequence with the rotation extension
    (`extensions.refuse_rotations`).
    """
    refuse_rotations(seq)
    if gradient_asc is None:
        return Card(
            id=card_id,
            title="PNS prediction",
            body_html=_NO_ASC_HTML,
            publishes=PUBLISHES,
        )
    summary = _pns_data(seq, gradient_asc=gradient_asc)
    if summary["reason"] is not None:
        return Card(
            id=card_id,
            title="PNS prediction",
            body_html=_pns_html(summary, None, card_id),
            publishes=PUBLISHES,
        )
    peak_time_s = pns_prediction(seq, gradient_asc=gradient_asc).peak_time_s
    data = _goto_data(seq, peak_time_s)
    goto_text = _GOTO_BLOCK_TEXT if "block" in data["goto"] else _GOTO_TR_TEXT
    return Card(
        id=card_id,
        title="PNS prediction",
        body_html=_pns_html(summary, goto_text, card_id),
        data=data,
        script="pns",
        scripts=(card_asset("pns"),),
        publishes=PUBLISHES,
    )


def _build(ctx: ReportContext) -> Card:
    return pns_card(ctx.seq, gradient_asc=ctx.option(options.gradient_asc), card_id=SPEC.name)


SPEC = CardSpec("pns", 60, _build, (options.gradient_asc,), publishes=PUBLISHES)
