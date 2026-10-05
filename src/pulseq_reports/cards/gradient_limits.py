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

from ..markup import fmt, gamma_select_html
from ..page import Card, card_asset
from ..registry import CardSpec, ReportContext
from ..targets import ReportTarget
from ..units import (
    GammaEntry,
    gamma_entries,
    hz_per_m_per_s_to_t_per_m_per_s,
    hz_per_m_to_mt_per_m,
)
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


def _limited(targets: Sequence[ReportTarget]) -> list[ReportTarget]:
    """The targets that have hardware limits, in their order: each has its percent columns."""
    return [t for t in targets if t.profile.hardware_limits is not None]


def _rows(
    windowed: GradientLimits,
    index: SequenceIndex,
    gamma: float,
    limited: Sequence[ReportTarget],
) -> list[list[str]]:
    """The four rows (Gx, Gy, Gz, |G|) of HTML cells, from one `gradient_limits` call. The
    peak, slew and RMS cells are in mT/m and T/m/s for |`gamma`|. `windowed.whole_rms_hz_per_m`
    gives the extra "RMS over whole file" column when `windowed` is over a window (computed in
    that same call); it is None when there is no window. A percent cell follows the peak
    cell and the slew cell for each of `limited`: the value in Hz/m (Hz/m/s) changes into
    mT/m (T/m/s) with |gamma| of that target, then divides by its limit."""
    whole_rms = (
        None
        if windowed.whole_rms_hz_per_m is None
        else {
            axis: hz_per_m_to_mt_per_m(v, gamma) for axis, v in windowed.whole_rms_hz_per_m.items()
        }
    )
    vector_peak_mt = hz_per_m_to_mt_per_m(windowed.vector_peak_hz_per_m, gamma)

    def peak_pct(peak_hz_per_m: float) -> list[str]:
        return [
            _pct(
                hz_per_m_to_mt_per_m(peak_hz_per_m, t.gamma),
                t.profile.hardware_limits.max_grad_mt_per_m,
            )
            for t in limited
        ]

    def slew_pct(slew_hz_per_m_per_s: float) -> list[str]:
        return [
            _pct(
                hz_per_m_per_s_to_t_per_m_per_s(slew_hz_per_m_per_s, t.gamma),
                t.profile.hardware_limits.max_slew_t_per_m_per_s,
            )
            for t in limited
        ]

    rows = []
    axis_rms_mt = {}
    for axis in _AXES:
        a = windowed.axes[axis]
        label = _AXIS_LABEL[axis]
        peak_mt = hz_per_m_to_mt_per_m(a.peak_hz_per_m, gamma)
        slew_t = hz_per_m_per_s_to_t_per_m_per_s(a.max_slew_hz_per_m_per_s, gamma)
        axis_rms_mt[axis] = hz_per_m_to_mt_per_m(a.rms_hz_per_m, gamma)
        row = [
            label,
            _value_cell(peak_mt, a.peak_block, a.peak_time_s, index, f"{label} peak"),
            *peak_pct(a.peak_hz_per_m),
            _value_cell(slew_t, a.slew_block, a.slew_time_s, index, f"{label} max slew"),
            *slew_pct(a.max_slew_hz_per_m_per_s),
            fmt(axis_rms_mt[axis]),
        ]
        if whole_rms is not None:
            row.append(fmt(whole_rms[axis]))
        rows.append(row)

    # |G|, the three-axis vector. There is no vector slew (see GradientLimits), so that
    # cell and its percent cells are blank. The percent of limit compares the vector peak
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
        *peak_pct(windowed.vector_peak_hz_per_m),
        _NO_VALUE,
        *[_NO_VALUE] * len(limited),
        fmt(_vector_rms(axis_rms_mt)),
    ]
    if whole_rms is not None:
        vector_row.append(fmt(_vector_rms(whole_rms)))
    rows.append(vector_row)
    return rows


