# Using pulseq-reports

`pulseq-reports` writes one self-contained HTML review report for one or more
Pulseq sequences. This document shows how a consumer project adds the
dependency, builds a page with the library's cards, and adds its own card.

## 1. Add the dependency

`mdtisdall/pulseq-reports` is a public GitHub repository. Consumers pin it by
git URL and tag. CI needs no credentials to fetch it.

In `pyproject.toml`:

```toml
[project]
dependencies = [
    "pulseq-reports @ git+https://github.com/mdtisdall/pulseq-reports@v0.1.0",
]
```

With uv:

```
uv add "pulseq-reports @ git+https://github.com/mdtisdall/pulseq-reports@v0.1.0"
```

To move to a later tag, change `@v0.1.0` and run `uv lock --upgrade-package
pulseq-reports` (or the equivalent command of your tool). This document
describes `main`; the release candidate `v0.2.0rc1` has everything in it. To
try it, pin `@v0.2.0rc1`, and add the pypulseq source line of the next
paragraph.

The PNS summary card and the diagram card's PNS lane need a chunked SAFE
recursion that stock pypulseq does not have: `pns_levels.py` imports a
private function of a pypulseq fork, `_safe_gwf_to_pns_chunk`. So
`pulseq-reports` pins a branch of that fork, `mdtisdall/pypulseq` at
`pns-chunked`, in its own `[tool.uv.sources]`. uv uses `[tool.uv.sources]`
only for this project's own environment: a project that depends on
`pulseq-reports` gets stock pypulseq from PyPI unless it adds the same
source line itself, and then a call into the PNS card or the PNS lane fails
with an `ImportError`. Add this to the consumer's own `pyproject.toml`, with
the same commit as `pulseq-reports`'s own `pyproject.toml`:

```toml
[tool.uv.sources]
pypulseq = { git = "https://github.com/mdtisdall/pypulseq", rev = "<the commit pulseq-reports pins>" }
```

This paragraph applies while `pulseq-reports` pins a fork commit instead of
a pypulseq release (`docs/plans/cards-at-scale.md`, section 3.6, item 7).

## 2. One sequence, every card

This example builds a page for one sequence with every library card. It uses
`your pp.Sequence` in place of a real sequence.

Wrap the sequence in a `NamedSequence`. Most card builders take a list of
`NamedSequence`, even for one file, so that the same call works for one file
or several.

The diagram card needs a list of `TimeWindow` objects: named time ranges to
show as buttons. `waveforms.first_adc_window` and `waveforms.full_window`
give the two standard views. A third window, the TR with the highest PNS,
comes from the PNS prediction: run `pns.pns_prediction` to get the peak time,
then `pns.peak_tr_window` to get the window. `peak_tr_window` returns `None`
when the sequence has no `TR` definition or is not longer than one TR, so
check for that before you add the window.

`PnsPrediction` is a summary only (`reason`, `hardware`, `asc_file`, `peak`,
`peak_time_s`, `axis_peaks`): it has no `t_s`, `norm` or `axes` array, unlike
in `v0.1.0`. A caller that wants the per-sample values of a short sequence
calls `seq.calculate_pns` directly; with the pinned pypulseq fork, its
memory is near the size of its result, about 40 bytes for each sample.

```python
from pulseq_reports import pns
from pulseq_reports.cards.blocks import blocks_card
from pulseq_reports.cards.definitions import definitions_card
from pulseq_reports.cards.diagram import diagram_card
from pulseq_reports.cards.gradient_limits import gradient_limits_card
from pulseq_reports.cards.pns import pns_card
from pulseq_reports.cards.rf_exposure import rf_exposure_card
from pulseq_reports.cards.rf_profile import rf_profile_card
from pulseq_reports.cards.spectrum import spectrum_card
from pulseq_reports.cards.timing import timing_card
from pulseq_reports.page import write_page
from pulseq_reports.rf_profiles import rf_uses_labeled
from pulseq_reports.seq_utils import NamedSequence
from pulseq_reports.waveforms import TimeWindow, first_adc_window, full_window

seq = your_pp_sequence  # a pypulseq Sequence
named = NamedSequence(name="my_scan.seq", seq=seq)
seqs = [named]

windows = [first_adc_window(seqs), full_window(seqs)]

prediction = pns.pns_prediction(seq)
peak_window = pns.peak_tr_window(seq, prediction.peak_time_s)
if peak_window is not None:
    start_s, end_s = peak_window
    windows.append(TimeWindow("Peak-PNS TR", 0, start_s, end_s))

cards = [
    timing_card(seqs),
    rf_exposure_card(seqs),
    diagram_card(seqs, windows, pns=True),
]
if rf_uses_labeled(seq):
    cards.append(rf_profile_card(seqs, views=("profile", "z_df")))
cards += [
    spectrum_card(seqs),
    pns_card(named),
    gradient_limits_card(seqs),
    definitions_card(seqs),
    blocks_card(seqs),
]

write_page(
    "report.html",
    title="my_scan.seq review",
    subtitle="Every library card for one sequence",
    cards=cards,
)
```

