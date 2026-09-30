# Using pulseq-reports

`pulseq-reports` writes one self-contained HTML review report for one Pulseq
sequence. This document shows how a consumer project adds the dependency,
builds a page with the library's cards or with the command line, and adds its
own card.

Each card shows one sequence, and a page shows one sequence. A caller with
several `.seq` files (for example the segment files of one acquisition) makes
one report for each file.

The public API is the names in this document. Other names can change in a
minor release. The card interface (section 7) is provisional in 0.2.0: it can
change in 0.3.0.

## 1. Add the dependency

`mdtisdall/pulseq-reports` is a public GitHub repository. Consumers pin it by
git URL and tag. CI needs no credentials to fetch it.

In `pyproject.toml`:

```toml
[project]
dependencies = [
    "pulseq-reports @ git+https://github.com/mdtisdall/pulseq-reports@v0.2.0rc2",
]
```

With uv:

```
uv add "pulseq-reports @ git+https://github.com/mdtisdall/pulseq-reports@v0.2.0rc2"
```

To move to a later tag, change `@v0.2.0rc2` and run `uv lock --upgrade-package
pulseq-reports` (or the equivalent command of your tool). This document
describes `main`. [`CHANGELOG.md`](../CHANGELOG.md) gives the changes of each
tag; a change under a heading marked "not released" is on `main` but in no tag
yet. Read the next paragraph about pypulseq.

The PNS summary card and the diagram card's PNS lane need a chunked SAFE
recursion that stock pypulseq does not have: `pns_levels.py` imports a
private function of a pypulseq fork, `_safe_gwf_to_pns_chunk`. So
`pulseq-reports` pins a commit of that fork, `mdtisdall/pypulseq`, in its own
`[tool.uv.sources]`: pypulseq 1.5.0.post1 with four changes (the fork's tag
`pulseq-reports-pin-1`; `TODO.md` lists the changes).

- **With uv**, a project that depends on `pulseq-reports` by git URL gets the
  same fork commit, because uv applies the `[tool.uv.sources]` of a git
  dependency. This is so even when the project lists pypulseq itself, or
  gives pypulseq its own index source (checked with uv 0.12.11). The project
  then builds its own sequences with the fork, which is pypulseq 1.5.0.post1
  apart from the four changes. To use a different pypulseq, the project sets
  `override-dependencies = ["pypulseq==<version>"]` in its `[tool.uv]`; the
  PNS card and the PNS lane then fail with an `ImportError`.
- **With pip**, which ignores `[tool.uv.sources]`, the project gets pypulseq
  from PyPI, and the PNS card and the PNS lane fail with an `ImportError`.
  Add the fork to the project's own requirements, with the commit that
  `pulseq-reports`'s own `pyproject.toml` pins:

```
pypulseq @ git+https://github.com/mdtisdall/pypulseq@<the commit pulseq-reports pins>
```

This paragraph applies while `pulseq-reports` pins a fork commit instead of
a pypulseq release (`docs/plans/cards-at-scale.md`, section 3.6, item 7).

## 2. One sequence, every card

`build_cards` builds the library's cards for one sequence, and `write_page`
writes them to one HTML file. This example uses `your_pp_sequence` in place of
a real sequence. The package also installs the command `pulseq-report`, which
does the same for `.seq` files (section 8).

```python
from pulseq_reports import build_cards, write_page

seq = your_pp_sequence  # a pypulseq Sequence

cards = build_cards(seq, pns_lane=True, views=("profile", "z_df"))

write_page(
    "report.html",
    title="my_scan.seq review",
    subtitle="Every library card for one sequence",
    cards=cards,
)
```

`build_cards(seq, *, cards=None, skip=(), **options)` finds the card specs (the
nine library cards, and the cards of installed plugins: section 7), builds the
cards in the order of their specs, and returns the list of `Card` objects.
`write_page` puts the cards on the page in the order of that list, so you can
reorder the list, or add a card to it, before you write the page.

- `cards` is the names of the cards to build (all of them when `None`), and
  `skip` is the names to leave out. The card names are in section 7. A name
  that no card has raises `ValueError`.
- Each other keyword is the value of one option, by option name. A card whose
  option you do not give uses the default of its builder, so `build_cards(seq)`
  gives the standard report. Section 5 has one line for each option. The
  example gives two: `pns_lane=True` adds the PNS lane to the sequence
  diagram, and `views` adds the `"z_df"` map to the RF pulse profiles. An
  option that none of the selected cards has raises `TypeError`, as an unknown
  keyword does.
- The RF pulse profiles card follows the sequence diagram, and it needs a use
  label on each RF pulse (see "RF use labels" in section 5). `build_cards`
  builds it only when the RF pulses have labels and a selected card publishes
  the `anchor` topic (the diagram card does). Without them, the report has no
  RF pulse profiles card.
- The card that shows the PNS prediction (`pns`) and the diagram's PNS lane
  (`pns_lane=True`) both use the option `gradient_asc`, so they show the same
  hardware, and the SAFE model runs one time for the sequence.
- When a card cannot be built (for example, `NotImplementedError` for a sequence
  with the rotation extension), `build_cards` makes an error card in its place
  and builds the other cards. The error card has the card's name as its `id`, the
  title "<name>: error", the message in its body and one failed check. The
  exception, with its traceback, goes to the logger `pulseq_reports`
  (`logging.getLogger("pulseq_reports")`).

A card can report checks (`Card.checks`), which the page does not show. The
timing card, the gradient limits card and the PNS card each have one (section
7 says what each one tests). To read them:

```python
failed = [(card.id, check) for card in cards for check in card.checks if not check.passed]
for card_id, check in failed:
    print(f"{card_id}: {check.name}: {check.message}")
```

A project's own card goes in the list like any other `Card`. This example
adds the card of section 4:

```python
from peak_grad_card import peak_grad_card  # the file of section 4
from pulseq_reports import build_cards, write_page

cards = build_cards(seq)
cards.append(peak_grad_card(seq))

write_page("report.html", title="my_scan.seq review", subtitle="With my card", cards=cards)
```

To have the card in the standard report on every run, and on the command line,
make it a plugin (section 7).

`build_cards` gives the diagram card two windows, `first_adc_window(seq)` and
`full_window(seq)`. For windows of your own, build the diagram card by hand
(section 3). A caller can also build every card by hand with the builders of
section 5, for a page that `build_cards` does not give.

## 3. Windows and the diagram

The diagram card needs a list of `TimeWindow` objects: named time ranges to
show as buttons. `TimeWindow(label, start_s, end_s)` takes seconds.
`first_adc_window(seq)` and `full_window(seq)` give the two standard views. The
first window in the list is the view that the card shows when it starts.
`diagram_card`, `blocks_card` and `gradient_limits_card` raise `ValueError`,
with the window's label, for a window that is outside the sequence or that does
not end after its start.

This example gives the diagram a one-TR window between the two standard ones,
and adds the diagram to the cards that `build_cards` makes:

```python
from pulseq_reports import TimeWindow, build_cards, first_adc_window, full_window
from pulseq_reports.cards import diagram_card

TR = 20e-3  # s

windows = [first_adc_window(seq), TimeWindow("TR 1", 0.0, TR), full_window(seq)]

cards = build_cards(seq, skip=("diagram",))
cards.insert(2, diagram_card(seq, windows, pns_lane=True))
```

Skip the diagram, and the RF pulse profiles card is not built either, because
no selected card publishes `anchor`. Add `rf_profile_card` by hand as in
section 5 when you want it.

A report is for one sequence. For the segment files of one acquisition, make
one report for each file. No card combines files: for example, the RF exposure
card has no B1+rms for files that play one after another.

The PNS card has a button that moves the diagram to the TR that holds the
highest predicted PNS, or, for a sequence with no `TR` definition, to the
block that holds it. So a window for that TR is not needed. The button is
shown only on a page where a card acts on the request, such as the diagram
card (section 4, "Messages between cards"). `pns.peak_tr_window` gives the
range of that TR, for a caller that wants a window for it (section 6).

`diagram_card` sends the compressed block and event tables of the sequence, not
expanded points. The page stays one self-contained file. Its size depends on
the number of blocks and of distinct events, not on the number of waveform
points.

In the browser, each view (a zoom, a pan, or a window button) shows the
exact waveform when that view has at most 20,000 points
(`SeqLanes.EXACT_POINT_LIMIT`). A view with more points shows the minimum and
the maximum of each lane in each of the chart's time bins instead, including
the RF phase lane; no peak and no ADC window is lost. A status line under the
chart says which of the two the current view shows. Windows are only
shortcut buttons: they do not change what a view shows, only where it starts.

`diagram_card`'s `pns_lane` argument adds a PNS lane next to the gradients,
for a sequence that has a gradient event: `False` (the default) adds no PNS
lane and computes no PNS; `True` predicts with pypulseq's example hardware, or
with the hardware of the gradient `.asc` file that `gradient_asc` names. A
`gradient_asc` without `pns_lane=True` raises `ValueError`, and a `pns_lane`
that is not a `bool` raises `TypeError`. A sequence with no gradient event gets
no PNS lane, whatever `pns_lane` is.

