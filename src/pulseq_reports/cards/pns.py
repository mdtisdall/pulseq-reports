"""PNS prediction summary card: the status line, the table of peaks, a button that
shows the peak in the diagram, and the hardware note. The PNS chart is the PNS lane of
the sequence diagram (`cards.diagram.diagram_card(..., pns_lane=True)`), not this card
(`docs/plans/diagram-lanes.md`, section 4.6)."""

import html
from pathlib import Path

import numpy as np
import pypulseq as pp

from pulseq_reports.extensions import refuse_rotations
from pulseq_reports.markup import html_table
from pulseq_reports.page import Card
from pulseq_reports.pns import peak_tr_window, pns_prediction
from pulseq_reports.seq_index import sequence_index

_GOTO_TR_TEXT = "Show the peak's TR in the diagram"
_GOTO_BLOCK_TEXT = "Show the peak's block in the diagram"


def _pns_data(seq: pp.Sequence, *, gradient_asc: str | Path | None = None) -> dict:
    """PNS prediction summary (`pns.pns_prediction`) as JSON-ready data, in percent of
    the stimulation limit and in ms. The card's body is written from it; it is not the
    card's own data (`_goto_data`)."""
    p = pns_prediction(seq, gradient_asc=gradient_asc)
    out = {
        "reason": p.reason,
        "hardware": p.hardware,
        "asc_file": p.asc_file,
        "example": p.asc_file is None,
        "peak_percent": round(100 * p.peak, 2),
        "peak_time_ms": round(p.peak_time_s * 1e3, 4) if p.peak_time_s is not None else None,
        "axis_peaks_percent": {axis: round(100 * v, 2) for axis, v in p.axis_peaks.items()},
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
    """The body of the "PNS prediction" card: the status line, the table of peaks, the
    button with the text `goto_text` (none when it is None) and the hardware note, or a
    note that there is no prediction."""
    if p["reason"] is not None:
        return f'<p class="muted">No PNS prediction: {html.escape(p["reason"])}.</p>'

    peak = p["peak_percent"]
    if peak >= 100:
        status = (
            '<p class="status bad"><span aria-hidden="true">✕</span> '
            f"Predicted PNS peak {peak:.1f} % is at or above the 100 % limit.</p>"
        )
    else:
        status = (
            '<p class="status good"><span aria-hidden="true">✓</span> '
            f"Predicted PNS peak {peak:.1f} % is below the 100 % limit.</p>"
        )
    if p["example"]:
        source = (
            "<p><strong>Example hardware, not a real scanner.</strong> Give the gradient "
            ".asc file of your scanner (<code>gradient_asc</code>) for a real prediction.</p>"
        )
        hardware = p["hardware"]
    else:
        source = ""
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
        "root-sum-of-squares of the three, and the check passes below 100 %. The stimulation "
        "over time is the PNS lane of the sequence diagram, not a chart on this card. The "
        "model can be inaccurate, and the scanner's own stimulation monitor decides: record "
        "the PNS level that the scanner reports.</p>"
    )
    return status + source + table + button + note


def pns_card(
    seq: pp.Sequence, *, gradient_asc: str | Path | None = None, card_id: str = "pns"
) -> Card:
    """The "PNS prediction" card for one sequence: the SAFE-model prediction summary
    (`_pns_data`) as a status line, a table of the peak percent of the stimulation limit
    for all axes, Gx, Gy and Gz, a button, and the hardware note.

    The card has no chart: the stimulation over time is the PNS lane of the sequence
    diagram (`cards.diagram.diagram_card(..., pns_lane=True)`). `gradient_asc` is the
    gradient .asc file of the scanner, or None for pypulseq's example hardware. The card
    shares its `PnsLevels` computation with the diagram's lane (`pns.pns_levels_for`)
    when both are given the same `gradient_asc`, so a page with both cards for one
    sequence runs the SAFE model once.

    The button shows the peak in the diagram: the TR that holds the peak, or, when the
    sequence has no `TR` definition, the block that holds it. Its script
    (`assets/cards/pns.js`) sends a `goto` message, and shows the button only while a
    card (the diagram) acts on `goto`. A sequence with no gradients has no prediction:
    then the card has no button, no script and no data.

    Raises `NotImplementedError` for a sequence with the rotation extension
    (`extensions.refuse_rotations`).
    """
    refuse_rotations(seq)
    summary = _pns_data(seq, gradient_asc=gradient_asc)
    if summary["reason"] is not None:
        return Card(id=card_id, title="PNS prediction", body_html=_pns_html(summary, None, card_id))
    peak_time_s = pns_prediction(seq, gradient_asc=gradient_asc).peak_time_s
    data = _goto_data(seq, peak_time_s)
    goto_text = _GOTO_BLOCK_TEXT if "block" in data["goto"] else _GOTO_TR_TEXT
    return Card(
        id=card_id,
        title="PNS prediction",
        body_html=_pns_html(summary, goto_text, card_id),
        data=data,
        script="pns",
    )