def _table_html(headers: list[str], rows: list[list[str]]) -> str:
    """The markup of `markup.html_table`, written locally because the peak and slew cells
    hold a "Show" button and the percent headings hold a swatch: every header and every cell
    of `rows` is HTML already."""
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _percent_heading(target: ReportTarget) -> str:
    """The heading of a percent column: the swatch of the color of `target` (as
    `markup.target_legend_html` writes one) and its name, escaped."""
    swatch = (
        f'<span class="swatch" style="background: var(--{target.color})" '
        f'aria-hidden="true"></span>'
    )
    return f"{swatch}% of limit ({html.escape(target.profile.name)})"


def _tables(
    windowed: GradientLimits,
    index: SequenceIndex,
    has_window: bool,
    entries: Sequence[GammaEntry],
    limited: Sequence[ReportTarget],
) -> str:
    """The table of the card for one range (a window, or the whole file), from its one
    `gradient_limits` call, and the reason note when there is no gradient event. With more
    than one of `entries`, one table for each, each in an element with `data-gamma-entry`
    (hidden but the first), as `PulseqReport.gammaSelect` shows them; the percent columns are
    in each table, because they use the gamma of their own target."""
    percent = [_percent_heading(t) for t in limited]
    rms = (
        ["RMS (mT/m)"]
        if not has_window
        else ["RMS over window (mT/m)", "RMS over whole file (mT/m)"]
    )
    headers = [
        *map(html.escape, ("Axis", "Peak (mT/m)")),
        *percent,
        html.escape("Max slew (T/m/s)"),
        *percent,
        *map(html.escape, rms),
    ]

    parts = []
    for k, entry in enumerate(entries):
        part = _table_html(headers, _rows(windowed, index, entry.gamma, limited))
        if windowed.reason is not None:
            part += f'<p class="muted">{html.escape(f"{windowed.reason}.")}</p>'
        if len(entries) > 1:
            hidden = "" if k == 0 else " hidden"
            part = f'<div data-gamma-entry="{k}"{hidden}>{part}</div>'
        parts.append(part)
    return "\n".join(parts)


def _limits_note(targets: Sequence[ReportTarget]) -> str:
    """The sentence at the end of the card about the limits of the targets: the label and the
    values of the limits of each target that has them, and the name of each target that has
    none. The text is HTML."""
    if not targets:
        return "No targets were given, so there is no percent of a limit."
    limited = _limited(targets)
    unlimited = [t for t in targets if t.profile.hardware_limits is None]
    parts = []
    if limited:
        items = []
        for t in limited:
            limits = t.profile.hardware_limits
            items.append(
                f"{limits.label} ({fmt(limits.max_grad_mt_per_m)} mT/m, "
                f"{fmt(limits.max_slew_t_per_m_per_s)} T/m/s)"
            )
        parts.append(f"Limits: {html.escape('; '.join(items))}.")
    else:
        parts.append("No target has limits, so there is no percent of a limit.")
    if unlimited:
        names = html.escape(", ".join(t.profile.name for t in unlimited))
        parts.append(f"No limits for: {names}.")
    return " ".join(parts)