`pns_card` takes one `NamedSequence`, not a list, because the SAFE-model
prediction is defined for one sequence. Every other card in this example
takes the list `seqs`.

`pns_card` and `diagram_card`'s PNS lane (`pns=True` here) share one PNS
computation for each sequence (`pns.pns_levels_for`), so this page runs the
SAFE model once for `named`, not twice.

`rf_profile_card` shows the RF pulses of the period at the cursor of the
diagram card, so it goes on a page with that diagram card, and it needs a use
label on each RF pulse: `rf_uses_labeled` checks that first. Without the
labels, the card shows a note in place of the profiles (see "The RF profile
card" in section 5).

The card order above is a suggestion, not a requirement: `write_page` puts
the cards on the page in the order of the `cards` list.

## 3. Several files with windows

A long acquisition is sometimes several `.seq` files, for example one file
for each segment. This example gives the diagram card a one-TR window and a
full-file window for each file, and combines the files in the spectrum and
RF exposure cards.

```python
from pulseq_reports.cards.diagram import diagram_card
from pulseq_reports.cards.rf_exposure import rf_exposure_card
from pulseq_reports.cards.spectrum import spectrum_card
from pulseq_reports.page import write_page
from pulseq_reports.seq_utils import NamedSequence
from pulseq_reports.waveforms import TimeWindow, full_window

TR = 20e-3  # s

seqs = [
    NamedSequence(name=f"segment-{i}.seq", seq=segment_sequences[i])
    for i in range(len(segment_sequences))
]

windows = []
for i, named in enumerate(seqs):
    windows.append(TimeWindow("TR 1", i, 0.0, TR))
    windows.append(full_window(seqs, file_index=i))

cards = [
    diagram_card(seqs, windows),
    spectrum_card(seqs),
    rf_exposure_card(seqs),
]

write_page("report.html", title="Acquisition review", subtitle="Several segment files", cards=cards)
```

`TimeWindow.label` here is just `"TR 1"`, not the file name: with more than
one file, `diagram_card` puts the file name in front of each button's label
itself, so a caller that also adds the file name gets it twice.

The spectrum and RF exposure cards give one combined result for all the
files in `seqs`: the spectrum card takes the maximum, at each frequency,
over the files (`grad_spectrum.combine`); the RF exposure card adds an "All
files" table that treats the files as played one after another with no gap.
`pns_card` takes one sequence, so a multi-file acquisition needs one PNS
card for each file it should cover, or none. Each card on a page needs its own id,
so give the PNS cards different ids, for example `pns_card(named, card_id=f"pns-{i}")`.

`diagram_card` sends the compressed block and event tables of each file that
at least one window uses, not expanded points. The page stays one
self-contained file. Its size depends on the number of blocks and of
distinct events, not on the number of waveform points.

In the browser, each view (a zoom, a pan, or a window button) shows the
exact waveform when that view has at most 20,000 points
(`SeqLanes.EXACT_POINT_LIMIT`). A view with more points shows the minimum and
the maximum of each lane in each of the chart's time bins instead, including
the RF phase lane; no peak and no ADC window is lost. A status line under the
chart says which of the two the current view shows. Windows are only
shortcut buttons: they do not change what a view shows, only where it starts.

`diagram_card`'s `pns` argument adds a PNS lane next to the gradients, for a
file that has a gradient event: `False` (the default) adds no PNS lane and
computes no PNS; `True` predicts with pypulseq's example hardware; the path
of a gradient `.asc` file predicts with that hardware. A file with no
gradient event gets no PNS lane, whatever `pns` is.

The PNS lane shows the total predicted stimulation (the root-sum-of-squares
of the three axes) as a percent of the SAFE stimulation limit. It is exact
for a view of 10 s or less. A longer view shows the minimum and the maximum
in stored bins instead, 6.15 ms wide, or a coarser pyramid of them for a
still longer view; no peak is lost. The status line under the chart says
which: "PNS: exact." or "PNS: minimum and maximum in bins of X ms." A file
longer than about 3.4 hours gets coarser stored bins, so that their number
stays bounded; for such a file, a view longer than 10 s but not much longer
shows bins wider than the usual 6.15 ms, and the status line adds "Zoom in
to 10 s or less for the exact values." to say so. For a file with a block
that is not a whole number of gradient-raster samples, there is no exact
view at any zoom, and the status line says so instead.

The Gradients group also has a |G| lane after Gz: the magnitude of the
gradient vector, `sqrt(Gx^2 + Gy^2 + Gz^2)` in mT/m, with each axis read from
its block's own event (0 outside it). It always shows the exact minimum and
maximum of |G| in each time bin of the chart, at every zoom, because |G| is
not a straight line between the corner points of the gradients. It needs no
argument and no data of its own: the browser computes it from the diagram
tables.

Above the chart, after the window buttons, one toggle button for each lane
group shows or hides that group: RF, ADC, Gradients (Gx, Gy, Gz and |G|), and
PNS when at least one file has PNS data. A hidden group costs no computation:
hiding the PNS group, for example, stops the PNS lane from being computed on
the next render.

`pns=True` or a path costs the SAFE model's own time: about 3 s of Python
for a 370 s file, about 100 s at 10^7 blocks. The stored level added to the
page is small after compression, even at that size.

The diagram, PNS, RF exposure, gradient limits and gradient spectrum cards
work for a file of up to 10^7 blocks. The time and the added memory of each,
measured on 2026-09-28 (a Mac with 10 cores and 64 GB,
`scripts/cards_scale.py`, synthetic repeating sequences; building the
sequence of 10^7 blocks in pypulseq itself takes about 90 s and 3.8 GB):

| Card | 370 s file (4 × 10^4 blocks) | 10^7 blocks (3.3 h) |
|---|---|---|
| Sequence diagram, without the PNS lane | 0.04 s, 4 MB | 10 s, 0.58 GB |
| PNS (summary card, or the PNS lane) | 2.9 s, 15 MB | 103 s, 0.43 GB |
| RF exposure | 0.03 s, 2 MB | 6.7 s, 0.85 GB |
| Gradient limits | 0.04 s, 5 MB | 7.6 s, 1.34 GB |
| Gradient spectrum | 3.9 s, 0.16 GB | 131 s, 0.31 GB |

The PNS computation is shared: the PNS card and the PNS lane of one sequence
run it one time. The blocks card reads only the rows that it shows, and the
definitions card only the definitions. The timing card runs pypulseq's
`check_timing`, which reads every block: about 9 µs for each block (0.9 s at
10^5 blocks), so about 90 s at 10^7 blocks; its time and memory at that size
were not measured.

The diagram card needs the browser's `DecompressionStream` with the "gzip"
format: Chrome 80, Edge 80, Firefox 113, Safari 16.4 or later (MDN
browser-compat-data, `api/DecompressionStream.json`, checked 2026-09-23).

## 4. Adding your own card

A card is a Python function that returns a `page.Card`, plus, when it has a
chart, a JavaScript file that draws it.

### The Python side

```python
from pulseq_reports.page import Card
from pulseq_reports.waveforms import file_lanes


def peak_grad_card(named, card_id="peak-grad"):
    lanes = {lane["id"]: lane for lane in file_lanes(named.seq)}
    gx = lanes["gx"]
    body = (
        f'<div class="chart" id="{card_id}-chart">'
        f'<svg id="{card_id}-diagram" tabindex="0" role="img" '
        'aria-label="Gx over time"></svg>'
        f'<div class="tip" id="{card_id}-tip" hidden></div></div>'
    )
    return Card(id=card_id, title="Peak Gx", body_html=body, data={"lane": gx}, script="peak-grad")
```

`Card.id` (and `Card.script`, when given) must match `[a-z][a-z0-9-]*`, and
must be unique among the cards on one page; `render_page` raises
`ValueError` otherwise. `data` is anything JSON-ready; when it is not
`None`, the page carries it in a `<script type="application/json">` element
and passes it to the card's JavaScript `init` function. `collapsed=True`
puts the title and body in a closed `<details>` element, as the library's
own blocks card does.

Give the elements inside `body_html` ids that start with `card_id`, for
example `{card_id}-chart`. A card script finds its own elements this way,
so two cards built from the same function, with different `card_id` values,
can be on one page without clashing.

### The JavaScript side

Pass the script as one of `extra_scripts` to `render_page` or `write_page`.
It must call `PulseqReport.registerCard` with the same name as the card's
`script` field:

```javascript
PulseqReport.registerCard("peak-grad", (section, data) => {
  PulseqReport.laneChart({
    svg: document.getElementById(`${section.id}-diagram`),
    chart: document.getElementById(`${section.id}-chart`),
    tip: document.getElementById(`${section.id}-tip`),
    lanes: [data.lane],
    xDomain: data.lane.domain,
    xLabel: "Gx (mT/m)",
    cursorText: v => `${v.toFixed(2)} mT/m`,
  });
});
```

```python
write_page(
    "report.html",
    title="my_scan.seq review",
    subtitle="A custom card",
    cards=[peak_grad_card(named)],
    extra_scripts=[open("peak_grad.js").read()],
)
```

`registerCard`'s `init(section, data)` runs once the page loads, with
`section` the card's `<section>` element and `data` the card's JSON data
(or `null` when the card has no `data`). Find elements inside the section by
an id that starts with `section.id`, and scope any `querySelectorAll` for
buttons or other controls to `section`, not to the whole document, so a
second copy of the same card does not answer to the first one's controls.

Script order on the page: `chart_math.js`, `lane_chart.js`, `map_chart.js`,
`rf_profiles.js`, `seq_lanes.js`, `pns_lanes.js`, `g_lanes.js`, the library's own card
scripts (each included once, by
name, from `assets/cards/`), then `extra_scripts` in the order given, then `page.js`.
`page.js` runs last and
calls each card's registered `init` function. `PulseqReport` (from
`lane_chart.js`) is loaded before any `extra_scripts`, so a custom card
script can call `PulseqReport.registerCard` and `PulseqReport.laneChart` at
its top level. A card whose `script` name is not registered by the time
`page.js` runs does not stop the rest of the page: that one card shows a
"This card could not be drawn" note instead.

