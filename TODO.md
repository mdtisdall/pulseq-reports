# TODO

Work that is planned but not started. Delete an item when its PR merges.

## Draw the sequence diagram from the event table in the browser

**Why.** The diagram card (phase 7 of `docs/plans/pulseq-reports.md`) sends
the expanded waveform points to the page. A file over the point budget gets an
envelope for its whole-file view and exact points only for the windows that the
caller chose in advance. In a whole-file view of a long file, the viewer cannot
zoom in to exact waveforms. The expanded points are large, but a Pulseq sequence
is compact: each block refers by ID to a small library of unique events. For the
ex-vivo protocol (about 39,000 blocks in each file), the block table is a few
integers for each block.

**What.** The page carries the compact form, and the chart script makes the
points for the current view:

- Python writes two tables into the card data, with pypulseq (no `.seq`
  parser in JavaScript):
  - the event library: the corner or sample points of each unique RF, gradient
    and ADC event, and the minimum and the maximum of each event;
  - the block table: the start time of each block and the IDs of its events.
- A new pure-JavaScript module gives the lanes for a time range:
  - with few blocks in the view, the exact points of those blocks;
  - with many blocks, the minimum and the maximum in each screen pixel, from the
    minimum and the maximum of each event, and the exact shape of the events
    that cross a pixel edge.
- `laneChart` asks the module for new lanes after each zoom or pan.
- The windows become shortcut buttons only. The point budget and the
  envelope-or-exact choice go away.
- The report stays one self-contained HTML file. Do not read the `.seq` file
  when the page is viewed: a page opened from a local file cannot read other
  files, and a server would stop the report working without it.

**How to check.**

- Node tests (pure functions, as for `chart_math.js`): the lanes that the module
  gives for a time range equal `waveforms.file_lanes` for that range, for the
  synthetic sequences. The Python functions in `waveforms.py` are the reference.
- The ex-vivo protocol (4 files) gives a page smaller than the phase 7 page
  (7.34 MB), and every view shows exact points when zoomed in.
- A browser check of zoom and pan across the whole file.

**When.** After the phases of `docs/plans/pulseq-reports.md` are merged, and
before ex-vivo-gre-pulseq moves to the library. Write a plan in `docs/plans/`
first: it changes the data of the diagram card, which vb-pulseq will also use.
