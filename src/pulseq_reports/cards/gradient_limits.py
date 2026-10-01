"""Gradient limits card: how near a sequence's gradients get to the hardware limits,
on each axis, and as a three-axis vector."""

import html
import math
from collections.abc import Sequence

import numpy as np
import pypulseq as pp

from .. import options
from ..extensions import refuse_rotations
from ..grad_limits import GradientLimits, HardwareLimits, _default_limits, gradient_limits
from ..markup import fmt
from ..page import Card, Check, card_asset
from ..registry import CardSpec, ReportContext
from ..seq_index import SequenceIndex, sequence_index
from ..seq_utils import GAMMA
from ..waveforms import TimeWindow, _check_windows

_AXES = ("x", "y", "z")
_AXIS_LABEL = {"x": "Gx", "y": "Gy", "z": "Gz"}
_NO_VALUE = "—"
# Relative tolerance: the unit conversions are floats, and a value at the limit passes.
_LIMIT_TOLERANCE = 1e-9
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


def _rows(windowed: GradientLimits, index: SequenceIndex) -> list[list[str]]:
    """The four rows (Gx, Gy, Gz, |G|) of HTML cells, from one `gradient_limits` call.
    `windowed.whole_rms_mt_per_m` gives the extra "RMS over whole file" column when
    `windowed` is over a window (computed in that same call); it is None when there is
    no window."""
    limits = windowed.limits
    whole_rms = windowed.whole_rms_mt_per_m
    rows = []
    for axis in _AXES:
        a = windowed.axes[axis]
        label = _AXIS_LABEL[axis]
        row = [
            label,
            _value_cell(a.peak_mt_per_m, a.peak_block, a.peak_time_s, index, f"{label} peak"),
            _pct(a.peak_mt_per_m, limits.max_grad_mt_per_m),
            _value_cell(
                a.max_slew_t_per_m_per_s, a.slew_block, a.slew_time_s, index, f"{label} max slew"
            ),
            _pct(a.max_slew_t_per_m_per_s, limits.max_slew_t_per_m_per_s),
            fmt(a.rms_mt_per_m),
        ]
        if whole_rms is not None:
            row.append(fmt(whole_rms[axis]))
        rows.append(row)

    # |G|, the three-axis vector. There is no vector slew (see GradientLimits), so that
    # cell is blank. The percent of limit compares the vector peak with the per-axis
    # max_grad, because an oblique prescription can put the vector peak onto a single
    # physical axis.
    vector_row = [
        "|G|",
        _value_cell(
            windowed.vector_peak_mt_per_m,
            windowed.vector_peak_block,
            windowed.vector_peak_time_s,
            index,
            "|G| peak",
        ),
        _pct(windowed.vector_peak_mt_per_m, limits.max_grad_mt_per_m),
        _NO_VALUE,
        _NO_VALUE,
        fmt(_vector_rms({axis: windowed.axes[axis].rms_mt_per_m for axis in _AXES})),
    ]
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
    seq: pp.Sequence, window: tuple[float, float] | None, limits: HardwareLimits
) -> tuple[str, GradientLimits]:
    """The table of the card, and the reason note when there is no gradient event, for one
    range (`window`, or the whole file), with the `GradientLimits` that it shows."""
    headers = [
        "Axis",
        "Peak (mT/m)",
        "% of limit",
        "Max slew (T/m/s)",
        "% of limit",
    ]
    headers += (
        ["RMS (mT/m)"]
        if window is None
        else ["RMS over window (mT/m)", "RMS over whole file (mT/m)"]
    )

    # One call: with a window, gradient_limits also computes the whole-file RMS in the
    # same pass over the index (GradientLimits.whole_rms_mt_per_m), instead of a second
    # call for it.
    windowed = gradient_limits(seq, window=window, limits=limits)

    body = _table_html(headers, _rows(windowed, sequence_index(seq)))
    if windowed.reason is not None:
        body += f'<p class="muted">{html.escape(f"{windowed.reason}.")}</p>'
    return body, windowed


def _excess(what: str, value: float, limit: float, unit: str, table_name: str) -> str | None:
    """The message for a value above 100 % of its limit, or None."""
    if value <= limit * (1 + _LIMIT_TOLERANCE):
        return None
    return (
        f"{what} {fmt(value)} {unit} is {_pct(value, limit)} % of the {fmt(limit)} {unit} "
        f"limit in {table_name}"
    )


