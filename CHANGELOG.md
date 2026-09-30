# Changelog

The changes since `v0.2.0rc1`. The public API is the names in
[docs/usage.md](docs/usage.md). The number of a pull request is in brackets.

## 0.2.0rc2 (2026-09-30)

### Breaking changes

Each item says what a caller of `v0.2.0rc1` changes.

- **One sequence per card, and one report for each file** (#88). A report is
  for one `.seq` file. A caller with several files (for example the segment
  files of one acquisition) makes one report for each file.
  - Every card builder takes one `pp.Sequence` in place of a list of
    `NamedSequence`: `timing_card(seq)`. `seq_utils.NamedSequence` is removed.
  - `waveforms.TimeWindow(label, start_s, end_s)` has no `file_index`.
    `first_adc_window(seq)` and `full_window(seq)` take the sequence, and no
    file index.
  - `grad_spectrum.combine` is removed, and the spectrum card has no maximum
    over files. The RF exposure card has no "All files" table.
  - The gradient limits note for a file with no gradient is "reason.", with no
    file name in front of it.
  - The data of the diagram card is `{"format": 2, "file": {...}, "windows":
    [{"label", "view_ms"}]}`. It was `{"format": 1, "files": [...], ...}`.
  - `laneChart` has no `setWindow`. `setView` and `setLanes` stay.
- **The options of the card builders are keyword-only** (#88, #89, #90). The
  signatures are:
  - `timing_card(seq, *, card_id)`, `definitions_card(seq, *, card_id)`
  - `rf_exposure_card(seq, *, periodic, b1rms_window_s, card_id)`
  - `spectrum_card(seq, *, coil, card_id)`
  - `pns_card(seq, *, gradient_asc, card_id)`
  - `gradient_limits_card(seq, *, windows, limits, check_norms, card_id)`
  - `diagram_card(seq, windows, *, pns_lane, gradient_asc, card_id)`
  - `blocks_card(seq, *, windows, max_rows, card_id)`

  Other functions with keyword-only options: `waveforms.block_rows(seq, *,
  start_s, end_s, max_rows)`, `waveforms.file_lanes(seq, *, start_s, end_s)`,
  `diagram_data.lane_meta(seq, *, tables)`, `grad_limits.gradient_limits(seq, *,
  window, limits)`, `rf_exposure.rf_exposure(seq, *, periodic,
  b1rms_window_s)`, `grad_spectrum.gradient_spectrum(seq, *, resonances)`, and
  `page.render_page` and `page.write_page` (`extra_scripts` is keyword-only).
- **The gradient `.asc` file has one name, `gradient_asc`** (#89). `asc_path` of
  `pns.pns_levels_for`, `pns.pns_prediction` and `pns_levels.pns_levels` is
  `gradient_asc`. It is keyword-only, as in `pns_card`.
  - `diagram_card(seq, windows, *, pns_lane=False, gradient_asc=None)` replaces
    `pns=False | True | path`. A `gradient_asc` without `pns_lane=True` raises
    `ValueError`, and a `pns_lane` that is not a `bool` raises `TypeError`.
  - `read_gradient_asc`, `hardware_name`, `EXAMPLE_HARDWARE` and `INCLUDE_LINE`
    move from `pns` to the new module `asc`. `NO_GRADIENTS` and
    `PEAK_TOLERANCE` move from `pns` to `pns_levels`. `pns` keeps no copy.
  - The recipe of five lines for a "Peak-PNS TR" window is no longer needed:
    the PNS card has a button (see "Added"). `pns.peak_tr_window` stays.
- **The gradient limits card takes `TimeWindow` objects** (#90).
  `windows=[TimeWindow(...), ...]` replaces `window=(start_s, end_s)`. With
  windows, the card has one table for each window. The function
  `gradient_limits(seq, *, window=(start_s, end_s))` keeps the tuple.
- **The B1+rms averaging window is `b1rms_window_s`** (#90). `window_s` of
  `rf_exposure_card` and `rf_exposure` is `b1rms_window_s`. `rf_exposure.WINDOW_S`
  is `rf_exposure.B1RMS_WINDOW_S`, and `grad_spectrum.WINDOW_S` is
  `grad_spectrum.FFT_WINDOW_S`. The fields `window_s` and `window_used_s` of
  `RfExposure` are `b1rms_window_s` and `b1rms_window_used_s`.
- **The spectrum card takes a coil** (#90). `spectrum_card(seq, *, coil=PRISMA_AS82)`
  replaces `resonances` and `scanner_label`.
  `GradientCoil(label, resonances)` holds the two.
- **Functions of the cards are private** (#90). `cards.rf_exposure.rf_exposure_data`,
  `cards.timing.timing_errors`, `cards.pns.pns_data` and `waveforms.block_row`
  have a leading underscore. `cards.spectrum.spectrum_data` is removed. Call the
  analysis functions of `docs/usage.md`, section 6, or the card builders.
- **Card scripts are texts on the card** (#91). `render_page` no longer looks up
  `assets/cards/<Card.script>.js` by the name in `Card.script`. A card gives its
  script text in `Card.scripts` (and its CSS in `Card.css`). `Card.script` is
  still the name that the script registers. The library's builders set
  `script` and `scripts`.
  A hand-made `Card(script="diagram")` gets no library script.
- **Removed or changed in the modules** (#78, #79, #80):
  - `seq_utils.BlockTiming` and `seq_utils.iter_blocks` are removed. They are in
    `tests/oracles/blocks.py`.
  - `pns_levels.pns_levels` has no `chunk_samples` keyword.
  - `seq_utils.gradient_offsets` needs `first`, `last` and `shape_dur` on a
    gradient that is not a trapezoid. Every gradient that pypulseq 1.5.0.post1
    makes has them.
  - `PnsLanes.statusText(result, onRaster)` is `statusText(result)`.
- **`report.css`** has no `--col-seq-*` tokens and no rules for vb-pulseq's own
  cards (#65).
- **`AxisResult` has `slew_time_s`** between `max_slew_t_per_m_per_s` and
  `slew_block` (#99). A caller that makes an `AxisResult` by position adds it.

### Added

- **The command line `pulseq-report`** (#92). `pulseq-report FILE.seq
  [FILE.seq ...] [-o OUT]` writes one report page for each file.
  - The flags come from the options of the installed cards (`--help` lists
    them). `--max-grad` and `--max-slew` give the gradient limits, `--coil` the
    gradient coil, and `--gradient-asc` the gradient `.asc` file.
  - `--cards` and `--skip` select the cards. `--card-module MODULE:ATTRIBUTE`
    adds a card that is not installed as a plugin.
  - `--config FILE` reads the values of the options from a `.toml` or a `.json`
    file. A flag overrides the file.
  - Without limits, a warning on stderr names the limits that the gradient check
    used.
  - The exit status is 0 when each page is written and each check passed, 2 when
    a check failed, and 1 for an error.
- **Card plugins, and `build_cards`** (#91). A card is a `CardSpec` (in
  `pulseq_reports.registry`, with `Option` and `ReportContext`) that a package
  lists in the entry-point group `pulseq_reports.cards`. The library's own nine
  cards are found in the same way. `build_cards(seq, *, cards=None, skip=(),
  **options)` builds the cards of a report for one sequence. A card that raises
  becomes an error card, and the other cards are built. The shared options are
  in `pulseq_reports.options`. The interface is provisional: it can change in
  0.3.0.
- **Checks** (#91). `page.Check(name, passed, message)` and the `Card` fields
  `checks`, `scripts`, `css`, `publishes` and `subscribes`. The timing card, the
  gradient limits card and the PNS card have a check each.
  `gradient_limits_card(..., check_norms=True)` also fails the check when the
  peak of |G| is above the amplitude limit. `render_page` raises `ValueError` for
  two cards that publish one state topic, or subscribe to one request topic
  (`page.TOPIC_KINDS`).
- **Exports.** `pulseq_reports` exports `build_cards`,
  `Card`, `Check`, `render_page`, `write_page`, `TimeWindow`, `first_adc_window`,
  `full_window`, `HardwareLimits`, `GradientCoil` and `PRISMA_AS82`.
  `pulseq_reports.cards` exports the nine card builders.
- **The PNS card has a button** (#89) that shows the peak in the diagram: the TR
  that holds it, or the block that holds it when the sequence has no `TR`
  definition. It replaces the "Peak-PNS TR" window. The button is shown only
  while a card acts on `goto` (the diagram).
- **Where the gradient limits happen** (#99). The peak and max slew cells of the
  gradient limits card give the block ID and the time where each value is reached,
  and a "Show" button that shows that block in the diagram (it sends `goto`, and is
  shown only while a card acts on it). `AxisResult.slew_time_s` and
  `GradientLimits.vector_peak_block` are new.
- **Gradient coils** (#90). `grad_spectrum.GradientCoil`, `PRISMA_AS82` and `COILS`
  (`{"prisma-as82": PRISMA_AS82}`).
- **Limits in the note** (#90). The note of the gradient limits card gives the
  limits, with their label and their values. `gradient_limits_card` and
  `gradient_limits` take `limits: HardwareLimits | None`.
- **The PNS cache has one result for each sequence and hardware** (#89). A page
  with two PNS cards for two `.asc` files, or a PNS card and a PNS lane for
  different files, runs the SAFE model once for each file.
- **Windows are checked** (#88, #90). `diagram_card`, `blocks_card` and
  `gradient_limits_card` raise `ValueError`, with the window's label, for a
  window that is outside the sequence or that does not end after its start.
- **Messages between cards** (#53). `PulseqReport.publish`, `subscribe` and
  `createMessageBus`, and the diagram's topics `sequence`, `cursor`, `anchor`,
  `view` and `goto`. `SeqLanes.sequenceView` and `SeqLanes.GRAD_HZ_PER_VALUE`.
  - `PulseqReport.watchSubscribers` and `PulseqReport.requestButton` (#88).
  - `goto` has a block form and a range form (`{source, t0S, t1S, anchorS}`)
    (#89).
  - `laneChart` takes `onCursor` and `onAnchor`.
- **The RF pulse profiles** (#57 to #62). `rf_profile_card`, the modules
  `rf_profiles`, `rf_sim` and `profile_metrics`, `RfProfiles` in JavaScript, and
  the card script `assets/cards/rf-profile.js`. The card follows the diagram
  through its messages.
- **Chart helpers** (#54, #83). `PulseqReport.mapChart`, and `ChartMath.colorRamp`,
  `colorIndex`, `nearestIndex`, `sig3`, `segTree` and `minMaxSegments`.
- **Helpers for project cards** (#65). `markup.fmt`, `html_table`, `zoom_controls`
  and `lanes_json` are public. `render_page` and `write_page` take `extra_css`,
  and raise `TypeError` for a `str` in `extra_scripts` or `extra_css`.

### Fixed

- Gradient limits for a window use only the junctions inside the window (B1,
  #69).
- The minimum and maximum view of the diagram shows the ADC only where it plays
  (B2, #70).
- The |G| lane of a file with many gradient events no longer stops the diagram
  card; a failure removes only that lane (B3, #71).
- An oversampled arbitrary gradient gives right values, with the pypulseq pin
  (B4, #67, #72).
- The spectrum card escapes the label of the scanner in its note (B5, #73).
- The note of the gradient limits card describes the junction step of the slew
  (B6, #74).
- `waveforms.duration_s` returns a Python `float` (P2, #79).
- `pns.peak_tr_window` returns `None` for a sequence with no block. Before, it
  raised `StopIteration` (P3, #79).
- The `aria-label` of the diagram names every lane (C13, #78).
- The `h3` and `h4` headings inside the cards have a style, smaller than the card
  title; they had the browser's default size (C8, #95).
- On an exact tie, `gradient_limits` credits the first block in play order, and
  the first time in it, for each peak, slew and the |G| peak; a value of 0 has no
  block (L3, #98).
