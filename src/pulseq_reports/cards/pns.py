"""PNS prediction summary card: the status line, the table of peaks and the hardware
note. The PNS chart is the PNS lane of the sequence diagram
(`cards.diagram.diagram_card(..., pns=...)`), not this card
(`docs/plans/diagram-lanes.md`, section 4.6)."""

import html
from pathlib import Path

import pypulseq as pp

from pulseq_reports.extensions import refuse_rotations
from pulseq_reports.markup import html_table
from pulseq_reports.page import Card
from pulseq_reports.pns import pns_prediction
from pulseq_reports.seq_utils import NamedSequence


def pns_data(seq: pp.Sequence, gradient_asc: str | Path | None = None) -> dict:
    """PNS prediction summary (`pns.pns_prediction`) as JSON-ready data, in percent of
    the stimulation limit and in ms."""
    p = pns_prediction(seq, gradient_asc)
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


def _pns_html(p: dict) -> str:
    """The body of the "PNS prediction" card: the status line, the table of peaks and the
    hardware note, or a note that there is no prediction."""
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
    note = (
        '<p class="muted">The prediction is the SAFE model (Hebrank and Gebhardt), from the '
        "pinned pypulseq fork's chunked SAFE recursion. Each axis is its predicted "
        "stimulation as a percent of that axis's stimulation limit. All axes is the "
        "root-sum-of-squares of the three, and the check passes below 100 %. The stimulation "
        "over time is the PNS lane of the sequence diagram, not a chart on this card. The "
        "model can be inaccurate, and the scanner's own stimulation monitor decides: record "
        "the PNS level that the scanner reports.</p>"
    )
    return status + source + table + note


def pns_card(
    seq: NamedSequence, gradient_asc: str | Path | None = None, card_id: str = "pns"
) -> Card:
    """The "PNS prediction" card for one sequence: the SAFE-model prediction summary
    (`pns_data`) as a status line, a table of the peak percent of the stimulation limit
    for all axes, Gx, Gy and Gz, and the hardware note.

    This card has no chart and no script: the stimulation over time is the PNS lane of
    the sequence diagram (`cards.diagram.diagram_card(..., pns=True)` or a gradient
    .asc path), which shares its `PnsLevels` computation with this card
    (`pns.pns_levels_for`), so a page with both cards for one sequence runs the SAFE
    model only once. A caller that wants the "TR with the highest PNS" view that the
    chart used to have adds `pns.peak_tr_window(seq, ...)` to the diagram card's
    windows.

    Raises `NotImplementedError` for a sequence with the rotation extension
    (`extensions.refuse_rotations`).
    """
    refuse_rotations(seq.seq)
    data = pns_data(seq.seq, gradient_asc)
    return Card(
        id=card_id,
        title="PNS prediction",
        body_html=_pns_html(data),
        data=data,
        script=None,
    )