The PNS lane shows the total predicted stimulation (the root-sum-of-squares
of the three axes) as a percent of the SAFE stimulation limit. It is exact
for a view of 10 s or less. A longer view shows the minimum and the maximum
in stored bins instead, or a coarser pyramid of them for a still longer view;
no peak is lost. At the usual gradient raster time of 10 µs, a stored bin is
615 samples, 6.15 ms wide. The status line under the chart says which view it
is: "PNS: exact." or "PNS: minimum and maximum in bins of X ms." A sequence
longer than about 3.4 hours at that raster gets coarser stored bins, so that
their number stays at most 2,000,000; for such a sequence, a view longer than
10 s but not much longer shows bins wider than the usual 6.15 ms, and the
status line adds "Zoom in to 10 s or less for the exact values." to say so.
Another raster time gives another number of samples in a bin (each bin is a
whole number of samples), and a bin of about the same width. For a
sequence with a block that is not a whole number of gradient-raster samples,
there is no exact view at any zoom, and the status line says so instead.

The Gradients group also has a |G| lane after Gz: the magnitude of the
gradient vector, `sqrt(Gx^2 + Gy^2 + Gz^2)` in mT/m, with each axis read from
its block's own event (0 outside it). It always shows the exact minimum and
maximum of |G| in each time bin of the chart, at every zoom, because |G| is
not a straight line between the corner points of the gradients. It needs no
argument and no data of its own: the browser computes it from the diagram
tables.

Above the chart, after the window buttons, one toggle button for each lane
group shows or hides that group: RF, ADC, Gradients (Gx, Gy, Gz and |G|), and
PNS when the card has PNS data. Hiding the Gradients group stops the browser
from computing the |G| lane, and hiding the PNS group stops it from computing
the PNS lane, on the next render. The RF, ADC, Gx, Gy and Gz lanes are computed
on every render, so hiding their groups saves no computation.

`pns_lane=True` costs the SAFE model's own time: about 3 s of Python
for a 370 s file, about 100 s at 10^7 blocks. The stored level added to the
page is small after compression, even at that size.

The diagram, PNS, RF exposure, gradient limits, gradient spectrum and RF
profile cards work for a file of up to 10^7 blocks. The time and the added
memory of each, measured on 2026-09-28 (the RF profile card on 2026-09-29; a
Mac with 10 cores and 64 GB, `scripts/cards_scale.py`, synthetic repeating
sequences; building the sequence of 10^7 blocks in pypulseq itself takes about
90 s and 3.8 GB):

| Card | 370 s file (4 × 10^4 blocks) | 10^7 blocks (3.3 h) |
|---|---|---|
| Sequence diagram, without the PNS lane | 0.04 s, 4 MB | 10 s, 0.58 GB |
| PNS (summary card, or the PNS lane) | 2.9 s, 15 MB | 103 s, 0.43 GB |
| RF exposure | 0.03 s, 2 MB | 6.7 s, 0.85 GB |
| Gradient limits | 0.04 s, 5 MB | 7.6 s, 1.34 GB |
| Gradient spectrum | 3.9 s, 0.16 GB | 131 s, 0.31 GB |
| RF pulse profiles | 0.03 s, 1 MB | 6.5 s, 0.54 GB |

The PNS computation is shared: the PNS card and the PNS lane of one sequence
run it one time when they use the same hardware (`pns.pns_levels_for` keeps one
result for each sequence and each hardware). The blocks card reads only the
rows that it shows, and the definitions card only the definitions. The timing
card runs pypulseq's `check_timing`, which reads every block: about 9 µs for
each block (0.9 s at 10^5 blocks), so about 90 s at 10^7 blocks; its time and
memory at that size were not measured.

The diagram card needs the browser's `DecompressionStream` with the "gzip"
format: Chrome 80, Edge 80, Firefox 113, Safari 16.4 or later (MDN
browser-compat-data, `api/DecompressionStream.json`, checked 2026-09-23).

## 4. Adding your own card

A card is a Python function that returns a `page.Card`, plus, when it has a
chart, a JavaScript file that draws it. A card that is a plugin also has a
`CardSpec` (section 7).

### The Python side

This is the file `peak_grad_card.py`. The script of the card, in the file
`peak_grad.js` next to it, is in "The JavaScript side" below.

```python
from pathlib import Path

from pulseq_reports import Card
from pulseq_reports.markup import fmt, html_table, zoom_controls
from pulseq_reports.waveforms import duration_s, file_lanes

SCRIPT = Path(__file__).with_name("peak_grad.js").read_text(encoding="utf-8")
CSS = ".peak-note { color: var(--ink-2); }"


def peak_grad_card(seq, *, peak_axis="x", card_id="peak-grad"):
    if peak_axis not in ("x", "y", "z"):
        raise ValueError(f"peak_axis must be 'x', 'y' or 'z': {peak_axis!r}")
    lane = {lane["id"]: lane for lane in file_lanes(seq)}[f"g{peak_axis}"]
    peak = max((abs(y) for segment in lane["segments"] for _, y in segment), default=0.0)
    body = (
        html_table(["Lane", "Peak (mT/m)"], [[f"G{peak_axis}", fmt(peak)]])
        + '<p class="peak-note">The peak of the lane points.</p>'
        + zoom_controls(f"{card_id}-diagram")
        + f'<div class="chart" id="{card_id}-chart">'
        f'<svg id="{card_id}-diagram" tabindex="0" role="img" '
        f'aria-label="G{peak_axis} over time"></svg>'
        f'<div class="tip" id="{card_id}-tip" hidden></div></div>'
    )
    data = {"lane": lane, "x_domain": [0.0, duration_s(seq) * 1e3]}  # ms
    return Card(
        id=card_id,
        title=f"Peak G{peak_axis}",
        body_html=body,
        data=data,
        script="peak-grad",
        scripts=(SCRIPT,),
        css=(CSS,),
    )
```

`file_lanes` builds every point of the range that it is given, so it is for a
short file, or for a time range (`start_s` and `end_s`). Its memory is too
large for the whole of a file of 10^7 blocks.

The fields of `Card`:

| Field | Meaning |
|---|---|
| `id` | The card's id, unique on the page. It must match `[a-z][a-z0-9-]*`. |
| `title` | The title, as plain text. |
| `body_html` | The HTML inside the card's `<section>`, after the title. |
| `data` | Anything JSON-ready, or `None` (the default). When it is not `None`, the page carries it in a `<script type="application/json">` element and passes it to the card's JavaScript `init` function. |
| `script` | The name that the card's script registers with `PulseqReport.registerCard`, or `None` for a card with no JavaScript. It must match `[a-z][a-z0-9-]*`. |
| `collapsed` | `True` puts the title and body in a closed `<details>` element, as the library's own blocks card does. |
| `scripts` | The texts of the JavaScript that the card needs. The page includes each distinct text one time, in the order of first use, so several cards can share a script. |
| `css` | The texts of the CSS that the card needs, included in the same way. |
| `checks` | The card's results, `Check(name, passed, message)` objects. The page does not show them (section 2, section 7). |
| `publishes`, `subscribes` | The topics of the card's messages (section 4, "Messages between cards"). |

`render_page` raises `ValueError` when two cards have the same `id`, or when
an `id` or a `script` does not match `[a-z][a-z0-9-]*`.

Give the elements inside `body_html` ids that start with `card_id`, for
example `{card_id}-chart`. A card script finds its own elements this way,
so two cards built from the same function, with different `card_id` values,
can be on one page without clashing.

### Helpers for the card HTML

`pulseq_reports.markup` has the helpers that the library's own cards use, so
that a project card looks the same:

| Name | Gives |
|---|---|
| `html_table(headers, rows)` | An HTML table in a horizontal scroll container. Each header and each cell (after `str`) is HTML-escaped. |
| `fmt(v)` | A number with 3 significant digits, with the minus sign U+2212, as in the library's tables. |
| `zoom_controls(svg_id)` | The zoom buttons (×10, ×2, ×0.5, ×0.1, Reset) of the `laneChart` chart whose `<svg>` has the id `svg_id`. Put them directly before the chart's `<div class="chart">`. |
| `Lane(...)` | One line lane, with the fields of the lane JSON format below, as keyword arguments. |
| `lanes_json(lanes)` | Each lane as a JSON-ready dict for a card's `data`: a `Lane` in field order, a dict (for example a gate lane) unchanged. |

The other names of `markup`, which start with `_`, are for the library's
own cards only.

### CSS

Give the CSS of a card in `Card.css`, as in the example above. For CSS that
belongs to no card, pass `extra_css` to `render_page` or `write_page`, a
keyword-only list of CSS texts:

```python
write_page(
    "report.html",
    title="my_scan.seq review",
    subtitle="A custom card",
    cards=[peak_grad_card(seq)],
    extra_css=[".peak-note { font-style: italic; }"],
)
```

