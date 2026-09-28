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
    diagram_card(seqs, windows, pns=True),
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

Above the chart, after the window buttons, one toggle button for each lane
group shows or hides that group: RF, ADC, Gradients, and PNS when at least
one file has PNS data. A hidden group costs no computation: hiding the PNS
group, for example, stops the PNS lane from being computed on the next
render.

`pns=True` or a path costs the SAFE model's own time: about 3 s of Python
for a 370 s file, about 100 s at 10^7 blocks. The stored level added to the
page is small after compression, even at that size.

The diagram, PNS, RF exposure, gradient limits and gradient spectrum cards
work for a file of up to 10^7 blocks. The time and the added memory of each,
measured on 2026-09-28 (a Mac with 10 cores and 64 GB,
`scripts/cards_scale.py`, synthetic repeating sequences; building the
sequence in pypulseq takes longer than any card at 10^7 blocks: about 90 s and
3.8 GB):

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

Script order on the page: `chart_math.js`, `lane_chart.js`, `seq_lanes.js`,
`pns_lanes.js`, `g_lanes.js`, the library's own card scripts (each included once, by
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
| `cards.pns.pns_card(seq, gradient_asc=None)` | The SAFE-model PNS prediction summary for one sequence: a status line, a table of the peaks (all axes, Gx, Gy, Gz) and the hardware note. No chart: the stimulation over time is `diagram_card`'s PNS lane. |
| `cards.gradient_limits.gradient_limits_card(seqs, window=None, limits=None)` | Peak amplitude, peak slew rate and RMS amplitude of each logical axis and of the three-axis vector, as a percent of the hardware limits. |
| `cards.diagram.diagram_card(seqs, windows, pns=False)` | RF magnitude and phase, the ADC gate, Gx, Gy, Gz and, when `pns` is not `False`, a PNS lane, against time, with one button for each window. |
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
`pns_card`, `gradient_limits_card` and `diagram_card` raise
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
