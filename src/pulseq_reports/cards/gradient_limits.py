"""Gradient limits card: how near a sequence's gradients get to the hardware limits,
on each axis, and as a three-axis vector."""

import html
import math
from collections.abc import Sequence

import pypulseq as pp

from ..extensions import refuse_rotations
from ..grad_limits import GradientLimits, HardwareLimits, _default_limits, gradient_limits
from ..markup import fmt, html_table
from ..page import Card
from ..waveforms import TimeWindow, _check_windows

_AXES = ("x", "y", "z")
_AXIS_LABEL = {"x": "Gx", "y": "Gy", "z": "Gz"}
_NO_VALUE = "—"


def _pct(value: float, limit: float) -> str:
    return fmt(value / limit * 100) if limit > 0 else _NO_VALUE


def _vector_rms(axis_rms_mt_per_m: dict[str, float]) -> float:
    """The RMS of |G|: the mean of |G|² is the sum of the three axis means of G²."""
    return math.sqrt(sum(axis_rms_mt_per_m[axis] ** 2 for axis in _AXES))


def _rows(windowed: GradientLimits) -> list[list]:
    """The four rows (Gx, Gy, Gz, |G|), from one `gradient_limits` call.
    `windowed.whole_rms_mt_per_m` gives the extra "RMS over whole file" column when
    `windowed` is over a window (computed in that same call); it is None when there is
    no window."""
    limits = windowed.limits
    whole_rms = windowed.whole_rms_mt_per_m
    rows = []
    for axis in _AXES:
        a = windowed.axes[axis]
        row = [
            _AXIS_LABEL[axis],
            fmt(a.peak_mt_per_m),
            _pct(a.peak_mt_per_m, limits.max_grad_mt_per_m),
            fmt(a.max_slew_t_per_m_per_s),
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
        fmt(windowed.vector_peak_mt_per_m),
        _pct(windowed.vector_peak_mt_per_m, limits.max_grad_mt_per_m),
        _NO_VALUE,
        _NO_VALUE,
        fmt(_vector_rms({axis: windowed.axes[axis].rms_mt_per_m for axis in _AXES})),
    ]
    if whole_rms is not None:
        vector_row.append(fmt(_vector_rms(whole_rms)))
    rows.append(vector_row)
    return rows


def _table(seq: pp.Sequence, window: tuple[float, float] | None, limits: HardwareLimits) -> str:
    """The table of the card, and the reason note when there is no gradient event, for one
    range (`window`, or the whole file)."""
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

    body = html_table(headers, _rows(windowed))
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
    (|G|), each as a percent of `limits` where a limit applies (see
    `grad_limits.gradient_limits`).

    With `windows` given, the card has one table for each window, headed by an `<h3>` with
    the window's label. The peak and the slew columns are over the window, and the RMS
    column is split into "RMS over window" and "RMS over whole file". With
    `windows=None`, there is one table, with one RMS column, over the whole file.

    The note at the end of the card gives the limits, with their label and their values.

    No chart: `data=None` and `script=None`.

    Raises `NotImplementedError` for a sequence with the rotation extension
    (`extensions.refuse_rotations`). Raises `ValueError` for a window that is not inside
    the sequence or that does not end after its start.
    """
    refuse_rotations(seq)
    used = limits if limits is not None else _default_limits(seq)
    if windows is None:
        body = _table(seq, None, used)
    else:
        _check_windows(seq, windows)
        body = "\n\n".join(
            f"<h3>{html.escape(w.label)}</h3>\n{_table(seq, (w.start_s, w.end_s), used)}"
            for w in windows
        )
    limits_text = (
        f"{used.label or ''} ({fmt(used.max_grad_mt_per_m)} mT/m, "
        f"{fmt(used.max_slew_t_per_m_per_s)} T/m/s)"
    )
    body += (
        '<p class="muted">Peak is the largest gradient amplitude at any point of the '
        "waveform. Max slew is the largest rate of change between neighbouring points "
        "of one gradient event, or the step at a block junction divided by the gradient "
        "raster time, as pypulseq's <code>add_block</code> checks it. RMS is the "
        "root-mean-square amplitude over the range "
        "shown. For |G|, the peak is the largest magnitude of the three-axis gradient "
        "vector, evaluated at every point where any axis changes slope, and the RMS is "
        "the RMS of that magnitude. These are the logical "
        "sequence axes: the scanner rotates them onto the physical gradient axes, so on "
        "an oblique slice, one physical axis can reach up to the |G| row's peak even "
        f"when no logical axis is near the limit. Limits: {html.escape(limits_text)}.</p>"
    )
    return Card(id=card_id, title="Gradient limits", body_html=body, data=None, script=None)
