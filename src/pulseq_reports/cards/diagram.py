"""Sequence diagram card: RF, ADC and gradient waveforms against time, with one button
for each time window that the caller gives, and an optional PNS lane.

The card sends the compressed block and event tables of each file that at least one
window uses (`diagram_data.diagram_tables`, `encode_tables`), not expanded points. The
browser (`assets/cards/diagram.js`, `assets/seq_lanes.js`) decodes them and draws the
exact waveform when a view has few enough points, or the minimum and the maximum of
each lane in each of the plot's time bins otherwise, so the card works for a file of up
to 10^7 blocks (`docs/plans/diagram-event-table.md`).

With `pns` not False, each file entry that has a gradient event also gets a `"pns"` key
(`docs/plans/diagram-lanes.md`, section 4.4): the SAFE hardware, the gradient raster,
the gyromagnetic-ratio scale and the stored minimum/maximum level of `pns.pns_levels_for`
(the same `PnsLevels` that the PNS summary card uses, so a page with both computes the
SAFE model once for one sequence). The browser (`assets/pns_lanes.js`) decodes it into
the PNS lane. `pns` is False by default: computing it costs the SAFE model's own time
(section 4.1 of that plan), which a caller opts into.
"""

import html
from collections.abc import Sequence
from pathlib import Path

import pypulseq as pp

from ..diagram_data import diagram_tables, encode_tables, lane_meta
from ..extensions import refuse_rotations
from ..markup import _zoom_controls
from ..page import Card
from ..pns import pns_levels_for
from ..pns_levels import PnsLevels
from ..seq_utils import GAMMA, NamedSequence
from ..waveforms import TimeWindow, duration_s


def _ms(t_s: float) -> float:
    return round(t_s * 1e3, 4)


def _pns_entry(seq: pp.Sequence, levels: PnsLevels) -> dict:
    """The `"pns"` key of a file entry (`docs/plans/diagram-lanes.md`, section 4.4),
    from `levels` (`pns.pns_levels_for(seq, asc_path)`): the hardware, the SAFE
    parameters, the gradient raster and the gyromagnetic-ratio scale (`seq_utils.GAMMA /
    seq.system.gamma`, decision 14 of that plan), the summary, and the stored level,
    encoded as `diagram_data.encode_tables` encodes a table."""
    return {
        "hardware": levels.hardware,
        "example": levels.asc_file is None,
        "asc_file": levels.asc_file,
        "hw": levels.hw,
        "dtS": levels.dt_s,
        "gradScale": GAMMA / seq.system.gamma,
        "binSamples": levels.bin_samples,
        "summary": {
            "peak": levels.peak,
            "peak_time_s": levels.peak_time_s,
            "axis_peaks": levels.axis_peaks,
        },
        "levels": encode_tables({"min": levels.level_min, "max": levels.level_max}),
    }


def _validate(seqs: Sequence[NamedSequence], windows: Sequence[TimeWindow]) -> None:
    if not windows:
        raise ValueError("the diagram card needs at least one time window")
    for w in windows:
        if not 0 <= w.file_index < len(seqs):
            raise ValueError(f"window {w.label!r}: file_index {w.file_index} is not a file")
        if not w.end_s > w.start_s:
            raise ValueError(f"window {w.label!r}: the end is not after the start")


