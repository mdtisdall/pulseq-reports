"""Sequence diagram card: RF, ADC and gradient waveforms against time, with one button
for each time window that the caller gives.

The card sends the compressed block and event tables of each file that at least one
window uses (`diagram_data.diagram_tables`, `encode_tables`), not expanded points. The
browser (`assets/cards/diagram.js`, `assets/seq_lanes.js`) decodes them and draws the
exact waveform when a view has few enough points, or the minimum and the maximum of
each lane in each of the plot's time bins otherwise, so the card works for a file of up
to 10^7 blocks (`docs/plans/diagram-event-table.md`).
"""

import html
from collections.abc import Sequence

from ..diagram_data import diagram_tables, encode_tables, lane_meta
from ..extensions import refuse_rotations
from ..markup import _zoom_controls
from ..page import Card
from ..seq_utils import NamedSequence
from ..waveforms import TimeWindow, duration_s


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


def _diagram_data(seqs: Sequence[NamedSequence], windows: Sequence[TimeWindow]) -> dict:
    """The card data (section 4.1 of `docs/plans/diagram-event-table.md`):
    `{"format": 1, "files": [...], "windows": [...]}`.

    `files` has one entry for each file that at least one window uses, in the order
    in which `windows` first use them (so the file of the first window is entry 0):
    `name`, `duration_s`, `num_blocks`, `lanes` (`lane_meta`) and `tables`
    (`encode_tables(diagram_tables(seq))`). `diagram_tables(seq)` is built once for
    each such file, and passed to `lane_meta` so it is not built twice. `windows` has
    one entry for each of `windows`: `label`, `file` (the index into `files`, not into
    `seqs`) and `view_ms`.
    """
    file_index: dict[int, int] = {}  # index into seqs -> index into "files"
    files: list[dict] = []
    out_windows: list[dict] = []

    for w in windows:
        if w.file_index not in file_index:
            seq = seqs[w.file_index].seq
            tables = diagram_tables(seq)
            file_index[w.file_index] = len(files)
            files.append(
                {
                    "name": seqs[w.file_index].name,
                    "duration_s": duration_s(seq),
                    "num_blocks": len(seq.block_events),
                    "lanes": lane_meta(seq, tables),
                    "tables": encode_tables(tables),
                }
            )
        named = seqs[w.file_index]
        label = w.label if len(seqs) == 1 else f"{named.name}: {w.label}"
        out_windows.append(
            {
                "label": label,
                "file": file_index[w.file_index],
                "view_ms": [_ms(w.start_s), _ms(w.end_s)],
            }
        )
    return {"format": 1, "files": files, "windows": out_windows}


def diagram_card(
    seqs: Sequence[NamedSequence],
    windows: Sequence[TimeWindow],
    card_id: str = "diagram",
) -> Card:
    """The "Sequence diagram" card: one button for each of `windows`, in the given
    order. The first window is the initial view. With more than one file, each button
    text starts with the file name.

    Each file that at least one window uses gets its block and event tables sent to
    the browser once (see `_diagram_data`); the browser decodes them and draws the
    waveform. A status line under the chart (`{card_id}-mode`) says whether the
    current view is exact or a minimum/maximum of time bins.

    Raises `ValueError` when `windows` is empty, or a window names no file or ends
    before it starts. Raises `NotImplementedError` (`extensions.refuse_rotations`) for
    a sequence that uses the Pulseq rotation extension: this card shows unrotated
    gradient events, which would be wrong for such a sequence.
    """
    _validate(seqs, windows)
    for named in seqs:
        refuse_rotations(named.seq)
    data = _diagram_data(seqs, windows)
    buttons = "".join(
        f'<button type="button" data-window="{i}" aria-pressed="{str(i == 0).lower()}">'
        f"{html.escape(w['label'])}</button>"
        for i, w in enumerate(data["windows"])
    )
    svg_id = f"{card_id}-diagram"
    body = (
        f'<div class="controls" role="group" aria-label="Time window">{buttons}</div>\n'
        + _zoom_controls(svg_id)
        + f'\n<div class="chart" id="{card_id}-chart">\n'
        f'<svg id="{svg_id}" tabindex="0" role="img"\n'
        '  aria-label="Sequence diagram: RF magnitude and phase, ADC, Gx, Gy and Gz against '
        'time"></svg>\n'
        f'<div class="tip" id="{card_id}-tip" hidden></div>\n'
        "</div>\n"
        f'<p class="muted" id="{card_id}-mode" aria-live="polite">Loading…</p>\n'
        '<p class="muted">Hover the diagram, or focus it and use the arrow keys, to read '
        "values.\nRF phase is drawn where |B1| is above 1% of that pulse's peak.\n"
        "Click the chart to mark the centre for the zoom buttons. Drag across the chart to "
        "zoom to that range. Hold Shift and drag, or scroll sideways, to pan.</p>"
    )
    return Card(id=card_id, title="Sequence diagram", body_html=body, data=data, script="diagram")