### `PulseqReport.laneChart` options

`laneChart(options)` draws one chart of stacked lanes with zoom, pan and a
hover tooltip, and returns `{setView, setLanes, setWindow}`.

| Option | Meaning |
|---|---|
| `svg`, `chart`, `tip` | Existing DOM elements: the chart's `<svg>` (needs a unique `id`), its wrapping element, and the tooltip element. |
| `lanes` | The lanes to draw, in the JSON format below. |
| `lanesFor(view, bins, visibleGroupIds)` | Called at the start of each render, with the current view, `bins` (the plot width in points) and the Set of currently visible group ids; its return is drawn instead of `lanes` for that render. Without `groups`, ignore the third argument, and the result must always have the same number of lanes. Without `lanesFor`, `lanes` is drawn as given to `laneChart`, `setLanes` or `setWindow`. |
| `xDomain` | The initial view, `[lo, hi]`. |
| `extent` | The widest view a zoom or pan can reach. Defaults to `xDomain`. |
| `minSpan` | The narrowest view width. Defaults to a millionth of `extent`. |
| `onViewChange(view, isInitial)` | Called after a zoom, pan or reset changes the view. |
| `xLabel` | The x-axis label text. |
| `cursorText(value)` | Formats the x value shown in the tooltip header. |
| `bands` | A list of `[lo, hi]` x ranges to shade, for example acoustic resonance bands. |
| `bandStyle` | The CSS `style` of a shaded band. |
| `groups` | A list of lane groups, `{id, label, laneIds, visible}`. A lane (of `lanes`, and of a `lanesFor` result) whose id is in no group's `laneIds` is always drawn; `groups` itself does not change after `laneChart` is called, not even through `setWindow`. |
| `groupControls` | An existing DOM element. With `groups` also given, one `<button type="button">` is rendered into it for each group, to show or hide that group; without `groupControls`, a group's own `visible` flag still governs it, but nothing in the page can change it. |

