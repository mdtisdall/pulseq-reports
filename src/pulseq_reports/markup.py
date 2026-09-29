"""HTML and lane helpers shared by the report cards.

The public names are for a project's own cards too (`docs/usage.md`, section 4):
`html_table`, `Lane`, `lanes_json`, `zoom_controls` and `fmt`. The names that start with `_`
are for the library's own cards only.
"""

import dataclasses
import html


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
