"""HTML and lane helpers shared by the report cards."""

import dataclasses
import html


def _points(t_s, values, digits: int = 4) -> list[list[float]]:
    return [[round(float(t) * 1e3, 4), round(float(v), digits)] for t, v in zip(t_s, values)]


def _fmt(v: float) -> str:
    return f"{v:.3g}".replace("-", "−")


@dataclasses.dataclass(frozen=True, kw_only=True)
class Lane:
    """One chart lane (a waveform, an RF pulse profile, a spectrum trace or a PNS trace).
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


def _lanes_json(lanes: list) -> list[dict]:
    """Each lane as a JSON-ready dict: a `Lane` via `dataclasses.asdict`, or a dict (the ADC
    gate lane) unchanged."""
    return [dataclasses.asdict(lane) if isinstance(lane, Lane) else lane for lane in lanes]


def _table(headers: list[str], rows: list[list]) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in row) + "</tr>" for row in rows
    )
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


_AXIS_COLOR = {"x": "gx", "y": "gy", "z": "gz"}


def _blocks_cell(blocks: list[int]) -> str:
    shown = ", ".join(str(b) for b in blocks[:4])
    if len(blocks) > 4:
        shown += f" … ({len(blocks)} blocks)"
    return shown


def _sig(v: float) -> float:
    return float(f"{v:.4g}")


def _zoom_controls(svg_id: str) -> str:
    """The zoom button group placed directly before a line chart's `<div class="chart">`."""
    svg_id = html.escape(svg_id)
    return (
        f'<div class="controls" role="group" aria-label="Zoom" data-zoom-for="{svg_id}">'
        '<button type="button" data-zoom="10" aria-label="Zoom in 10 times">×10</button>'
        '<button type="button" data-zoom="2" aria-label="Zoom in 2 times">×2</button>'
        '<button type="button" data-zoom="0.5" aria-label="Zoom out 2 times">×0.5</button>'
        '<button type="button" data-zoom="0.1" aria-label="Zoom out 10 times">×0.1</button>'
        '<button type="button" data-zoom="reset">Reset</button></div>'
    )