def _diagram_data(
    seqs: Sequence[NamedSequence], windows: Sequence[TimeWindow], pns: bool | str | Path
) -> dict:
    """The card data (section 4.1 of `docs/plans/diagram-event-table.md`, plus the
    `"pns"` key of section 4.4 of `docs/plans/diagram-lanes.md`):
    `{"format": 1, "files": [...], "windows": [...]}`.

    `files` has one entry for each file that at least one window uses, in the order
    in which `windows` first use them (so the file of the first window is entry 0):
    `name`, `duration_s`, `num_blocks`, `lanes` (`lane_meta`) and `tables`
    (`encode_tables(diagram_tables(seq))`). `diagram_tables(seq)` is built once for
    each such file, and passed to `lane_meta` so it is not built twice. When `pns` is
    not False and the file has a gradient event, the entry also gets a `"pns"` key
    (`_pns_entry`); a file without gradients gets no `"pns"` key. `windows` has one
    entry for each of `windows`: `label`, `file` (the index into `files`, not into
    `seqs`) and `view_ms`.
    """
    # None for the example hardware (pns is True); the given path for pns is a path.
    # Unused when pns is False (guarded below), so its value there does not matter.
    asc_path = None if pns is True else pns
    file_index: dict[int, int] = {}  # index into seqs -> index into "files"
    files: list[dict] = []
    out_windows: list[dict] = []

    for w in windows:
        if w.file_index not in file_index:
            seq = seqs[w.file_index].seq
            tables = diagram_tables(seq)
            file_index[w.file_index] = len(files)
            entry = {
                "name": seqs[w.file_index].name,
                "duration_s": duration_s(seq),
                "num_blocks": len(seq.block_events),
                "lanes": lane_meta(seq, tables),
                "tables": encode_tables(tables),
            }
            if pns is not False:
                levels = pns_levels_for(seq, asc_path)
                if levels.reason is None:
                    entry["pns"] = _pns_entry(seq, levels)
            files.append(entry)
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
    pns: bool | str | Path = False,
) -> Card:
    """The "Sequence diagram" card: one button for each of `windows`, in the given
    order. The first window is the initial view. With more than one file, each button
    text starts with the file name.

    Each file that at least one window uses gets its block and event tables sent to
    the browser once (see `_diagram_data`); the browser decodes them and draws the
    waveform. A status line under the chart (`{card_id}-mode`) says whether the
    current view is exact or a minimum/maximum of time bins.

    `pns` (`docs/plans/diagram-lanes.md`, section 4.7) adds a PNS lane: `False` (the
    default) computes no PNS and adds no `"pns"` key; `True` predicts with pypulseq's
    example hardware; a string or `Path` predicts with the gradient `.asc` file at that
    path. A file with no gradient event gets no `"pns"` key even when `pns` is not
    False. The PNS prediction is `pns.pns_levels_for`, which a PNS summary card for the
    same sequence (`cards.pns.pns_card`) shares, so the SAFE model runs once.

    A group-controls container (`{card_id}-groups`) sits above the chart, after the
    window buttons: the card script (`assets/cards/diagram.js`) fills it with one
    toggle button for each lane group (RF, ADC, Gradients, and PNS when at least one
    file has PNS data), so any of them can be hidden. The explanation paragraph under
    the chart gets one more sentence about the PNS lane when the card has PNS data.

    Raises `ValueError` when `windows` is empty, or a window names no file or ends
    before it starts. Raises `NotImplementedError` (`extensions.refuse_rotations`) for
    a sequence that uses the Pulseq rotation extension: this card shows unrotated
    gradient events, which would be wrong for such a sequence.
    """
    _validate(seqs, windows)
    for named in seqs:
        refuse_rotations(named.seq)
    data = _diagram_data(seqs, windows, pns)
    has_pns = any("pns" in f for f in data["files"])
    buttons = "".join(
        f'<button type="button" data-window="{i}" aria-pressed="{str(i == 0).lower()}">'
        f"{html.escape(w['label'])}</button>"
        for i, w in enumerate(data["windows"])
    )
    svg_id = f"{card_id}-diagram"
    # The group-controls container (assets/cards/diagram.js: RF, ADC, Gradients, and
    # PNS when `has_pns`, docs/plans/diagram-lanes.md section 4.5, item 3) is always
    # present, above the chart and after the window buttons, so that the RF, ADC and
    # gradient groups can be hidden even when the file has no PNS data. It is empty
    # here: the card script fills it with one toggle button for each group.
    pns_note = (
        " The PNS lane shows the total predicted stimulation (the root-sum-of-squares "
        "of the three axes) as a percent of the SAFE stimulation limit. It is exact "
        "for a view of 10 s or less; a longer view shows the minimum and the maximum "
        "in time bins."
        if has_pns
        else ""
    )
    body = (
        f'<div class="controls" role="group" aria-label="Time window">{buttons}</div>\n'
        f'<div class="controls" role="group" aria-label="Lanes" id="{card_id}-groups">'
        "</div>\n" + _zoom_controls(svg_id) + f'\n<div class="chart" id="{card_id}-chart">\n'
        f'<svg id="{svg_id}" tabindex="0" role="img"\n'
        '  aria-label="Sequence diagram: RF magnitude and phase, ADC, Gx, Gy and Gz against '
        'time"></svg>\n'
        f'<div class="tip" id="{card_id}-tip" hidden></div>\n'
        "</div>\n"
        f'<p class="muted" id="{card_id}-mode" aria-live="polite">Loading…</p>\n'
        '<p class="muted">Hover the diagram, or focus it and use the arrow keys, to read '
        "values.\nRF phase is drawn where |B1| is above 1% of that pulse's peak.\n"
        "Click the chart to mark the centre for the zoom buttons. Drag across the chart to "
        f"zoom to that range. Hold Shift and drag, or scroll sideways, to pan.{pns_note}</p>"
    )
    return Card(id=card_id, title="Sequence diagram", body_html=body, data=data, script="diagram")