def gradient_limits_card(
    seq: pp.Sequence,
    *,
    windows: Sequence[TimeWindow] | None = None,
    targets: Sequence[ReportTarget] = (),
    card_id: str = "gradient-limits",
) -> Card:
    """The "Gradient limits" card: one table with the peak amplitude, the peak slew rate
    and the RMS amplitude of each logical axis (Gx, Gy, Gz) and of the three-axis vector
    (|G|). The values are in Hz/m and Hz/m/s from `grad_limits.gradient_limits`, one call
    for each window, and the table shows mT/m and T/m/s.

    Each of `targets` that has `profile.hardware_limits` adds two "% of limit" columns, one
    after the peak and one after the max slew, with the color and the name of the target in
    the heading. A percent changes the value in Hz/m (Hz/m/s) into mT/m (T/m/s) with |gamma|
    of that target (`target.gamma`), then divides it by the limit of the target and
    multiplies by 100, as the gradient checks of pulseq-checks do. The |G| row compares the
    vector peak with the max amplitude limit. A target without limits has no column, and the
    note at the end names it. Without a target that has limits, the card has no percent
    columns, and the note says so.

    The peak, slew and RMS columns use |gamma| of one entry of
    `units.gamma_entries(targets, seq, signed=False)`. With one entry, the card has one table
    for each range. With more than one (targets with different |gamma|), it has one table for
    each entry, each in an element with `data-gamma-entry` (the index of the entry; all but
    the first `hidden`), and, near the top, the control of `markup.gamma_select_html`. Without
    `targets`, the entry is `seq.system.gamma`.

    With `windows` given, the card has one table for each window (for each entry), headed by
    an `<h3>` with the window's label. The peak and the slew columns are over the window, and
    the RMS column is split into "RMS over window" and "RMS over whole file". With
    `windows=None`, there is one table, with one RMS column, over the whole file.

    The peak and max slew cells also give where the value is reached: the block ID and the
    time in ms from the sequence start (`AxisResult.peak_block` and `peak_time_s`,
    `slew_block` and `slew_time_s`, `GradientLimits.vector_peak_block` and
    `vector_peak_time_s`), and a "Show" button. Its script (`assets/cards/gradient-limits.js`)
    sends a `goto` message that shows the block in the diagram with the anchor at that time,
    and shows the button only while a card (the diagram) acts on `goto`. A value of 0 has no
    block, no time and no button.

    The note at the end of the card gives the label and the values of the limits of each
    target, and the name of each target without limits.

    No chart and no data (`data=None`). The card publishes `PUBLISHES` (`goto`). It has
    `scripts` with `assets/cards/gradient-limits.js` when a table has a button (the script
    also runs the gamma control), and with `assets/cards/gamma-select.js` when there is a
    control and no button.

    Raises `NotImplementedError` for a sequence with the rotation extension
    (`extensions.refuse_rotations`). Raises `ValueError` for a window that is not inside
    the sequence or that does not end after its start.
    """
    refuse_rotations(seq)
    ranges: list[tuple[str | None, tuple[float, float] | None]]
    if windows is None:
        ranges = [(None, None)]
    else:
        _check_windows(seq, windows)
        ranges = [(w.label, (w.start_s, w.end_s)) for w in windows]
    entries = gamma_entries(targets, seq, signed=False)
    limited = _limited(targets)
    index = sequence_index(seq)

    parts = []
    for label, window in ranges:
        # One call: with a window, gradient_limits also computes the whole-file RMS in the
        # same pass over the index (GradientLimits.whole_rms_hz_per_m), instead of a second
        # call for it.
        tables = _tables(
            gradient_limits(seq, window=window), index, window is not None, entries, limited
        )
        parts.append(tables if label is None else f"<h3>{html.escape(label)}</h3>\n{tables}")
    body = "\n\n".join(parts)
    has_button = "<button" in body
    control = gamma_select_html(entries, card_id)
    if control:
        body = control + "\n" + body
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
        + _limits_note(targets)
        + "</p>"
    )
    if has_button:
        script, scripts = "gradient-limits", (card_asset("gradient-limits"),)
    elif control:
        script, scripts = "gamma-select", (card_asset("gamma-select"),)
    else:
        script, scripts = None, ()
    return Card(
        id=card_id,
        title="Gradient limits",
        body_html=body,
        data=None,
        script=script,
        scripts=scripts,
        publishes=PUBLISHES,
    )


def _build(ctx: ReportContext) -> Card:
    return gradient_limits_card(ctx.seq, targets=ctx.targets, card_id=SPEC.name)


SPEC = CardSpec("gradient-limits", 70, _build, (), publishes=PUBLISHES)
