"""Gradient limits card: how near a sequence's gradients get to the hardware limits,
on each axis, and as a three-axis vector."""

import html
import math
from collections.abc import Sequence

import numpy as np
import pypulseq as pp
from pulseq_analysis.extensions import refuse_rotations
from pulseq_analysis.grad_limits import GradientLimits, gradient_limits
from pulseq_analysis.seq_index import SequenceIndex, sequence_index
from pulseq_checks import HardwareLimits

from .. import options
from ..markup import fmt
from ..page import Card, card_asset
from ..registry import CardSpec, ReportContext
from ..units import PROTON_GAMMA, hz_per_m_per_s_to_t_per_m_per_s, hz_per_m_to_mt_per_m
from ..waveforms import TimeWindow, _check_windows

_AXES = ("x", "y", "z")
_AXIS_LABEL = {"x": "Gx", "y": "Gy", "z": "Gz"}
_NO_VALUE = "—"
# The narrowest view of a "Show" button, as the diagram's `goto` of a block.
_GOTO_MIN_VIEW_S = 1e-3

PUBLISHES = ("goto",)


def _pct(value: float, limit: float) -> str:
    return fmt(value / limit * 100) if limit > 0 else _NO_VALUE


def _vector_rms(axis_rms_mt_per_m: dict[str, float]) -> float:
    """The RMS of |G|: the mean of |G|² is the sum of the three axis means of G²."""
    return math.sqrt(sum(axis_rms_mt_per_m[axis] ** 2 for axis in _AXES))


def _goto_button(index: SequenceIndex, block_id: int, time_s: float, what: str) -> str:
    """A hidden "Show" button whose `goto` message (the card script) shows the block
    `block_id` in the diagram, with the anchor at `time_s`. The view is the block with half its
    duration on each side, at least 1 ms wide, as the diagram's own `goto` of a block."""
    play = int(np.flatnonzero(index.block_id == block_id)[0])
    start = float(index.start_s[play])
    duration = float(index.duration_s[play])
    half = max(2 * duration, _GOTO_MIN_VIEW_S) / 2
    middle = start + duration / 2
    label = html.escape(f"Show the {what} in the diagram", quote=True)
    return (
        f'<button type="button" data-t0="{middle - half!r}" data-t1="{middle + half!r}" '
        f'data-anchor="{time_s!r}" aria-label="{label}" hidden>Show</button>'
    )


def _value_cell(
    value: float, block_id: int | None, time_s: float, index: SequenceIndex, what: str
) -> str:
    """The HTML of a peak or slew cell: the value, then the block ID and the time (ms from the
    sequence start) where it is reached and a "Show" button, when a block is credited."""
    text = fmt(value)
    if block_id is None:
        return html.escape(text)
    text += f" (block {block_id}, {time_s * 1e3:.3f} ms)"
    return f"{html.escape(text)} {_goto_button(index, block_id, time_s, what)}"


def _rows(
    windowed: GradientLimits, index: SequenceIndex, limits: HardwareLimits | None
) -> list[list[str]]:
    """The four rows (Gx, Gy, Gz, |G|) of HTML cells, from one `gradient_limits` call.
    `windowed.whole_rms_hz_per_m` gives the extra "RMS over whole file" column when
    `windowed` is over a window (computed in that same call); it is None when there is
    no window. The rows have the two "% of limit" cells only when `limits` is given."""
    whole_rms = (
        None
        if windowed.whole_rms_hz_per_m is None
        else {
            axis: hz_per_m_to_mt_per_m(v, PROTON_GAMMA)
            for axis, v in windowed.whole_rms_hz_per_m.items()
        }
    )
    vector_peak_mt = hz_per_m_to_mt_per_m(windowed.vector_peak_hz_per_m, PROTON_GAMMA)
    rows = []
    axis_rms_mt = {}
    for axis in _AXES:
        a = windowed.axes[axis]
        label = _AXIS_LABEL[axis]
        peak_mt = hz_per_m_to_mt_per_m(a.peak_hz_per_m, PROTON_GAMMA)
        slew_t = hz_per_m_per_s_to_t_per_m_per_s(a.max_slew_hz_per_m_per_s, PROTON_GAMMA)
        axis_rms_mt[axis] = hz_per_m_to_mt_per_m(a.rms_hz_per_m, PROTON_GAMMA)
        row = [
            label,
            _value_cell(peak_mt, a.peak_block, a.peak_time_s, index, f"{label} peak"),
        ]
        if limits is not None:
            row.append(_pct(peak_mt, limits.max_grad_mt_per_m))
        row.append(_value_cell(slew_t, a.slew_block, a.slew_time_s, index, f"{label} max slew"))
        if limits is not None:
            row.append(_pct(slew_t, limits.max_slew_t_per_m_per_s))
        row.append(fmt(axis_rms_mt[axis]))
        if whole_rms is not None:
            row.append(fmt(whole_rms[axis]))
        rows.append(row)

    # |G|, the three-axis vector. There is no vector slew (see GradientLimits), so that
    # cell and its percent cell are blank. The percent of limit compares the vector peak
    # with the per-axis max_grad, because an oblique prescription can put the vector peak
    # onto a single physical axis.
    vector_row = [
        "|G|",
        _value_cell(
            vector_peak_mt,
            windowed.vector_peak_block,
            windowed.vector_peak_time_s,
            index,
            "|G| peak",
        ),
    ]
    if limits is not None:
        vector_row.append(_pct(vector_peak_mt, limits.max_grad_mt_per_m))
    vector_row.append(_NO_VALUE)
    if limits is not None:
        vector_row.append(_NO_VALUE)
    vector_row.append(fmt(_vector_rms(axis_rms_mt)))
    if whole_rms is not None:
        vector_row.append(fmt(_vector_rms(whole_rms)))
    rows.append(vector_row)
    return rows


