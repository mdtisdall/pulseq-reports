"""Gradient limits card: how near a sequence's gradients get to the hardware limits,
on each axis, and as a three-axis vector."""

import html
import math
from collections.abc import Sequence

from ..extensions import refuse_rotations
from ..grad_limits import GradientLimits, gradient_limits
from ..markup import _fmt, _table
from ..page import Card
from ..seq_utils import NamedSequence

_AXES = ("x", "y", "z")
_AXIS_LABEL = {"x": "Gx", "y": "Gy", "z": "Gz"}
_NO_VALUE = "—"


def _pct(value: float, limit: float) -> str:
    return _fmt(value / limit * 100) if limit > 0 else _NO_VALUE


def _vector_rms(result: GradientLimits) -> float:
    """The RMS of |G|: the mean of |G|² is the sum of the three axis means of G²."""
    return math.sqrt(sum(result.axes[axis].rms_mt_per_m ** 2 for axis in _AXES))


def _file_rows(
    windowed: GradientLimits, whole: GradientLimits | None, file_label: str | None
) -> list[list]:
    """The four rows (Gx, Gy, Gz, |G|) for one file. `whole` is the whole-file result,
    used only for the extra RMS column when `windowed` is over a window; None when
    there is no window. `file_label` is the file name for the first cell of the first
    row (blank for the other three rows), or None to leave out that column."""
    limits = windowed.limits
    rows = []
    for i, axis in enumerate(_AXES):
        a = windowed.axes[axis]
        row = [] if file_label is None else [file_label if i == 0 else ""]
        row += [
            _AXIS_LABEL[axis],
            _fmt(a.peak_mt_per_m),
            _pct(a.peak_mt_per_m, limits.max_grad_mt_per_m),
            _fmt(a.max_slew_t_per_m_per_s),
            _pct(a.max_slew_t_per_m_per_s, limits.max_slew_t_per_m_per_s),
            _fmt(a.rms_mt_per_m),
        ]
        if whole is not None:
            row.append(_fmt(whole.axes[axis].rms_mt_per_m))
        rows.append(row)

    # |G|, the three-axis vector. There is no vector slew (see GradientLimits), so that
    # cell is blank. The percent of limit compares the vector peak with the per-axis
    # max_grad, because an oblique prescription can put the vector peak onto a single
    # physical axis.
    vector_row = [] if file_label is None else [""]
    vector_row += [
        "|G|",
        _fmt(windowed.vector_peak_mt_per_m),
        _pct(windowed.vector_peak_mt_per_m, limits.max_grad_mt_per_m),
        _NO_VALUE,
        _NO_VALUE,
        _fmt(_vector_rms(windowed)),
    ]
    if whole is not None:
        vector_row.append(_fmt(_vector_rms(whole)))
    rows.append(vector_row)
    return rows


def gradient_limits_card(
    seqs: Sequence[NamedSequence],
    window: tuple[float, float] | None = None,
    limits=None,
    card_id: str = "gradient-limits",
) -> Card:
    """The "Gradient limits" card: for each file, one table row group with the peak
    amplitude, the peak slew rate and the RMS amplitude of each logical axis (Gx, Gy,
    Gz) and of the three-axis vector (|G|), each as a percent of `limits` where a limit
    applies (see `grad_limits.gradient_limits`). With more than one file in `seqs`,
    the table has a leading "File" column with the file name (HTML-escaped) on the
    first row of each file's group.

    With `window` given, the peak and the slew columns are over `window`, and the RMS
    column is split into "RMS over window" and "RMS over whole file". With
    `window=None`, there is one RMS column, over the whole file.

    No chart: `data=None` and `script=None`.

    Raises `NotImplementedError` for a sequence with the rotation extension
    (`extensions.refuse_rotations`).
    """
    for ns in seqs:
        refuse_rotations(ns.seq)
    multi = len(seqs) > 1
    headers = (["File"] if multi else []) + [
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

    rows: list[list] = []
    reason_notes: list[str] = []
    limits_label = None
    for ns in seqs:
        windowed = gradient_limits(ns.seq, window=window, limits=limits)
        whole = gradient_limits(ns.seq, window=None, limits=limits) if window is not None else None
        limits_label = windowed.limits.label
        if windowed.reason is not None:
            reason_notes.append(f"{ns.name}: {windowed.reason}.")
        rows.extend(_file_rows(windowed, whole, ns.name if multi else None))

    body = _table(headers, rows)
    for note in reason_notes:
        body += f'<p class="muted">{html.escape(note)}</p>'
    body += (
        '<p class="muted">Peak is the largest gradient amplitude at any point of the '
        "waveform. Max slew is the largest rate of change between neighbouring points "
        "of one gradient event. RMS is the root-mean-square amplitude over the range "
        "shown. For |G|, the peak is the largest magnitude of the three-axis gradient "
        "vector, evaluated at every point where any axis changes slope, and the RMS is "
        "the RMS of that magnitude. These are the logical "
        "sequence axes: the scanner rotates them onto the physical gradient axes, so on "
        "an oblique slice, one physical axis can reach up to the |G| row's peak even "
        f"when no logical axis is near the limit. Limits: {html.escape(limits_label or '')}.</p>"
    )
    return Card(id=card_id, title="Gradient limits", body_html=body, data=None, script=None)