The page has one `<style>` element: the library's `report.css`, then each
distinct text of the cards' `css` in the order of first use, then each
`extra_css` text in the order given. So a rule of `extra_css` wins over a
library rule of the same specificity. A text that contains `</style` raises
`ValueError`. Use the color tokens of `report.css` (`var(--ink)`,
`var(--ink-2)`, `var(--muted)`, `var(--grid)`, `var(--axis)`, `var(--rf)`,
`var(--gx)` and the others), so that a card follows the light and the dark
theme. Start each selector with a class that only your card uses, not with
a card id: the caller of a card builder can give a different `card_id`. The
library's own `report.css` has no id selector for the same reason.

### The JavaScript side

The script must call `PulseqReport.registerCard` with the same name as the
card's `script` field. Give the script text to the card in `Card.scripts`, as
in the example above. For a script that belongs to no card, pass it as one of
`extra_scripts` to `render_page` or `write_page`.

Use a name that no other card script on the page uses. `registerCard` throws
"already registered" for a name that is taken, and only the browser console
shows it. The library's card scripts are `diagram`, `spectrum`, `rf-profile`
and `pns`.

This is the file `peak_grad.js`:

```javascript
PulseqReport.registerCard("peak-grad", (section, data) => {
  PulseqReport.laneChart({
    svg: document.getElementById(`${section.id}-diagram`),
    chart: document.getElementById(`${section.id}-chart`),
    tip: document.getElementById(`${section.id}-tip`),
    lanes: [data.lane],
    xDomain: data.x_domain,
    xLabel: "Time (ms)",
    cursorText: v => `${v.toFixed(3)} ms`,
  });
});
```

```python
from peak_grad_card import peak_grad_card

write_page(
    "report.html",
    title="my_scan.seq review",
    subtitle="A custom card",
    cards=[peak_grad_card(seq, peak_axis="y")],
)
```

`registerCard`'s `init(section, data)` runs once the page loads, with
`section` the card's `<section>` element and `data` the card's JSON data
(or `null` when the card has no `data`). Find elements inside the section by
an id that starts with `section.id`, and scope any `querySelectorAll` for
buttons or other controls to `section`, not to the whole document, so a
second copy of the same card does not answer to the first one's controls.

Script order on the page: `chart_math.js`, `lane_chart.js`, `map_chart.js`,
`rf_profiles.js`, `seq_lanes.js`, `pns_lanes.js`, `g_lanes.js`, the cards'
`scripts` (each distinct text one time, in the order of first use), then
`extra_scripts` in the order given, then `page.js`. `page.js` runs last and
calls each card's registered `init` function. `PulseqReport` (from
`lane_chart.js`) is loaded before any card script, so a script can call
`PulseqReport.registerCard` and `PulseqReport.laneChart` at its top level. A
card whose `script` name is not registered by the time `page.js` runs does not
stop the rest of the page: that one card shows a "This card could not be
drawn" note instead.

### `PulseqReport.laneChart` options

`laneChart(options)` draws one chart of stacked lanes with zoom, pan and a
hover tooltip, and returns `{setView, setLanes, setAnchor}`.

| Option | Meaning |
|---|---|
| `svg`, `chart`, `tip` | Existing DOM elements: the chart's `<svg>` (needs a unique `id`), its wrapping element, and the tooltip element. |
| `lanes` | The lanes to draw, in the JSON format below. With `lanesFor`, the chart does not draw `lanes`. Without `groups`, `lanes` then only sets the SVG height, so give as many lanes as `lanesFor` returns. With `groups`, each render sets the height, and `lanes` can be `[]`. |
| `lanesFor(view, bins, visibleGroupIds)` | Called at the start of each render, with the current view, `bins` (the plot width in points) and the Set of currently visible group ids; its return is drawn instead of `lanes` for that render. Without `groups`, ignore the third argument, and the result must always have the same number of lanes. Without `lanesFor`, `lanes` is drawn as given to `laneChart` or `setLanes`. |
| `xDomain` | The initial view, `[lo, hi]`. |
| `extent` | The widest view a zoom or pan can reach. Defaults to `xDomain`. |
| `minSpan` | The narrowest view width. Defaults to a millionth of `extent`. |
| `onViewChange(view, isInitial)` | Called after a zoom, pan or reset changes the view. |
| `onCursor(x, pxX)` | Called when the hover cursor's value changes: `x` in chart units, or `null` when the pointer leaves the plot or the cursor is cleared. `pxX` is the chart units for each unit of the plot's width. |
| `onAnchor(x)` | Called when the anchor (the zoom marker that a click or the arrow keys set) changes, with `null` when it is cleared. |
| `xLabel` | The x-axis label text. |
| `cursorText(value)` | Formats the x value shown in the tooltip header. |
| `bands` | A list of `[lo, hi]` x ranges to shade, for example acoustic resonance bands. |
| `bandStyle` | The CSS `style` of a shaded band. |
| `groups` | A list of lane groups, `{id, label, laneIds, visible}`. A lane (of `lanes`, and of a `lanesFor` result) whose id is in no group's `laneIds` is always drawn; `groups` itself does not change after `laneChart` is called. |
| `groupControls` | An existing DOM element. With `groups` also given, one `<button type="button">` is rendered into it for each group, to show or hide that group; without `groupControls`, a group's own `visible` flag still governs it, but nothing in the page can change it. |

The returned `setView(view)` changes the view without calling
`onViewChange`. `setLanes(lanes)` replaces the lanes, keeping their number
the same. With `lanesFor`, `setLanes` has no effect, because each render
calls `lanesFor` again. `setAnchor(x)` sets the anchor to `x` (or clears it
with `null`), draws it and calls `onAnchor`.

`PulseqReport.el` and `PulseqReport.text` build SVG elements directly, for a
card that does not use `laneChart`. `el(name, attrs, parent)` makes the SVG
element `name` with the attributes of the object `attrs`, appends it to
`parent`, and returns it. `text(attrs, content, parent)` makes an SVG
`<text>` element with the text `content` in the same way, and returns
nothing.

### `PulseqReport.mapChart` options

`mapChart(options)` draws a 2D heat map: a canvas raster (one canvas pixel
per grid point) with an SVG overlay for the axes, a color legend, a
crosshair and a hover tooltip. It generalizes vb-pulseq's column
cross-section chart to any grid and any values. There is no zoom.

```html
<div class="chart map-chart" id="{card_id}-map">
  <canvas id="{card_id}-map-canvas"></canvas>
  <svg id="{card_id}-map-axes" tabindex="0" role="img"
    aria-label="Excitation |Mxy| map"></svg>
  <div class="tip" id="{card_id}-map-tip" hidden></div>
</div>
```

```javascript
PulseqReport.mapChart({
  canvas: document.getElementById(`${section.id}-map-canvas`),
  svg: document.getElementById(`${section.id}-map-axes`),
  chart: document.getElementById(`${section.id}-map`),
  tip: document.getElementById(`${section.id}-map-tip`),
  x: {lo: -0.02, hi: 0.02, n: 128, label: "x (m)"},
  y: {lo: -0.02, hi: 0.02, n: 128, label: "y (m)"},
  values: data.mxy, // a Float32Array of length 128 * 128, row-major over (y, x)
  domain: [0, 1],
  scale: "sequential",
  valueLabel: "|Mxy|",
});
```

| Option | Meaning |
|---|---|
| `canvas`, `svg`, `chart`, `tip` | Existing DOM elements: the chart's `<canvas>`, its `<svg>` overlay (needs `tabindex="0"`, `role="img"` and an `aria-label`, as above), its wrapping element, and the tooltip element. `mapChart` makes no ids of its own for the caller's elements, so several maps can be on one page. |
| `x`, `y` | The two axes, `{lo, hi, n, label}`: the axis value at each end of the grid, the number of grid points, and the axis label. |
| `values` | A `Float32Array` or `Float64Array` of length `x.n * y.n`, row-major over `(y.n, x.n)`: `values[iy * x.n + ix]` is the value at grid point `(x` index `ix`, `y` index `iy)`. |
| `domain` | `[lo, hi]` for the color scale. A value outside it is clamped to the nearer end; `NaN` is drawn transparent. |
| `scale` | `"sequential"` or `"diverging"` (default `"sequential"`); which of `report.css`'s color ramps (`--map-seq-*`, a single-hue ramp, or `--map-div-*`, a ramp with a neutral middle for a value that can be negative or positive) the raster and the legend are drawn with. |
| `valueLabel` | The legend's label, for example `"\|Mxy\|"`. |
| `cursorText(x, y, v)` | Formats the tooltip text at the grid point nearest the pointer. Default: the two axis labels and `valueLabel`, each with its value formatted by `ChartMath.fmt`. |
| `outlines` | A list of `[x0, x1, y0, y1]` rectangles, in axis units, drawn dashed over the raster, for example a `W × W` slice-thickness box. |

The returned `setData({x, y, values, domain})` replaces the axes, the
values and the color domain, and redraws, without making a new chart: for
example to show another pulse or another view. The cursor and the
crosshair are hidden after a `setData` call. `scale`, `valueLabel`,
`cursorText` and `outlines` are not replaced; they stay as given to
`mapChart`.