The returned `setView(view)` changes the view without calling
`onViewChange`. `setLanes(lanes)` replaces the lanes, keeping their number
the same. `setWindow({lanes, xDomain, extent})` replaces the lanes (any
number), the initial view and the widest view together, and resets to the
new `xDomain`; the diagram card's window buttons use it, including to
switch to another file's model. `PulseqReport.el` and `PulseqReport.text`
are small helpers for building SVG elements directly, for a card that does
not use `laneChart`.

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
one of:

- a **line** lane (the default `kind`): `id`, `title`, `unit`, `color` (a
  `--<color>` CSS custom property name), `segments` (a list of line
  segments, each a list of `[x, y]` points), `domain` (`[lo, hi]` for the y
  axis), `ticks` and `tick_labels` (the y-axis tick values and their text),
  `empty` (true to show "no events" instead of a line), and `fill` (a
  baseline y value to fill to, or `null` for no fill).
- a **gate** lane: the same `id`, `title`, `unit`, `color`, `domain`,
  `ticks`, `tick_labels`, `empty`, plus `kind: "gate"` and `windows` (a list
  of `[start, end]` ranges that are "on") in place of `segments`.

### Messages between cards

A card never reads the data or the DOM of another card. Cards on one page
talk only through published messages, on a small publish/subscribe bus that
`PulseqReport` keeps:

