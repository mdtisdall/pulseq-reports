"""PNS prediction card: the stimulation percent over time, full sequence and peak TR."""

import html
import math
from pathlib import Path

import numpy as np
import pypulseq as pp

from pulseq_reports.extensions import refuse_rotations
from pulseq_reports.markup import _AXIS_COLOR, Lane, _lanes_json, _points, _table, _zoom_controls
from pulseq_reports.page import Card
from pulseq_reports.pns import peak_tr_window, pns_prediction
from pulseq_reports.seq_utils import NamedSequence

_PNS_MAX_POINTS = 100_000  # the most points drawn in each PNS lane
_PNS_ZERO_PERCENT = 0.01  # each lane leaves out the inside of runs at or below this


def _max_envelope(
    t: np.ndarray, values: np.ndarray, max_points: int
) -> tuple[np.ndarray, np.ndarray]:
    """At most `max_points` points: the maximum of `values` in each run of equal length,
    at the time of the run's first sample."""
    step = math.ceil(values.size / max_points)
    if step <= 1:
        return t, values
    starts = np.arange(0, values.size, step)
    return t[starts], np.maximum.reduceat(values, starts)


def _active_samples(
    t: np.ndarray, values: np.ndarray, floor: float
) -> tuple[np.ndarray, np.ndarray]:
    """The samples above `floor`, the samples next to them, and the first and last sample.
    A run at or below `floor` keeps only its ends, so it is drawn as a straight line."""
    above = values > floor
    keep = above.copy()
    keep[1:] |= above[:-1]
    keep[:-1] |= above[1:]
    keep[[0, -1]] = True
    return t[keep], values[keep]


def _pns_lane(lane_id: str, title: str, color: str, top: float, t, values) -> Lane:
    return Lane(
        id=lane_id,
        title=title,
        unit="%",
        color=color,
        segments=[_points(t, values, digits=2)],
        domain=[0.0, top],
        ticks=[0.0, 100.0],
        tick_labels=["0", "100"],
    )


def pns_data(seq: pp.Sequence, gradient_asc: str | Path | None = None) -> dict:
    """PNS prediction (`pns.pns_prediction`) as JSON-ready data, in ms and percent of the
    stimulation limit."""
    p = pns_prediction(seq, gradient_asc)
    out = {
        "reason": p.reason,
        "hardware": p.hardware,
        "asc_file": p.asc_file,
        "example": p.asc_file is None,
        "peak_percent": round(100 * p.peak, 2),
        "peak_time_ms": round(p.peak_time_s * 1e3, 4) if p.peak_time_s is not None else None,
        "axis_peaks_percent": {axis: round(100 * v, 2) for axis, v in p.axis_peaks.items()},
        "end_ms": round(float(p.t_s[-1]) * 1e3, 4) if p.t_s.size else None,
        "lanes": [],
        # The TR that holds the peak, in ms, for the card's zoomed view; None without a TR
        # definition or with only one TR.
        "peak_tr_ms": None,
    }
    if p.reason is not None:
        return out

    window = peak_tr_window(seq, p.peak_time_s)
    if window is not None:
        out["peak_tr_ms"] = [round(w * 1e3, 4) for w in window]
    top = 1.1 * max(100.0, 100 * p.peak)
    series = [("pns", "All axes", "ink-2", p.norm)]
    series += [(f"g{a}", f"G{a}", _AXIS_COLOR[a], p.axes[a]) for a in "xyz"]
    for lane_id, title, color, values in series:
        t, v = _active_samples(p.t_s, 100 * values, _PNS_ZERO_PERCENT)
        t, v = _max_envelope(t, v, _PNS_MAX_POINTS)
        out["lanes"].append(_pns_lane(lane_id, title, color, top, t, v))
    out["lanes"] = _lanes_json(out["lanes"])
    return out


def _pns_html(p: dict, card_id: str) -> str:
    """The body of the "PNS prediction" card: the result, the table, the chart and its
    explanation, or a note that there is no prediction."""
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
    table = _table(
        ["Quantity", "Value"],
        [
            ["Hardware", hardware],
            ["Peak, all axes (%)", f"{peak:.1f} at {p['peak_time_ms']:.3f} ms"],
            *[[f"Peak, G{a} (%)", f"{axes[a]:.1f}"] for a in "xyz"],
        ],
    )
    aria = (
        "PNS prediction: all axes, Gx, Gy and Gz in percent of the stimulation limit "
        f"against time, peak {peak:.1f} %"
    )
    controls = zoom_note = ""
    if p["peak_tr_ms"] is not None:
        lo, hi = p["peak_tr_ms"]
        controls = (
            '<div class="controls" role="group" aria-label="PNS time window">'
            '<button type="button" data-pns-view="full" aria-pressed="true">'
            f"Full sequence (0–{p['end_ms']:g} ms)</button>"
            '<button type="button" data-pns-view="peak-tr" aria-pressed="false">'
            f"TR with the highest PNS ({lo:g}–{hi:g} ms)</button></div>"
        )
        zoom_note = (
            "TR with the highest PNS shows the TR that holds the peak, counted from the "
            "sequence start in steps of the TR definition. "
        )
    chart = (
        f'<div class="chart" id="{card_id}-chart">'
        f'<svg id="{card_id}-diagram" tabindex="0" role="img" aria-label="{html.escape(aria)}">'
        "</svg>"
        f'<div class="tip" id="{card_id}-tip" hidden></div></div>'
    )
    note = (
        '<p class="muted">The prediction is the SAFE model (Hebrank and Gebhardt) in pypulseq '
        "<code>calculate_pns</code>, a port of safe_pns_prediction by Szczepankiewicz and "
        "Witzel. Each axis is its predicted stimulation as a percent of that axis's "
        "stimulation limit. All axes is the root-sum-of-squares of the three, and the check "
        "passes below 100 %. The gradients are sampled at the gradient raster time up to the "
        "last gradient point. Each lane leaves out the inside of each run of samples at or "
        f"below {_PNS_ZERO_PERCENT:g} %. When a lane still has more than {_PNS_MAX_POINTS} "
        "samples, it draws the maximum of each run. "
        f"{zoom_note}The model can be inaccurate, and the scanner's own stimulation monitor "
        "decides: record the PNS level that the scanner reports. "
        "Click the chart to mark the centre for the zoom buttons. "
        "Drag across the chart to zoom to that range. Hold Shift and drag, or scroll "
        "sideways, to pan.</p>"
    )
    return status + source + table + controls + _zoom_controls(f"{card_id}-diagram") + chart + note


def pns_card(
    seq: NamedSequence, gradient_asc: str | Path | None = None, card_id: str = "pns"
) -> Card:
    """The "PNS prediction" card for one sequence: the SAFE-model prediction (`pns_data`)
    as a status line, a table of the peak percent of the stimulation limit for all axes,
    Gx, Gy and Gz, and a chart of the stimulation over time, with a "peak TR" view when
    the sequence has a TR definition and more than one TR.

    The SAFE model runs over the whole gradient waveform, so this card is slow for a
    long sequence.

    Raises `NotImplementedError` for a sequence with the rotation extension
    (`extensions.refuse_rotations`).
    """
    refuse_rotations(seq.seq)
    data = pns_data(seq.seq, gradient_asc)
    return Card(
        id=card_id,
        title="PNS prediction",
        body_html=_pns_html(data, card_id),
        data=data,
        script="pns",
    )