def _table_html(headers: list[str], rows: list[list[str]]) -> str:
    """The markup of `markup.html_table`, written locally because the peak and slew cells
    hold a "Show" button: every cell of `rows` is HTML already."""
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _table(
    seq: pp.Sequence, window: tuple[float, float] | None, limits: HardwareLimits | None
) -> str:
    """The table of the card, and the reason note when there is no gradient event, for one
    range (`window`, or the whole file). It has the "% of limit" columns only when `limits`
    is given."""
    headers = ["Axis", "Peak (mT/m)"]
    if limits is not None:
        headers.append("% of limit")
    headers.append("Max slew (T/m/s)")
    if limits is not None:
        headers.append("% of limit")
    headers += (
        ["RMS (mT/m)"]
        if window is None
        else ["RMS over window (mT/m)", "RMS over whole file (mT/m)"]
    )

    # One call: with a window, gradient_limits also computes the whole-file RMS in the
    # same pass over the index (GradientLimits.whole_rms_hz_per_m), instead of a second
    # call for it.
    windowed = gradient_limits(seq, window=window)

    body = _table_html(headers, _rows(windowed, sequence_index(seq), limits))
    if windowed.reason is not None:
        body += f'<p class="muted">{html.escape(f"{windowed.reason}.")}</p>'
    return body


def gradient_limits_card(
    seq: pp.Sequence,
    *,
    windows: Sequence[TimeWindow] | None = None,
    limits: HardwareLimits | None = None,
    card_id: str = "gradient-limits",
) -> Card:
    """The "Gradient limits" card: one table with the peak amplitude, the peak slew rate
    and the RMS amplitude of each logical axis (Gx, Gy, Gz) and of the three-axis vector
    (|G|). With `limits` given, the table has two "% of limit" columns, the peak and the
    max slew as a percent of `limits` where a limit applies (see
    `grad_limits.gradient_limits`). With `limits=None`, it has no percent columns, and the
    note says that no limits were given. The card does not take limits from the sequence's
    system.

    With `windows` given, the card has one table for each window, headed by an `<h3>` with
    the window's label. The peak and the slew columns are over the window, and the RMS
    column is split into "RMS over window" and "RMS over whole file". With
    `windows=None`, there is one table, with one RMS column, over the whole file.

    The peak and max slew cells also give where the value is reached: the block ID and the
    time in ms from the sequence start (`AxisResult.peak_block` and `peak_time_s`,
    `slew_block` and `slew_time_s`, `GradientLimits.vector_peak_block` and
    `vector_peak_time_s`), and a "Show" button. Its script (`assets/cards/gradient-limits.js`)
    sends a `goto` message that shows the block in the diagram with the anchor at that time,
    and shows the button only while a card (the diagram) acts on `goto`. A value of 0 has no
    block, no time and no button.

    The note at the end of the card gives the limits, with their label and their values,
    when `limits` is given.

    No chart and no data (`data=None`). The card publishes `PUBLISHES` (`goto`), and has
    `scripts` with `assets/cards/gradient-limits.js` when a table has a button.

    Raises `NotImplementedError` for a sequence with the rotation extension
    (`extensions.refuse_rotations`). Raises `ValueError` for a window that is not inside
    the sequence or that does not end after its start.
    """
    refuse_rotations(seq)
    if windows is None:
        body = _table(seq, None, limits)
    else:
        _check_windows(seq, windows)
        parts = []
        for w in windows:
            table = _table(seq, (w.start_s, w.end_s), limits)
            parts.append(f"<h3>{html.escape(w.label)}</h3>\n{table}")
        body = "\n\n".join(parts)
    if limits is None:
        limits_sentence = "No limits were given, so there is no percent of a limit."
    else:
        limits_text = (
            f"{limits.label or ''} ({fmt(limits.max_grad_mt_per_m)} mT/m, "
            f"{fmt(limits.max_slew_t_per_m_per_s)} T/m/s)"
        )
        limits_sentence = f"Limits: {html.escape(limits_text)}."
    body += (
        '<p class="muted">Peak is the largest gradient amplitude at any point of the '
        "waveform. Max slew is the largest rate of change between neighbouring points "
        "of one gradient event, or the step at a block junction divided by the gradient "
        "raster time of the file, as pypulseq's <code>add_block</code> checks it. RMS is the "
        "root-mean-square amplitude over the range "
        "shown. For |G|, the peak is the largest magnitude of the three-axis gradient "
        "vector, evaluated at every point where any axis changes slope, and the RMS is "
        "the RMS of that magnitude. These are the logical "
        "sequence axes: the scanner rotates them onto the physical gradient axes, so on "
        "an oblique slice, one physical axis can reach up to the |G| row's peak even "
        "when no logical axis is near the limit. The block and the time after a value are "
        "where it is first reached, in ms from the start of the sequence; for the max "
        "slew, the start of the steepest segment, or the block junction. "
        + limits_sentence
        + "</p>"
    )
    has_button = "<button" in body
    return Card(
        id=card_id,
        title="Gradient limits",
        body_html=body,
        data=None,
        script="gradient-limits" if has_button else None,
        scripts=(card_asset("gradient-limits"),) if has_button else (),
        publishes=PUBLISHES,
    )


def _build(ctx: ReportContext) -> Card:
    return gradient_limits_card(
        ctx.seq,
        limits=ctx.option(options.limits),
        card_id=SPEC.name,
    )


SPEC = CardSpec("gradient-limits", 70, _build, (options.limits,), publishes=PUBLISHES)