The returned `destroy()` removes the two listeners that the chart adds
outside its own elements: one for a change of the system's color scheme,
and one for a change of the page's `data-theme`. A card that removes a map
chart from the page, for example to draw another one, calls `destroy()`
first; otherwise the listeners keep the removed chart in memory for the
life of the page. Do not use a chart after `destroy()`.

The hover cursor and the arrow keys (when the `svg` has focus) both snap to
the nearest grid point; Escape hides the cursor. The chart redraws its
raster with the new theme's colors after a change to
`prefers-color-scheme` or to the page root's `data-theme` attribute, as
`laneChart`'s own charts do.

The caller's container needs `class="chart map-chart"`: `.chart` gives it
the tokens, the `position: relative` and the tooltip rules that the other
charts also use; `.map-chart` sizes the chart and positions its canvas and
SVG absolutely over one another.

### Lane JSON format

Each entry of `lanes` (and of a `Card`'s own `data`, when it holds lanes) is
one of the two kinds below. `markup.Lane` makes a line lane, and
`markup.lanes_json` makes the JSON of a list of lanes.

- a **line** lane (the default `kind`):
  - `id`, `title` and `unit`.
  - `color`: the name of a color token of `report.css` without the leading
    `--`, for example `"gx"` for `var(--gx)`. With `"--gx"`, the lane has no
    color, and there is no error.
  - `segments`: a list of line segments. Each segment is a list of `[x, y]`
    points in increasing `x`: the chart finds a point by binary search.
  - `domain` (`[lo, hi]` for the y axis), `ticks` and `tick_labels` (the
    y-axis tick values and their text).
  - `empty`: true to add a "no events" label to the lane. The chart still
    draws the segments.
  - `fill`: the value that the tooltip shows where no segment covers the
    cursor, for example `0` between two gradient events. `null` shows "—".
  - `minmax` (optional): true when each segment holds pairs of points, (bin
    start, minimum) and (bin centre, maximum), one pair for each bin. The
    tooltip then shows "minimum – maximum" for the bin at the cursor.
    `markup.Lane` has no `minmax` field, so give such a lane as a dict.
- a **gate** lane: the same `id`, `title`, `unit`, `color`, `domain`,
  `ticks`, `tick_labels`, `empty`, plus `kind: "gate"` and `windows` (a list
  of `[start, end]` ranges that are "on") in place of `segments`. The chart
  draws each window from y = 0 to y = 1, and the tooltip shows "on" or
  "off".

### Messages between cards

A card never reads the data or the DOM of another card. Cards on one page
talk only through published messages, on a small publish/subscribe bus that
`PulseqReport` keeps. The page has one bus, and a message names a topic and
nothing else: it has no target, and a card is never given the id of another
card.

```javascript
PulseqReport.publish(topic, message)
PulseqReport.subscribe(topic, handler, {replay = true} = {})
PulseqReport.watchSubscribers(topic, fn)
PulseqReport.requestButton(button, topic)
```

`message` must be a plain object with a string `source` (the id of the
publishing card), and `topic` must be a non-empty string; otherwise `publish`
throws `TypeError`. `publish` freezes the message (`Object.freeze`, one
level). `subscribe` returns an unsubscribe function.

The bus keeps the last message of each `(topic, source)` pair. With the
default `replay: true`, `subscribe` calls the new handler at once with each
kept message of that topic, in the order those pairs were first published, so
the order in which the page starts its cards does not matter. Pass `{replay:
false}` to skip that and see only messages published after subscribing (for
example `goto`, below, which is a one-time action, not state to catch up on).

The handlers of a topic run in the order they subscribed. A handler that
throws does not stop the other handlers or the publisher: the error goes to
the console, with the topic and the source. A `publish` made from inside a
handler is queued and delivered only once the current message has finished
reaching every handler of its topic, never nested inside that delivery.

`watchSubscribers(topic, fn)` calls `fn(count)` at once with the number of
subscribers of `topic`, and again each time that number changes (a subscribe
or an unsubscribe). It returns a function that stops the watch.
`requestButton(button, topic)` uses it to keep `button.hidden` true while
`topic` has no subscriber, so a button that sends a request is shown only when
a card acts on the request. It returns the function that stops the watch. The
library's "Show" buttons (the RF pulse profiles card's, and the PNS card's) do
this. Write such a button with the `hidden` attribute in `body_html`, as the
PNS card does, so that it stays hidden when the card's script does not run.

`PulseqReport.createMessageBus({onError} = {})` builds a private bus with the
`publish`, `subscribe` and `watchSubscribers` functions, for a card (or a
test) that wants one of its own; the page's own `PulseqReport.publish`,
`PulseqReport.subscribe` and `PulseqReport.watchSubscribers` are one such bus,
shared by every card on the page.

**One hub for each page load.** Each tab (each load of the page) runs the
scripts in its own JavaScript realm, with its own `PulseqReport` and its own
bus, so two tabs of one report never share a message. The library's scripts
use no API that reaches another tab or window, and a plugin's script must not
use one: `BroadcastChannel`, storage events (`localStorage` and
`sessionStorage`), shared workers and service workers, `postMessage`,
IndexedDB and cookies.

**The topics.** A topic is of one of two kinds:

- A *state* topic has at most one publisher on a page. A subscriber that comes
  later gets the last message (`replay`).
- A *request* topic has at most one card that acts on it (one subscriber). A
  card sends a request with `publish`.

The topics of the library:

| Topic | Kind | Published by | Acted on by |
|---|---|---|---|
| `sequence` | state | the diagram card | |
| `cursor` | state | the diagram card | |
| `anchor` | state | the diagram card | |
| `view` | state | the diagram card | |
| `goto` | request | the RF pulse profiles card, the PNS card and the gradient limits card | the diagram card |

A card gives its topics in `Card.publishes` and `Card.subscribes` (tuples of
topic names; the `CardSpec` of a plugin gives the same topics, section 7).
`render_page` checks them, with the list of kinds in `page.TOPIC_KINDS`: it
raises `ValueError` for two cards that publish one state topic (for example
two diagram cards), and for two cards that subscribe to one request topic. A
topic that is not in `TOPIC_KINDS`, such as a topic of a plugin, is not
checked while the interface is provisional. This check sees only conflicts of
messages: two cards that use no topic (for example two timing cards, made for
two sequences) pass it, and a page for one sequence is the caller's rule.

**The sequence diagram card's messages.** The sequence diagram card
(`cards.diagram_card`) publishes these topics. `source` is the card's id. Times
are file times in seconds. `block` is the play index of a block (0 is the
first block).

| Topic | Message | When |
|---|---|---|
| `sequence` | `{source, view}` | Once, right after the diagram has decoded its tables. `view` is the sequence view, below. |
| `cursor` | `{source, tS, block, pxS}`, or `{source, tS: null}` | The hover cursor moves (at most one message in each animation frame), or leaves the plot. `pxS` is the time, in seconds, of one unit of the plot's width in the current view (the plot is 812 units wide, so this is about one pixel at the chart's full width). |
| `anchor` | `{source, tS, block}`, or `{source, tS: null}` | A click, the arrow keys or a `goto` set the anchor (the zoom marker), or a reset clears it. |
| `view` | `{source, t0S, t1S}` | At the start (the view of the first window), and after each zoom, pan, reset, window button and `goto`. |

The diagram card also subscribes to one topic, `goto`. A message has one of
two forms:

| Topic | Message | What the diagram does |
|---|---|---|
| `goto` | `{source, block}` | Shows the first window (as its button does), then sets the view to that block, with half the block's own duration as padding on each side, widened to at least 1 ms and moved inside the file if the padding would reach past an end, then sets the anchor to the middle of the block. A block that the file does not have: a console warning, and no change. |
| `goto` | `{source, t0S, t1S, anchorS}` | Shows the first window, then sets the view to `[t0S, t1S]` (widened to at least the narrowest view of the chart, 0.01 ms, and moved inside the file if it reaches past an end), and sets the anchor to `anchorS`. A message that does not have three finite numbers, or that has `t1S <= t0S`: a console warning, and no change. |

A `goto` message with neither a `block` nor a range gets a console warning and
no change.

**The sequence view.** `SeqLanes.sequenceView(model)` returns a frozen,
read-only view of one decoded file, for the `view` field of a `sequence`
message. A subscriber uses only this object, never a card's own tables or
model:

```javascript
view.numBlocks, view.durationS
view.blockAt(tS)      // the block that holds file time tS (s)
view.blockStart(i)    // the start time (s) of block i
view.blockDuration(i) // the duration (s) of block i
view.events(i)        // {rf, gx, gy, gz, adc}: dense event indexes, 0 = none
view.gradEvent(k)     // {delayS, offsetsS, values}: typed arrays, do not change them
view.gradHzPerValue
view.adcEvent(k)      // {delayS, lengthS}
view.rfDelayS(k)
```

`gradEvent(k).values` are in mT/m, the same units the diagram shows;
`gradHzPerValue` is the factor that converts them to Hz/m. The dense event
indexes are those of `seq_index.SequenceIndex`: a card with its own data for
the same file can use them as keys.

## 5. Card builders