```javascript
PulseqReport.publish(topic, message)
PulseqReport.subscribe(topic, handler, {replay = true} = {})
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

`PulseqReport.createMessageBus({onError} = {})` builds a private bus with the
same two functions, for a card (or a test) that wants one of its own; the
page's own `PulseqReport.publish`/`PulseqReport.subscribe` are one such bus,
shared by every card on the page.

**The sequence diagram card's messages.** The sequence diagram card
(`cards.diagram.diagram_card`) publishes these topics. `source` is the card's
id. Times are file times in seconds. `file` is the index of the file in the
card's own list, the same index the card's data uses. `block` is the play
index of a block (0 is the first block).

| Topic | Message | When |
|---|---|---|
| `sequence` | `{source, file, name, view}` | Once for each file, right after the diagram has decoded it. `view` is the sequence view, below. |
| `cursor` | `{source, file, tS, block, pxS}`, or `{source, file: null}` | The hover cursor moves (at most one message in each animation frame), or leaves the plot. `pxS` is the time, in seconds, of one unit of the plot's width in the current view (the plot is 812 units wide, so this is about one pixel at the chart's full width). |
| `anchor` | `{source, file, tS, block}`, or `{source, file: null}` | A click or the arrow keys set the anchor (the zoom marker), or a reset clears it. |
| `view` | `{source, file, t0S, t1S}` | After each zoom, pan, reset, window button, change of file and `goto`. |

The diagram card also subscribes to one topic:

| Topic | Message | What the diagram does |
|---|---|---|
| `goto` | `{source, target, file, block}`, or `{source, target, name, block}` | When `target` is that diagram card's id: shows the first window of the file (switching files first, if it is showing another file), then sets the view to that block, with half the block's own duration as padding on each side, widened to at least 1 ms and moved inside the file if the padding would reach past an end, then sets the anchor to the middle of the block. `file` is the diagram's own file index (as in its messages); `name` is a file name, for the first file of the diagram with that name, and is used when the message has it. A card that has not had the `sequence` message of a file yet (the diagram decodes a file the first time it shows it) can name it by `name`. A file with no window, a name that no file has, or a block that the file does not have: a console warning, and no change. A message for another `target` is ignored. |

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

| Function | Shows |
|---|---|
| `cards.timing.timing_card(seqs)` | pypulseq's own timing check for each sequence: a status line, and an error table when there are errors. |
| `cards.definitions.definitions_card(seqs)` | The Pulseq `Definitions` of each sequence, one table row for each key. |
| `cards.rf_exposure.rf_exposure_card(seqs, periodic=True, window_s=10.0)` | Peak B1, RF energy and B1+rms, per file, and a combined "All files" table for more than one file. |
| `cards.spectrum.spectrum_card(seqs, resonances=PRISMA_AS82_RESONANCES, scanner_label=...)` | The gradient spectrum of each axis and their root-sum-of-squares, against a gradient coil's acoustic resonance bands. |
| `cards.pns.pns_card(seq, gradient_asc=None)` | The SAFE-model PNS prediction summary for one sequence: a status line, a table of the peaks (all axes, Gx, Gy, Gz) and the hardware note. No chart: the stimulation over time is `diagram_card`'s PNS lane. |
| `cards.gradient_limits.gradient_limits_card(seqs, window=None, limits=None)` | Peak amplitude, peak slew rate and RMS amplitude of each logical axis and of the three-axis vector, as a percent of the hardware limits. |
| `cards.diagram.diagram_card(seqs, windows, pns=False)` | RF magnitude and phase, the ADC gate, Gx, Gy, Gz, \|G\| and, when `pns` is not `False`, a PNS lane, against time, with one button for each window and one for each lane group. |
| `cards.blocks.blocks_card(seqs, windows=None, max_rows=500)` | A collapsed, block-by-block table: block id, start, duration and events. |
| `cards.rf_profile.rf_profile_card(seqs, diagram_card_id="diagram", views=("profile",), plane=None, extent_m=None)` | The RF pulses of the period at the cursor of a diagram card, simulated in the browser: each distinct pulse with its 1D profile and its widths, the combined profile of the first echo, optional maps, and the distinct pulses of each file with a button that moves the diagram to each one. Needs RF use labels. |

All nine functions take `card_id` with a default, so a page can hold two
cards built by the same function.

### The RF profile card

```python
from pulseq_reports.cards.rf_profile import rf_profile_card
from pulseq_reports.rf_profiles import rf_uses_labeled

