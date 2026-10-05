# Plan: pulseq-reports on pulseq-checks and pulseq-analysis

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: approved, written on 2026-10-04. The user decided D1 to D11 of
section 2.4 on the same day. Phase 1 can start when this plan is merged.

Amendment 1, 2026-10-04: phases 1 to 4 are done (#111, #112, #113, #110).
`pulseq-checks` and `pulseq-analysis` released `v0.1.0rc4`, and the design
is now version 4 (section 3.4 of the design, decisions P29 to P32). This
amendment adds phase 2b (the pins), rewrites phase 6 (the spectrum card),
corrects the series names of phase 7, and adds the facts 14 to 18 and the
decisions D12 to D15. Section 8.1 records it.

Amendment 2, 2026-10-04: `pulseq-analysis` and `pulseq-checks` released
`v0.1.0rc5`, and the design is now version 5 (section 3.5 of the design,
principles 8 and 11, decisions P33 to P39). This amendment moves the pins to
`v0.1.0rc5` and replaces the proton rule P21 with the gamma of each target.
It redefines phase 2b, adds the phases 2c and 7b, changes the phases 5 to 8
and 11, and adds the facts 19 to 24 and the decisions D16 to D19. Section
8.1 records it.

This is the implementation plan of `docs/plans/pulseq-checks.md`, version 5
(the design). The design gives the concepts, the principles and the
decisions P1 to P39. This plan gives the phases, the tasks, the files, the
workers and the order. Where this plan and the design do not agree, the
design is correct: stop and ask the user.

## 1. Goal

Do steps 1 to 6 of section 7 of the design, and release `0.2.0rc3`:

1. Remove the verdicts and the hidden defaults (design step 1, P25).
2. Depend on `pulseq-checks` `v0.1.0rc3` and `pulseq-analysis` `v0.1.0rc2`,
   and delete the eight copied modules (design step 2). Then move both pins
   to `v0.1.0rc5` (phase 2b, decision P34), and use the gamma of each target
   in every card (phase 2c, decision P35).
3. Add the targets, the target colors and the result matrix to the report
   (design step 3).
4. Change each card that needs scanner context to read the targets, and the
   PNS card and lane to read the analysis results (design step 4).
5. Add the check summary card, and the findings in the cards (design step 5).
6. The documents, the example report and the release (design step 6).

Not in this plan: changes to `pulseq-checks` or `pulseq-analysis`, and the
"later" items of section 6 of the design.

## 2. Read this first (context for the executing agent)

### 2.1 The state of the repositories (2026-10-04)

- **pulseq-reports** (`main` at `a435eb7`, version `0.2.0rc2`). The code is
  the same as at `4fa7e6d`: the commits after it change only documents.
  The design is `docs/plans/pulseq-checks.md`, version 3.
- **pulseq-checks** (`v0.1.0rc3`, commit `4ec751b`). It depends on
  `pulseq-analysis` `v0.1.0rc2` by a direct git reference.
- **pulseq-analysis** (`v0.1.0rc2`, commit `9f65863`).
- **pypulseq.** All three repositories pin the fork commit `a74ab06` in
  `[tool.uv.sources]`.
- **Data.** The real ex-vivo file is `data/exvivo_gre_seg_0.seq` in the main
  checkout (git-ignored). Never commit it. Real `.asc` files are
  confidential. Tests write synthetic `.asc` files (`write_gradient_asc` in
  `tests/conftest.py`).

### 2.2 Decisions that are already made

The decisions of the design (sections 9.1 to 9.5) apply. Do not open them
again. The decisions that this plan uses most:

| # | Decision |
|---|---|
| P1 | One release, `0.2.0rc3`, does all of this work. |
| P14 | A page with an error card gives exit status 1. |
| P15 | The old import paths of the moved modules go away. |
| P18 | At most 100 findings for each result, `--max-findings N`. |
| P21 | Replaced by P35 (amendment 2). |
| P22 | The PNS lane marks the runs of `pns_above_1` (amendment 2: `pns_above_0`, P34). |
| P23 | No result matrix: no PNS, with a note. |
| P24 | The promise of each check in a closed element. |
| P25 | The verdicts and the defaults go first. |
| P26 | `build_cards` takes `check_results=` and never runs checks. |
| P27 | The example report has two example targets. |
| P28 | At most 6 targets. |
| P29 | Replaced by P34 (amendment 2). |
| P30 | The spectrum card: the bands and the `acoustic.resonance-energy` line of each target. No band peaks. |
| P31 | The spectrum comes only from the analysis result `gradient.spectrum`. |
| P32 | Changed by P37 (amendment 2). |
| P33 | A negative gamma is valid: \|γ\| for a magnitude, γ for a signed value. |
| P34 | The pins are `v0.1.0rc5`. |
| P35 | Each card uses the gamma of each target. Without targets: `seq.system.gamma`. A gamma that is 0 or not finite is an error. |
| P36 | Sequence-only cards: a control selects the target when the gammas differ. |
| P37 | The spectrum: one line for each group with the same \|γ\| and spectrum. |
| P38 | The PNS percent is `100 * v / meta["threshold"]`. |
| P39 | A result file with a PNS series not in `"Hz/T"` is an error of the run. |

### 2.3 Facts that this plan uses (verified on 2026-10-04)

Paths are in `src/pulseq_reports/` unless a path says otherwise. Line
numbers are at `a435eb7`.

Facts 1 to 13 give the state at `a435eb7`, before phase 1. Phases 1 to 4
changed some of them: for example the signatures of fact 5, the options of
fact 4 and the modes of `scripts/cards_scale.py` in fact 13. Before a phase
uses a fact of 1 to 13, it checks the fact on `main`. Facts 14 to 18 give the
state at amendment 1, and facts 19 to 24 the state at amendment 2.

1. **The registry.** `CardSpec(name, order, build, options=(), publishes=(),
   subscribes=(), when=None)` (`registry.py:156`). `ReportContext(seq,
   specs, values)` (`:184`). `build_cards(seq, *, cards=None, skip=(),
   **options)` (`:322`). An exception in a card gives `_error_card` (`:300`),
   which has a failed `Check("error", ...)` (`:306`).
2. **The page.** `Check(name, passed, message)` (`page.py:39`). `Card` has
   the fields `id, title, body_html, data, script, collapsed, scripts, css,
   checks, publishes, subscribes` (`page.py:48`). `render_page` does not show
   the checks.
3. **The command.** `cli.py`: `_write_pages` (`:238`) reads each file with
   `pp.Sequence().read`, writes the default-limits warning (`:255-263`, with
   `_default_limits` and `GAMMA`), builds the cards, and gives status 2 for a
   failed check (`:271-276`). The configuration keys are `cards`, `skip` and
   each option name (`:197`).
4. **The options** (`options.py`): `gradient_asc` (`:74`, cards `pns` and
   `diagram`), `limits` (`:95`, `HardwareLimits`, flags `--max-grad` and
   `--max-slew`), `coil` (`:121`, default `PRISMA_AS82`), `periodic`,
   `b1rms_window_s`, `pns_lane`, `views`, `plane`, `extent_m`, `max_rows`,
   and `check_norms` (`:193`).
5. **The cards and their checks.**
   - `timing_card` (`cards/timing.py:55`) calls `seq.check_timing()`, writes a
     "passed" or "failed" status paragraph and has `Check("timing")`.
   - `gradient_limits_card(seq, *, windows, limits, check_norms, card_id)`
     (`cards/gradient_limits.py:199`) uses `_default_limits(seq, GAMMA)`
     when `limits` is `None` (`:243`), `_excess` and `_excesses` (`:155-196`)
     and `Check("gradient-limits")` (`:276-286`). Its "Show" buttons give the
     time range of a block (`_goto_button`, `:41-54`).
   - `pns_card(seq, *, gradient_asc, card_id)` (`cards/pns.py:134`) calls
     `pns_prediction` (the example hardware when `gradient_asc` is `None`),
     and `_check` (`:61`) applies the 100 % rule.
   - `diagram_card(seq, windows, *, pns_lane, gradient_asc, card_id)`
     (`cards/diagram.py:107`) adds `file.pns` from `_pns_entry` (`:46-66`):
     `hardware, example, asc_file, hw, dtS, gradScale, binSamples, summary,
     levels`.
   - `spectrum_card(seq, *, coil, card_id)` (`cards/spectrum.py:152`) draws
     the resonances of one coil as bands.
   - `rf_profile_card` uses `seq.system.gamma` and `seq.system.B0`
     (`cards/rf_profile.py:148-149`, `:230-231`). It changes the `ppm`
     offsets into Hz in Python, and does not send the `ppm` terms to the
     browser.
6. **The exports** (`__init__.py`): `PRISMA_AS82`, `Card`, `Check`,
   `GradientCoil`, `HardwareLimits` (from `grad_limits`), `TimeWindow`,
   `__version__`, `build_cards`, `first_adc_window`, `full_window`,
   `render_page`, `write_page`.
7. **The imports of the copied modules** from the modules that stay:
   `options.py`, `__init__.py`, `cli.py`, `diagram_data.py`
   (`_index_dtype, adc_events, grad_events, rf_events, sequence_index`,
   `GAMMA, gradient_offsets`), `waveforms.py`, `rf_exposure.py`,
   `grad_spectrum.py`, `rf_profiles.py`, and the card modules
   `gradient_limits`, `pns`, `diagram`, `spectrum` and `rf_profile`. Tests:
   `synthetic.py`, `test_registry.py`, `test_cli.py`, `test_rf_exposure.py`,
   `test_rf_profiles_golden.py`, `test_pns_card.py`,
   `test_gradient_limits_card.py` (it patches `grad_limits.grad_events` at
   `:215` and `grad_limits.sequence_index` at `:312`), `test_extensions.py`,
   `test_pns_lanes_golden.py`, `test_rf_profile_card.py`,
   `test_rf_exposure_card.py`, `test_waveforms.py`, `test_diagram_card.py`,
   `tests/oracles/rf_exposure.py`.
8. **The tests of the copied modules only**: `test_grad_limits.py` (23 tests)
   with `tests/oracles/grad_limits.py`, `test_pns_levels.py` (10),
   `test_sampling.py` (21), `test_seq_index.py` (14) and `test_seq_utils.py`
   (9). `TESTS.md` sections 2.1, 2.13, 2.22, 2.23 and 2.24. `test_pns.py` (20,
   section 2.11) and `test_extensions.py` (6, section 2.21) test both copied
   code and cards.
9. **`TESTS.md`** has one `####` entry for each test, under a heading
   `### 2.N Title (`test_file`)`. `scripts/check_tests_md.py` checks that
   each collected test has exactly one entry. The section numbers do not have
   to be consecutive.
10. **The JavaScript.**
    - A lane of `laneChart` has one color (`lane_chart.js:191`). There are no
      series, no legend, and `bands` are chart-wide rectangles with one style
      (`:162-167`).
    - The `goto` message takes the play index from 0 (`{block}`) or a time
      range (`{t0S, t1S, anchorS}`) (`cards/diagram.js:322-356`).
    - `pns_lanes.js` decodes one PNS model (`decode`, `:217`) and calculates
      the exact PNS for a view of 10 s or less from the SAFE parameters
      `hw`.
    - `report.css` has no color tokens for categories. Light tokens are at
      `:2-17`, and the dark tokens are written two times (`:18-39`).
    - Node tests cover only DOM-free modules (`tests/js/test_*.js`). The cards
      are checked in a browser with the `dev-workflow:browser-check-localhost`
      skill.
11. **`pulseq-analysis` `v0.1.0rc2`** documents each name that pulseq-reports
    imports (its `docs/usage.md`, sections 1 to 4), except `_index_dtype` and
    `_default_limits`. Section 1 gives the rule for the dtype of the index
    columns: the smallest of uint8, uint16 and uint32 that holds the count.
    `gradient_limits(seq, *, window=None, gamma=GAMMA)` has no `limits`.
    `series.encode_array(a)` uses the same algorithm as
    `diagram_data.encode_tables` for one array (gzip level 6, `mtime=0`, OS
    byte 255, base64).
12. **`pulseq-checks` `v0.1.0rc3`.** `run_checks(sequence, targets, *, select,
    required, fast_only, limits_from_sequence, analyses)`. A `Location` gives
    the block ID. `ResultMatrix.analysis(target, "pns.safe.levels")` gives an
    `AnalysisResult` with the series `pns_total` (`ENVELOPE`, `min` and
    `max`, the `meta` of the PNS summary) and `pns_above_1` (`RUNS`).
    `TargetProfile.models["pns.safe"]` gives the SAFE parameters: `x`, `y`
    and `z`, each with `tau1`, `tau2`, `tau3`, `a1`, `a2`, `a3`,
    `stim_limit`, `stim_thresh` and `g_scale`.
13. **The scripts and the example.** `examples/gre_report.py` calls
    `build_cards(seq, pns_lane=True, views=("profile", "z_df"))` and writes
    `docs/examples/gre.html`. A person runs it and commits the page. No CI step
    makes it. `tests/test_rf_profiles_golden.py` loads the example script by
    path (`:728`). `scripts/cards_scale.py` measures one card at a time, with
    the defaults of the card.

14. **The state at amendment 1** (`main` at `7ae78af`). Phases 1 to 4 are
    merged. `pyproject.toml` pins `pulseq-checks` `v0.1.0rc3` (`4ec751b`) and
    `pulseq-analysis` `v0.1.0rc2` (`9f65863`). The pypulseq fork commit is
    `a74ab06` in all three repositories, also at `v0.1.0rc4`. No module of
    `src/` reads a field of a `Series`. `cli.py:342` sets `analyses` to
    `("pns.safe.levels",)` when the `pns` card, or the `diagram` card with
    `pns_lane`, is on the page.
15. **The `v0.1.0rc4` tags.** `pulseq-checks` `v0.1.0rc4` is the commit
    `e38bf5c`, and `pulseq-analysis` `v0.1.0rc4` is the commit `0afc759`.
    Between `v0.1.0rc2` and `v0.1.0rc4`, `pulseq-analysis` changed only
    `analyses.py`, `grad_spectrum.py` (new) and `series.py`. `encode_array`
    did not change. Thus the pin change does not change a page.
16. **The local spectrum module.** `src/pulseq_reports/grad_spectrum.py`
    (`gradient_spectrum`, `GradientSpectrum`, `BandPeak`, `MAX_FREQUENCY_HZ`,
    `FFT_WINDOW_S`) is the source of `pulseq_analysis.grad_spectrum`. It
    gives mT/m/√Hz with `seq.system.gamma`. Phase 1 gave it a `resonances`
    argument and the band peaks. Its tests are `tests/test_grad_spectrum.py`
    with `tests/oracles/grad_spectrum.py` (`TESTS.md` section 2.9). These
    also import it: `cards/spectrum.py`, `tests/test_spectrum_card.py`
    (section 2.10), `tests/test_registry.py`, `tests/test_exports.py`,
    `tests/test_extensions.py`, `tests/test_file_rasters.py` and
    `scripts/cards_scale.py`.
17. **The spectrum card at amendment 1.** `spectrum_card(seq, *, card_id)`
    calls `gradient_spectrum(seq)`. Its data has `reason`,
    `max_frequency_hz`, `db_floor`, `resonances` (empty), `lanes` and `bands`
    (empty). `assets/cards/spectrum.js` reads `data.resonances` and shades
    each band in one style. It does not read `data.bands`.
18. **`TODO.md`.** The table of the places that change Hz into T has a row
    for `grad_spectrum.gradient_spectrum`.
19. **The `v0.1.0rc5` tags** (design, section 3.5). `pulseq-checks`
    `v0.1.0rc5` is the commit `369fd65`, and `pulseq-analysis` `v0.1.0rc5` is
    the commit `8043553`. Both pin the pypulseq fork commit `a74ab06`.
20. **The names that `v0.1.0rc5` changed, in pulseq-reports** (`main` at
    `2a516b4`):
    - `cards/gradient_limits.py:74-116` reads the `*_mt_per_m` and
      `*_t_per_m_per_s` fields of `GradientLimits` and `AxisResult`, and
      `:152` calls `gradient_limits(seq, window=window)`.
    - `cards/pns.py:40-42` reads `PnsPrediction.peak` and `axis_peaks` as
      fractions.
    - `cards/diagram.py:61-68` reads `PnsLevels.peak`, `axis_peaks`,
      `level_min` and `level_max` as fractions, and writes
      `gradScale = GAMMA / seq.system.gamma`. `:104` calls
      `pns_levels_for(seq, gradient_asc=...)` with no threshold.
    - The `HardwareLimits` of `pulseq-checks` keeps its mT/m and T/m/s names.
21. **The uses of `GAMMA`** (`pulseq_analysis.seq_utils`, removed in
    `v0.1.0rc5`): `registry.py:22`, `targets.py:14`, `diagram_data.py:18`,
    `waveforms.py:19`, `rf_exposure.py:24` and `cards/diagram.py:31`. Tests:
    `synthetic.py`, `test_diagram_card.py`, `test_gradient_limits_card.py`,
    `test_pns_lanes_golden.py`, `test_rf_exposure.py` (`seq_utils.GAMMA` at
    `:15`), `test_rf_exposure_card.py`, `test_rf_profiles_golden.py`,
    `test_targets.py`, `test_waveforms.py` and `tests/oracles/rf_exposure.py`.
    The node tests `tests/js/test_seq_lanes.js` and `tests/js/test_rf_profiles.js:19`
    use the proton factor 42576 of `seq_lanes.js`. (`test_grad_spectrum.py`
    goes away in phase 6.)
22. **The conversions with a gamma at `2a516b4`.**
    - With `GAMMA`: `diagram_data.py:127` (the gradient values of the
      diagram data, in mT/m), `waveforms.py:92` (\|B1\|, µT) and `:121`
      (gradient lanes, mT/m), `rf_exposure.py:76` (\|B1\|, µT).
    - `assets/seq_lanes.js:37` (`GRAD_HZ_PER_VALUE = 42576`, the proton
      gamma times 1e-3) changes the mT/m values of the diagram data back into
      Hz/m, and gives the factor as `gradHzPerValue` (`:402`), which
      `assets/rf_profiles.js:827` reads. `assets/pns_lanes.js` multiplies the
      values by `gradScale` (`:140`, `:219`).
    - The lane domains and tick labels of the diagram are in mT/m and µT,
      from Python (`waveforms._value_domain:187`, `diagram_data.lane_meta:192`).
    - With `abs(seq.system.gamma)` and `seq.system.B0`:
      `cards/rf_profile.py:149-150` (a `ppm` offset in Hz), `:231-232`
      (`b0_t` and `gamma_hz_per_t` of the page data), and
      `rf_profiles.py:916-917`. `assets/rf_profiles.js:994-1014` divides by
      `gammaHzPerT` for \|B1\|. pypulseq changes a `ppm` offset with the
      signed gamma.
    - The proton rule: `registry.py:338-341` (`build_cards` refuses another
      `seq.system.gamma`) and `targets.py:56-59` (`supported`).
    - The RF exposure card has no card script. The gradient limits card has
      the script `gradient-limits` only when it has a "Show" button.
23. **What `pulseq-checks` `v0.1.0rc5` documents for a caller.** The gamma of
    a target is `target.make_opts().gamma`, and its magnitude is
    `abs(target.make_opts().gamma)` (`bindings.gamma_magnitude` needs a
    `RunContext`). The PNS percent of a value `v` is `100 * v /
    meta["threshold"]` of `pns_above_0`. A result JSON of `v0.1.0rc4` reads,
    with PNS series in the unit `"1"`.
24. **`TODO.md`, "Use the gyromagnetic ratio of the sequence".** Its table
    lists the conversions of fact 22. Phase 2c closes the item: it removes
    it, and section 4.8 of the design is the list.

### 2.4 Decisions of this plan (approved by the user on 2026-10-04)

Do not open these decisions again.

| # | Decision | Answer | Why |
|---|---|---|---|
| D1 | How the command knows that a card is an error card (P14) | A new field `Card.error: str \| None = None`. `_error_card` sets it to the message. | A test of the title text is fragile, and the design forbids a hidden rule. |
| D2 | When the `coil` option goes away | In phase 1, with `PRISMA_AS82`. Without the default coil, the option has no value to choose. `gradient_spectrum` takes the resonances as (frequency, bandwidth) pairs in Hz, the form of `TargetProfile.acoustic_resonances`, and `AcousticResonance` goes away. Amendment 1: phase 6 deletes the `gradient_spectrum` of pulseq-reports (D12). | P8 and the design, section 4.7. |
| D3 | The timing card from phase 1 to phase 10 | Phase 1 removes its `Check` and its "passed" and "failed" text. The card shows the number of errors of `check_timing` and the error table, with no verdict. Phase 10 makes it from the results. | No release comes between the phases. |
| D4 | `encode_tables` | It goes away, with `decode_tables`. Each caller calls `pulseq_analysis.series.encode_array` (or `decode_array`) for each array. The JSON of the page does not change. | No duplicate code. `docs/usage.md` does not document `encode_tables`. |
| D5 | The form of the pins | Direct references in `[project] dependencies`, as `pulseq-checks` does: `pulseq-checks @ git+https://github.com/mdtisdall/pulseq-checks@v0.1.0rc3` and `pulseq-analysis @ git+https://github.com/mdtisdall/pulseq-analysis@v0.1.0rc2`, with `[tool.hatch.metadata] allow-direct-references = true`. Amendment 1: the tags are `v0.1.0rc4` (P29, phase 2b). Amendment 2: the tags are `v0.1.0rc5` (P34). The form stays. | The tags of the design, section 5. `uv.lock` records the commits. |
| D6 | The target colors | Six tokens `--target-1` to `--target-6` in `report.css`, light and dark. Phase 3 selects them with the `dataviz` skill. | P28. |
| D7 | The targets in a card | `ReportContext.targets`: a tuple of `ReportTarget(profile, color, supported, reason)`, in the order of the targets. `supported` is false for a gamma other than `GAMMA`, with the reason. `ReportContext.check_results` is the matrix or `None`. Amendment 2: phase 2c changes it to `ReportTarget(profile, color, gamma)`, with no `supported` and no `reason` (P35). | One place for the rules of P21 and P28. |
| D8 | The "Show" buttons | Phase 3 adds one helper for the button HTML and one card script, `show-buttons`, that wires each button to a `goto` message. The summary card, the timing card and the gradient limits card use them. The helper changes a block ID into the play index. | Phases 9 and 10 do not depend on each other. |
| D9 | The chart support | Phase 4 adds series to a lane (several colored lines in one lane, one tooltip row for each) and marks in a lane (intervals with a color, drawn only in that lane). A lane without series draws as now. | The PNS lane, the spectrum bands and the RF profiles need them. |
| D10 | The version during the work | `0.2.0rc3.dev0` from phase 1. Phase 12 sets `0.2.0rc3`. | A page written from `main` does not say that it is `0.2.0rc2`. |
| D11 | The documents | Each phase updates `TESTS.md`. `docs/usage.md`, `README.md` and `CHANGELOG.md` change in phase 11 only. | As in `docs/plans/public-api.md`. |
| D12 | Where the local spectrum module goes away (amendment 1) | In phase 6, not in phase 2b. Phase 2b changes only the pins, so its pages are equal byte for byte. Amendment 2: phase 2b is the refactor of section 4.2b, and its pages differ only as the row `2b` of section 3.5 says. | With P31, the card never calls a spectrum function. A change of the card to `pulseq_analysis.grad_spectrum` in phase 2b is work that phase 6 removes. |
| D13 | The analyses that the command asks for (amendment 1) | `pns.safe.levels` as now, and `gradient.spectrum` when the `gradient-spectrum` card is on the page. | Principle 10 of the design. |
| D14 | The unit of the spectrum card (amendment 1) | mT/m/√Hz, as now: the card multiplies the values of the series by `1e3 / GAMMA`. Amendment 2: by `1e3 / |γ|` of each group (P37). | Principle 8 of the design. Section 8.1 of the `pulseq-analysis` plan `docs/plans/gradient-spectrum.md`. |
| D15 | `fast_only` and the analyses (amendment 1) | The command asks for the analyses of the cards on the page also with `fast_only`, as `pulseq-checks` does. A caller that does not want the time uses `--skip` for the card. `docs/usage.md` gives the cost (phase 11). | The card on the page is the request. `fast_only` selects checks, not analyses. |
| D16 | The order of the move to `v0.1.0rc5` (amendment 2) | Phase 2b is a refactor: the pins and the new names, with the proton rule still in force, and the comparison of section 3.5. Phase 2c then changes the gamma rule. | The comparison of phase 2b is a safety net for the change of the API. |
| D17 | One module for the gamma (amendment 2) | `units.py` (new in phase 2b). Phase 2b gives it `PROTON_GAMMA = 42.576e6` (Hz/T, the default of pypulseq) in place of `GAMMA`, `gamma_magnitude(gamma)` (`abs`), and the conversion functions (Hz/m to mT/m, Hz/m/s to T/m/s, Hz to µT, each with the magnitude of its gamma argument). Phase 2c adds `target_gamma(profile)`, `check_gamma` and `gamma_entries`. Phase 7b removes `PROTON_GAMMA`, after its last use. The tests do not use `PROTON_GAMMA`: they have their own `GAMMA_1H = 42.576e6` in `tests/synthetic.py`, with a test that it is the default of pypulseq. After phase 8, no module but `units.py` writes `abs(` of a gamma. | As `gamma_magnitude` in `pulseq-checks`: `abs` in one place. |
| D18 | The `ppm` offsets and the RF phase (amendment 2) | A `ppm` offset changes into Hz with the signed γ and B0 of the target, as pypulseq does. This changes `abs(seq.system.gamma)` of fact 22. The RF phase of the diagram stays the phase of the file. | P33: a `ppm` offset is a signed value. The phase of the file is what the interpreter plays. |
| D19 | The control of P36 (amendment 2) | Phase 2c adds `markup.gamma_select_html(entries, card_id)` and `PulseqReport.gammaSelect(section, onChange)` in `lane_chart.js`. A card with a static table (the peaks of the gradient limits card, the RF exposure card) writes one table for each entry, and the control shows one (design, section 4.8). A chart card (the diagram) rescales its lanes in `onChange`. The control of a card does not change another card. Phase 2c also adds the card script `gamma-select` for a card that has no other script. A card with its own script (for example `gradient-limits` when it has a "Show" button) calls `gammaSelect` from that script. | One control for all the cards. A message between the cards is not necessary. |

### 2.5 Terms

- **Target.** A `TargetProfile` that the caller gives to the report.
- **Supported target.** A target whose gamma is the proton gamma (P21).
  Amendment 2: from phase 2c, each target whose gamma is finite and not 0
  is valid, and the term goes away (P35).
- **Gamma of a target.** `target.make_opts().gamma`, in Hz/T. It can be
  negative. \|γ\| is its magnitude.
- **Result matrix.** A `ResultMatrix` of `pulseq-checks`.
- **Play index.** The position of a block in play order, from 0. The `goto`
  message uses it.
- **Block ID.** The key of a block in `seq.block_events`. A `Location` gives
  it.
- **Baseline.** pulseq-reports at the merge-base of the branch of a phase, in
  `.worktrees/base`.

## 3. How to execute this plan

### 3.1 Workflow

1. Start each phase with the `dev-workflow:start-task` skill, from the latest
   `origin/main`.
2. Run `nix develop --command uv sync --frozen` one time in each new
   worktree, before a worker starts. Phase 2 changes `uv.lock`, so from phase
   2 the sync installs the two packages.
3. Each phase that adds, removes or changes a test updates `TESTS.md`.
4. Run `nix develop --command scripts/check` before each PR.
5. Show the commit message to the user, and wait for approval before
   `git commit`. Merge only when the user tells you to.
6. At most three phase PRs are open at one time.
7. Each phase ends with a line-by-line review of each worker's diff by the
   executing agent.
8. When a phase finds that this plan or the design is wrong, stop and ask the
   user. Do not change a decision of section 2.2 or 2.4.
9. Do not test a fixed sentence (a note, a heading). Test what a card
   calculates, and test that a value is not there when it must not be there.

### 3.2 Worker model tiers

The workers are the agents in `.claude/agents/`.

| Tier | Agent | Use it when |
|---|---|---|
| M | `worker-medium` | A removal, a move, an import change, or code whose form this plan gives exactly. |
| H | `worker-high` | A card, a JavaScript chart change, a public interface with local decisions, or a long document. |
| X | the executing agent | The interfaces, the pins, the comparisons, the browser checks, the questions to the user, and the review of each diff. |

Give each worker the task, the worktree, this plan with the sections of the
task, the files that it owns (section 3.4), and the checks to run. A worker
that finds that the task and this plan do not agree stops and reports.

### 3.3 Order and parallel work

```
Wave 1:  Phase 1 (verdicts and defaults)
Wave 2:  Phase 2 (dependencies)
Wave 3:  Phase 3 (targets and matrix)   Phase 4 (chart support)
Wave 3b: Phase 2b (pins v0.1.0rc5, refactor), then Phase 2c (target gamma)
Wave 4:  Phase 5 (gradient limits)   Phase 6 (spectrum)   Phase 7 (PNS)
         Phase 8 (RF profile), when one of phases 5 to 7 is merged
         Phase 7b (diagram and RF exposure gamma), when phases 5 and 7 are merged
Wave 5:  Phase 9 (check summary)   Phase 10 (findings in cards)
Wave 6:  Phase 11 (documents and example)
Wave 7:  Phase 12 (release)
```

- Phase 2 needs phase 1, because phase 1 removes the use of
  `_default_limits`.
- Phase 3 and phase 4 share no file.
- Phase 5 needs phase 3. Phases 6, 7 and 8 need phases 3 and 4.
- Amendment 2: phase 2c needs phase 2b. Phases 5, 6, 7, 7b and 8 need
  phase 2c: they use the gamma of each target and `units.py`. Phase 7b
  needs phase 7, because both edit `cards/diagram.py` and
  `assets/cards/diagram.js`, and phase 5, because phase 7b removes
  `PROTON_GAMMA` after its last use.
- Amendment 2: from phase 2c to phase 7b, `build_cards` accepts each gamma,
  but a card that a later phase changes keeps the gamma that it has (the
  proton gamma of `PROTON_GAMMA`, or `seq.system.gamma`). No release comes
  between the phases (D10).
- Phase 9 needs phase 3. Phase 10 needs phases 3 and 5.
- Phase 11 needs phases 5 to 10.

### 3.4 File ownership

"New" marks a file that the phase makes. Each phase also edits its own
`TESTS.md` sections and its own tests.

| Phase | Branch | Files |
|---|---|---|
| 1 | `feature/remove-verdicts` | `page.py`, `registry.py`, `cli.py`, `options.py`, `grad_spectrum.py`, `__init__.py` (also `__version__`), `pyproject.toml` (the version only), `uv.lock` (the version only), `cards/timing.py`, `cards/gradient_limits.py`, `cards/pns.py`, `cards/diagram.py`, `cards/spectrum.py`, `scripts/cards_scale.py` |
| 2 | `refactor/use-pulseq-analysis` | `pyproject.toml`, `uv.lock`, the eight copied modules (deleted), each importing module of fact 7, `diagram_data.py`, `cards/diagram.py` and `cards/rf_profile.py` (the calls of `encode_tables` only), `scripts/diagram_scale.py`, `TODO.md` (the fork item) |
| 2b | `refactor/pulseq-rc5` | `pyproject.toml` (the two pins and their comment), `uv.lock`, `units.py` (new), each module and Python test of facts 20 and 21 (the names and the imports only) |
| 2c | `feature/target-gamma` | `units.py`, `targets.py`, `registry.py` (the gamma rule only), `markup.py` (`gamma_select_html`, and `target_legend_html` for `supported`), `assets/lane_chart.js` (`gammaSelect`), `assets/cards/gamma-select.js` (new), `TODO.md` (fact 24), `tests/profiles/example_c.toml` (new), `tests/test_targets.py`, `tests/test_registry.py`, `tests/test_markup.py` |
| 3 | `feature/report-targets` | `registry.py`, `targets.py` (new), `markup.py`, `assets/report.css`, `assets/cards/show-buttons.js` (new), `cli.py`, `__init__.py` |
| 4 | `feature/chart-series` | `assets/lane_chart.js`, `assets/chart_math.js` |
| 5 | `feature/gradient-limits-targets` | `cards/gradient_limits.py`, `assets/cards/gradient-limits.js`, `options.py` (the `limits` option only), `cli.py` (only if the `limits` flags need it), `scripts/cards_scale.py` (the `limits` mode only) |
| 6 | `feature/spectrum-targets` | `cards/spectrum.py`, `assets/cards/spectrum.js`, `grad_spectrum.py` (deleted), `tests/test_grad_spectrum.py` and `tests/oracles/grad_spectrum.py` (deleted), the imports of fact 16, `cli.py` (the `analyses` line only), `scripts/cards_scale.py` (the `spectrum` mode only). Amendment 2: not `TODO.md` (phase 2c removes the item of fact 18) |
| 7 | `feature/pns-targets` | `cards/pns.py`, `cards/diagram.py`, `assets/cards/pns.js`, `assets/cards/diagram.js`, `assets/pns_lanes.js`, `options.py` (the `gradient_asc` option only), `scripts/cards_scale.py` (the `pns` and `diagram` modes only), `cli.py` and `registry.py` (the check of P39 only) |
| 7b | `feature/diagram-gamma` | `units.py` (`PROTON_GAMMA` removed), `diagram_data.py`, `waveforms.py`, `rf_exposure.py`, `cards/diagram.py` (the gradient and RF lanes only), `cards/rf_exposure.py`, `assets/seq_lanes.js`, `assets/pns_lanes.js` (the Hz/m samples only), `assets/rf_profiles.js` (the line of fact 22 only), `assets/chart_math.js` (the lane domain function), `assets/cards/diagram.js` (the control and the domains only), `tests/js/test_seq_lanes.js`, `tests/js/test_rf_profiles.js` (the factor only), `scripts/diagram_scale.py` (only if the data format needs it) |
| 8 | `feature/rf-profile-targets` | `cards/rf_profile.py`, `rf_profiles.py`, `assets/cards/rf-profile.js`, `assets/rf_profiles.js`, `scripts/rf_references.py` (the arguments of `block_pulse`, amendment 2) |
| 9 | `feature/check-summary` | `cards/checks.py` (new), `assets/cards/checks.js` (new, if `show-buttons` is not enough), `cards/__init__.py`, `pyproject.toml` (the card entry point only), `cli.py` (`--max-findings`, `--fail-on-check`) |
| 10 | `feature/findings-in-cards` | `cards/timing.py`, `cards/gradient_limits.py` (the findings list only) |
| 11 | `docs/reports-on-checks` | `docs/usage.md`, `README.md`, `CHANGELOG.md`, `examples/gre_report.py`, `examples/targets/` (new), `docs/examples/gre.html`, `tests/test_rf_profiles_golden.py` (only if the example change needs it) |
| 12 | `chore/release-0.2.0rc3` | `pyproject.toml` (the version), `__init__.py` (`__version__`), `CHANGELOG.md` (the date), this plan (status and results), `docs/plans/pulseq-checks.md` (status) |

Rules:

1. A phase edits only its files. If it must edit a different file, it stops
   and asks the executing agent.
2. `options.py`, `cli.py`, `scripts/cards_scale.py`, `units.py`,
   `assets/rf_profiles.js`, `tests/test_cli.py`, `tests/test_registry.py`,
   `tests/test_extensions.py` and `tests/test_file_rasters.py`: several
   phases edit different parts. Rebase
   the later phase and keep both edits.
3. `TESTS.md`: each phase edits only the sections of its test files. If a
   conflict occurs, keep both sides.

### 3.5 Behavior preservation

1. **The baseline.** `git -C <main checkout> worktree add --detach
   .worktrees/base origin/main`, then `nix develop --command uv sync
   --frozen` in it. Before each comparison, check out the merge-base of the
   branch of the phase. Remove it after phase 12.
2. **The comparison set.**
   - The example page: `examples/gre_report.py` on the baseline and on the
     branch.
   - The command pages of three synthetic `.seq` files: the spin echo and the
     GRE of `tests/synthetic.py` and `build_repeating(1000)` of
     `scripts/diagram_scale.py`, with the options that the phase still has.
   - Amendment 2, until phase 7: the page of the GRE with `--gradient-asc`
     and a synthetic `.asc` file (`write_gradient_asc` of
     `tests/conftest.py`) and `--pns-lane`, so that the comparison covers
     the PNS.
   - Compare with the masked page diff of `docs/plans/public-api.md`, section
     9.2: every difference, with the text of each script that the phase
     changes masked.
3. **Expected differences.** Any other difference stops the phase.

   | Phase | Expected differences |
   |---|---|
   | 1 | The version in the subtitle (`0.2.0rc3.dev0`, D10). The timing card has no "passed" or "failed" text. Without `limits`, the gradient limits card has no percent columns. Without `gradient_asc`, the PNS card has no PNS and the diagram has no PNS lane. The spectrum card has no bands. |
   | 2 | None. The pages are equal byte for byte. |
   | 2b | Amendment 2: the PNS values of the PNS card and of the PNS entry of the diagram data, to the float rounding, on a page with a gradient `.asc` file (the SAFE model runs on Hz/m, and the card divides after it). The level arrays are float32: a value can differ by 1 unit in the last place of float32 (relative 2⁻²³). Nothing else: the other parts of the pages are equal byte for byte. |
   | 2c | None without targets. |
   | 3 | None without targets. |
   | 4 | The text of `lane_chart.js` and `chart_math.js` only. The browser shows each chart as on the baseline. |
   | 5 to 10 | The cards of the phase. Each page without targets is as in phase 1, with these exceptions (amendment 2): in phase 6, the spectrum card has a note and no chart (principle 10 of the design); in phase 7, the diagram data of each page has the new format number and no PNS entry; in phase 8, the data of the RF profile card of each page has the new format. In phases 7 and 8, the browser shows the same values as on the baseline. |
   | 7b | The diagram data (Hz/m and Hz, a new format number) and the HTML of the RF exposure card. Without targets, the browser shows the same values, domains and tick labels as on the baseline. |

### 3.6 The browser checks

Phases 3 to 10 change what a browser shows. Before the PR, check the pages of
section 3.5 with the `dev-workflow:browser-check-localhost` skill, in light
and dark mode. From phase 3, also check a page with two targets: use two
example profiles from `tests/profiles/` (phase 3 makes them, section 4.3).
The console must have no error.

## 4. Design

### 4.1 Phase 1: the verdicts and the defaults

1. `page.py`: remove `Check` and `Card.checks`. Add `Card.error: str | None
   = None` (D1). `render_page` does not show it.
2. `registry.py`: `_error_card` sets `error` to the message, and has no
   check.
3. `cli.py`: remove the loop over `card.checks` and the exit status 2. The
   status is 1 when a card of a page has `error`, and the page is written.
   Remove the default-limits warning and its imports. The module docstring
   gives the statuses 0 and 1.
4. `options.py`: remove `check_norms`, and `coil` with `COILS` and
   `_coil_from_name` (D2).
5. `grad_spectrum.py`: remove `AcousticResonance`, `GradientCoil`, `COILS`,
   `PRISMA_AS82` and `PRISMA_AS82_RESONANCES`. `gradient_spectrum` takes
   `resonances` as a tuple of (frequency, bandwidth) pairs in Hz. The default
   is `()`.
6. `__init__.py`: remove `Check`, `GradientCoil` and `PRISMA_AS82` from the
   exports.
7. The cards:
   - `timing`: as D3.
   - `gradient_limits`: remove `check_norms`, `_excess`, `_excesses`,
     `_LIMIT_TOLERANCE` and the check. With `limits=None`, the card has no
     percent columns and a note. It does not call `_default_limits`.
   - `pns`: remove `_check` and the 100 % rule of the status line. With
     `gradient_asc=None`, the card has no PNS and a note. It does not call
     `pns_prediction`.
   - `diagram`: with `pns_lane=True` and `gradient_asc=None`, the data has no
     `pns` entry, and the status gives a note.
   - `spectrum`: remove `coil`. The card has no bands (phase 6 adds them).
8. `scripts/cards_scale.py`: the `pns` mode and the `diagram --pns-lanes`
   mode take a necessary `--gradient-asc PATH`.
9. The version is `0.2.0rc3.dev0` in `pyproject.toml` and `__init__.py`
   (D10). Run `nix develop --command uv lock` for the version line of
   `uv.lock`.

### 4.2 Phase 2: the dependencies

1. **The pins (D5).** Add the two direct references and
   `allow-direct-references`. Keep `[tool.uv.sources]` for pypulseq. Run
   `nix develop --command uv lock`. Then confirm in `uv.lock`:
   `pulseq-checks` at `4ec751b`, `pulseq-analysis` at `9f65863`, and one
   pypulseq at `a74ab06`. If a commit is different, stop and ask the user
   (design, section 5).
2. **The copies.** Delete `grad_limits.py`, `pns.py`, `pns_levels.py`,
   `asc.py`, `extensions.py`, `sampling.py`, `seq_index.py` and
   `seq_utils.py`. Change each import of fact 7 to the module of the same
   name in `pulseq_analysis`. `HardwareLimits` comes from `pulseq_checks`.
3. **The private names.** `diagram_data.py` gets its own `_index_dtype`, by
   the rule of fact 11. `gradient_limits_card` calls `gradient_limits`
   without `limits`.
4. **`encode_tables` and `decode_tables`** go away (D4). `diagram_data.py`,
   `cards/diagram.py`, `cards/rf_profile.py`, `scripts/diagram_scale.py` and
   the tests (`test_diagram_data.py`, `test_diagram_card.py`,
   `test_rf_profile_card.py`, `test_seq_lanes_golden.py`,
   `test_rf_profiles_golden.py`, `test_pns_lanes_golden.py`) call
   `encode_array` and `decode_array` for each array. The comparison of item 7
   shows that the JSON of the page does not change.
5. **The tests.** Delete the tests of fact 8 that test only copied code, with
   their `TESTS.md` sections. In `test_pns.py` and `test_extensions.py`, keep
   each test of a card, with the new imports, and delete each test of a
   copied function. In `test_gradient_limits_card.py`, replace the two
   patches of `grad_limits` (fact 7): `pulseq-analysis` does not document
   those names. If the test checks a number of calls inside
   `pulseq-analysis`, delete it. Do not renumber the `TESTS.md` sections.
6. **`TODO.md`.** The fork item: `pns_levels.py` is in `pulseq-analysis`
   now. A change of the pin changes the three repositories.
7. **The comparison** (section 3.5): the pages are equal byte for byte.

### 4.2b Phase 2b: the move to `v0.1.0rc5` (amendment 2)

Amendment 2 rewrote this section (P34, D16, D17). It is a refactor: the
proton rule P21 stays in force until phase 2c.

1. **The pins (P34).** Change the two direct references to
   `pulseq-checks @ git+https://github.com/mdtisdall/pulseq-checks@v0.1.0rc5`
   and `pulseq-analysis @ git+https://github.com/mdtisdall/pulseq-analysis@v0.1.0rc5`.
   Run `nix develop --command uv lock`. Then confirm in `uv.lock`:
   `pulseq-checks` at `369fd65`, `pulseq-analysis` at `8043553`, scipy as a
   dependency of `pulseq-analysis`, and one pypulseq at `a74ab06`. If a
   commit is different, stop and ask the user (design, section 5).
2. **`units.py` (new, D17).** `PROTON_GAMMA = 42.576e6` (Hz/T, the default
   of pypulseq), `gamma_magnitude(gamma)`, and the conversion functions:
   Hz/m to mT/m, Hz/m/s to T/m/s and Hz to µT, each with the magnitude of
   its gamma argument. Each import of `GAMMA` in `src` (fact 21) becomes
   `units.PROTON_GAMMA`, or a call of a conversion function. Keep each
   expression in the order of `v0.1.0rc4` (`value / gamma * 1e3`), so that a
   positive gamma gives the same float. The Python tests of fact 21 use
   `GAMMA_1H = 42.576e6` of `tests/synthetic.py` (D17), with a test that it
   equals `pp.Opts().gamma`.
3. **The names (fact 20).**
   - `cards/gradient_limits.py`: the `*_hz_per_m` and `*_hz_per_m_per_s`
     fields, converted with `PROTON_GAMMA`.
   - `cards/pns.py`: `peak_hz_per_t` and `axis_peaks_hz_per_t`, divided by
     `units.gamma_magnitude(seq.system.gamma)`. This is the gamma that
     `v0.1.0rc4` used.
   - `cards/diagram.py`: the level arrays and the summary divided by
     `units.gamma_magnitude(seq.system.gamma)`, so the data format of the
     diagram does not change. `pns_levels_for` needs no threshold: the diagram does not read
     `above`.
4. **No other change.** If `scripts/check` fails for a reason other than a
   name of fact 20 or 21, stop and ask the user.
5. **The comparison** (section 3.5): the expected differences of the row
   `2b`, with the page with a gradient `.asc` file. Decode the PNS level
   arrays and compare them with the baseline to 1 unit in the last place of
   float32. Compare the other PNS values (the summary, the percent text)
   with a relative tolerance of 1e-6. List each value that differs.

### 4.2c Phase 2c: the gamma of each target (amendment 2)

P33, P35, D7, D17, D19.

1. **`units.py`.** `target_gamma(profile)` gives `profile.make_opts().gamma`
   (signed). `check_gamma(gamma, where)` raises `ValueError` for a gamma
   that is 0 or not finite. `gamma_entries(targets, seq, *, signed)` gives
   the entries of the control of P36: one entry for each distinct γ
   (`signed=True`) or \|γ\| (`signed=False`), in the order of the first
   target of each entry, with the names of its targets. Without targets, one
   entry with `seq.system.gamma`. `PROTON_GAMMA` stays: the cards that use
   it change in phases 5 and 7b, and phase 7b removes it (D17).
2. **`targets.py` (D7).** `ReportTarget(profile, color, gamma)`.
   `report_targets` calls `check_gamma` for each target. `supported` and
   `reason` go away, and each module that reads them uses every target
   (`markup.target_legend_html:114`). No card reads them at `2a516b4`.
3. **`registry.py`.** `build_cards` calls `check_gamma(seq.system.gamma)` in
   place of the proton rule (P35). `ReportContext` does not change.
4. **The control (D19).** `markup.gamma_select_html(entries, card_id)`: a
   group of buttons with `aria-pressed`, as the scale buttons of the
   spectrum card, or nothing for one entry. `PulseqReport.gammaSelect(section,
   onChange)` in `lane_chart.js`: it wires the buttons, shows the block of
   the selected entry (`data-gamma-entry`), and calls `onChange(entry)`.
   `assets/cards/gamma-select.js` registers the card script `gamma-select`,
   which only calls `gammaSelect`.
5. **`TODO.md`.** Remove the item "Use the gyromagnetic ratio of the
   sequence" (fact 24). Section 4.8 of the design is the list now.
6. **The tests and a profile.** `tests/profiles/example_c.toml` (new): an
   example target with a negative gamma (-11.777e6 Hz/T, as ¹²⁹Xe), a
   comment that it is not a real scanner, and the other values of
   `example_a.toml`. The browser checks of phases 5, 7, 7b and 8 use it
   with `example_a.toml`. A negative gamma is valid. A gamma of 0, `inf`
   and `nan` each give `ValueError` in `report_targets` and in
   `build_cards`.
   `build_cards` accepts a `Sequence` object with another gamma. The entries
   of `gamma_entries` for two targets with γ and -γ: two entries with
   `signed=True`, one with `signed=False`. A test of the control in the
   browser comes with the first card that uses it.

### 4.3 Phase 3: the targets and the matrix

1. **`targets.py` (new).** `ReportTarget(profile, color, supported, reason)`
   (D7). `report_targets(profiles) -> tuple[ReportTarget, ...]`: `ValueError`
   for more than 6 profiles or for two profiles with one name. `color` is
   `"target-1"` to `"target-6"`, in order. `supported` is false, with a
   reason, when `profile.opts` gives a `gamma` other than `GAMMA`.
2. **`registry.py`.** `build_cards(seq, *, cards=None, skip=(), targets=(),
   check_results=None, **options)`. It raises `ValueError` when:
   `seq.system.gamma` is not `GAMMA` (P21), the target rules of item 1 fail,
   or the target names of `check_results` are not the names of `targets`.
   `ReportContext` gets `targets` and `check_results`.
3. **The colors (D6).** `report.css` gets `--target-1` to `--target-6`, in
   the light block and in both dark blocks. Select them with the `dataviz`
   skill, and check the contrast on `--surface` in both themes.
4. **The legend.** `markup.target_legend_html(targets)`: a list of the target
   names, each with a swatch of its color.
5. **The "Show" buttons (D8).** `markup.show_button_html(index, block_id,
   label)` takes a `SequenceIndex` and a block ID, and gives a button with
   the play index. `assets/cards/show-buttons.js` registers the card script
   `show-buttons`: it wires each button with `requestButton` and publishes
   `{source, block}`.
6. **The command.**
   - `--target PROFILE` (more than one time), `--check-config FILE` and
     `--check-results FILE.json`. Give at most one of `--target` and
     `--check-config`, as `pulseq-check` does. `--check-results` needs
     targets.
   - The configuration file gets the keys `targets` (a list of paths,
     relative to the file), `check_config` and `check_results`.
   - The command reads the profiles with `read_profile` and the configuration
     with `read_check_config`. Without `--check-results`, it calls
     `run_checks(path, profiles, select=..., required=..., fast_only=...,
     analyses=...)`. `analyses` is `("pns.safe.levels",)` when the `pns` card
     is selected, or the `diagram` card with `pns_lane`, and `()` otherwise.
   - With `--check-results`, it reads the matrix with
     `ResultMatrix.from_json`.
   - A `ProfileError`, `ConfigError`, `RunError`, or a refused result file,
     gives status 1 and no page.
   - It gives the targets and the matrix to `build_cards`.
7. **Test profiles.** `tests/profiles/` (new): two example profiles with
   different limits and B0, the SAFE parameters of the example hardware of
   pypulseq, and invented resonances. Phase 11 uses the same values for the
   example report.
8. No card uses the targets in this phase.

### 4.4 Phase 4: the chart support

1. **Series in a lane (D9).** A lane can have `series`: a list of
   `{label, color, segments}`. A lane with `series` draws one line for each,
   in its color. The tooltip has one row for each series, with a swatch.
   `ChartMath` gets the pure functions that the drawing needs (for example
   the value of each series at a time), with node tests.
2. **Marks in a lane (D9).** A lane can have `marks`: a list of `{lo, hi,
   color}` in milliseconds, drawn as rectangles in that lane only.
3. **Bands with a color.** An entry of `bands` can be `{lo, hi, color}`, and
   the old `[lo, hi]` form stays.
4. A lane without `series` or `marks` draws as now. The comparison of
   section 3.5 shows no difference in the browser.

### 4.5 Phase 5: the gradient limits card on targets

Amendment 2 changed items 2 and 3 and added item 5.

1. Remove the option `limits`, its flags `--max-grad` and `--max-slew`, and
   its configuration table.
2. `gradient_limits_card(seq, *, windows=None, targets=(), card_id=...)`. The
   peaks are measured one time, in Hz/m and Hz/m/s
   (`gradient_limits(seq, window=...)`).
3. One percent column for each target that has `profile.hardware_limits`,
   with the color of the target in its heading. The percent converts the
   peak with \|γ\| of that target (`units`), and divides it by the mT/m or
   T/m/s limit, as the gradient checks do (design, section 4.6). A note
   names each target without limits.
4. The "Show" buttons stay.
5. **The peaks in the gamma of a target (P36).** The table of the peaks
   shows mT/m and T/m/s for one \|γ\|. With more than one entry of
   `gamma_entries(..., signed=False)`, the card writes one table for each
   entry and the control of phase 2c. With a "Show" button, the card script
   `gradient-limits` calls `gammaSelect`. Without one, the card has the card
   script `gamma-select` (D19). Without targets, the card uses
   `seq.system.gamma`, not `PROTON_GAMMA`.

### 4.6 Phase 6: the spectrum card on targets

Amendment 1 rewrote this section (design principle 10, P30 to P32, D12 to
D14). Amendment 2 changed items 3, 5, 6, 7 and 10 (P33, P35, P37).

1. **The local module goes away (D12).** Delete `grad_spectrum.py`,
   `tests/test_grad_spectrum.py`, `tests/oracles/grad_spectrum.py` and
   `TESTS.md` section 2.9. Change or delete each import of fact 16. A test
   that only tests the spectrum calculation goes away: `pulseq-analysis`
   tests it (design, section 8). Do not renumber the `TESTS.md` sections.
   `test_rf_exposure_and_spectrum_do_not_depend_on_the_reader_opts`
   (`test_file_rasters.py`) keeps its `rf_exposure` part and loses its
   spectrum part. Its name and its `TESTS.md` entry change with it.
2. **The signature.** `spectrum_card(seq, *, targets=(), check_results=None,
   card_id=...)`. It keeps `refuse_rotations(seq)`, so a file with the
   rotation extension still gives an error card, as the other cards do. It
   does not call a spectrum function.
3. **The spectrum (P31, P37).** The targets whose `AnalysisResult` of
   `gradient.spectrum` has the state "done". The card reads each series
   `gradient_spectrum`: the frequency `k` is `coord_start + k * coord_step`,
   and the arrays `value` (the RSS), `x`, `y` and `z` are in Hz/m/√Hz. The
   card makes groups of the targets with the same \|γ\| and the same series
   (item 5). Each group is one series in each of the four lanes (phase 4),
   in mT/m/√Hz with `1e3 / |γ|` of the group (D14), in the color of its
   first target, with the names of its targets in the tooltip. The text of the
   method takes the window from `meta["window_s"]` and the maximum frequency
   from `meta["max_frequency_hz"]`, not from constants. A result "done" with
   no series is a sequence with no gradient event: the card says so, as now.
4. **No spectrum.** The card shows a note and no chart when: there is no
   target, there is no matrix, no target has an analysis result
   `gradient.spectrum`, or no such result is "done". The note gives the
   reason of each result that is not "done".
5. **The same spectrum (P37).** Two results are the same when their four
   arrays and `coord_start` and `coord_step` are equal, exactly (in
   Hz/m/√Hz). With one \|γ\| and one spectrum, the card draws one series in
   each lane, as before.
6. **The bands.** For each target with `acoustic_resonances`: its bands
   `[f - bw/2, f + bw/2]` in the color of the target, in the form
   `{lo, hi, color}` of phase 4 (section 4.4, item 3). The tooltip names the
   target of a band. A note names each target without resonances.
7. **The check line (P30).** For each target: the `Result` of
   `acoustic.resonance-energy` from `check_results.results` (by `check_id`
   and `target`, section 3.4 of the design). The line gives the state, and the
   value and the limit with the unit, or the reason. Without that result
   (the check was not selected), the line says that the check did not run.
   The card does not calculate a share of the energy, and it has no table of
   band peaks. Its data has no `bands` entry.
8. **The command (D13).** `cli.py` adds `"gradient.spectrum"` to `analyses`
   when the `gradient-spectrum` card is on the page.
9. **`scripts/cards_scale.py`.** The `spectrum` mode runs `run_checks(...,
   select=[], analyses=["gradient.spectrum"])` with
   `tests/profiles/example_a.toml`, and gives the matrix to the card. It
   gives the time of `run_checks` and the time of the card separately.
10. **`TODO.md`.** Amendment 2: no change. Phase 2c removed the item of
    fact 18.

### 4.7 Phase 7: the PNS card and the PNS lane

Amendment 2 changed items 2 to 4 and 6, and added item 7 (P33, P38, P39).

1. Remove the option `gradient_asc`, its flag and its configuration key.
2. **The PNS card.** For each target: its `AnalysisResult` of
   `pns.safe.levels` from the matrix. With the state "done": the peak, its
   time, the axis peaks and the hardware name, from the `meta` of
   `pns_total`, in percent: `100 * v / meta["threshold"]` of `pns_above_0`
   (P38). The button goes to the TR of the peak
   (`pulseq_analysis.pns.peak_tr_window`). With another state: its reason.
   Without a matrix, or without the analysis: a note (P23). The card does
   not call the SAFE model.
3. **The PNS lane.** `file.pns` becomes a list, one entry for each target
   with the state "done": the target name, its color, `hw` (from
   `profile.models["pns.safe"]`), `dtS`, `binSamples`, `gammaMagnitude`
   (\|γ\| of the target, `units`), `threshold` (`meta["threshold"]`), the
   summary, `levels` (the `min` and `max` arrays of `pns_total` in Hz/T,
   encoded as now), and `runs` (the arrays `start` and `end` of
   `pns_above_0`, in s: its `coord_unit` is `"s"`). The time of a sample of
   `pns_total` comes from `coord_start` and `coord_step`, not from the names
   `t0_s` and `step_s` of `v0.1.0rc2` (amendment 1). `gradScale` goes away.
   The data format of the diagram changes, and its number goes up.
4. **The JavaScript.** `diagram.js` decodes one model for each entry. The PNS
   lane has one series for each target, in percent of its `threshold`
   (section 4.4), one domain for all, and the runs as marks in the color of
   the target (P22). The status text gives the peak of each target.
   `pns_lanes.js` runs the SAFE model of a zoomed view on the gradient
   samples in Hz/m, and divides the result by `gammaMagnitude`. Until phase
   7b, the samples are the mT/m values of the diagram data (made with
   `PROTON_GAMMA`) times `gradHzPerValue` of `SeqLanes` (fact 22).
5. `scripts/cards_scale.py`: the `pns` and `diagram --pns-lanes` modes run
   `run_checks(..., select=[], analyses=["pns.safe.levels"])` with
   `tests/profiles/example_a.toml`, and give the matrix to the card. They
   give the time of `run_checks` and the time of the card separately.
6. `tests/test_pns_lanes_golden.py` stays: it compares the exact PNS of the
   JavaScript with `pulseq_analysis.pns_levels`, both in percent of
   \|γ\|. It also runs with a negative gamma.
7. **The older result form (P39).** One function (in `registry.py`) raises
   `ValueError` for a matrix that has a series of `pns.safe.levels` with a
   unit other than `"Hz/T"`. `build_cards` calls it. The command calls it
   after it reads a `--check-results` file, and gives status 1 and no page.

### 4.7b Phase 7b: the diagram and the RF exposure card in the gamma of a target (amendment 2)

P33, P36, D18, D19. Design, section 4.8.

1. **The diagram data in the units of the file.** `diagram_data.py` keeps
   the gradient values in Hz/m and the RF magnitude in Hz, with no gamma.
   `waveforms.py` gives the exact lanes of a window in Hz/m and Hz.
   `seq_lanes.js` reads Hz/m: `GRAD_HZ_PER_VALUE` and `gradHzPerValue` go
   away, and `pns_lanes.js` and `rf_profiles.js:827` use the Hz/m values.
   The data format of the diagram changes, and its number goes up. Remove
   `units.PROTON_GAMMA`: its last uses are here.
2. **The control.** The diagram has the control of phase 2c with
   `gamma_entries(..., signed=True)`. The gradient lanes show `value / γ *
   1e3` (mT/m) and the RF lane `|value| / |γ| * 1e6` (µT) for the selected
   entry. The RF phase does not change (D18). A change of the entry rescales
   the lanes and keeps the view.
3. **The domains and the tick labels.** Python gives the peak of each lane
   in the units of the file. A pure function of `chart_math.js` (the form
   of `waveforms._value_domain`) gives the domain, the ticks and the labels
   for the selected gamma, with node tests. For `seq.system.gamma` of a
   file, it gives the domains and labels of the baseline.
4. **The RF exposure card.** `rf_exposure.py` takes the gamma as an
   argument (its magnitude, `units`). The card writes one table for each
   entry of `gamma_entries(..., signed=False)`, and the control of phase 2c,
   with the card script `gamma-select`.
5. Without targets, each card shows the values of `seq.system.gamma`, as on
   the baseline.
6. The tests: the values for a negative gamma are the values of its
   magnitude for \|B1\| and the energy, and the negative of the gradient
   values. The golden tests of the diagram (`test_seq_lanes_golden.py`,
   `test_pns_lanes_golden.py`) read Hz/m.

### 4.8 Phase 8: the RF profile card on targets

Amendment 2 changed items 2 to 4 (P33, P35, D18).

1. The Python side sends the `ppm` terms of each RF event (`freq_ppm` and
   `phase_ppm`), and no B0 and no gamma.
2. The browser calculates `freq_hz = freq_offset + freq_ppm * 1e-6 * γ * B0`
   (and the same for the phase) with the signed γ and the B0 of each target
   (D18), and \|B1\| with \|γ\|. It overlays the profiles, one series for
   each group of targets with the same γ and B0, in the color of the first
   target of the group.
3. Without a target that gives B0: a pulse with a `ppm` offset has a note,
   and the other pulses draw as now. Without targets, \|B1\| uses
   `seq.system.gamma`.
4. `rf_profiles.py`: the Python reference takes `b0_t` and `gamma_hz_per_t`
   as arguments, not `seq.system.B0` and `seq.system.gamma`, and uses the
   signed gamma for a `ppm` offset. The golden tests compare the JavaScript
   and Python for two values of B0, and for a gamma and its negative.
5. The data format of the card changes, and its number goes up.

### 4.9 Phase 9: the check summary card

1. `cards/checks.py` (new): `CardSpec("checks", 5, ...)`, with `publishes=
   ("goto",)`. It is built only when there are targets.
2. The content of design section 4.3: the legend, the sources and the unused
   sections of each target, one row for each check (state, value and limit
   with the unit, detail, location with a "Show" button, a mark for a
   required check, the link to the specification), the closed element "What
   this check promises" (P24), the reasons of each result that is "not
   evaluated" or "error", each analysis result that is not "done", and the
   number of findings with the number omitted.
3. Without a matrix: the card says that no checks were run.
4. The command: `--max-findings N` (default 100) applies
   `with_max_findings(N)` to the matrix. A matrix from `--check-results`
   gets it too, so the smaller limit applies. `--fail-on-check` makes the
   status `ResultMatrix.exit_status()`, and 1 when 1 applies for another
   reason (design section 4.2).

### 4.10 Phase 10: the findings in the cards

1. **The timing card.** It is built only when the matrix has a result of
   `timing.pypulseq` or `timing.rasters`. For each target: the result, and a
   table of its findings (code, message, block, time, "Show" button), and the
   number omitted. It does not call `check_timing`.
2. **The gradient limits card.** For each target: a list of the findings of
   the three gradient checks, with a "Show" button for each, and the number
   omitted.

### 4.11 Phase 11: the documents and the example

1. `docs/usage.md`: each section that names a check, an option that went
   away, an old module path or the exit status (sections 2 to 8, and
   "Rotation extension"). The new inputs, the summary card, the targets in
   the cards, and the lane format of phase 4. Amendment 2: the gamma of a
   target in the cards (design, section 4.8), a negative gamma, the control
   of P36, and the refusal of a result file of `pulseq-checks` `v0.1.0rc4`
   (P39). The table of the times of the
   cards: the PNS and spectrum rows give the time of their analysis in
   `run_checks` and the time of the card (section 4.6, item 9, and section
   4.7, item 5). The cost of the analyses with `fast_only` (D15).
2. `README.md`: the questions of "What it is for" and the list of cards.
3. `CHANGELOG.md`: the entry `0.2.0rc3` with "Breaking changes", "Added" and
   "Fixed". Each removed name or option, with what replaces it.
   Amendment 2: under "Added", each card uses the gamma of each target, and
   a negative gamma is valid. The proton rule was not in a release (it came
   in phase 3), so it is not a breaking change.
   `pulseq_reports.grad_spectrum` is one of them: `gradient_spectrum` and
   `GradientSpectrum` are in `pulseq_analysis.grad_spectrum` (in Hz/m/√Hz),
   and the check `acoustic.resonance-energy` replaces `band_peaks` and
   `BandPeak`.
4. **The example (P27).** `examples/targets/` (new): two profiles whose names
   say that they are examples, with the values of section 4.3, item 7, and
   resonance bands that a comment calls invented. `examples/gre_report.py`
   reads them, calls `run_checks` with `analyses=("pns.safe.levels",
   "gradient.spectrum")` and `build_cards`, and writes the page. Run
   it, check the page in the browser, and commit `docs/examples/gre.html`.

### 4.12 Phase 12: the release

The version `0.2.0rc3`, the date in `CHANGELOG.md`, the results of this plan
(section 8), and the status of the design. After the merge, the tag
`v0.2.0rc3`, only when the user tells you to.

## 5. Phases

### Phase 1: the verdicts and the defaults

Branch: `feature/remove-verdicts`. Wave 1. Section 4.1.

**Task 1.1.** Tier H. Items 1 to 3 and 6 of section 4.1 (`page.py`,
`registry.py`, `cli.py`, `__init__.py`).

**Task 1.2.** Tier H. Items 4, 5, 7 and 8 (the options, the spectrum module,
the cards and the scale script).

**Task 1.2a.** Tier X. Item 9 (the version), before task 1.4.

**Task 1.3.** Tier M. The tests and `TESTS.md`: remove the tests of `Check`,
`Card.checks`, the exit status 2, `check_norms`, `coil`, the default limits
and the example hardware. Add these tests:

- An error card has `error`, and the command gives 1.
- A gradient limits card without limits has no percent columns.
- A PNS card and a diagram without `gradient_asc` have no PNS data.
- A spectrum card has no bands.

**Task 1.4.** Tier X. The comparison (section 3.5) and the review.

Tasks 1.1 and 1.2 run at the same time. Task 1.3 starts when they are done.

Checks:

- [ ] `rg 'Check\b|\.checks|check_norms|PRISMA|GradientCoil|_default_limits'
      src tests` finds nothing.
- [ ] The comparison shows only the differences of section 3.5.
- [ ] `scripts/check` passes.

### Phase 2: the dependencies

Branch: `refactor/use-pulseq-analysis`. Wave 2. Section 4.2.

**Task 2.1.** Tier X. The pins and `uv.lock` (item 1).

**Task 2.2.** Tier M. Items 2 to 4 and 6.

**Task 2.3.** Tier M. Item 5 (the tests).

**Task 2.4.** Tier X. The comparison (item 7) and the review.

Task 2.1 comes first. Tasks 2.2 and 2.3 run at the same time.

Checks:

- [ ] `uv.lock` has the three commits of item 1.
- [ ] No module of `src/pulseq_reports/` has the name of a copied module.
- [ ] `rg 'encode_tables|decode_tables' src tests scripts` finds nothing.
- [ ] `rg 'from \.\.?(grad_limits|pns|pns_levels|asc|extensions|sampling|seq_index|seq_utils) import'
      src tests` finds nothing.
- [ ] The pages are equal byte for byte.
- [ ] `scripts/check` passes.

### Phase 2b: the move to `v0.1.0rc5`

Branch: `refactor/pulseq-rc5`. Wave 3b. Section 4.2b. Amendment 2.

**Task 2b.1.** Tier X. The pins and `uv.lock` (item 1), and `units.py`
(item 2).

**Task 2b.2.** Tier M. Items 2 and 3: the imports and the names in `src`,
`tests` and `scripts`, with `TESTS.md` where a test changes.

**Task 2b.3.** Tier X. The comparison (item 5) and the review.

Task 2b.1 comes first.

Checks:

- [ ] `uv.lock` has the three commits of section 4.2b, item 1.
- [ ] `rg 'seq_utils\.GAMMA|import[^\n]*\bGAMMA\b' src tests scripts` finds
      nothing.
- [ ] `rg '\.(peak|rms|whole_rms|vector_peak)_mt_per_m|\.(max_slew|slew|junction)_t_per_m_per_s' src tests scripts`
      finds nothing. (`max_grad_mt_per_m` and `max_slew_t_per_m_per_s` of
      `HardwareLimits` stay.)
- [ ] `rg 'abs\(.*gamma' src --glob '*.py'` finds only `units.py`,
      `cards/rf_profile.py` and `rf_profiles.py` (phase 8 changes them).
- [ ] The pages differ only as the row `2b` of section 3.5 says.
- [ ] `scripts/check` passes.

### Phase 2c: the gamma of each target

Branch: `feature/target-gamma`. Wave 3b, after phase 2b. Section 4.2c.
Amendment 2.

**Task 2c.1.** Tier X. `units.py`, `targets.py` and `registry.py` (items 1
to 3).

**Task 2c.2.** Tier H. The control (item 4), with node tests of any pure
function.

**Task 2c.3.** Tier M. Items 5 and 6: `TODO.md`, the tests and `TESTS.md`.

**Task 2c.4.** Tier X. The comparison and the review.

Task 2c.1 comes first. Tasks 2c.2 and 2c.3 run at the same time.

Checks:

- [ ] `rg '\.supported|supported=' src --glob '*.py'` finds nothing.
- [ ] `rg 'abs\(.*gamma' src --glob '*.py'` finds only `units.py`,
      `cards/rf_profile.py` and `rf_profiles.py` (phase 8 changes them).
- [ ] A page without targets is equal to the baseline.
- [ ] `scripts/check` passes.

### Phase 3: the targets and the matrix

Branch: `feature/report-targets`. Wave 3. Section 4.3.

**Task 3.1.** Tier X. The interfaces: `ReportTarget`, `report_targets`, the
new arguments of `build_cards` and `ReportContext`, and
`show_button_html`. Write them first, so that tasks 3.2 to 3.4 use them.

**Task 3.2.** Tier H. The colors and the legend (items 3 and 4), with the
`dataviz` skill.

**Task 3.3.** Tier H. The command (item 6) and the test profiles (item 7).

**Task 3.4.** Tier M. The tests and `TESTS.md`: the rules of item 2, the
command arguments and their errors, a run with two targets that gives the
matrix to `build_cards`, and a `--check-results` file.

Tasks 3.2, 3.3 and 3.4 run at the same time after task 3.1.

Checks:

- [ ] A page without targets is equal to the baseline.
- [ ] Seven targets, two targets with one name, and a `Sequence` with
      another gamma each give `ValueError`.
- [ ] The browser check of section 3.6.
- [ ] `scripts/check` passes.

### Phase 4: the chart support

Branch: `feature/chart-series`. Wave 3. Section 4.4.

**Task 4.1.** Tier H. Items 1 to 3, and node tests of the new pure functions
of `ChartMath`, with their `TESTS.md` entries.

**Task 4.2.** Tier X. The comparison and the browser check: the charts of the
example page are as on the baseline. Then a test page (not committed) with a
lane with two series, marks and colored bands, in both themes.

Checks:

- [ ] The example page shows no difference in the browser.
- [ ] `scripts/check` passes.

### Phase 5: the gradient limits card on targets

Branch: `feature/gradient-limits-targets`. Wave 4. Section 4.5.

**Task 5.1.** Tier H. Section 4.5, with the tests and `TESTS.md`.

**Task 5.2.** Tier X. The browser check with two targets, and the review.

Checks:

- [ ] A target without limits has no percent column.
- [ ] A target with a negative gamma has the percent of its magnitude, and
      the same percent as the gradient checks (amendment 2).
- [ ] With two \|γ\|, the control shows the table of each (amendment 2).
- [ ] `scripts/check` passes.

### Phase 6: the spectrum card on targets

Branch: `feature/spectrum-targets`. Wave 4, after phase 2c. Section 4.6
(amendments 1 and 2).

**Task 6.1.** Tier M. Item 1 of section 4.6: the deletions and the imports,
with `TESTS.md`.

**Task 6.2.** Tier H. Items 2 to 10 of section 4.6 (Python and
`spectrum.js`), with the tests and `TESTS.md`. Test with hand-made
`ResultMatrix` objects: two targets with the same spectrum and gamma, two
with different spectra, two with γ and -γ (one group), two with different
\|γ\| (two groups), a target without resonances, a result that is not
"done", a matrix without the analysis, and no matrix.

**Task 6.3.** Tier X. The data format of the card first (before task 6.2),
the browser check with two targets, and the review.

Task 6.1 and the data format of task 6.3 come first. Task 6.2 starts when
both are done.

Checks:

- [ ] Each target with resonances has its bands, in its color.
- [ ] Each target has its line of `acoustic.resonance-energy`.
- [ ] Each group of P37 has one series in each lane (amendment 2).
- [ ] `rg 'grad_spectrum|band_peaks|BandPeak' src scripts` finds nothing (the
      card imports no spectrum module). `rg 'pulseq_reports\.grad_spectrum' tests`
      finds nothing.
- [ ] Without a matrix, the card has a note and no chart.
- [ ] `scripts/check` passes.

### Phase 7: the PNS card and the PNS lane

Branch: `feature/pns-targets`. Wave 4, after phase 2c. Section 4.7
(amendment 2).

**Task 7.1.** Tier H. Items 1, 2, 3, 5 and 7 (Python), with the tests and
`TESTS.md`.

**Task 7.2.** Tier H. Item 4 (JavaScript), with node tests of the new pure
functions of `pns_lanes.js`.

**Task 7.3.** Tier X. The data format between tasks 7.1 and 7.2 (write it
first), the browser check with two targets (the overlay, the marks, the exact
PNS of a zoomed view), and the review.

Checks:

- [ ] No card calls `pns_levels`, `pns_levels_for` or `pns_prediction`.
- [ ] Without a matrix, the card and the lane have no PNS.
- [ ] Each PNS percent is `100 * v / meta["threshold"]` (amendment 2).
- [ ] A `--check-results` file with a PNS series in the unit `"1"` gives
      status 1 and no page (amendment 2).
- [ ] `rg 'gradScale|pns_above_1' src tests` finds nothing (amendment 2).
- [ ] `test_pns_lanes_golden.py` passes, also with a negative gamma.
- [ ] `scripts/check` passes.

### Phase 7b: the diagram and the RF exposure card in the gamma of a target

Branch: `feature/diagram-gamma`. Wave 4, after phase 7. Section 4.7b.
Amendment 2.

**Task 7b.1.** Tier H. Items 1, 4 and 5 (Python, and the data format), with
the tests and `TESTS.md`.

**Task 7b.2.** Tier H. Items 1 to 3 (JavaScript), with node tests of the
new pure functions.

**Task 7b.3.** Tier X. The data format first, the comparison, the browser
check with two targets of γ and -γ (the control, the sign of the gradient
lanes, the same \|B1\|), and the review.

Checks:

- [ ] `rg 'PROTON_GAMMA|42\.576e6|\b42576\b|GRAD_HZ_PER_VALUE|gradHzPerValue' src tests/js`
      finds nothing.
- [ ] Without targets, the browser shows the values of the baseline.
- [ ] `scripts/check` passes.

### Phase 8: the RF profile card on targets

Branch: `feature/rf-profile-targets`. Wave 4, after phase 2c, when one of
phases 5 to 7 is merged. Section 4.8 (amendment 2).

**Task 8.1.** Tier H. Items 1, 4 and 5 (Python), with the tests.

**Task 8.2.** Tier H. Items 2 and 3 (JavaScript), with the node tests and
the golden tests.

**Task 8.3.** Tier X. The data format first, the browser check with two
targets of different B0, a target with a negative gamma, and a pulse with a
`ppm` offset, and the review.

Checks:

- [ ] No module reads `seq.system.B0`. The RF profile card reads
      `seq.system.gamma` only without targets (amendment 2).
- [ ] A `ppm` offset uses the signed γ (D18).
- [ ] `rg 'abs\(.*gamma' src --glob '*.py'` finds only `units.py`
      (amendment 2).
- [ ] `scripts/check` passes.

### Phase 9: the check summary card

Branch: `feature/check-summary`. Wave 5. Section 4.9.

**Task 9.1.** Tier H. The card (items 1 to 3), with the tests and
`TESTS.md`.

**Task 9.2.** Tier M. The command (item 4), with the tests.

**Task 9.3.** Tier X. The browser check (a page with a pass, a fail, a "not
evaluated" result, an analysis result that is not "done", and findings), and
the review.

Checks:

- [ ] Each state of a result, and each state of an analysis result, is on the
      card.
- [ ] `--fail-on-check` gives the statuses of design section 4.2.
- [ ] `scripts/check` passes.

### Phase 10: the findings in the cards

Branch: `feature/findings-in-cards`. Wave 5. Section 4.10.

**Task 10.1.** Tier H. The timing card (item 1), with the tests.

**Task 10.2.** Tier H. The gradient limits findings (item 2), with the tests.

**Task 10.3.** Tier X. The browser check (each "Show" button moves the
diagram to the correct block), and the review.

Checks:

- [ ] No module of `src/pulseq_reports/` calls `check_timing`.
- [ ] The number omitted is on each list that the findings limit cuts.
- [ ] `scripts/check` passes.

### Phase 11: the documents and the example

Branch: `docs/reports-on-checks`. Wave 6. Section 4.11.

**Task 11.1.** Tier H. `docs/usage.md` and `README.md`.

**Task 11.2.** Tier M. `CHANGELOG.md`.

**Task 11.3.** Tier X. The example (item 4), the browser check of the example
page, and the review.

Checks:

- [ ] `rg 'check_norms|gradient_asc|--max-grad|--coil|PRISMA|exit status 2|pulseq_reports\.(grad_limits|grad_spectrum|pns|seq_index)' docs README.md`
      finds only the history in `CHANGELOG.md`.
- [ ] The example profiles have no vendor values (P9).
- [ ] `scripts/check` passes.

### Phase 12: the release

Branch: `chore/release-0.2.0rc3`. Wave 7. Section 4.12.

**Task 12.1.** Tier X. All of section 4.12.

Checks:

- [ ] `scripts/check` passes, and CI passes.
- [ ] The tag only when the user tells you to.

## 6. Summary of parallel work

| Wave | Phases | Condition to start |
|---|---|---|
| 1 | 1 | This plan is merged. |
| 2 | 2 | Phase 1 merged. |
| 3 | 3, 4 | Phase 2 merged. |
| 3b | 2b, then 2c | Amendment 2 merged (phase 2b). Phase 2b merged (phase 2c). |
| 4 | 5, 6, 7, then 7b and 8 | Phase 2c merged (all). Phase 7 merged (phase 7b). One of phases 5 to 7 merged (phase 8). At most three open. |
| 5 | 9, 10 | Phase 3 merged (phase 9). Phases 3 and 5 merged (phase 10). |
| 6 | 11 | Phases 5 to 10 merged. |
| 7 | 12 | Phase 11 merged. |

## 7. Questions still open

None. The user decided D1 to D11 on 2026-10-04, and P33 to P39 for
amendment 2. D16 to D19 follow from them, and the approval of amendment 2
approves them. The user chose the
alternative for D4 (remove `encode_tables`) and D10 (`0.2.0rc3.dev0` from
phase 1), and the proposal for the others.

## 8. Results

### 8.1 Changes to the order

- 2026-10-04: The user approved the start of phase 4 at the same time as
  phase 1, not after phase 2 (section 3.3, wave 3). Phase 4 edits only
  `lane_chart.js` and `chart_math.js`, which phases 1 and 2 do not edit
  (section 3.4). Its baseline is `main` at `9276cfd`.
- 2026-10-04, amendment 1: phases 1 to 4 were merged (#111 `cffad7c`, #112
  `cc87563`, #113 `7ae78af`, #110 `ca322b0`). `pulseq-checks` and
  `pulseq-analysis` then released `v0.1.0rc4`. A review of the merged work
  found that it reads no `Series` field, so it needs no refactor for the new
  series names. It found one duplicate: `grad_spectrum.py` is the source of
  `pulseq_analysis.grad_spectrum`. The user decided P29 to P32 of the design
  and D12 to D14. New phase 2b moves the pins. Phase 6 deletes the duplicate
  and reads the spectrum from the matrix. Phase 7 uses the new series names.
- 2026-10-04, review of amendment 1: the user decided D15 (`fast_only`
  keeps the analyses of the cards) and narrowed P30 (it does not change P6).
  Facts 1 to 13 are marked as the state before phase 1. The user also
  decided to replace P21 with the gamma of each target, in all cards, in
  `0.2.0rc3`. That is amendment 2 and design version 5, in a separate pull
  request. Until then, the text of amendment 1 keeps P21.
- 2026-10-04, amendment 2: `pulseq-analysis` `v0.1.0rc5` gives no value with
  a gamma, and `pulseq-checks` `v0.1.0rc5` converts with \|γ\| of the
  target (and fixed a false pass of its gradient checks for a negative
  gamma). The user decided P33 to P39: a negative gamma is valid, the pins
  are `v0.1.0rc5`, each card uses the gamma of each target, a control for
  the sequence-only cards, the spectrum by \|γ\| group, the PNS percent
  from `meta["threshold"]`, and the refusal of a result file of
  `v0.1.0rc4`. Phase 2b became the refactor to `v0.1.0rc5`. Phases 2c and
  7b are new. Phases 5 to 8 and 11 changed.
