"""HTML and lane helpers shared by the report cards.

The public names are for a project's own cards too (`docs/usage.md`, section 4):
`html_table`, `Lane`, `lanes_json`, `zoom_controls` and `fmt`. The names that start with `_`
are for the library's own cards only.
"""

import dataclasses
import html
from collections.abc import Sequence

import numpy as np
from pulseq_analysis.seq_index import SequenceIndex

from .targets import ReportTarget
from .units import GammaEntry


def _points(t_s, values, digits: int = 4) -> list[list[float]]:
    return [[round(float(t) * 1e3, 4), round(float(v), digits)] for t, v in zip(t_s, values)]


def fmt(v: float) -> str:
    """`v` with 3 significant digits, as the library cards show a number, with the minus
    sign U+2212 in place of the hyphen."""
    return f"{v:.3g}".replace("-", "−")


@dataclasses.dataclass(frozen=True, kw_only=True)
class Lane:
    """One line lane of a `PulseqReport.laneChart` chart, for example a waveform or a
    spectrum trace. `docs/usage.md` ("Lane JSON format") gives the meaning of each field.
    Field order is the JSON key order that `dataclasses.asdict` gives."""

    id: str
    title: str
    unit: str
    color: str
    kind: str = "line"
    segments: list
    domain: list
    ticks: list
    tick_labels: list
    empty: bool = False
    fill: float | None = None


def lanes_json(lanes: list) -> list[dict]:
    """Each lane as a JSON-ready dict: a `Lane` via `dataclasses.asdict`, or a dict (for
    example a gate lane) unchanged."""
    return [dataclasses.asdict(lane) if isinstance(lane, Lane) else lane for lane in lanes]


def html_table(headers: list[str], rows: list[list]) -> str:
    """An HTML table in a horizontal scroll container. Each header and each cell (after
    `str`) is HTML-escaped."""
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in row) + "</tr>" for row in rows
    )
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


_AXIS_COLOR = {"x": "gx", "y": "gy", "z": "gz"}


def _sig(v: float) -> float:
    return float(f"{v:.4g}")


def zoom_controls(svg_id: str) -> str:
    """The zoom button group of the `laneChart` chart whose `<svg>` has the id `svg_id`.
    Put it directly before the chart's `<div class="chart">`."""
    svg_id = html.escape(svg_id)
    return (
        f'<div class="controls" role="group" aria-label="Zoom" data-zoom-for="{svg_id}">'
        '<button type="button" data-zoom="10" aria-label="Zoom in 10 times">×10</button>'
        '<button type="button" data-zoom="2" aria-label="Zoom in 2 times">×2</button>'
        '<button type="button" data-zoom="0.5" aria-label="Zoom out 2 times">×0.5</button>'
        '<button type="button" data-zoom="0.1" aria-label="Zoom out 10 times">×0.1</button>'
        '<button type="button" data-zoom="reset">Reset</button></div>'
    )


def show_button_html(index: SequenceIndex, block_id: int, label: str) -> str:
    """A hidden "Show" button that shows the block `block_id` (a key of `seq.block_events`,
    as a pulseq-checks `Location` gives it) in the sequence diagram. The button has the play
    index of the block (its position in play order, from 0, in `index`) in `data-block`, and
    the text `label` (escaped).

    The card script `show-buttons` (`assets/cards/show-buttons.js`) wires each such button
    of its card: a click publishes the `goto` message `{source, block}`, and the button is
    shown only while a card (the diagram) acts on `goto`. A card with these buttons has
    `script="show-buttons"`, the script in `scripts`, and `"goto"` in `publishes`.

    Raises `ValueError` when `index` has no block `block_id`."""
    plays = np.flatnonzero(index.block_id == block_id)
    if plays.size == 0:
        raise ValueError(f"the sequence has no block {block_id!r}")
    return (
        f'<button type="button" data-block="{int(plays[0])}" hidden>{html.escape(label)}</button>'
    )


def target_legend_html(targets: Sequence[ReportTarget]) -> str:
    """The legend of the report's targets: a list with the name of each target (escaped),
    in order, after a swatch of its color (`var(--target-k)`). Returns `""` for no targets."""
    if not targets:
        return ""
    items = [
        f'<li><span class="swatch" style="background: var(--{target.color})" '
        f'aria-hidden="true"></span>{html.escape(target.profile.name)}</li>'
        for target in targets
    ]
    return f'<ul class="target-legend" aria-label="Targets">{"".join(items)}</ul>'


def gamma_select_html(entries: Sequence[GammaEntry], card_id: str) -> str:
    """The control that selects the gamma of a card (`units.gamma_entries`): a group of
    buttons, one for each entry, with `data-gamma-choice` (the index of the entry),
    `data-gamma` (its gamma, Hz/T) and `aria-pressed` (true for the first). The label of a
    button gives the names of the targets of the entry and its gamma in MHz/T. The card
    writes the block of entry `k` with `data-gamma-entry="k"`, and
    `PulseqReport.gammaSelect` shows the block of the pressed button. Returns `""` for one
    entry (or none): a card with one gamma has no control."""
    if len(entries) < 2:
        return ""
    buttons = []
    for k, entry in enumerate(entries):
        label = f"{', '.join(entry.names)} ({entry.gamma / 1e6:.6g} MHz/T)"
        buttons.append(
            f'<button type="button" data-gamma-choice="{k}" data-gamma="{entry.gamma!r}" '
            f'aria-pressed="{"true" if k == 0 else "false"}">{html.escape(label)}</button>'
        )
    return (
        f'<div class="controls" id="{html.escape(card_id, quote=True)}-gamma" role="group" '
        f'aria-label="Gamma of the target">{"".join(buttons)}</div>'
    )