cards = [diagram_card(seqs, windows)]
if all(rf_uses_labeled(named.seq) for named in seqs):
    cards.append(rf_profile_card(seqs, views=("profile", "z_df")))
```

`rf_profile_card` simulates the RF pulses of a sequence in the browser, as
they play: the RF with its frequency and phase offsets, and the gradients of
its block, with a spin-domain (Cayley-Klein) rotation for each RF sample and
no relaxation. It sends no profiles in the page: only the RF table of each
file, from which the browser computes the pulses that you point at.

**One diagram card.** The card follows the diagram card `diagram_card_id`
through its messages ("Messages between cards", section 4), and never reads
its data. Give the card the same list of files as that diagram card, with
the same names: the card matches the diagram's files by name, so the names
must be unique (`ValueError` otherwise). The card needs that diagram card on
the page.

**The period.** The card shows the period that holds the diagram's marker (a
click or the arrow keys set it; Escape or Reset clears it), or the hover
cursor when there is no marker. A block starts a period when it has an RF
pulse that is not a refocusing pulse and the last block before it with an RF
pulse or an ADC has an ADC; the first block with an RF pulse always starts
one. So a period of a GRE is one TR, a period of a TSE is one echo train, and
dummy scans without an ADC are in the period of the first ADC after them. A
move of the cursor inside the period changes nothing, and the card keeps the
last period when the cursor leaves the diagram.

**What it shows.** A status line with the file, the blocks and the time of
the period. For each distinct pulse of the period (its blocks with the same
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
linear rephasing. Last, the card lists the distinct pulses of each file,
with a "Show" button that moves the diagram to the first block of each one.

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
| `diagram_card_id` | The id of the diagram card to follow. Default `"diagram"`. |

A map computes in slices while the page stays responsive, with a progress
text; a move to another period stops it, and it goes on when you come back.
The card keeps the profiles and maps of the last 64 distinct pulses.

**RF use labels.** The card must know which pulses excite and which refocus.
`rf_profiles.rf_uses_labeled(seq)` returns `False` when an RF event of `seq`
has the use `undefined`, which is the default of each pypulseq
`make_*_pulse` function: set `use=` there (`"excitation"`, `"refocusing"`,
`"inversion"`, `"saturation"`, `"preparation"`). The card does not raise for
such a file: it shows a note for the file with the count of pulses without a
label, and the other files of the card still work. Two cases need care:

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

## Notes

The library is sequence-agnostic: every card builder takes `pp.Sequence`
objects wrapped in `NamedSequence`, and no library code knows about a
specific sequence type, label or TR structure.

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
rotations.

Limits: pypulseq 1.5.0.post1 cannot make a rotation, and its
`Sequence.read` raises `ValueError` for a `.seq` file with a rotation
section, so with that version no sequence with rotations reaches a card.
The guard also detects a rotation the way pypulseq draft PR #372 stores it
in memory (a non-empty `seq.rotation_library`) and the way its
`Sequence.read` marks a file it has read (the `"ROTATIONS"` extension
type). A later pypulseq version that stores rotations in a different way
can get past the guard undetected. Support for the rotation extension is
planned; see `TODO.md`.
