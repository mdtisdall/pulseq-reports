# Code review, 2026-09-28

A review of the whole library before the 0.2.0 release: dead code, code that
can be simpler or clearer, missing or wrong documentation, the public API, and
features that a user can expect. It does not propose tests for edge cases,
except where a finding is a bug that gives a wrong value on a report.

## Scope and method

- **Code read:** `src/pulseq_reports/` (the Python modules, the cards, and the
  JavaScript and CSS assets), `scripts/`, the helpers in `tests/` and
  `tests/js/`, `README.md`, `docs/usage.md`, `TODO.md` and `TESTS.md`.
- **Code state:** `main` at `a6ec78b`, plus commit `5a2ae35` of the branch
  `feature/public-card-helpers` (the markup helpers `html_table`, `fmt`,
  `zoom_controls`, `lanes_json` and `Lane` become public; `render_page` and
  `write_page` get `extra_css`; `report.css` loses the rules of vb-pulseq's
  own cards). Line numbers are for that state. `main` then got `4a49d2e`
  (#48, a new README and an example report); the README findings below were
  checked again against it.
- **Method:** six reviewers each read one part in full: the Python data core,
  the Python analyses, the page and the cards (with the documents), the
  diagram JavaScript, the PNS and |G| lane JavaScript, and the scripts and test
  helpers. Each "dead code" finding comes with a search of the whole
  repository for callers.
- **Checked:** the bugs B1, B2 and B3 were reproduced (B1 in Python, B2 in
  Node, B3 from the key check in the code and a reviewer's Node run). The
  dead-code findings marked "checked" were searched again. The other findings
  are the reviewers' reading of the code and were not each checked again.

The findings have IDs: B (bugs), A (API), F (features), D (dead code), S
(simplifications), P (time and memory at scale), C (documentation and
comments), L (model details with a low reach).

## Status on 2026-09-29

The findings were checked again against `main` at `4e17c66`, after #48 to
#63 (the RF pulse profiles). The line numbers in the sections below are still
those of the review state.

- **Fixed:** C21. #53 moved `decodeTable` to `lane_chart.js`, and the text
  went with it.
- **No longer apply:** D5, S17 and C11, because #55 deleted
  `scripts/vb_parity.py`. The `vb_parity.py` parts of A8 no longer apply
  either.
- **Open:** all the other findings. `feature/public-card-helpers` is not
  merged.
- **New cases of the same findings,** in the code of #48 to #63:
  - B3: the `goto` message (#53), which the "Show" buttons of the RF profile
    card send, also calls `showWindow`. A `GLanes` error there also leaves
    "Loading…" and disabled buttons.
  - A6: there are nine card builders now, with `rf_profile_card`.
  - A8: `rf_profile_data` and `rf_table` (`cards/rf_profile.py`) have public
    names and are not in `docs/usage.md`.
  - A10: the reserved script names are now `diagram`, `spectrum` and
    `rf-profile`.
  - C7: the sentence is already false on `main`. The RF profiles, `mapChart`
    and the message bus are not in `v0.2.0rc1`.
  - C8: the RF profile card adds more `<h3>` and `<h4>` headings.
  - S14: `tests/test_rf_profile_card.py` copies helpers from
    `tests/test_rf_profiles.py`.
  - S16: `_run_rf_profile` is a fifth runner that does not use `pns_lanes`.
  - C25: #53 added history words to `lane_chart.js` ("moved here from …",
    "as it did before …") and kept "(as before)" in `diagram.js`.
- **The new code follows A3 and B5:** `rf_profile_card` and the functions of
  `rf_profiles.py` take keyword-only options, and `cards/rf_profile.py`
  escapes every name.

## 1. Bugs

### B1. Gradient limits with a window: the slew includes a junction before the window

- **Where:** `src/pulseq_reports/grad_limits.py:410-438` and `451-455`
  (`gradient_limits`).
- **What:** the comment says that a window's slew "uses only the junctions
  inside it". The code uses the incoming junction of every processed block,
  and that includes the block that the window start cuts. The junction of that
  block is before the window. The window slew and `slew_block` can then come
  from a step outside the window. A window with no gradient gets
  `reason=None` and a non-zero slew, because `has_event` is set from the
  junction.
- **Checked:** a gradient block (0 to 0.2 ms) that ends at 0.9 of the largest
  step `add_block` accepts, then a 1 ms delay. With `window=(0.5e-3, 1.0e-3)`,
  inside the delay, the result is `reason: None`, Gx slew 135 T/m/s,
  `slew_block` 2, peak 0.
- **Change:** use `processed & (start_s >= lo)` for the junctions, in the
  `np.where` and in the `np.any` guard. The whole-file results do not change
  (`lo = 0`). The gradient limits card has no vb-pulseq parity. Add one
  regression test: a window inside a block with no gradient, after a gradient
  that ends at a non-zero value, gives "no gradient events in the window" and
  slew 0.

### B2. Sequence diagram, min/max view: a bin shows the ADC on when no ADC plays in it

- **Where:** `src/pulseq_reports/assets/seq_lanes.js:960` (`_adcOverlaps`).
- **What:** `gFrom` comes from `from = first - 1`. When `first` is the first
  block of a 64-block group, the prefix count of "the groups strictly between"
  includes the group of `first`. That block holds `e0`, so its ADC window can
  end before the bin starts, and the bin is still marked on. This contradicts
  the comment at lines 937-943 and section 4.4, item 2, of
  `docs/plans/diagram-event-table.md`. The tests do not find it:
  `buildRandomModel` puts an ADC in 20 % of the blocks, so each group has one.
- **Checked:** in Node, 400 blocks of 1 ms, one ADC window in block 64 (64.0 to
  64.5 ms). `minMaxLanes(m, 0.0647, 0.2647, 1)` gives the ADC window
  `[[64.7, 264.7]]`; `exactLanes` over the same range gives `[]`.
- **Change:** `const gFrom = Math.floor(first / GROUP_BLOCKS);`. The first
  `scan(from, (gFrom + 1) * GROUP_BLOCKS - 1)` then covers `first - 1` to the
  end of the group of `first` (at most 65 blocks). The reviewer applied this
  change and all 30 tests of `test_seq_lanes.js` still passed. Add a case with
  a sparse ADC to `test_min_max_lanes_matches_brute_force_for_adc_windows`.

### B3. The |G| lane stops the diagram card for a file with many gradient events

- **Where:** `src/pulseq_reports/assets/g_lanes.js:431-435` (`decode`) and
  `src/pulseq_reports/assets/cards/diagram.js:188-194`.
- **What:** `GLanes.decode` throws when `(M^3 - 1)·D + D - 1 > 2^53`, with `M`
  the number of gradient events plus 1 and `D` the number of distinct block
  durations. With `D = 5`, that is about 1.2 × 10^5 gradient events or more:
  for example a 3D radial sequence that `pp.rotate` makes, with new events for
  each spoke. `GLanes.decode` runs in the chart's `lanesFor`, and the card
  does not catch the error. For the first file, the whole card shows "This
  card could not be drawn". For a later file, the error is in
  `chart.setWindow` (`diagram.js:251`) after `setButtonsDisabled(true)`
  (`diagram.js:228`): the buttons stay disabled and the status stays
  "Loading…". The card drew these files before #44.
- **Checked:** the key check in the code; a reviewer's Node run with 150,000
  events and 5 durations: `SeqLanes.decode` succeeds and `GLanes.decode`
  throws.
- **Change:** a key in two levels (an outer `Map` on `kx*M + ky`, an inner
  `Map` on `kz*D + durIdx`), which moves the limit to about 9.5 × 10^7 events.
  Put the `GLanes` build in `diagram.js` in a `try`/`catch`, so that an error
  removes only the |G| lane. After this fix, memory is the next limit (P6).

### B4. An oversampled arbitrary gradient gives wrong values

- **Where:** `src/pulseq_reports/seq_utils.py:65-67` (`gradient_offsets`).
- **What:** `gradient_offsets` adds a last point at `g.shape_dur`. In the
  pinned pypulseq, `get_block` doubles `shape_dur` for an oversampled
  arbitrary gradient (`time_id == -1`; pypulseq `Sequence/block.py:428`), so
  that point is after the end of the block. This is draft 02
  (`02-oversampled-get-block`) of `github.com/mdtisdall/pypulseq-issues`. No
  test uses `oversampling=True`.
- **Reviewer's measurement** (an oversampled ramp that ends at a non-zero
  value, an extended trapezoid, a trapezoid): `GradientSampler.sample` (the
  spectrum card) differs from `seq.get_gradients()` by 14 % of the peak;
  `gradient_limits` gives a Gx RMS of 7.61 mT/m against 7.33 mT/m from
  `get_gradients`; the diagram tables hold an offset of 0.22 ms in a block of
  0.11 ms. `block_samples` (PNS) is not affected.
- **Change:** until a pypulseq release fixes `get_block`, either refuse an
  oversampled arbitrary gradient in the gradient cards (as
  `extensions.refuse_rotations` refuses rotations), or correct `shape_dur` to
  `(n + 1) * 0.5 * grad_raster_time` for `time_id == -1` (the value that
  `make_arbitrary_grad` sets). Add one test that compares with
  `get_gradients`.

### B5. The spectrum card does not escape `scanner_label` in its note

- **Where:** `src/pulseq_reports/cards/spectrum.py:150` (`_spectrum_html`).
- **What:** the note's f-string puts `scanner_label` in the HTML as it is. The
  table header (through `html_table`) and the `aria-label` (line 132) escape
  it. A label with `<` or `&` breaks the HTML of the note only.
- **Change:** `html.escape(scanner_label)` in the note. The default label does
  not change, so the vb-pulseq parity holds.

### B6. The gradient limits card's note describes the old slew

- **Where:** `src/pulseq_reports/cards/gradient_limits.py:126-128`.
- **What:** the note on the report says "Max slew is the largest rate of change
  between neighbouring points of one gradient event". Since #38 (decision 6 of
  `docs/plans/cards-at-scale.md`), the slew column also has the steps at block
  junctions, divided by `grad_raster_time`. A reader who sees a junction step
  is told that it is a different thing.