Import the builders from `pulseq_reports.cards`:

```python
from pulseq_reports.cards import (
    blocks_card,
    definitions_card,
    diagram_card,
    gradient_limits_card,
    pns_card,
    rf_exposure_card,
    rf_profile_card,
    spectrum_card,
    timing_card,
)
```

Each builder takes one `pp.Sequence`. The options after `seq` (and after
`windows`, for `diagram_card`) are keyword-only.

| Function | Shows |
|---|---|
| `timing_card(seq, *, card_id="timing")` | pypulseq's own timing check: a status line, and an error table when there are errors. |
| `definitions_card(seq, *, card_id="definitions")` | The Pulseq `Definitions`, one table row for each key. |
| `rf_exposure_card(seq, *, periodic=True, b1rms_window_s=10.0, card_id="rf-exposure")` | Peak B1, RF energy and B1+rms. |
| `spectrum_card(seq, *, coil=PRISMA_AS82, card_id="gradient-spectrum")` | The gradient spectrum of each axis and their root-sum-of-squares, against a gradient coil's acoustic resonance bands. |
| `pns_card(seq, *, gradient_asc=None, card_id="pns")` | The SAFE-model PNS prediction summary: a status line, a table of the peaks (all axes, Gx, Gy, Gz), a button that shows the peak in the diagram, and the hardware note. No chart: the stimulation over time is `diagram_card`'s PNS lane. |
| `gradient_limits_card(seq, *, windows=None, limits=None, check_norms=False, card_id="gradient-limits")` | Peak amplitude, peak slew rate and RMS amplitude of each logical axis and of the three-axis vector, as a percent of the hardware limits. The peak and slew cells give the block and the time where each value is reached, and a "Show" button that shows that block in the diagram (the button sends `goto`). |
| `diagram_card(seq, windows, *, pns_lane=False, gradient_asc=None, card_id="diagram")` | RF magnitude and phase, the ADC gate, Gx, Gy, Gz, \|G\| and, with `pns_lane`, a PNS lane, against time, with one button for each window and one for each lane group. |
| `blocks_card(seq, *, windows=None, max_rows=500, card_id="blocks")` | A collapsed, block-by-block table: block id, start, duration and events. |
| `rf_profile_card(seq, *, views=("profile",), plane=None, extent_m=None, card_id="rf-profile")` | The RF pulses of the period at the cursor of the diagram card, simulated in the browser: each distinct pulse with its 1D profile and its widths, the combined profile of the first echo, optional maps, and the distinct pulses with a button that moves the diagram to each one. Needs RF use labels. |

These are the options:

| Option | Builders | Meaning |
|---|---|---|
| `card_id` | All nine | The id of the card and the start of the ids of its elements. The default is the card's name (the first column above). Each card on a page needs its own id, so a page can hold two cards built by the same function if they have different ids. |
| `periodic` | `rf_exposure_card` | `True` (the default): the sequence is one period that repeats, for example one TR, so a B1+rms window can include the end of one repetition and the start of the next. `False`: the sequence plays one time. |
| `b1rms_window_s` | `rf_exposure_card` | The length, in s, of the averaging window of the highest B1+rms. Default 10.0 (`rf_exposure.B1RMS_WINDOW_S`). |
| `coil` | `spectrum_card` | A `GradientCoil(label, resonances)`: the label and the acoustic resonance bands that the card compares with. Default `PRISMA_AS82` (MAGNETOM Prisma, AS82). Section 6 has the type. |
| `gradient_asc` | `pns_card`, `diagram_card` | The gradient `.asc` file of the scanner, for the SAFE model, as a path. `None` (the default) uses pypulseq's example hardware, which is not a real scanner. `diagram_card` needs `pns_lane=True` to use it. |
| `pns_lane` | `diagram_card` | `True` adds the PNS lane (section 3). |
| `windows` | `diagram_card` (a required argument), `gradient_limits_card`, `blocks_card` | A list of `TimeWindow` objects (section 3). `gradient_limits_card` and `blocks_card` make one table for each window, with the window's label in an `<h3>`; with `windows=None`, one table for the whole file. |
| `limits` | `gradient_limits_card` | A `HardwareLimits(max_grad_mt_per_m, max_slew_t_per_m_per_s, label)`: the limits that the card compares with. `None` (the default) uses the limits of `seq.system`, with the label "pypulseq system limits". A sequence that `Sequence.read` reads has pypulseq's default system, not the system of a scanner, so give `limits` for a file. The card's note gives the limits, with their label and their values. |
| `check_norms` | `gradient_limits_card` | `True` also fails the card's check when the peak of \|G\| is above the amplitude limit `max_grad`. That check does not depend on the rotation of the gradients onto the scanner's axes. |
| `max_rows` | `blocks_card` | The largest number of blocks in each table. Default 500. |
| `views`, `plane`, `extent_m` | `rf_profile_card` | See "The RF profile card". |

`HardwareLimits` and `GradientCoil` are in `pulseq_reports`:

```python
from pulseq_reports import PRISMA_AS82, GradientCoil, HardwareLimits, build_cards

limits = HardwareLimits(max_grad_mt_per_m=28.0, max_slew_t_per_m_per_s=150.0, label="my scanner")
cards = build_cards(seq, limits=limits, coil=PRISMA_AS82)
```

**One PNS computation for each sequence and hardware.** `pns_card` and the PNS
lane of `diagram_card` both run the SAFE model through `pns.pns_levels_for`,
which keeps one result for each sequence object and each hardware: the
resolved path of the `gradient_asc` file, or the example hardware. A page with
a PNS card and a PNS lane that have the same `gradient_asc` runs the model one
time. A relative and an absolute path of one file are one hardware. If the
card and the lane are given different files, the model runs for each, and
they show different hardware. The kept results are built again when the
number of blocks or the last block id of the sequence changes, for example
after `add_block`. The stored level of a result is at most 16 MB.

Each PNS card, and each PNS lane, takes at most one `.asc` file. A page that
shows two systems has two PNS cards with different ids:

```python
cards = [
    pns_card(seq, gradient_asc="system_a.asc", card_id="pns-a"),
    pns_card(seq, gradient_asc="system_b.asc", card_id="pns-b"),
]
```

### The RF profile card

`build_cards` adds this card when the RF pulses have use labels and the diagram
is on the page. To build it by hand:

```python
from pulseq_reports import first_adc_window, full_window
from pulseq_reports.cards import diagram_card, rf_profile_card
from pulseq_reports.rf_profiles import rf_uses_labeled

windows = [first_adc_window(seq), full_window(seq)]
cards = [diagram_card(seq, windows)]
if rf_uses_labeled(seq):
    cards.append(rf_profile_card(seq, views=("profile", "z_df")))
```

`rf_profile_card` simulates the RF pulses of a sequence in the browser, as
they play: the RF with its frequency and phase offsets, and the gradients of
its block, with a spin-domain (Cayley-Klein) rotation for each RF sample and
no relaxation. It sends no profiles in the page: only the RF table of the
sequence, from which the browser computes the pulses that you point at.

**One diagram card.** The card follows the diagram card of the page through
its messages (`sequence`, `cursor` and `anchor`: "Messages between cards",
section 4), and never reads its data. Give the card the same sequence as
the diagram card. The card needs the diagram card on the page: a page has at
most one, because a page has one publisher of each of these topics.

**The period.** The card shows the period that holds the diagram's marker (a
click or the arrow keys set it; Escape or Reset clears it), or the hover
cursor when there is no marker. A block starts a period when it has an RF
pulse that is not a refocusing pulse and the last block before it with an RF
pulse or an ADC has an ADC; the first block with an RF pulse always starts
one. So a period of a GRE is one TR, a period of a TSE is one echo train, and
dummy scans without an ADC are in the period of the first ADC after them. A
move of the cursor inside the period changes nothing, and the card keeps the
last period when the cursor leaves the diagram.

**What it shows.** A status line with the blocks and the time of the period. For each distinct pulse of the period (its blocks with the same
RF event, without its phase offsets, and the same gradients during the RF): a
table row (use, count, gradient, flip angle, peak B1, energy, W, slice
centre, FWHM, 10–90 % edge, passband ripple, stopband level, and for an
excitation the rephasing error, the non-linear residual and the centre phase)
and a chart of its 1D profile, with the band of W shaded:

| Use | Lanes |
|---|---|
| excitation | \|Mxy\|, Mz, and the phase at the echo |
| refocusing | \|β\|² |
| inversion, saturation | Mz |
| preparation, other | \|Mxy\|, Mz |

W is the `SliceThickness` definition. A pulse with a gradient in one
direction has its profile along that direction, in mm, over c ± 2W around
its slice centre c (without W, over twice the width of its RF spectrum over
the gradient); a pulse without a gradient has its profile against the
frequency offset Δf. The phase at the echo follows the primary echo pathway
from the end of the RF to the centre of the next ADC: the gradient moments
of the blocks between, with a change of sign at each refocusing pulse. The
rephasing error is the linear phase across W that the sequence leaves, and
the non-linear residual is the phase of the pulse itself after the best
linear rephasing. Last, the card lists the distinct pulses of the sequence,
with a "Show" button that moves the diagram to the first block of each one
(the button sends a `goto` message, and is shown only while a card acts on it).

