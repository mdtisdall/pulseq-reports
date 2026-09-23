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
pulseq-reports` (or the equivalent command of your tool).

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

```python
from pulseq_reports import pns
from pulseq_reports.cards.blocks import blocks_card
from pulseq_reports.cards.definitions import definitions_card
from pulseq_reports.cards.diagram import diagram_card
from pulseq_reports.cards.gradient_limits import gradient_limits_card
from pulseq_reports.cards.pns import pns_card
from pulseq_reports.cards.rf_exposure import rf_exposure_card
from pulseq_reports.cards.spectrum import spectrum_card
from pulseq_reports.cards.timing import timing_card
from pulseq_reports.page import write_page
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
    diagram_card(seqs, windows),
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

`diagram_card` sends exact waveform points for a file up to `point_budget`
points (200,000 by default, `waveforms.DIAGRAM_POINT_BUDGET`). A file over
that budget does not get an exact whole-file view: instead, the full-file
window becomes a minimum/maximum envelope in equal time bins, without the RF
phase lane, with close ADC windows merged. A smaller window of the same file
still gets exact points, unless that window is itself over the budget, in
which case it also becomes an envelope over its own range. The card adds a
note that names the files this happened to. Nothing in the caller's code
needs to change for this: `diagram_card` decides per file and per window.

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

Script order on the page: `chart_math.js`, `lane_chart.js`, the library's
own card scripts (each included once, by name, from `assets/cards/`), then
`extra_scripts` in the order given, then `page.js`. `page.js` runs last and
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
| `xDomain` | The initial view, `[lo, hi]`. |
| `extent` | The widest view a zoom or pan can reach. Defaults to `xDomain`. |
| `minSpan` | The narrowest view width. Defaults to a millionth of `extent`. |
| `onViewChange(view, isInitial)` | Called after a zoom, pan or reset changes the view. |
| `xLabel` | The x-axis label text. |
| `cursorText(value)` | Formats the x value shown in the tooltip header. |
| `bands` | A list of `[lo, hi]` x ranges to shade, for example acoustic resonance bands. |
| `bandStyle` | The CSS `style` of a shaded band. |

The returned `setView(view)` changes the view without calling
`onViewChange`. `setLanes(lanes)` replaces the lanes, keeping their number
the same. `setWindow({lanes, xDomain, extent})` replaces the lanes (any
number), the initial view and the widest view together, and resets to the
new `xDomain`; the PNS card's "peak TR" button and the diagram card's window
buttons both use it. `PulseqReport.el` and `PulseqReport.text` are small
helpers for building SVG elements directly, for a card that does not use
`laneChart`.

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

## 5. Card builders

| Function | Shows |
|---|---|
| `cards.timing.timing_card(seqs)` | pypulseq's own timing check for each sequence: a status line, and an error table when there are errors. |
| `cards.definitions.definitions_card(seqs)` | The Pulseq `Definitions` of each sequence, one table row for each key. |
| `cards.rf_exposure.rf_exposure_card(seqs, periodic=True, window_s=10.0)` | Peak B1, RF energy and B1+rms, per file, and a combined "All files" table for more than one file. |
| `cards.spectrum.spectrum_card(seqs, resonances=PRISMA_AS82_RESONANCES, scanner_label=...)` | The gradient spectrum of each axis and their root-sum-of-squares, against a gradient coil's acoustic resonance bands. |
| `cards.pns.pns_card(seq, gradient_asc=None)` | The SAFE-model PNS prediction over time for one sequence, with a "peak TR" view when the sequence has a `TR` definition and more than one TR. |
| `cards.gradient_limits.gradient_limits_card(seqs, window=None, limits=None)` | Peak amplitude, peak slew rate and RMS amplitude of each logical axis and of the three-axis vector, as a percent of the hardware limits. |
| `cards.diagram.diagram_card(seqs, windows, point_budget=DIAGRAM_POINT_BUDGET)` | RF magnitude and phase, the ADC gate, and Gx, Gy, Gz against time, with one button for each window. |
| `cards.blocks.blocks_card(seqs, windows=None, max_rows=500)` | A collapsed, block-by-block table: block id, start, duration and events. |

All eight functions take `card_id` with a default, so a page can hold two
cards built by the same function.

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

When the library gets the same single sequence as vb-pulseq, the timing,
definitions, RF exposure, gradient spectrum and PNS cards give the same
data as vb-pulseq's own report; `scripts/vb_parity.py` checks this.

## Rotation extension

The Pulseq rotation extension rotates the gradients of a block on the
scanner. `pulseq-reports` does not support it yet: `spectrum_card`,
`pns_card` and `gradient_limits_card` (and, later, the diagram card) raise
`NotImplementedError` for a sequence that uses it
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