- **Change:** add "or the step at a block junction divided by the gradient
  raster time, as pypulseq's `add_block` checks it". Also remove the history
  words "(as before)" and "(new: … did not report it before this module's
  phase 4 rewrite)" from the module docstring of `grad_limits.py` (lines
  19-23).

## 2. The public API

0.2.0 is the first release that consumers pin, so a change that breaks a
caller costs least before it. The example script `examples/gre_report.py`
(from #48) shows several of these points: 13 imports from the library, and
five lines to make the peak-PNS window.

### A1. One name for the gradient `.asc` file, and one hardware for each page

- **Where:** `cards/pns.py` (`pns_card(gradient_asc=…)`, `pns_data`),
  `pns.py` (`pns_prediction(asc_path=…)`, `pns_levels_for(asc_path=…)`),
  `cards/diagram.py` (`diagram_card(pns=True | path)`).
- **What:** three names for the same file. The PNS cache (`pns.py:99-125`)
  keeps one result for each sequence and replaces it when the hardware
  differs. So `pns_card(named, gradient_asc=path)` with
  `diagram_card(..., pns=True)` runs the SAFE model two times (about 100 s at
  10^7 blocks), and the card and the lane show different hardware with no
  warning.
- **Change:** `gradient_asc` in every function; `diagram_card(pns: bool =
  False, gradient_asc=None)`. Optionally keep one cache entry for each
  hardware.

### A2. `pns_card` takes one sequence; every other builder takes a list

- **Where:** `cards/pns.py:82` (`pns_card(seq: NamedSequence, …)`).
- **What:** the parameter is a `NamedSequence` with the name `seq`, and
  `pns_data(seq: pp.Sequence)` in the same file uses `seq` for a pypulseq
  sequence. For several files, `docs/usage.md` section 3 tells the caller to
  make one PNS card for each file, each with its own `card_id`.
- **Change:** `pns_card(seqs, …)`, with one table for each file, as the RF
  exposure card does. If it stays as it is, at least rename the parameter to
  `named` in `docs/usage.md` section 5.

### A3. Keyword-only options

- **What:** every option can be given by position, for example
  `diagram_card(seqs, windows, "diagram", True)`. `rf_exposure(seq, window_s,
  periodic)` and `rf_exposure_data(seq, periodic, window_s)` take the same two
  options in opposite orders.
- **Change:** a `*` after `seqs` (and after `windows` for `diagram_card`) in
  every card builder and data function. Then the names can change later
  without a silent change of meaning.

### A4. Four meanings of "window"

- **What:**
  - `waveforms.TimeWindow`: a time range in one file (`file_index`).
  - `gradient_limits_card(window=(start_s, end_s))`: a tuple applied to every
    file. `gradient_limits` raises `ValueError` when a file does not hold it
    (`grad_limits.py:525-531`). Not documented.
  - `rf_exposure_card(window_s=10.0)`: the length of the B1+rms averaging
    window, not a range.
  - `grad_spectrum.WINDOW_S`: the FFT window.
- **Change:** `gradient_limits_card` takes `TimeWindow` objects, as
  `blocks_card` does. Rename `rf_exposure_card`'s `window_s`, for example to
  `b1rms_window_s`.

### A5. The peak-PNS window takes five lines

- **What:** `docs/usage.md` section 2 and `examples/gre_report.py` both run
  `pns.pns_prediction`, then `pns.peak_tr_window`, then check for `None`, then
  make a `TimeWindow` from the tuple.
- **Change:** `pns.peak_pns_window(seqs, file_index=0, gradient_asc=None) ->
  TimeWindow | None`.

### A6. Imports

- **What:** `pulseq_reports/__init__.py` and `pulseq_reports/cards/__init__.py`
  export nothing, so a page with every card needs eight
  `pulseq_reports.cards.<module>` imports, plus `page`, `seq_utils`,
  `waveforms` and `pns`.
- **Change:** export the eight card builders from `pulseq_reports.cards`, and
  `Card`, `render_page`, `write_page`, `NamedSequence`, `TimeWindow`,
  `first_adc_window` and `full_window` from `pulseq_reports`.

### A7. Hardware defaults that the caller does not see

- **What:**
  - `gradient_limits_card(limits=None)` uses `seq.system`. After
    `Sequence.read`, that is pypulseq's default (40 mT/m, 170 T/m/s), not the
    scanner and not the sequence's design limits. The quick start of the new
    README reads a `.seq` file and calls `gradient_limits_card(seqs)`, so its
    percentages are of these defaults. For a sequence built in the same
    Python process, the default is the sequence's own design limits, which
    is nearly circular. `limits` has no type annotation
    (`cards/gradient_limits.py:74`).
  - `spectrum_card` uses the Prisma AS82 resonances by default, and takes the
    coil's name as a separate `scanner_label`.
  - `docs/usage.md` does not name `grad_limits.HardwareLimits` or
    `grad_spectrum.AcousticResonance`, and no test or caller builds a
    `HardwareLimits`.
- **Change:** annotate `limits: HardwareLimits | None`. Document both types.
  Consider a `GradientCoil(label, resonances)` value, as `HardwareLimits`
  holds its label. Make the README quick start give limits, or say what the
  default is.

### A8. Public names with no documentation

- **What:** `pns_data`, `rf_exposure_data`, `spectrum_data` and
  `timing_errors` have public names but are not in `docs/usage.md`.
  `scripts/vb_parity.py` uses them. The analysis functions
  (`grad_limits.gradient_limits`, `rf_exposure.rf_exposure`,
  `grad_spectrum.gradient_spectrum`, `pns.pns_prediction`) are the API for a
  check in CI, but `docs/usage.md` section 5 lists only the card builders.
  `waveforms.block_row` has a public name and one caller
  (`waveforms.py:141`).
- **Change:** a section "Analysis functions" in `docs/usage.md`, with their
  results. Make the `*_data` functions private or document them as "the
  card's JSON data". Rename `block_row` to `_block_row`.

### A9. A `str` for `extra_css` or `extra_scripts` is split into characters

- **Where:** `src/pulseq_reports/page.py:93-97` and `142-151`.
- **What:** a `str` is a `Sequence[str]`, so `extra_css=".x { color: red; }"`
  gives one CSS text for each character, and `extra_scripts="…"` gives one
  `<script>` element for each character. There is no error.
- **Change:** raise `TypeError` at the start of `render_page` when either is a
  `str`.

### A10. Reserved card script names

- **Where:** `src/pulseq_reports/page.py:137-141`; `docs/usage.md` section 4.
- **What:** `render_page` includes `assets/cards/<name>.js` when that file
  exists. A project card with `script="spectrum"` or `script="diagram"` gets
  the library's script, and its own `registerCard` call then throws "already
  registered" (`lane_chart.js:494`), which only the browser console shows.
  Also, `docs/usage.md` says that `Card.script` "must be unique among the
  cards on one page"; only `Card.id` must be unique, and the section's own
  example has two cards with one script.
- **Change:** list the reserved names (the files in `assets/cards/`) in
  `docs/usage.md`, and correct the sentence on uniqueness.

## 3. Features

- **F1. A command line.** For example `pulseq-report a.seq b.seq -o
  report.html --gradient-asc F --max-grad 28 --max-slew 10`. A person who has
  only `.seq` files has no way in without writing Python.
- **F2. The standard cards in one call.** For example
  `standard_cards(seqs, *, gradient_asc=None, limits=None) -> list[Card]`, so
  that a project can add its own cards to the list. `docs/usage.md` section 2,
  `examples/gre_report.py` and each consumer project repeat the same code.
- **F3. Pass or fail against limits.** A status line (as the timing card has)
  for a PNS peak at 100 % or more, a gradient value over 100 % of its limit,
  and B1+rms over a limit that the caller gives. A limit column in the PNS and
  RF exposure cards.
- **F4. Overlaid traces in one lane.** `laneChart` draws one line or one gate
  in each lane. A chart that compares several traces (for example one line for
  each TR type, with dashes and markers) cannot use it.
- **F5. Number columns in `html_table`.** Right alignment for columns of
  numbers.
- **F6. A light/dark switch.** `report.css` has `data-theme` rules
  (`:root:not([data-theme="light"])` and `:root[data-theme="dark"]`), but no
  code sets `data-theme` and no document names it. Add a switch, document the
  hook for a project script, or remove the rules (see C8).
- **F7. Already in `TODO.md`:** the gyromagnetic ratio of the sequence, the
  rotation extension, and the slew definitions (the vector slew). Not yet in
  `TODO.md`: PNS for the worst orientation (the axis permutations).

## 4. Dead code

| ID | Where | What | Checked |
|---|---|---|---|
| D1 | `markup.py:60-64` | `_blocks_cell` has no caller: copied from vb-pulseq in phase 1 and never used. Delete. | yes |
| D2 | `report.css:8, 17, 26` | `--col-seq-0` to `--col-seq-3`: tokens of vb-pulseq's column card. Delete. | yes |
| D3 | `cards/pns.py:105` | `pns_card` sends `data`, but the card has no script since #42 (`pns.js` was removed), and `page.js` reads data only for a card with a script. Set `data=None`; `tests/test_pns_card.py:125` and its TESTS.md entry change. | yes |
| D4 | `tests/test_diagram_card.py:180-190` | `_ZOOM_HELP_SENTENCE` is not used. #42 removed the assertion `result.count(_ZOOM_HELP_SENTENCE) == 1`, but the test name (`..._and_the_help_sentence_once`) and its TESTS.md entry still say it checks the sentence. Put the assertion back or rename the test. Also remove "Phases 4 … and 5 … are not merged into this branch" from its docstring and TESTS.md. | yes |
| D5 | `scripts/vb_parity.py:349, 359-360` | `notes` is never appended to (the last append was removed in #17), so its loop never prints. Delete. | yes |
| D6 | `scripts/check:22-46` | The guards `if [ -d tests ]` (two) and "skip node: no JavaScript tests" are always false now. If `tests/` were lost, CI would say "skip" and pass. Remove them and the matching text in TESTS.md (lines 138-140, 157-159). Also in `check_tests_md.py`: the `root` parameter (lines 89, 94) is never given, and the example heading at lines 19-20 names vb-pulseq's `test_bandwidths.py`. | yes (guards) |
| D7 | `seq_lanes.js:175-192` | `_blockRange` has never had a caller (since `63030b5`). Delete. | no |
| D8 | `seq_lanes.js:1006-1008` | The outer `inBin` of `minMaxLanes` is shadowed by the one in the `map` callback (1072-1074) and never read. Delete. Also move `const take` (1078) out of the per-bin loop. | no |
| D9 | `seq_lanes.js:882-904` | In `_blockSpan`, `start` is written but never read, so its first `blockStart` call is wasted. See S9. | no |
| D10 | `seq_lanes.js:583, 589` | `gFrom === gTo ? from : from` has two equal branches; `lane \|\| _laneArrays(...)` never uses the second part (the only caller always passes `laneCols`). | no |
| D11 | `pns_lanes.js:763-770` | `_internal.AXES`, `applyBlockMap`, `runBlockSamples`, `eventEntry` and `groupForSample` are exported but no code uses them (only `_plainRecursion` and `sampleRangeFor` are used by tests). Remove the five keys. | no |
| D12 | `pns_lanes.js:184-274` | `_runBlockSamples` and `_plainRecursion` (about 90 lines) are in every report page, but only `tests/js/test_pns_lanes.js` runs them. Move them to the test file (TESTS.md names `_internal._plainRecursion`). | no |
| D13 | `pns_lanes.js:144`, `475` | In `_powPair`, `n === 0 ? …` never applies (the caller returns first for `n === 0`). In `exactView`, `\|\| model.numBlocks === 0` never decides the result. | no |
| D14 | `grad_spectrum.py:105, 112-115` | The `n < nwin` branches and their comment cannot run: after the `NO_GRADIENTS` return, `n = nt + 2*(nwin//2) >= nwin`. Remove them. In the same change, compute the `freq <= MAX_FREQUENCY_HZ + 1e-6` mask one time. | no |
| D15 | `pns_levels.py:157, 178, 182, 198-199, 206` | Empty-input guards that cannot apply after `_has_gradients` (`if cumulative.size`, `if num_samples`, `if axis_frac.size`, `if total.size`, `if chunk_records`). The `chunk_samples` keyword and its `ValueError` exist only for tests; a monkeypatch of `CHUNK_SAMPLES` can replace them, as `test_grad_spectrum.py` does for `CHUNK_WINDOWS`. | no |
| D16 | `sampling.py:226-239, 248-253` | In `block_samples`, `step = t1_mid == t0_mid` is never true (`searchsorted(side="right") - 1` gives `points_t[p+1] > t`), so the `np.errstate` guard and `np.where(step, …)` do nothing. The same branch in `pns_lanes.js:86` (`t1 === t0 ? v1`) is unreachable too; remove both or neither. Also, lines 251-253 compute `event_samples(event_k, 0)` before the `continue`. | no |
| D17 | `rf_exposure.py:94` | `if blocks.size else np.empty(0)`: indexing with an empty array already gives an empty array. | no |
| D18 | `seq_utils.py:15-33` | `BlockTiming` and `iter_blocks` have no caller in the library since #38 and #41; only the tests and the oracles use them. Move them next to the oracles, or say "kept for the test oracles". The docstrings of `waveforms._timed_blocks` and `duration_s` (`waveforms.py:52, 134`) still name `iter_blocks` as their reference. | no |
| D19 | `seq_utils.py:65` | The `False` branch of `hasattr(g, "first") and hasattr(g, "shape_dur")` never runs with pypulseq 1.5 (every `grad` event has both). Remove the guard, or say that it is for an older pypulseq. See B4. | no |
| D20 | `tests/synthetic.py:43-47` | The `crusher_2_cycles` and `prephaser_fraction` parameters of `spin_echo_sequence` are never given. Remove them. | no |
| D21 | `waveforms.py:240-242, 305-309` | The `joined` callback of `_lanes` exists because `file_envelope` also used it; `file_envelope` was removed in #17. Join the parts in `file_lanes`. | no |

## 5. Simplifications

- **S1. The timing card repeats `html_table`.**
  `cards/timing.py:21-76`: `_error_table_html` builds the same HTML as
  `html_table` (checked by the reviewer, with and without `message`), and
  `_timing_html` and `_status_line` differ only in the `"{name}: "` prefix.
  Make one `_timing_html(errors, name=None)` that calls `html_table`. The
  output does not change. `tests/test_timing_card.py:25` calls
  `_timing_html`.
- **S2. The RF exposure card's "All files" path.**
  `cards/rf_exposure.py:110-153` and `174-178` use five private names of
  `rf_exposure.py` and rebuild `_to_dict` key by key. Add a public
  `rf_exposure_files(seqs, window_s, periodic) -> (list[RfExposure],
  RfExposure)` (the combined result with `peak_block=None`); the card then
  calls `_to_dict`. The reviewer compared both on 24 cases: equal after the
  card's rounding. The multi-file path has no vb-pulseq parity.
- **S3. `lane_meta` repeats the lane definitions.**
  `diagram_data.py:231-291` copies the RF, RF phase, ADC and gradient lane
  fields of `waveforms.py:189-237` (`_value_lane`, `_phase_lane`,
  `_adc_lane`). Only one test (spin echo) finds a difference. Let
  `_value_lane` take a peak, and build `lane_meta` from the same functions.
- **S4. `_rounded_peak`.** `diagram_data.py:187-207` rounds every value with
  Python `round` before the maximum. `round(max(abs(v)), d)` gives the same
  result (the reviewer found no difference over 20,000 random arrays, with
  values near a rounding tie). Parity holds (still Python `round`).
- **S5. `diagram.js`'s placeholder lanes.** `cards/diagram.js:163-176` and
  `245-255` build `initialLanes` in two places, with about 16 lines of comment.
  With `lanesFor` and `groups`, `laneChart` never draws `lanes`. Pass
  `lanes: []` with a one-line comment.
- **S6. `rf_exposure._Search.max_energy`.** `rf_exposure.py:211` and `217`
  call `self._before(self.first[pulses] + length)` two times with the same
  argument. Use the result of the first call.
- **S7. The `pns` / `pns_levels` import loop.** `pns.py` imports
  `pns_levels` inside a function (with `TYPE_CHECKING`) because
  `pns_levels.py:28` imports `pns` for `read_gradient_asc`, `hardware_name`
  and three constants. Move these to `pns_levels.py` or a small `asc.py`, and
  keep the names in `pns` for the tests.
- **S8. `grad_limits`, the result with no gradient.** `grad_limits.py:320-322`
  and `535-542` make a separate result when there is no event, but every value
  is already 0 then. One `GradientLimits(...)` with `reason = None if
  has_event else …` is enough.
- **S9. The backward walk in `seq_lanes.js`.** `_blockSpan` (882-904) copies
  the backward walk of `_forEachBlockInRange` (391-404). The clamps
  `Math.min(Math.max(blockAt(...), 0), N - 1)` (391, 522, 529, 885, 894) do
  nothing. Each `blockAt` then `blockStart` pair scans a group two times,
  where `_blockAtStart` gives both. One helper
  `_firstOverlapping(model, lo, hi) -> [i, start]` can serve both. It must
  keep `blockStart(model, i - 1)` for each step back (the block starts are
  forward sums).
- **S10. `pns_lanes.statusText`.** Its `onRaster` argument is "passed
  separately because a caller that skips a hidden PNS group never calls
  `lanesFor`", but `statusText` needs `result` too, and `diagram.js` calls it
  only with a result. Let `lanesFor` return `onRaster` and make
  `statusText(result)`. At the least, correct the comment
  (`pns_lanes.js:731-743`).
- **S11. `g_lanes.js` arguments.** `_rangeGMinMax` and `_exactBlockGRange`
  take 8 positional arguments that are the fields of the model;
  `_tripleGeometry` takes `kx, ky, kz, dur, key` for a cache miss only;
  `decode`'s whole-file peak scans again although the tree's root has it
  (`gTree.max.query(0, gTree.max.n)`). Pass `model`. Optionally rename
  `_quadRangeExtrema`'s `tb` (the tables everywhere else in the file).
- **S12. Helpers copied between the JavaScript modules.** `g_lanes.js:508-524`
  repeats `pns_lanes.js`'s `_zigzag` (603-618); `g_lanes.js:532` (`_fmt`) and
  `pns_lanes.js:727` (`_fmtBinMs`) repeat `ChartMath.fmt`;
  `g_lanes.js:61-111` copies `_segTree`, `_lowerBound` and `_upperBound` of
  `seq_lanes.js`. Put the shared ones in `chart_math.js` or export them from
  `SeqLanes`.
- **S13. `seq_lanes.js` layout.** `decode` uses `GROUP_BLOCKS` (117-121) 50
  lines before its definition (170); move it next to `CHECKPOINT_BLOCKS`.
- **S14. Test helpers copied between test files.** `_load_diagram_scale`
  (`test_seq_index.py:36-43`, `test_grad_spectrum.py:199-206`, and
  `cards_scale.py`) and `_border_sequence` (`test_pns_levels.py:33-52`,
  `test_pns_lanes_golden.py:75-96`). Move them to `tests/synthetic.py`.
- **S15. The PNS golden test copies `_pns_entry`.**
  `tests/test_pns_lanes_golden.py:184-200` rebuilds `cards/diagram.py`'s
  `_pns_entry` field by field (with `gradScale`). If the card changes, the
  golden test keeps its own copy. Take the payload from `_pns_entry` or from
  `diagram_card(..., pns=True).data`.
- **S16. `cards_scale.py` arguments.** `scripts/cards_scale.py:170-204,
  284-290`: four runners take `pns_lanes` and do not use it; `CARD_NAMES`
  repeats the keys of `CARD_RUNNERS`; the `_run_all` docstring does not list
  `--pns-lanes`, and `--card all --pns-lanes` runs again the four cards that
  it does not change. Use `CARD_NAMES = tuple(CARD_RUNNERS)` and give
  `pns_lanes` to the diagram runner only.
- **S17. `vb_parity.compare_text`.** `scripts/vb_parity.py:141-144` shows the
  context with `vb[i - 40 : i + 80]`; for `i < 40` the slice starts from the
  end of the string. Use `max(i - 40, 0)`. The `compare` docstring (115-116)
  reads as if extra keys were accepted; the code requires the same keys in
  the same order.
- **S18. `rf_exposure.py:147, 152`.** `copies = 1 if period is None else 2`
  but `shift` tests `if period`. Test `period is not None` in both places.

## 6. Time and memory at scale

The cards work up to 10^7 blocks (`docs/usage.md`, section 3). These
functions still walk every block in Python, or keep memory for each distinct
event. The times are the reviewers' measurements or estimates from them.

- **P1. `first_adc_window`** (`waveforms.py:312-324`) calls `get_block` with
  the block cache on and computes all the events of each block before the
  first ADC. For a file with no ADC, that is every block: 0.91 s and 20,000
  cached blocks for 20,000 blocks, so about 450 s and several GB at 10^7.
  Use `sequence_index(seq)` (`adc_first`, `start_s`) and read the one ADC.
  The reviewer found the same `end_s` for all four synthetic builders.
- **P2. `duration_s`** (`waveforms.py:133-138`) sums every block in Python;
  `sequence_index(seq).end_s` is the same value, bit for bit
  (`tests/test_seq_index.py:209`). `cards/diagram.py:104` calls it after
  `diagram_tables` has built the index; `full_window` and `first_adc_window`
  call it again.
- **P3. `peak_tr_window`** (`pns.py:157`) calls `seq.duration()[0]`, a Python
  loop in pypulseq: 0.108 s at 10^5 blocks, so about 11 s at 10^7. Use
  `sequence_index(seq).end_s` (the reviewer found it bit-identical).
- **P4. `block_rows`** (`waveforms.py:162-167`) has no early exit after the
  range: about 3.5 s for each window at 10^7 blocks. Add
  `if end_s is not None and t > end_s: break` (the output does not change).
- **P5. `seq_lanes._blockPoints`** (`seq_lanes.js:200-203`) makes an array
  `["gx", "gy", "gz"]` for each call, and `_buildGroups` calls it for each
  block: about 40 % of `decode`. The reviewer measured 336 ms before and
  206 ms after unrolling it, for 2 × 10^6 blocks.
- **P6. Files with many distinct events.** `pns_lanes.js` keeps the full
  sample array `g` of each distinct (event, axis, length) (lines 118-134,
  166-169, 350-366), but the block map uses only `g[0]`, `g[n-1]` and `h`:
  228 MB for 2 × 10^5 events of 100 samples. Keep `{g0, gLast, h}` and build
  `g` in `exactView`. `g_lanes.js` keeps about 1.6 KB for each distinct
  triple. The 10^7-block measurements used repeating files, with few distinct
  events; a file with many (B3) was not measured.

## 7. Documentation and comments

### User documentation

- **C1. The Lane JSON format** (`docs/usage.md`, "Lane JSON format"; the
  `Lane` docstring, `markup.py:24-26`). `markup.Lane` is now public, with a
  reference to this section, and the section is wrong in five places:
  - `color` is the token name without `--` (`"gx"` for `var(--gx)`;
    `lane_chart.js:167`). With `"--gx"`, the lane has no color and there is
    no error.
  - `fill` is not a fill: it is the tooltip value where no segment covers the
    cursor (`chart_math.js:36`, `lane_chart.js:236`), and `null` shows "—".
  - `empty` adds a "no events" label; the segments are still drawn
    (`lane_chart.js:168-186`).
  - The `minmax: true` key (the tooltip shows "min – max") is missing.
  - The points of a segment must be in increasing x (binary search).

  The `Lane` docstring names "an RF pulse profile … or a PNS trace"; no code
  builds either with `Lane`. Say "a waveform or a spectrum trace".
- **C2. `laneChart` with `lanesFor`** (`lane_chart.js:32-37`;
  `docs/usage.md`, the options table). "`lanes` is then only the initial
  lanes, shown by the first render" is wrong since `1204e8b`: `render` calls
  `lanesFor` for every render. `lanes` only sets the SVG height before the
  first render (nothing with `groups`), and `setLanes` has no effect.
  `PulseqReport.el(name, attrs, parent)` and `text(attrs, content, parent)`
  have no documented signatures.
- **C3. "A hidden group costs no computation"** (`docs/usage.md:221-223`).
  True only for |G| and PNS: `diagram.js:186` calls `SeqLanes.lanesFor` for
  the six RF, ADC and gradient lanes on every render, and `pointsIn` counts
  the points of hidden lanes. Say that hiding Gradients skips |G| and hiding
  PNS skips PNS. Also, "6.15 ms" and "about 3.4 hours" (lines 201, 204) hold
  for the 10 µs raster only.
- **C4. "Share one PNS computation"** (`docs/usage.md:124-126`,
  `pns.py:99-108`): only with the same hardware (A1).
- **C5. The card arguments** (`docs/usage.md:439-442`). `limits`,
  `resonances`, `window` and `periodic` are not explained (A4, A7).
- **C6. `file_lanes` in the custom card example** (`docs/usage.md:264-268`).
  The example calls `file_lanes(named.seq)` on the whole file, which reads
  every block with the cache on; `lane_meta`'s docstring
  (`diagram_data.py:214`) says that this costs too much memory at 10^7
  blocks. Say that `file_lanes` is for short files or a time range.
- **C7. The release candidate sentence** (`docs/usage.md:28-31`). "The
  release candidate `v0.2.0rc1` has everything in it" stops being true when
  `feature/public-card-helpers` merges (`html_table`, `fmt`, `zoom_controls`
  and `extra_css` are not in `v0.2.0rc1`). The version change to `0.2.0rc2`
  fixes it.
- **C8. CSS.** No `h3` rule: the RF exposure (`cards/rf_exposure.py:180,
  184`) and blocks (`cards/blocks.py:61, 67`) cards put `<h3>` headings, which
  get the browser default (about 16.4 px, larger than the 15 px card title).
  The only `h3` rule was `#pulse-profiles h3`, of vb-pulseq's own card, so no
  library heading ever had a style. Add `h3 { font-size: 13px; font-weight:
  600; margin: 12px 0 6px; color: var(--ink-2); }`. For `data-theme`, see F6.
- **C9. The uv claim.** `docs/usage.md` section 1, `TODO.md:26-27` and
  `pyproject.toml:29-32` say that a consumer gets pypulseq from PyPI unless it
  adds the source line. For pip that is true; uv applies the
  `[tool.uv.sources]` of a git dependency (found by the ex-vivo-gre-pulseq
  review with a scratch project). Correct all three.
- **C10. `TODO.md`.** Lines 130-131 ("The card gets the junction steps in
  phase 4") are done (#38). The "When" conditions of the gyromagnetic ratio
  item (lines 113-115) are met (#38, #42).
- **C11. `scripts/vb_parity.py` run command** (lines 8-9). With only
  `--with-editable <vb-pulseq>`, uv installs pypulseq from PyPI over the fork
  pin (`docs/plans/diagram-lanes.md:840-842`), so a parity run as documented
  compares stock pypulseq. Add `--with-editable <fork checkout>`. On a
  `git archive` extract, `vb_version()` cannot check `VB_COMMIT`; say so.
- **C12. TESTS.md.** "Only the pure functions in `chart_math.js` are tested"
  (line 164): `seq_lanes.js`, `pns_lanes.js` and `g_lanes.js` have node tests
  too. The contents list (lines 32-33) does not name the index, the sampler,
  the PNS levels or the lane modules.

### Code comments

- **C13. The diagram `aria-label`** (`cards/diagram.py:196-197`): "RF
  magnitude and phase, ADC, Gx, Gy and Gz against time" leaves out |G| (always
  drawn) and PNS (when `has_pns`). No test pins the string. The comment at
  lines 174-178 repeats the docstring and is far from the code it explains.
- **C14. `grad_limits.py` docstrings.** "Every numeric field is its zero
  value" (75-80) is false for `whole_rms_mt_per_m`; "(at most two, plus a
  block of zero duration at an edge)" and "makes every block fully inside"
  (298-302) do not happen (`skip` drops a zero-duration block at an edge). The
  tie rule "smallest play index … single pass" is false when a window cuts
  the first block (the reviewer found a case where the oracle gives block 1
  and the code block 2). `AxisResult.peak_block`, `slew_block`, `peak_time_s`
  and `GradientLimits.vector_peak_time_s` are read by no card: show them on
  the card (as the RF card shows the block) or say that they are only
  diagnostic.
- **C15. `pns_levels.py`.** "as the other gradient cards do" (117-118):
  `pns_levels` is not a card, and the other analysis functions leave
  `refuse_rotations` to their cards. `DISPLAY_BINS = 812` (36-37) does not
  say that it is `PLOT_W` of `lane_chart.js` (960 - 128 - 20), and no test
  ties `EXACT_MAX_S` to `PnsLanes.EXACT_MAX_S`.
- **C16. `grad_spectrum.py:98`.** `nt = ceil(sum(seq.block_durations.values())
  / dt)` differs from `index.end_s` (Python's `sum` is compensated; the
  reviewer found one sample of difference at 10^5 blocks). The oracle has the
  same line, for vb-pulseq parity. Add a comment so that nobody changes it to
  `index.end_s`.
- **C17. `sampling.py:146-149`.** The `block_samples` docstring says that it
  differs from `sample` only for a step at a junction, "which pypulseq's
  `add_block` does not accept". `add_block` accepts a step up to
  `max_slew * grad_raster_time`, and the two methods also differ by the drift
  of the block start sums (`tests/test_sampling.py:80-86, 236-242`). The same
  words are in `docs/plans/diagram-lanes.md` section 4.1, item 3.
- **C18. `waveforms.py:38`.** The `_BlockEvents` docstring says "as arrays in
  ms and display units"; every field is in seconds.
- **C19. `diagram_data.py` and `seq_index.py`.** "As the per-block dict of the
  former loop matched them" (`diagram_data.py:72-75`) refers to code that #29
  removed. `seq_index.py:5-6` ("as `diagram_data.diagram_tables` numbers
  them") is circular since #29. `diagram_data.py:132, 136` recompute a dtype
  that the index already has; they are copies, so use `.copy()`.
- **C20. `chart_math.js`.** Line 1 says "loaded before report.js" (now
  `lane_chart.js`). `fmt`, `niceTicks` and `valueAt` have no comment
  (`valueAt` is where `fill` gets its meaning). In `minMaxAt`, "`2 * centre -
  start`, which is exact" is not true (it differs by one ulp in 61 % of bins);
  say "equal up to rounding".
- **C21. `diagram.js:57-58`.** "The six diagram tables never use it": there
  are 27 tables (six is the number of lanes), and "(plan section 4.4)" does
  not say which plan.
- **C22. `pns_lanes.js`.**
  - The `onRaster` comment (line 335) says an off-raster file gives
    "gap = true"; `gap` never depends on `onRaster` (line 663).
  - References that a reader cannot follow: `prototypes/pns_lanes/…` without
    the tag `archive/pns-lanes-prototype` (lines 9, 19-20; #47 fixed only
    `g_lanes.js`); "README 'Per-event data …'" (50) is not a heading of that
    README; "interface doc" and "interface note" (62, 454, 621); "plan section
    3.5, item 1" (226) and "section 4.3, item 3" (466) point at other items.
    Put the block-map formula `s_n = c^n·s + c^(n-1)·α·u0 + h[n-1]` in
    `_applyBlockMap`'s comment.
  - The same missing tag in `tests/js/test_pns_lanes.js:12, 16, 323`.
- **C23. `g_lanes.js`.**
  - `_axisValueAt` (158-167, 26-28) says "0 outside the event … even when it
    does not [end at 0]", but pieces are linear between breakpoints, so after
    an event's last point the value ramps to 0 at the next breakpoint. This
    differs from `pns_lanes.js` only for files that pypulseq does not write;
    say so, as `pns_lanes.js` (27-33) does.
  - `laneMeta` (536-547): the one-sided domain is the style of the RF |B1|
    lane, not of the gx/gy/gz lanes (they are symmetric); `empty` is
    `peak === 0`, not "no gradient event".
  - Line 15 points to "the module doc of `_tripleGeometry`" for text that is
    at lines 19-24; lines 30-33 say that `minMax` and `lanesFor` build the
    tree (only `decode` does); the `GROUP_BLOCKS` comment (41-51) says a bin
    "touches a couple of hundred groups" (at most 2 partial groups and
    O(log G) tree nodes), and the `typeof require` / `typeof module`
    reasoning describes no real difference.
- **C24. `seq_lanes.js:85-89`.** The `decode` comment lists "point count" as
  computed (it is the `*_n` table) and does not list `groupStart`, `groups` or
  `pyramids`.
- **C25. History in comments.** Comments that make sense only next to an old
  diff: "as before", "exactly as it did before `groups` existed", "Unlike the
  old card…" (`lane_chart.js:37, 49-50, 64-66, 124-126, 227`;
  `cards/diagram.js:3-4, 43, 87`; `grad_limits.py:19-23`). Keep the statement
  of what the code does now.
- **C26. References to files that are not in the repository.** 22 lines
  name a scratchpad file, "the worker spec", or "the executing agent", for
  example `tests/test_rf_exposure.py:186-187` ("S/compare.py's
  `random_seq`"), `tests/js/test_seq_lanes.js:84-85, 602, 780`
  (`validate_minmax.js`), `tests/js/test_pns_lanes.js:259, 541, 735, 829, 884`,
  `tests/js/test_g_lanes.js:612`, `tests/test_diagram_card.py:316`,
  `src/pulseq_reports/assets/g_lanes.js:248`, and TESTS.md lines 3751-3754,
  3786-3788, 5184, 5210, 5225, 5343, 5433. Replace each with the plan section
  that gave the rule, or delete it.
- **C27. Other stale test comments.**
  - `tests/js/test_g_lanes.js:39-45` names `TEMPLATE_DUR`, which never
    existed (see `durationOptions`).
  - `tests/test_rf_exposure_card.py:241-243` says "within the tolerance
    above"; the helper compares with `==` (TESTS.md says "exactly"). Line 130
    points at a docstring that does not say what it claims.
  - `scripts/diagram_scale.py:26-28` says "on stdout"; the code writes to
    stderr.
  - `tests/js/test_seq_lanes.js:351`: `buildPointBudgetModel` is named after
    the removed point budget; `tests/test_diagram_data.py:4` names "a later
    phase" that is now `test_seq_lanes_golden.py`.

## 8. Model details with a low reach

These give a value that differs from the stated rule, but only for input that
pypulseq does not make. Say so in the comments, or align the code:

- **L1. `seq_lanes._edgeValue`** (`seq_lanes.js:836-837`, comments 787-790
  and 858-862): when a bin edge is bit-exactly on a block start and the block
  before has a point exactly at its end with a different value, that point is
  not used, against the tie rule of the comment. The reviewer made a case
  with a gradient that is not continuous across the junction; pypulseq keeps
  gradients continuous across blocks and an RF pulse cannot end at its block
  end.
- **L2. `g_lanes.js`, a block of zero duration** (287-292): it gets
  `blockMin = blockMax = 0`, which pulls a bin's minimum to 0; the test's
  brute force gives "no value" for it. Not visible for a file that pypulseq
  writes.
- **L3. `grad_limits`, the tie rule** (see C14): on an equal value, the edge
  loop can credit the later block. Keep the smaller play index.

## 9. Looked at and judged fine

- The private names `_points`, `_sig` and `_AXIS_COLOR` of `markup.py` are
  used by the library.
- `_substitute` replaces in one pass, which is needed because script and CSS
  text can hold `__X__`. `_json_script` escapes `</`; `allow_nan=False` is
  deliberate.
- With no `extra_css`, the `<style>` text is the same as before
  `feature/public-card-helpers`.
- No block start in the JavaScript is computed by subtracting a duration from
  a later start.
- `visiblePoints` decimates above 4 × 1624 points per segment and keeps each
  bucket's first, last, minimum and maximum, so no peak is lost.
- `_blockAtStart`'s last fallback can apply for `t = NaN`, so it stays.
- The PNS block map and the SAFE output agree with pypulseq and with the
  prototype's formulas; the pyramid lookup covers every stored bin of a
  display bin.
- `pns_levels.py` imports the fork's private `_safe_gwf_to_pns_chunk`: a
  documented decision (`TODO.md`).
- The 64-step fix-up loops of `rf_exposure._Search` are needed for exact float
  comparisons.
- `combo = (gx*base + gy)*base + gz` (`grad_limits.py:390`) can overflow above
  about 2.1 × 10^6 unique gradient events; a collision is very unlikely and has
  no effect on the result.
- `diagram_scale.py --timing-probe` and `cards_scale.py --tr-s` /
  `--pns-lanes` gave documented measurements, so they are not dead.
- `tests/oracles/` has no `__init__.py` on purpose; the oracles import live
  `seq_utils` helpers, which have their own tests.
- No two tests are exact copies (Python test bodies compared by AST, and
  JavaScript test bodies with whitespace removed).

## 10. Suggested order

1. Before `feature/public-card-helpers` merges: the findings about the API
   that it makes public (D1, D2, A9, A10, C1, C2).
2. The bugs B1 to B6, one branch each, each with a regression test.
3. The API decisions A1 to A8, before the `0.2.0rc2` version change.
4. The rest (D, S, P, C, L) and the features (F), after 0.2.0, in plans or
   `TODO.md` items.