**The combined profile of the first echo.** For a period with an excitation
and refocusing pulses before its first ADC, the card also shows their
combined effect, with this note:

> **Primary echo pathway only.** This is the excitation |Mxy| times |β|² of
> each refocusing pulse before the first ADC of this period, with ideal
> crushers. It does not include the FID or stimulated-echo pathways, the
> later echoes of an echo train, the effect of preparation pulses, or
> relaxation.

Pulses on one direction give a chart with a lane for each pulse and one for
the product. Pulses on two or three directions give numbers (the signal
kept, the fraction inside W, the signal at the slice centres), and with the
`"2d"` view a map of the two directions, or the three central sections. A
pulse without a gradient is a factor, its value at the centre. A GRE has no
combined profile, and the card shows nothing for it.

**Options.**

| Option | Effect |
|---|---|
| `views` | `"profile"` (the 1D profiles, always; it must be in the list), `"z_df"` (for each pulse with a gradient in one direction, a map of the select coordinate against Δf), `"2d"` (a map on two spatial axes of a pulse whose gradient direction changes during the RF, and the map of a combined profile on two or three directions). The page has no control for them: the caller chooses. |
| `plane` | The two logical axes, for example `("x", "y")`, of the `"2d"` map of a pulse whose gradient direction changes. Default: the two axes with the largest RMS gradient during the RF. |
| `extent_m` | The width of that map on each axis, in m. Default: the `FOV` definition. Without both, the card shows the reason in place of the map. |

A map computes in slices while the page stays responsive, with a progress
text; a move to another period stops it, and it goes on when you come back.
The card keeps the profiles and maps of the last 64 distinct pulses.

**Validation.** The simulation of the browser (`assets/rf_profiles.js`) gives
the values of a Python reference (`rf_profiles.py`, `rf_sim.py`) within
1e-12, and the reference is checked against external programs and theory
(`tests/test_rf_references.py`):

- MATLAB Pulseq's `mr.simRf` (GNU Octave, MATLAB Pulseq at a pinned commit)
  on the pulse as played: the same rotation to float rounding on the RF that
  `mr.simRf` resamples itself, and within the error of that resampling (at
  most 2.4e-4) on the RF as the `.seq` file plays it;
- sigpy's `abrm_nd` on slice-select gradients, gradients on their ramps, an
  oblique gradient and a gradient that turns: `a` and `b` within 1e-12;
- an SLR excitation designed by sigpy: the profile of the pulse as the
  `.seq` file stores it equals sigpy's `abrm` of that design within 1e-12;
- a hyperbolic secant inversion: Mz is at most −0.9 across the inversion band
  of its analytic formula (Silver, Joseph and Hoult; Zhang, Garwood and Park,
  Magn. Reson. Med. 77:1630, 2017).

The fixtures are in `tests/fixtures/rf_references/`, so the tests need
neither Octave nor sigpy; `scripts/rf_references.py` makes them again in the
`rf-references` shell of `flake.nix`.

**RF use labels.** The card must know which pulses excite and which refocus.
`rf_profiles.rf_uses_labeled(seq)` returns `False` when an RF event of `seq`
has the use `undefined`, which is the default of each pypulseq
`make_*_pulse` function: set `use=` there (`"excitation"`, `"refocusing"`,
`"inversion"`, `"saturation"`, `"preparation"`). `build_cards` leaves the card
out for such a sequence. `rf_profile_card` does not raise for it: it shows a
note with the count of pulses without a label. Two cases need care:

- A `.seq` file older than format 1.5 has no use labels, and
  `Sequence.read` reads each use as `undefined`. With
  `seq.read(path, detect_rf_use=True)`, pypulseq guesses them: a flip angle
  below 90.01° is `excitation`, any other pulse is `refocusing`, or
  `saturation` when it is longer than 6 ms and between −3.5 and −3.4 ppm off
  resonance. So an inversion pulse reads as `refocusing`. The library cannot
  tell a guessed label from one that the author set: check the guesses, or
  set the labels yourself.
- pypulseq (1.5.0.post1, and the fork that this library pins) stores
  `use="other"` as `undefined`, so a file with such a pulse gets the note.
  Use another label for it.

## 6. Analysis functions

The cards are built on analysis functions that a caller can use on their own,
for example in a test of a sequence generator. Each takes one `pp.Sequence`,
and its options are keyword-only.

```python
from pulseq_reports import HardwareLimits
from pulseq_reports.grad_limits import gradient_limits
from pulseq_reports.grad_spectrum import gradient_spectrum
from pulseq_reports.pns import peak_tr_window, pns_prediction
from pulseq_reports.rf_exposure import rf_exposure

limits = gradient_limits(seq, limits=HardwareLimits(28.0, 150.0, "my scanner"))
print(limits.axes["x"].peak_mt_per_m, limits.vector_peak_mt_per_m)

exposure = rf_exposure(seq, periodic=True)
print(exposure.peak_b1_ut, exposure.b1rms_ut)

spectrum = gradient_spectrum(seq)
for band in spectrum.band_peaks:
    print(band.resonance.frequency_hz, band.relative)

prediction = pns_prediction(seq)
print(prediction.peak, prediction.peak_time_s)
print(peak_tr_window(seq, prediction.peak_time_s))
```

| Function | Gives |
|---|---|
| `grad_limits.gradient_limits(seq, *, window=None, limits=None)` | A `GradientLimits`: the peak amplitude, the peak slew rate and the RMS amplitude of each logical axis, and the peak and the RMS of the three-axis vector \|G\|, compared with `limits`. `window` is a tuple `(start_s, end_s)` in seconds; the default is the whole sequence. A window that does not end after its start, or that is not inside the sequence, raises `ValueError`. `limits` is a `HardwareLimits`; `None` uses the limits of `seq.system`. |
| `rf_exposure.rf_exposure(seq, *, periodic=True, b1rms_window_s=B1RMS_WINDOW_S)` | An `RfExposure`: the peak B1, the energy and the B1+rms. It takes the sequence as one period that repeats when `periodic` is true. `b1rms_window_s` is the length of the averaging window of the highest B1+rms; `B1RMS_WINDOW_S` is 10 s. |
| `grad_spectrum.gradient_spectrum(seq, *, resonances=PRISMA_AS82_RESONANCES)` | A `GradientSpectrum`: the spectrum of each gradient axis up to 2000 Hz (`MAX_FREQUENCY_HZ`), their root-sum-of-squares, and the largest value in each resonance band of `resonances`. |
| `pns.pns_prediction(seq, *, gradient_asc=None)` | A `PnsPrediction`, the SAFE-model summary. `gradient_asc` is the gradient `.asc` file of the scanner; `None` uses pypulseq's example hardware. |
| `pns.peak_tr_window(seq, peak_time_s)` | The start and the end, in seconds, of the TR that holds `peak_time_s` (for example `PnsPrediction.peak_time_s`), counted from the sequence start in steps of the `TR` definition. `None` without a `TR` definition, or when the sequence is not longer than one TR. |

The results are frozen dataclasses. Amplitudes are in mT/m, slew rates in
T/m/s, B1 in µT, and times in seconds.

| Type | Fields |
|---|---|
| `GradientLimits` | `reason` (`None`, or why there is no value, for example "no gradient events in the sequence"), `range_s`, `axes` (a dict from `"x"`, `"y"`, `"z"` to `AxisResult`), `vector_peak_mt_per_m`, `vector_peak_time_s`, `vector_peak_block`, `limits` (the `HardwareLimits` used), `whole_rms_mt_per_m` (a dict of the RMS of each axis over the whole sequence; `None` unless `window` was given). There is no vector slew rate. |
| `AxisResult` | `peak_mt_per_m`, `peak_time_s`, `peak_block`, `max_slew_t_per_m_per_s`, `slew_time_s`, `slew_block`, `rms_mt_per_m`. The slew is the largest of the slope of each straight segment of a gradient event, and the step at each block junction divided by the gradient raster time; its time is the start of the steepest segment, or the time of the junction. A block field is the pypulseq block ID. When several blocks reach the same largest value, the first block in play order, and the first time in it, are given. A largest value of 0 has no block (`None`). |
| `RfExposure` | `duration_s` (one period), `num_pulses`, `peak_b1_ut`, `peak_block`, `energy_ut2_s` (the integral of B1² over one period), `b1rms_ut` (the square root of the energy over the duration), `b1rms_window_s` (the window you asked for), `b1rms_window_ut` (the highest B1+rms over any such window), `b1rms_window_used_s` (the real length of the window that `b1rms_window_ut` covers). |
| `GradientSpectrum` | `reason`, `resonances`, `frequency_hz`, `axes` (a dict from `"x"`, `"y"`, `"z"` to the spectrum in mT/m/√Hz: the maximum over the windows), `rss` (the root-sum-of-squares of the axes in each window, then the maximum), `band_peaks` (a tuple of `BandPeak`: `resonance`, `peak`, `frequency_hz`, `relative` to the largest RSS value). |
| `PnsPrediction` | `reason`, `hardware`, `asc_file`, `peak` (the largest total, the root-sum-of-squares of the axes: 1 is the stimulation limit), `peak_time_s`, `axis_peaks` (a dict from `"x"`, `"y"`, `"z"`). |
| `HardwareLimits` | `max_grad_mt_per_m`, `max_slew_t_per_m_per_s`, `label`. Input of `gradient_limits`, and the `limits` option of the gradient limits card. |
| `GradientCoil` | `label`, `resonances` (a tuple of `AcousticResonance`). The `coil` option of the spectrum card. `PRISMA_AS82` is the MAGNETOM Prisma with the AS82 gradient coil, and `grad_spectrum.COILS` is a dict from the coil names of the command line (`"prisma-as82"`) to coils. |
| `AcousticResonance` | `frequency_hz` (the centre of the band), `bandwidth_hz` (its full width), and the properties `low_hz` and `high_hz`. |

