"""Sequence diagram card: RF, ADC and gradient waveforms against time, with one button
for each time window that the caller gives."""

import html
from collections.abc import Sequence

from ..markup import _zoom_controls
from ..page import Card
from ..seq_utils import NamedSequence
from ..waveforms import (
    DIAGRAM_POINT_BUDGET,
    TimeWindow,
    duration_s,
    file_envelope,
    file_lanes,
    point_count,
)

# The envelope bins for a view of `point_budget` points: 6 lanes, and up to 3 points
# for each bin and lane.
_BINS_DIVISOR = 6 * 3
# Two times that round to the same 0.1 µs are the same time.
_SAME_TIME_S = 1e-7


def _ms(t_s: float) -> float:
    return round(t_s * 1e3, 4)


def _validate(seqs: Sequence[NamedSequence], windows: Sequence[TimeWindow]) -> None:
    if not windows:
        raise ValueError("the diagram card needs at least one time window")
    for w in windows:
        if not 0 <= w.file_index < len(seqs):
            raise ValueError(f"window {w.label!r}: file_index {w.file_index} is not a file")
        if not w.end_s > w.start_s:
            raise ValueError(f"window {w.label!r}: the end is not after the start")


def _diagram_data(
    seqs: Sequence[NamedSequence], windows: Sequence[TimeWindow], point_budget: int
) -> tuple[dict, list[str]]:
    """The card data, and the names of the files that have an envelope view.

    The data is {"lane_sets": [...], "windows": [...]}. A lane set is {"lanes",
    "extent_ms", "envelope"}. A window is {"label", "lane_set", "view_ms"}: the button
    text, the index of its lane set, and the initial view.

    A file within `point_budget` has one lane set with the exact lanes of the whole file,
    and each of its windows is a view into it (the vb-pulseq behavior). A file over the
    budget has one lane set for each window: a window of the whole file is an envelope
    of `point_budget // 18` bins; another window has the exact lanes of its blocks, with
    the window as the extent, or an envelope of the window when those are over the
    budget too.
    """
    lane_sets: list[dict] = []
    out_windows: list[dict] = []
    envelope_files: list[str] = []
    whole_file_set: dict[int, int] = {}  # file index -> lane set of a file within budget
    over_budget: set[int] = set()
    bins = max(1, point_budget // _BINS_DIVISOR)

    for w in windows:
        named = seqs[w.file_index]
        seq = named.seq
        end = duration_s(seq)
        label = w.label if len(seqs) == 1 else f"{named.name}: {w.label}"
        view = [_ms(w.start_s), _ms(w.end_s)]

        if w.file_index not in whole_file_set and w.file_index not in over_budget:
            if point_count(seq) <= point_budget:
                whole_file_set[w.file_index] = len(lane_sets)
                lane_sets.append(
                    {"lanes": file_lanes(seq), "extent_ms": [0.0, _ms(end)], "envelope": False}
                )
            else:
                over_budget.add(w.file_index)

        if w.file_index in whole_file_set:
            index = whole_file_set[w.file_index]
        else:
            whole = w.start_s <= _SAME_TIME_S and w.end_s >= end - _SAME_TIME_S
            if whole:
                lanes, extent, envelope = file_envelope(seq, bins), [0.0, _ms(end)], True
            elif point_count(seq, w.start_s, w.end_s) <= point_budget:
                lanes, extent, envelope = file_lanes(seq, w.start_s, w.end_s), view, False
            else:
                lanes, extent, envelope = file_envelope(seq, bins, w.start_s, w.end_s), view, True
            if envelope and named.name not in envelope_files:
                envelope_files.append(named.name)
            index = len(lane_sets)
            lane_sets.append({"lanes": lanes, "extent_ms": extent, "envelope": envelope})
        out_windows.append({"label": label, "lane_set": index, "view_ms": view})
    return {"lane_sets": lane_sets, "windows": out_windows}, envelope_files


def diagram_card(
    seqs: Sequence[NamedSequence],
    windows: Sequence[TimeWindow],
    card_id: str = "diagram",
    point_budget: int = DIAGRAM_POINT_BUDGET,
) -> Card:
    """The "Sequence diagram" card: one button for each of `windows`, in the given order.
    The first window is the initial view. With more than one file, each button text
    starts with the file name. `point_budget` is the largest number of exact points that
    the card sends for one file (see `_diagram_data`); over it, the card sends an
    envelope or only the points of the windows, so that the page stays small.

    Raises ValueError when `windows` is empty, or a window names no file or ends before
    it starts.
    """
    _validate(seqs, windows)
    data, envelope_files = _diagram_data(seqs, windows, point_budget)
    buttons = "".join(
        f'<button type="button" data-window="{i}" aria-pressed="{str(i == 0).lower()}">'
        f"{html.escape(w['label'])}</button>"
        for i, w in enumerate(data["windows"])
    )
    svg_id = f"{card_id}-diagram"
    envelope_note = ""
    if envelope_files:
        bins = max(1, point_budget // _BINS_DIVISOR)
        envelope_note = (
            f'<p class="muted">{html.escape(", ".join(envelope_files))}: the file has too many '
            "points to send them all, so a view of the whole file shows the minimum and the "
            f"maximum of each waveform in each of {bins} equal time bins, without the RF "
            "phase, and ADC windows closer than one bin are merged. The other views show "
            "every point, unless they also have too many points; then they show the same "
            "minimum and maximum for their own time range.</p>"
        )
    body = (
        f'<div class="controls" role="group" aria-label="Time window">{buttons}</div>\n'
        + _zoom_controls(svg_id)
        + f'\n<div class="chart" id="{card_id}-chart">\n'
        f'<svg id="{svg_id}" tabindex="0" role="img"\n'
        '  aria-label="Sequence diagram: RF magnitude and phase, ADC, Gx, Gy and Gz against '
        'time"></svg>\n'
        f'<div class="tip" id="{card_id}-tip" hidden></div>\n'
        "</div>\n"
        '<p class="muted">Hover the diagram, or focus it and use the arrow keys, to read '
        "values.\nRF phase is drawn where |B1| is above 1% of that pulse's peak.\n"
        "Click the chart to mark the centre for the zoom buttons. Drag across the chart to "
        "zoom to that range. Hold Shift and drag, or scroll sideways, to pan.</p>" + envelope_note
    )
    return Card(id=card_id, title="Sequence diagram", body_html=body, data=data, script="diagram")
