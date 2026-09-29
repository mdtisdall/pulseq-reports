"""Sequence diagram card: RF, ADC and gradient waveforms against time, with one button
for each time window that the caller gives, and an optional PNS lane.

The card sends the compressed block and event tables of the sequence
(`diagram_data.diagram_tables`, `encode_tables`), not expanded points. The
browser (`assets/cards/diagram.js`, `assets/seq_lanes.js`) decodes them and draws the
exact waveform when a view has few enough points, or the minimum and the maximum of
each lane in each of the plot's time bins otherwise, so the card works for a file of up
to 10^7 blocks (`docs/plans/diagram-event-table.md`).

With `pns` not False, a sequence that has a gradient event also gets a `"pns"` key in
the card's `"file"` entry (`docs/plans/diagram-lanes.md`, section 4.4): the SAFE
hardware, the gradient raster, the gyromagnetic-ratio scale and the stored minimum/maximum
level of `pns.pns_levels_for` (the same `PnsLevels` that the PNS summary card uses, so a
page with both computes the SAFE model once for one sequence). The browser
(`assets/pns_lanes.js`) decodes it into the PNS lane. `pns` is False by default:
computing it costs the SAFE model's own time (section 4.1 of that plan), which a caller
opts into.
"""

import html
from collections.abc import Sequence
from pathlib import Path

import pypulseq as pp

from ..diagram_data import diagram_tables, encode_tables, lane_meta
from ..extensions import refuse_rotations
from ..markup import zoom_controls
from ..page import Card
from ..pns import pns_levels_for
from ..pns_levels import PnsLevels
from ..seq_utils import GAMMA
from ..waveforms import TimeWindow, _check_windows, duration_s


def _ms(t_s: float) -> float:
    return round(t_s * 1e3, 4)


def _pns_entry(seq: pp.Sequence, levels: PnsLevels) -> dict:
    """The `"pns"` key of the `"file"` entry (`docs/plans/diagram-lanes.md`, section 4.4),
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


def _validate(seq: pp.Sequence, windows: Sequence[TimeWindow]) -> None:
    if not windows:
        raise ValueError("the diagram card needs at least one time window")
    _check_windows(seq, windows)


def _diagram_data(seq: pp.Sequence, windows: Sequence[TimeWindow], pns: bool | str | Path) -> dict:
    """The card data (section 4.1 of `docs/plans/diagram-event-table.md`, plus the
    `"pns"` key of section 4.4 of `docs/plans/diagram-lanes.md`):
    `{"format": 2, "file": {...}, "windows": [...]}`.

    `file` has `duration_s`, `num_blocks`, `lanes` (`lane_meta`) and `tables`
    (`encode_tables(diagram_tables(seq))`). `diagram_tables(seq)` is built once and
    passed to `lane_meta` so it is not built twice. When `pns` is not False and the
    sequence has a gradient event, `file` also gets a `"pns"` key (`_pns_entry`); a
    sequence without gradients gets no `"pns"` key. `windows` has one entry for each of
    `windows`: `label` and `view_ms`.
    """
    # None for the example hardware (pns is True); the given path for pns is a path.
    # Unused when pns is False (guarded below), so its value there does not matter.
    asc_path = None if pns is True else pns
    tables = diagram_tables(seq)
    file = {
        "duration_s": duration_s(seq),
        "num_blocks": len(seq.block_events),
        "lanes": lane_meta(seq, tables),
        "tables": encode_tables(tables),
    }
    if pns is not False:
        levels = pns_levels_for(seq, asc_path)
        if levels.reason is None:
            file["pns"] = _pns_entry(seq, levels)
    out_windows = [{"label": w.label, "view_ms": [_ms(w.start_s), _ms(w.end_s)]} for w in windows]
    return {"format": 2, "file": file, "windows": out_windows}


def diagram_card(
    seq: pp.Sequence,
    windows: Sequence[TimeWindow],
    *,
    pns: bool | str | Path = False,
    card_id: str = "diagram",
) -> Card:
    """The "Sequence diagram" card: one button for each of `windows`, in the given
    order. The first window is the initial view.

    The sequence's block and event tables are sent to the browser once (see
    `_diagram_data`); the browser decodes them and draws the waveform. A status line
    under the chart (`{card_id}-mode`) says whether the current view is exact or a
    minimum/maximum of time bins.

    `pns` (`docs/plans/diagram-lanes.md`, section 4.7) adds a PNS lane: `False` (the
    default) computes no PNS and adds no `"pns"` key; `True` predicts with pypulseq's
    example hardware; a string or `Path` predicts with the gradient `.asc` file at that
    path. A sequence with no gradient event gets no `"pns"` key even when `pns` is not
    False. The PNS prediction is `pns.pns_levels_for`, which a PNS summary card for the
    same sequence (`cards.pns.pns_card`) shares, so the SAFE model runs once.

    A group-controls container (`{card_id}-groups`) sits above the chart, after the
    window buttons: the card script (`assets/cards/diagram.js`) fills it with one
    toggle button for each lane group (RF, ADC, Gradients, and PNS when the card has
    PNS data), so any of them can be hidden. The Gradients group also has a
    |G| lane (`docs/plans/diagram-lanes.md`, phase 5): the exact minimum and maximum of
    the gradient vector's magnitude in each time bin, computed in the browser
    (`assets/g_lanes.js`) from the same tables as Gx, Gy and Gz, no extra data from this
    function. The explanation paragraph under the chart always gets one sentence about
    the |G| lane, and one more about the PNS lane when the card has PNS data.

    Raises `ValueError` when `windows` is empty, or a window is not inside the sequence
    or does not end after its start (the message names the window's label). Raises
    `NotImplementedError` (`extensions.refuse_rotations`) for a sequence that uses the
    Pulseq rotation extension: this card shows unrotated gradient events, which would
    be wrong for such a sequence.
    """
    _validate(seq, windows)
    refuse_rotations(seq)
    data = _diagram_data(seq, windows, pns)
    has_pns = "pns" in data["file"]
    buttons = "".join(
        f'<button type="button" data-window="{i}" aria-pressed="{str(i == 0).lower()}">'
        f"{html.escape(w['label'])}</button>"
        for i, w in enumerate(data["windows"])
    )
    svg_id = f"{card_id}-diagram"
    lanes_after_adc = "Gx, Gy, Gz, |G| and PNS" if has_pns else "Gx, Gy, Gz and |G|"
    g_note = (
        " The |G| lane shows the magnitude of the gradient vector (the root-sum-of-squares "
        "of Gx, Gy and Gz), as the exact minimum and maximum in each time bin."
    )
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
        "</div>\n" + zoom_controls(svg_id) + f'\n<div class="chart" id="{card_id}-chart">\n'
        f'<svg id="{svg_id}" tabindex="0" role="img"\n'
        f'  aria-label="Sequence diagram: RF magnitude and phase, ADC, {lanes_after_adc} '
        'against time"></svg>\n'
        f'<div class="tip" id="{card_id}-tip" hidden></div>\n'
        "</div>\n"
        f'<p class="muted" id="{card_id}-mode" aria-live="polite">Loading…</p>\n'
        '<p class="muted">Hover the diagram, or focus it and use the arrow keys, to read '
        "values.\nRF phase is drawn where |B1| is above 1% of that pulse's peak.\n"
        "Click the chart to mark the centre for the zoom buttons. Drag across the chart to "
        f"zoom to that range. Hold Shift and drag, or scroll sideways, to pan.{g_note}"
        f"{pns_note}</p>"
    )
    return Card(id=card_id, title="Sequence diagram", body_html=body, data=data, script="diagram")