def _excesses(windowed: GradientLimits, table_name: str, check_norms: bool) -> list[str]:
    """The messages for the values of one table that are above 100 % of their limit: the
    peak amplitude and the peak slew of each axis, and with `check_norms` the |G| peak
    against the amplitude limit. A table with a `reason` has none."""
    if windowed.reason is not None:
        return []
    limits = windowed.limits
    found = []
    for axis in _AXES:
        a = windowed.axes[axis]
        label = _AXIS_LABEL[axis]
        found += [
            _excess(f"{label} peak", a.peak_mt_per_m, limits.max_grad_mt_per_m, "mT/m", table_name),
            _excess(
                f"{label} slew",
                a.max_slew_t_per_m_per_s,
                limits.max_slew_t_per_m_per_s,
                "T/m/s",
                table_name,
            ),
        ]
    if check_norms:
        found.append(
            _excess(
                "|G| peak",
                windowed.vector_peak_mt_per_m,
                limits.max_grad_mt_per_m,
                "mT/m",
                table_name,
            )
        )
    return [message for message in found if message is not None]


def gradient_limits_card(
    seq: pp.Sequence,
    *,
    windows: Sequence[TimeWindow] | None = None,
    limits: HardwareLimits | None = None,
    check_norms: bool = False,
    card_id: str = "gradient-limits",
) -> Card:
    """The "Gradient limits" card: one table with the peak amplitude, the peak slew rate
    and the RMS amplitude of each logical axis (Gx, Gy, Gz) and of the three-axis vector
    (|G|), each as a percent of `limits` where a limit applies (see
    `grad_limits.gradient_limits`).

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

    The note at the end of the card gives the limits, with their label and their values.

    No chart and no data (`data=None`). The card publishes `PUBLISHES` (`goto`), and has
    `scripts` with `assets/cards/gradient-limits.js` when a table has a button.

    The card has one check, `gradient-limits`. It fails when the peak amplitude or the peak
    slew of Gx, Gy or Gz in a table is above 100 % of its limit; the message names the
    axis, the value and the table (the window's label, or the whole file). With
    `check_norms`, it also fails when the |G| peak of a table is above 100 % of the amplitude
    limit: a check that does not depend on the rotation of the gradients onto the scanner's
    axes. The library has no vector slew, so there is no check on it. A table with no
    gradient event has no value to check.

    Raises `NotImplementedError` for a sequence with the rotation extension
    (`extensions.refuse_rotations`). Raises `ValueError` for a window that is not inside
    the sequence or that does not end after its start.
    """
    refuse_rotations(seq)
    used = limits if limits is not None else _default_limits(seq, GAMMA)
    excesses: list[str] = []
    if windows is None:
        body, windowed = _table(seq, None, used)
        excesses += _excesses(windowed, "the whole file", check_norms)
    else:
        _check_windows(seq, windows)
        parts = []
        for w in windows:
            table, windowed = _table(seq, (w.start_s, w.end_s), used)
            parts.append(f"<h3>{html.escape(w.label)}</h3>\n{table}")
            excesses += _excesses(windowed, f'the window "{w.label}"', check_norms)
        body = "\n\n".join(parts)
    limits_text = (
        f"{used.label or ''} ({fmt(used.max_grad_mt_per_m)} mT/m, "
        f"{fmt(used.max_slew_t_per_m_per_s)} T/m/s)"
    )
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
        f"Limits: {html.escape(limits_text)}.</p>"
    )
    check = Check(
        name="gradient-limits",
        passed=not excesses,
        message=(
            "; ".join(excesses)
            if excesses
            else "No peak amplitude or peak slew"
            + (" (or |G| peak)" if check_norms else "")
            + f" is above its limit ({used.label})."
        ),
    )
    has_button = "<button" in body
    return Card(
        id=card_id,
        title="Gradient limits",
        body_html=body,
        data=None,
        script="gradient-limits" if has_button else None,
        scripts=(card_asset("gradient-limits"),) if has_button else (),
        checks=(check,),
        publishes=PUBLISHES,
    )


def _build(ctx: ReportContext) -> Card:
    return gradient_limits_card(
        ctx.seq,
        limits=ctx.option(options.limits),
        check_norms=ctx.option(options.check_norms),
        card_id=SPEC.name,
    )


SPEC = CardSpec(
    "gradient-limits", 70, _build, (options.limits, options.check_norms), publishes=PUBLISHES
)