`HardwareLimits`, `GradientCoil` and `PRISMA_AS82` are in `pulseq_reports`;
the other types are in the module of their function, and
`AcousticResonance` is in `grad_spectrum`. The resonance values of
`PRISMA_AS82` are published values, not read from a scanner: check them
against the `.asc` file of the scanner you use.

`PnsPrediction` is a summary only: it has no `t_s`, `norm` or `axes` array,
unlike in `v0.1.0`. A caller that wants the per-sample values of a short
sequence calls `seq.calculate_pns` directly; with the pinned pypulseq fork,
its memory is near the size of its result, about 40 bytes for each sample.
`pns.pns_levels_for(seq, *, gradient_asc=None)` gives the stored level that the
PNS card and the PNS lane use, and `pns_prediction` is built from it (section
5, "One PNS computation for each sequence and hardware").

## 7. Card plugins

A plugin adds cards to the standard report. It is a Python package that lists
a `CardSpec` in the entry-point group `pulseq_reports.cards`. `build_cards`
(section 2) and the command line (section 8) find every such spec, in the
installed packages. The library's own nine cards are found in the same way,
with the same specs.

This interface is provisional in 0.2.0. It can change in 0.3.0.

### The spec

A card is declared by a `CardSpec`, in `pulseq_reports.registry`:
`CardSpec(name, order, build, options=(), publishes=(), subscribes=(),
when=None)`.

| Field | Meaning |
|---|---|
| `name` | The name of the card, matching `[a-z][a-z0-9-]*`. It is the name in `cards=` and `skip=`, and the `card_id` of the card in the standard report. |
| `order` | A number. The cards of a report are in the order of their `order`. |
| `build` | `build(ctx) -> Card`: makes the card from a `ReportContext`. |
| `options` | The tuple of `Option` objects that `build` reads, and no others. |
| `publishes`, `subscribes` | The topics of the card's messages (section 4, "Messages between cards"). The card that `build` makes has the same topics. |
| `when` | `when(ctx) -> bool`: says if the card applies to the report. With `None`, it always applies. |

`ReportContext` is what `build` and `when` know about the report:

| Name | Gives |
|---|---|
| `ctx.seq` | The `pp.Sequence`. |
| `ctx.option(option)` | The value of `option`: the value the caller gave, or the default of the option. It raises `ValueError` for an option that the spec does not declare, so the declarations stay complete. |
| `ctx.windows()` | The standard windows: `first_adc_window(seq)` and `full_window(seq)`, made on the first call. |
| `ctx.publishes(topic)`, `ctx.subscribes(topic)` | `True` when a selected card declares the topic. |

A card never asks for another card by name. A card that follows another
card's messages asks if a selected card publishes the topic, as the RF pulse
profiles card does with `ctx.publishes("anchor")`.

An `Option` is one option of one or more cards: `Option(name, type, default,
help, cli=None)`. `name` is the keyword of the card builder that the option
stands for, in lowercase (`[a-z][a-z0-9_]*`). One name has one meaning on a
page: two cards that declare an option with one name declare the same `Option`
object, or the start of the report raises `ValueError`. `default` is the value
when the caller gives none, and `help` is the text of the option's flag on the
command line. `type` says how the command line and the config file give the
value:

| `type` | On the command line | In a config file |
|---|---|---|
| `bool` | `--name` and `--no-name` (with `_` as `-` in the name) | `true` or `false` |
| `int`, `float`, `str`, `Path` | `--name VALUE` | a number, or text |
| `tuple[str, ...]` | `--name a,b` | a list of text |

Any other type needs `cli`, an `OptionCli(flags, from_flags, from_config)`
(`pulseq_reports.registry`). `flags` is a tuple of `Flag(name, type, help,
metavar=None, choices=None)` objects, the flags that the option adds. The
function `from_flags(values)` makes the value of the option from the flags
that the caller gave (a dict from the name of a flag, without the dashes and
with `_`, to its value), and `from_config(value, base_dir)` makes it from the
value in a config file (`base_dir` is the directory of the file). Each raises
`ValueError` or `TypeError`, with a message for the caller, for an input that
is not valid. `pulseq_reports/options.py` has three examples: `limits`,
`coil` and `gradient_asc`.

### The shared options

`pulseq_reports.options` has the options that the library's cards use. A
plugin whose card reads one of these imports its object from there, and does
not make its own:

| Option | Type | Default | Read by |
|---|---|---|---|
| `gradient_asc` | `Path` | `None` | `pns`, `diagram` |
| `limits` | `HardwareLimits` (`--max-grad` and `--max-slew`) | `None` | `gradient-limits` |
| `coil` | `GradientCoil` (`--coil`) | `PRISMA_AS82` | `gradient-spectrum` |
| `periodic` | `bool` | `True` | `rf-exposure` |
| `b1rms_window_s` | `float` | 10.0 | `rf-exposure` |
| `pns_lane` | `bool` | `False` | `diagram` |
| `views` | `tuple[str, ...]` | `("profile",)` | `rf-profile` |
| `plane` | `tuple[str, ...]` | `None` | `rf-profile` |
| `extent_m` | `float` | `None` | `rf-profile` |
| `max_rows` | `int` | 500 | `blocks` |
| `check_norms` | `bool` | `False` | `gradient-limits` |

The default of an option is the default of the builder keyword, so the
standard report uses the defaults of the builders.

### The library's cards

The names, the order and the topics of the library's cards are part of the
provisional interface:

| Name | Order | Options | Publishes | Subscribes | Check |
|---|---|---|---|---|---|
| `timing` | 10 | | | | `timing` |
| `rf-exposure` | 20 | `periodic`, `b1rms_window_s` | | | |
| `diagram` | 30 | `pns_lane`, `gradient_asc` | `sequence`, `cursor`, `anchor`, `view` | `goto` | |
| `rf-profile` | 40 | `views`, `plane`, `extent_m` | `goto` | `sequence`, `cursor`, `anchor` | |
| `gradient-spectrum` | 50 | `coil` | | | |
| `pns` | 60 | `gradient_asc` | `goto` | | `pns` |
| `gradient-limits` | 70 | `limits`, `check_norms` | `goto` | | `gradient-limits` |
| `definitions` | 80 | | | | |
| `blocks` | 90 | `max_rows` | | | |

