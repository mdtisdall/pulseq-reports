"""The report page: a list of cards in one self-contained HTML file.

Each card is one `<section>` with a title, HTML, optional JSON data and an optional
card script. The page includes the CSS and all the JavaScript inline, so the file
needs nothing else to show.
"""

import html
import importlib.resources
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_ASSETS = importlib.resources.files("pulseq_reports").joinpath("assets")

_ID_RE = re.compile(r"[a-z][a-z0-9-]*")
_PLACEHOLDER_RE = re.compile(r"__[A-Z_]+__")


def _asset(name: str) -> str:
    return _ASSETS.joinpath(name).read_text(encoding="utf-8")


@dataclass(frozen=True)
class Card:
    """One section of the report page.

    `id` is unique on the page and matches `[a-z][a-z0-9-]*`. `title` is plain text.
    `body_html` is the HTML inside the section, after the title. `data` is JSON-ready;
    when it is not None, the page has it in `<script type="application/json"
    id="{id}-data">`. `script` is the name that a card script registered with
    `PulseqReport.registerCard`, or None for a card with no JavaScript. With `collapsed`,
    the title and the body are in a closed `<details>` element.
    """

    id: str
    title: str
    body_html: str
    data: object | None = None
    script: str | None = None
    collapsed: bool = False


def card_asset(name: str) -> str:
    """The text of the library card script `assets/cards/<name>.js`."""
    if not _ID_RE.fullmatch(name):
        raise ValueError(f"card script name {name!r} does not match [a-z][a-z0-9-]*")
    return _asset(f"cards/{name}.js")


def _substitute(template: str, replacements: dict[str, str]) -> str:
    """Replace each `__NAME__` placeholder in `template` with its value from
    `replacements`. Raises ValueError if the template has a `__NAME__`-shaped placeholder
    that `replacements` does not give.

    The replacement is one pass over the template, so a value that contains a
    `__NAME__`-shaped text is not changed and is not an error."""

    def value(match: re.Match) -> str:
        placeholder = match.group()
        if placeholder not in replacements:
            raise ValueError(f"unresolved placeholder {placeholder!r} in report template")
        return replacements[placeholder]

    return _PLACEHOLDER_RE.sub(value, template)


def _json_script(element_id: str, data: object) -> str:
    # `</` is escaped so that the JSON cannot end the script element.
    payload = json.dumps(data, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    return f'<script type="application/json" id="{element_id}-data">{payload}</script>'


def _card_html(card: Card) -> str:
    title = html.escape(card.title)
    script = "" if card.script is None else f' data-card-script="{card.script}"'
    if card.collapsed:
        inner = f"<details>\n<summary>{title}</summary>\n{card.body_html}\n</details>"
    else:
        inner = f"<h2>{title}</h2>\n{card.body_html}"
    data = "" if card.data is None else "\n" + _json_script(card.id, card.data)
    return f'<section class="card" id="{card.id}"{script}>\n{inner}{data}\n</section>'


def _script_element(source: str) -> str:
    if re.search(r"</script", source, re.IGNORECASE):
        raise ValueError("a page script must not contain '</script'")
    return f"<script>\n{source}\n</script>"


def render_page(
    title: str, subtitle: str, cards: Sequence[Card], extra_scripts: Sequence[str] = ()
) -> str:
    """The HTML of a page with `cards` in the given order.

    Scripts, in this order: chart_math.js, lane_chart.js, seq_lanes.js, the library card
    script of each distinct `Card.script` name (one time each), `extra_scripts` in the
    given order, and page.js. A card whose script is not a library card script gets it
    from `extra_scripts`, which registers it with `PulseqReport.registerCard`. Each
    script is in its own `<script>` element, so an error in one does not stop the others.

    Raises ValueError when two cards have the same id, or when a card id or a script name
    does not match `[a-z][a-z0-9-]*`.
    """
    seen: set[str] = set()
    script_names: list[str] = []
    for card in cards:
        if not _ID_RE.fullmatch(card.id):
            raise ValueError(f"card id {card.id!r} does not match [a-z][a-z0-9-]*")
        if card.id in seen:
            raise ValueError(f"two cards have the id {card.id!r}")
        seen.add(card.id)
        if card.script is not None:
            if not _ID_RE.fullmatch(card.script):
                raise ValueError(f"card script name {card.script!r} does not match [a-z][a-z0-9-]*")
            if card.script not in script_names:
                script_names.append(card.script)

    library_card_scripts = [
        card_asset(name)
        for name in script_names
        if _ASSETS.joinpath("cards", f"{name}.js").is_file()
    ]
    scripts = [
        _asset("chart_math.js"),
        _asset("lane_chart.js"),
        _asset("seq_lanes.js"),
        *library_card_scripts,
        *extra_scripts,
        _asset("page.js"),
    ]
    return _substitute(
        _asset("template.html"),
        {
            "__TITLE__": html.escape(title),
            "__SUBTITLE__": html.escape(subtitle),
            "__CARDS__": "\n\n".join(_card_html(card) for card in cards),
            "__CSS__": _asset("report.css"),
            "__JS__": "\n".join(_script_element(s) for s in scripts),
        },
    )


def write_page(
    path: str | Path,
    title: str,
    subtitle: str,
    cards: Sequence[Card],
    extra_scripts: Sequence[str] = (),
) -> None:
    """Write `render_page(title, subtitle, cards, extra_scripts)` to `path` as UTF-8."""
    Path(path).write_text(render_page(title, subtitle, cards, extra_scripts), encoding="utf-8")