The `diagram` card gives `gradient_asc` to `diagram_card` only when `pns_lane`
is true, so a `gradient_asc` for the PNS card alone does not raise the
`ValueError` of section 3. The `rf-profile` card applies when the RF pulses
have use labels and a selected card publishes `anchor`. The keywords that the
standard report does not set are `card_id` (it is the card's name) and the
`windows` of the blocks and gradient limits cards (the standard report shows
the whole file).

The checks:

- `timing` fails when pypulseq's timing check gives errors.
- `gradient-limits` fails when the peak amplitude or the peak slew of Gx, Gy or
  Gz, in a table of the card, is above 100 % of its limit. The message names
  the axis, the value and the table. With `check_norms`, it also fails when
  the peak of \|G\| is above 100 % of `max_grad`. The library has no vector slew
  rate yet, so it does not check one.
- `pns` fails when the predicted peak is 100 % or more of the stimulation
  limit.

A card that has no value to check (for example, no gradients) passes its
check.

### The assets and the checks of a card

A `Card` carries what it needs on the page (section 4): `scripts` and `css`
are texts, and `render_page` includes each distinct text one time, in the
order of first use, so two cards of a plugin can share a script. `checks` is a
tuple of `Check(name, passed, message)` objects, in `pulseq_reports`: the card
reports its results with them, and `render_page` does not show them (the
card's own text says the values). `build_cards` gives them to the caller, and
the command line uses them for its exit status. `publishes` and `subscribes`
are the same topics as in the spec.

### An example

This plugin adds the card of section 4, with the option `peak_axis`. It has
the files `peak_grad_card.py` and `peak_grad.js` of section 4, and this file,
`peak_grad_plugin.py`:

```python
from peak_grad_card import peak_grad_card
from pulseq_reports.registry import CardSpec, Option

PEAK_AXIS = Option(
    "peak_axis",
    str,
    "x",
    "The gradient axis of the peak gradient card: x, y or z.",
)


def _build(ctx):
    return peak_grad_card(ctx.seq, peak_axis=ctx.option(PEAK_AXIS), card_id=SPEC.name)


SPEC = CardSpec("peak-grad", 65, _build, (PEAK_AXIS,))
```

The card is between the PNS card (order 60) and the gradient limits card (order
70). The package lists the spec in its `pyproject.toml`, in the group
`pulseq_reports.cards`. The name of the entry point is a label:

```toml
[project]
name = "my-pulseq-cards"
version = "0.1.0"
dependencies = ["pulseq-reports"]

[project.entry-points."pulseq_reports.cards"]
peak-grad = "peak_grad_plugin:SPEC"
```

The package must include `peak_grad.js`. When the package is
installed in the environment of the caller, `build_cards` builds the card, and
takes its option:

```python
cards = build_cards(seq, peak_axis="y")
```

and the command line has the flag `--peak-axis` (section 8).

### The errors

`build_cards` and the command line check the specs before they build a card,
and raise an error for:

- an entry point that cannot be loaded (`RuntimeError`), an entry point that is
  not a `CardSpec` (`TypeError`), a `build` or a `when` that is not callable
  (`TypeError`), and a name or an order that is not valid (`ValueError`);
- two specs with one name (`ValueError` that names both entry points);
- two options with one name that are not the same `Option` object
  (`ValueError` that names both cards and the option).

A `build` or a `when` that raises while the report is built gives an error card
in place of the card (section 2), and the other cards are built. A `build` that
does not return a `Card` does the same.

## 8. Command line

The package installs the command `pulseq-report`. It writes one report page
for each `.seq` file:

```
pulseq-report my_scan.seq
```

This reads `my_scan.seq` with `pp.Sequence().read`, builds the cards with
`build_cards`, and writes `my_scan.html` in the current directory. The page's
title is the file name, and its subtitle is "pulseq-reports" and the version.
The command line is the first way in: for a `.seq` file, it needs no Python of
your own.

### The files and the output

```
pulseq-report FILE.seq [FILE.seq ...] [-o OUT] [options]
```

- With one file, `OUT` is the page. The default is `<stem>.html` in the current
  directory.
- With several files, `OUT` is a directory (made if it does not exist; the
  default is the current directory), and each page is `<stem>.html` in it.
  Two files with one stem give exit status 1, and no page is written.

```
pulseq-report my_scan.seq other_scan.seq -o reports/
```

Each file has its own report. The command does not combine files.

### The flags

The flags come from the card specs (section 7): one flag, or one pair, for
each option of the installed cards, with the help text of the option. A plugin's
options are on the command line when the plugin is installed. `pulseq-report
--help` lists them all, and their defaults are the defaults of the card
builders. A `bool` option has a pair of flags, `--pns-lane` and
`--no-pns-lane`. A `tuple` option takes a comma list, `--views
profile,z_df`. Three options are not one plain flag:

- `limits`: `--max-grad` (mT/m) and `--max-slew` (T/m/s). Give both or neither;
  one alone gives exit status 1. The label of the limits, in the card's note,
  is "command line".
- `coil`: `--coil`, with a name of `grad_spectrum.COILS` (now `prisma-as82`).
- `gradient_asc`: `--gradient-asc PATH`.

`--cards NAME,...` builds only these cards, and `--skip NAME,...` leaves these
out. The names are the card names of section 7. A name that no card has gives
exit status 1. A flag of an option that no selected card has gives exit status
1, with a message that names the flag and the cards that have the option:

```
pulseq-report my_scan.seq --cards timing,diagram --pns-lane
pulseq-report my_scan.seq --skip blocks,definitions
```

`--card-module MODULE:ATTRIBUTE` adds a `CardSpec` from a module that is not
installed as a plugin, for example a file of your project. The module is
imported with the current directory on the import path. The spec has the same
checks as an installed one, and its options have flags. `--card-module` can be
given more than one time. For the plugin of section 7, in the current
directory:

```
pulseq-report my_scan.seq --card-module peak_grad_plugin:SPEC --peak-axis y
```

### The config file

`--config FILE` reads the values of the options from a file, for the options
that a site sets in the same way for every run. The file is TOML when its name
ends in `.toml`, and JSON when it ends in `.json`. Another name gives exit
status 1.

- The keys are the option names, as in Python (`pns_lane`, `b1rms_window_s`),
  and `cards` and `skip`, as lists of card names.
- The values are plain, except: `limits` is a table with the keys
  `max_grad_mt_per_m`, `max_slew_t_per_m_per_s` and, optional, `label` (the
  default is "config file"); `coil` is a coil name; `views` and `plane` are
  lists; and `gradient_asc` is a path, relative to the directory of the config
  file.
- A flag on the command line overrides the same key of the file.
- A key that no option has gives exit status 1 (this finds a typing error).
- A key of an option that no selected card has is ignored, because a site's
  file holds the values for every card.

This is the file of a site, in TOML (`site.toml`):

```toml
# The values of one site. The keys are option names.
skip = ["definitions"]

pns_lane = true
gradient_asc = "scanner.asc"  # relative to this file
coil = "prisma-as82"
views = ["profile", "z_df"]
max_rows = 200

[limits]
max_grad_mt_per_m = 28.0
max_slew_t_per_m_per_s = 150.0
label = "Site scanner"
```

and the same values in JSON (`site.json`):

```json
{
  "skip": ["definitions"],
  "pns_lane": true,
  "gradient_asc": "scanner.asc",
  "coil": "prisma-as82",
  "views": ["profile", "z_df"],
  "max_rows": 200,
  "limits": {
    "max_grad_mt_per_m": 28.0,
    "max_slew_t_per_m_per_s": 150.0,
    "label": "Site scanner"
  }
}
```

```
pulseq-report my_scan.seq --config site.toml
pulseq-report my_scan.seq --config site.toml --no-pns-lane
```

The two files give the same page. The second command overrides `pns_lane` of
the file.

### The limits warning

The gradient limits card compares with the limits of the sequence's system
when it has no `limits`. After `Sequence.read`, that is pypulseq's default
system, not the system of your scanner. So when you give neither `--max-grad`
and `--max-slew` nor `limits` in the config file (and the gradient limits card
is selected), the command writes a warning to stderr that names the limits that
the gradient check used, and the card's note gives them:

```
pulseq-report: warning: my_scan.seq: no gradient limits were given (--max-grad and --max-slew, or limits in the config file): the gradient check used the limits of the sequence's system, 40 mT/m and 170 T/m/s
```

### The checks and the exit status

The command writes each page, and then reads the checks of each card
(section 7). It writes each failed check to stderr, with the file, the card and
the message. An error card (section 2) has a failed check too.

| Status | Meaning |
|---|---|
| 0 | Each page is written, and each check passed. |
| 2 | Each page is written, and at least one check failed. |
| 1 | An error in the arguments or in the config file; a failed start check of the specs (section 7, "The errors"), and then no page is written; a file that cannot be read (the pages of the other files are written); or a page that cannot be built or written. |

When 1 and 2 both apply, the status is 1. For example:

```
pulseq-report my_scan.seq --max-grad 20 --max-slew 100
```

gives a page, lines on stderr like `pulseq-report: my_scan.seq: gradient-limits:
gradient-limits: Gx peak 28 mT/m is 140 % of the 20 mT/m limit in the whole
file; ...`, and the status 2. A script or a CI job can use the status to stop.

## Notes

The library is sequence-agnostic: every card builder takes a `pp.Sequence`,
and no library code knows about a specific sequence type, label or TR
structure.

Time values in the JSON data that reaches the browser (window views, chart
points) are in milliseconds, even though the Python functions that build
`TimeWindow` objects and PNS windows (`pns.peak_tr_window`,
`waveforms.first_adc_window`, `waveforms.full_window`) take and return
seconds. Frequencies (the gradient spectrum) are in hertz. Other units, for
example µT, mT/m, T/m/s and percent, are named in each card's table.

## Rotation extension

The Pulseq rotation extension rotates the gradients of a block on the
scanner. `pulseq-reports` does not support it yet: `spectrum_card`,
`pns_card`, `gradient_limits_card`, `diagram_card` and `rf_profile_card`
raise `NotImplementedError` for a sequence that uses it
(`extensions.refuse_rotations`). The RF exposure, timing, definitions and
block table cards do not use the gradients, so they accept a sequence with
rotations. `build_cards` makes an error card in place of a card that raises
(section 2), and the command line exits with 2 when a report has one
(section 8).

Limits: pypulseq 1.5.0.post1 cannot make a rotation, and its
`Sequence.read` raises `ValueError` for a `.seq` file with a rotation
section, so with that version no sequence with rotations reaches a card.
The guard also detects a rotation the way pypulseq draft PR #372 stores it
in memory (a non-empty `seq.rotation_library`) and the way its
`Sequence.read` marks a file it has read (the `"ROTATIONS"` extension
type). A later pypulseq version that stores rotations in a different way
can get past the guard undetected. Support for the rotation extension is
planned; see `TODO.md`.
