# Design: pulseq-reports on pulseq-checks and pulseq-analysis

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: design, version 5, written on 2026-10-04. The user made the decisions
of sections 9.3 to 9.5 on the same day. This is not an implementation plan. It gives
the goals, the principles and the design decisions for the work in
pulseq-reports. An implementation plan comes next.

History:

- Version 1 (commit `475a1eb`) gave the design of the checks and the reports.
  The part for the checks moved to `pulseq-checks`, in
  [`docs/plans/pulseq-checks.md`](https://github.com/mdtisdall/pulseq-checks/blob/main/docs/plans/pulseq-checks.md).
- Version 2 (commit `a322517`) gave only the work in pulseq-reports, for
  `pulseq-checks` `v0.1.0rc2`.
- Version 3 (commit `9276cfd`) is for two packages. The measurement modules moved
  from `pulseq-checks` to a new package, `pulseq-analysis`
  ([`docs/plans/pulseq-analysis.md`](https://github.com/mdtisdall/pulseq-checks/blob/main/docs/plans/pulseq-analysis.md)
  of pulseq-checks). Section 8 of that plan gives the work in pulseq-reports,
  and this version follows it.
- Version 4 (commit `2a516b4`) is for `pulseq-checks` `v0.1.0rc4` and
  `pulseq-analysis` `v0.1.0rc4`. Each series has a coordinate unit, the
  gradient spectrum moved to `pulseq-analysis`, and the check
  `acoustic.resonance-energy` compares the spectrum with the resonances of a
  target. Section 3.4 gives the changes. Principle 10 and the decisions P29
  to P32 are new. Phases 1 to 4 of the implementation plan were done with
  version 3.
- Version 5 (this version) is for `pulseq-checks` `v0.1.0rc5` and
  `pulseq-analysis` `v0.1.0rc5`. No value of `pulseq-analysis` uses a gamma
  now, and `pulseq-checks` converts with the magnitude of the gamma of each
  target. pulseq-reports does the same: each card uses the gamma of each
  target, and a gamma can be negative. This replaces the proton rule P21.
  Section 3.5 gives the changes. Principle 8 is new, principle 11 is new, and
  the decisions P33 to P39 are new.

The `pulseq-checks` and `pulseq-analysis` documents refer to versions 1 and 2
by commit, so their links still work. Both packages are stable for this work,
at the tags of section 5.

## 1. Goal

Remove all check behavior from pulseq-reports. pulseq-reports gets each
verdict from `pulseq-checks`, and each measurement that the packages share
from `pulseq-analysis`.

After this work:

- **A card describes. A card does not decide.** No card calculates a pass or
  a fail. The only verdicts on a page come from a `pulseq-checks` result.
- **A report shows the results of the checks.** A summary card near the top
  of the page shows the result matrix: what passed, what failed, and what was
  not asserted. The command `pulseq-report` gets the matrix from `run_checks`,
  the same function that `pulseq-check` uses, or from a result file of an
  earlier run.
- **The PNS comes from the result matrix.** The PNS card and the PNS lane of
  the diagram show the result of the analysis `pns.safe.levels` of each
  target. The report does not run the SAFE model a second time.
- **The gradient spectrum comes from the result matrix.** The gradient
  spectrum card shows the result of the analysis `gradient.spectrum`, the
  resonance bands of each target, and the result of the check
  `acoustic.resonance-energy` of each target. The report does not calculate
  the spectrum a second time.
- **The cards read target profiles.** A card that needs scanner context (the
  limits, the SAFE parameters, the acoustic resonances, B0) reads it from the
  target profile format of `pulseq-checks`. The card options for scanner
  context go away.
- **No hidden defaults.** A report uses defaults as `pulseq-checks` does. A
  value that no target gives is not replaced by a default. The card says what
  is missing.
- **No duplicate code.** pulseq-reports deletes its copies of the modules
  that moved, and imports them from `pulseq-analysis`.
- **The gamma of the target.** A card changes a value into tesla units with
  the gamma of a target, by the rule of `pulseq-checks`. pulseq-reports
  supports each nucleus, also a nucleus with a negative gamma.

The main goal of a report is still to describe the sequence. A report with
no targets is complete. It has no verdicts and no check summary.

## 2. Principles

1. **One source of verdicts.** A verdict (pass, fail, not evaluated, error)
   comes only from a `pulseq-checks` `Result`. A card that marks a value or a
   place against a limit (for example a percent above 100, or a block above
   the slew limit) takes the mark from a check result, from its findings, or
   from an analysis result that uses the same threshold as the check. It does
   not make its own comparison. Thus a card and the summary cannot disagree.
   (In version 1, the PNS card failed from 99.995 % because it rounded, and
   `pns.safe` failed from 100 %.)
2. **One target profile format.** pulseq-reports reads targets with
   `pulseq_checks.read_profile` and uses `TargetProfile`. It does not define a
   second format.
3. **Defaults as in `pulseq-checks`.** When `pulseq-checks` gives "not
   evaluated" because a target does not give a value, the card shows no value
   for that target, and a note with the reason. The card does not use the
   pypulseq defaults, the example SAFE hardware of pypulseq, or a built-in
   coil. The limits of a `Sequence` object (`seq.system`) are used only with
   the explicit opt-in that `pulseq-checks` has (`limits_from_sequence`, for a
   `Sequence` object only), and the card says where the limits came from.
4. **Each card selects its own targets.** A card can use all the targets,
   one target, or no target. Section 4.4 gives the rule for each card. When a
   card shows several targets, it overlays them or gives a column for each.
5. **One color for each target.** The page gives each target one color, in
   the order of the targets. Each card that shows targets uses that color for
   that target, and the page has one legend for the targets. A report has at
   most 6 targets (decision P28).
6. **Only documented names.** pulseq-reports imports only the names that
   `pulseq-analysis` and `pulseq-checks` document, in their `docs/usage.md`.
   It does not import a private name (a name that starts with `_`).
7. **The file gives the rasters.** A card does not read a value from
   `seq.system` that the file does not give. `seq.read` keeps the rasters of
   the file in `seq.grad_raster_time` and the other raster attributes, and
   leaves `seq.system` at the `Opts` of the caller. Values that a file does
   not give (limits, B0, dead times) come from a target, or they are missing.
   A file older than format 1.4.0, or a damaged file, can leave out a raster.
   Then pypulseq uses its own default. A card does not: it mirrors R8 of the
   `pulseq-checks` design, and uses the raster of a target, or shows a note
   that names the missing raster.
8. **The gamma of the target.** pulseq-reports changes Hz into T, and Hz/m
   into T/m, with the gamma of a target, as `pulseq-checks` does (decisions
   P33 and P35). Version 4 supported only the proton gamma (P21). Version 5
   removes that rule.
   - **The gamma of a target** is `target.make_opts().gamma`: the `opts.gamma`
     of the profile, or the default of pypulseq (42.576 MHz/T) when the
     profile does not give it. This is the one default, as in
     `pulseq-checks`. Without targets, a card uses `seq.system.gamma`: the
     default of pypulseq for a file that `seq.read` reads, or the gamma that a
     Python caller gave to its `Sequence` object.
   - **The sign.** A gamma can be negative (for example ¹⁵N or ²⁹Si). A
     magnitude uses \|γ\|: a peak, a slew rate, an RMS, \|B1\|, an energy,
     the spectrum, a PNS value and a percent of a limit. A signed value uses
     γ: a gradient waveform, and the change of a `ppm` offset into Hz (as
     pypulseq does). A value that needs no gamma does not use one: the RF
     phase of the file, the Bloch simulation in Hz, and the frequencies.
   - **A gamma that is 0 or not finite** is an error of the arguments:
     `report_targets` and `build_cards` raise `ValueError`. `pulseq-checks`
     `v0.1.0rc5` does not refuse it (section 3.5).
   - **Sequence-only cards.** A card whose values depend only on the
     sequence and one gamma (the diagram, the RF exposure card, the peaks of
     the gradient limits card) shows them for one gamma. When the targets
     give more than one gamma, a control on the card selects the target
     (decision P36).
   - Section 4.8 gives each conversion of the cards.

9. **One source of the PNS.** In a report, the PNS of a target comes only
   from the analysis result `pns.safe.levels` in the result matrix. Without a
   result matrix, or without that analysis result, the PNS card and the PNS
   lane show a note, not a PNS (decision P23).
10. **One source of the gradient spectrum.** In a report, the gradient
    spectrum comes only from the analysis result `gradient.spectrum` in the
    result matrix. The card does not call `pulseq_analysis.grad_spectrum`.
    Without a result matrix, or without that analysis result, the card shows a
    note and no chart (decision P31). A report has no default target: a
    caller that wants a spectrum gives a target, and the spectrum goes through
    `pulseq-checks` and `pulseq-analysis`. The share of the gradient energy in
    the resonance bands is a comparison with target data. It comes only from
    the check `acoustic.resonance-energy` (principle 1, and decision L11 of the
    `pulseq-analysis` plan `docs/plans/series-coordinate.md`).
11. **One role for each package.** pulseq-reports uses each package for its
    role, and does not do the work of another package:
    - **`pulseq-analysis` measures the sequence.** Its values have no gamma
      and no data of a target. They are magnitudes in the units of the
      `.seq` file: Hz/m, Hz/m/s, Hz/m/√Hz and Hz/T. Data of a target goes in
      only as an explicit argument (`hardware`, `thresholds_hz_per_t`).
    - **`pulseq-checks` applies a target.** It reads the profile, gives the
      data of the target to the analyses (the bindings), converts with
      \|γ\| of the target, and gives the verdicts and the findings. Its
      result JSON does not repeat the data of the target, for example the
      gamma.
    - **pulseq-reports shows the results, and converts for the display.** It
      reads the targets with `pulseq-checks`. It takes the verdicts, the
      findings and each analysis result that needs a target from the result
      matrix. It takes a value that needs no target from the matrix when the
      analysis gives a series (`gradient.spectrum`, principle 10), and from
      `pulseq-analysis` when the analysis gives no series (the peaks of
      `gradient.limits`). It converts the units for the display with the
      rule of principle 8.

## 3. The state of the code

Sections 3.1 to 3.3 give the state at version 3, before phase 1 of the
implementation plan. Section 3.4 gives the changes of the `v0.1.0rc4`
releases, and section 3.5 the changes of the `v0.1.0rc5` releases. Where
they do not agree, the later section is correct.

### 3.1 pulseq-reports (`main` at `a322517`, version `0.2.0rc2`)

The check behavior that this work removes:

| What | Where |
|---|---|
| `Check` and `Card.checks` | `page.py` |
| The timing check (`check_timing`, pass or fail, error table) | `cards/timing.py` |
| The gradient limits check and `check_norms` | `cards/gradient_limits.py`, `options.py` |
| The PNS check (100 % rule of the status line) | `cards/pns.py` |
| A failed check named `error` for a card that raises | `registry.py` (`_error_card`) |
| Exit status 2, and the warning about default limits | `cli.py` |
| `seq.system` limits when no limits are given | `cli.py` and `cards/gradient_limits.py` (`_default_limits`) |
| The example SAFE hardware of pypulseq when no `.asc` file is given | `pns.py`, `pns_levels.py`, `cards/pns.py`, `cards/diagram.py` |

The scanner context that is now in card options:

| Option | Cards |
|---|---|
| `limits` (`HardwareLimits`) | `gradient-limits` |
| `gradient_asc` | `pns`, `diagram` (PNS lane) |
| `coil` (`GradientCoil`, default `PRISMA_AS82`) | `gradient-spectrum` |
| `check_norms` | `gradient-limits` |

Values that cards read from `seq.system` of a file, where `seq.system` has
only the defaults of pypulseq:

- B0 and gamma in the RF profile card (`cards/rf_profile.py`,
  `rf_profiles.py`), to change `freq_ppm` and `phase_ppm` into Hz.
- Gamma in the diagram (`cards/diagram.py`) and in `grad_spectrum.py`, to
  change Hz/m into mT/m. Only the proton gamma is supported (principle 8 of version 4).

The rasters already follow principle 7 (#105, and #106 for the junction step
of `gradient_limits`).

The copies of the moved modules are `grad_limits`, `pns`, `pns_levels`,
`asc`, `extensions`, `sampling`, `seq_index` and `seq_utils`. Compared with
`pulseq-analysis` `v0.1.0rc2`:

| Module | Difference |
|---|---|
| `asc` | None. |
| `extensions`, `sampling`, `seq_index`, `seq_utils` | Docstrings only. |
| `grad_limits` | `pulseq-analysis` has no `HardwareLimits`, no `limits` argument of `gradient_limits` and no `GradientLimits.limits` field. Its `gradient_limits` refuses the rotation extension itself. It adds `block_gradient_values` and `BlockGradientValues`. |
| `pns`, `pns_levels` | `pulseq-analysis` takes a SAFE hardware struct (`hardware=`) and `thresholds`. `PnsLevels.above` (a dict from each threshold to its `PnsInterval` runs) replaces `above_limit`. `SAFE_MODEL` and `hw_from_dict` are in `pulseq_checks.safe_model`, not here. |

pulseq-reports also uses two private names of these modules:
`grad_limits._default_limits` and `seq_index._index_dtype`.

`diagram_data.encode_tables` writes each array as gzip and base64. It is the
same form as `pulseq_analysis.series.encode_array` (T7 of the
`pulseq-analysis` design).

`PRISMA_AS82` (in `grad_spectrum.py`) contains the published acoustic
resonances of a Siemens coil. It is in the public repository, its history,
the released tags and the example report.

### 3.2 pulseq-analysis (`v0.1.0rc2`)

An *analysis* takes a sequence and explicit physical parameters, and gives a
derived value. It has no target profile, no limit, no pass and no fail.

- **The measurement modules**, with their interface in `docs/usage.md`
  sections 1 to 4: `seq_index`, `grad_limits`, `pns`, `pns_levels`,
  `sampling`, `seq_utils`, `asc` and `extensions`. They document each name
  that pulseq-reports uses, except `_index_dtype` and `_default_limits`.
  Section 1 gives the rule for the dtype of the index columns (the smallest
  of uint8, uint16 and uint32 that holds the count), so pulseq-reports can
  make the dtype itself.
- **`series`**: `Series`, `SeriesKind` (`SAMPLES`, `ENVELOPE`, `POINTS`,
  `RUNS`), `to_obj` and `from_obj`, `encode_array` and `decode_array`.
- **`analyses`**: `AnalysisSpec`, the `Analysis` protocol, the entry-point
  group `pulseq_analysis.analyses` and its registry. The analyses are
  `seq.index`, `gradient.limits`, `gradient.blocks` and `pns.safe.levels`.
  Only `pns.safe.levels` gives series:

  | Series | Kind | Arrays | `meta` |
  |---|---|---|---|
  | `pns_total` | `ENVELOPE`, unit `"1"` (1 is 100 %) | `min`, `max` (float32) | `hardware`, `asc_file`, `dt_s`, `bin_samples`, `num_samples`, `peak`, `peak_time_s`, `axis_peaks_x`, `axis_peaks_y`, `axis_peaks_z` |
  | `pns_above_1` | `RUNS` | `start_s`, `end_s`, `num_samples`, `peak`, `peak_time_s` | `threshold` |

  The series do not have the SAFE parameters. The exact PNS of a zoomed view
  in the browser needs them, so it gets them from the target profile.

- It pins the same pypulseq fork commit as pulseq-reports (`a74ab06`).

### 3.3 pulseq-checks (`v0.1.0rc3`)

What pulseq-reports can use:

- `read_profile(path) -> TargetProfile`. A profile gives `hardware_limits`
  (a `HardwareLimits`, or `None`), `opts` (with B0 and gamma, when given),
  `rasters`, `models["pns.safe"]` (the SAFE parameters),
  `acoustic_resonances`, `sources` (the source of each value) and `name`.
- `read_check_config(path) -> CheckConfig`: the targets, `select`,
  `required` and `fast_only`.
- `run_checks(sequence, targets, *, select, required, fast_only,
  limits_from_sequence, analyses) -> ResultMatrix`. With a path, it reads the
  file one time for each target, with the `Opts` of that target. With a
  `Sequence` object, it accepts exactly one target. `analyses` names the
  analyses whose results the matrix keeps, for each target. They are
  calculated also when no check is selected, and `fast_only` does not remove
  them.
- `ResultMatrix`: `results`, `analyses`, `targets` (with the source of each
  value), `exit_status()` (0, 2 or 1, and an analysis result does not change it),
  `analysis(target, id)`, `with_max_findings(n)`, `without_series()`,
  `to_json()` and `from_json()`.
- `Result`: the check ID and spec version, the target, the state, the value,
  the limit and the unit, the location (block ID and time), the model, the
  reason, the link to the specification, `findings` and `findings_omitted`.
- `Finding`: a `code`, a `message`, a `location` (block ID and time, or none)
  and `data`. Findings do not change the state of a result or the exit
  status:

  | Check | One finding for each | Codes |
  |---|---|---|
  | `timing.pypulseq` | error of `check_timing`, in the play order of the blocks | the error type of pypulseq |
  | `timing.rasters` | raster with a problem | `RASTER_NOT_DECLARED`, `RASTER_INVALID`, `RASTER_MISMATCH` |
  | `gradient.amplitude.axis`, `gradient.slew.axis`, `gradient.amplitude.any-orientation` | block (and axis) above the limit, only for a fail | `AMPLITUDE_ABOVE_LIMIT`, `SLEW_ABOVE_LIMIT`, `JUNCTION_SLEW_ABOVE_LIMIT`, `VECTOR_AMPLITUDE_ABOVE_LIMIT` |
  | `pns.safe` | interval of samples at or above 100 % | `PNS_ABOVE_LIMIT` |

- `AnalysisResult` (`id`, `version`, `target`, `state`, `reason`, `series`)
  and `AnalysisState` (`done`, `not evaluated`, `error`).
- `CheckSpec.promise`, a `CheckPromise`: what a pass guarantees (`on_pass`),
  what a fail means (`on_fail`) and what the check does not promise
  (`not_promised`).
- `HardwareLimits`, exported. `pulseq_checks.safe_model.hw_from_dict` makes a
  SAFE hardware struct from `TargetProfile.models["pns.safe"]`.

Rules that the cards mirror (principles 3 and 7): the measurements use the
rasters of the file, and the raster of the target for a raster that the file
does not declare (R8). The gradient checks convert with the gamma of the
target (R9).

Facts about the result JSON:

- The JSON of `v0.1.0rc3` and the JSON of `v0.1.0rc2` cannot read each
  other, although both are format 1.
- On 10⁶ blocks with an error in each TR, `timing.pypulseq` gives 4 × 10⁵
  findings, and the JSON result is about 200 MB. `with_max_findings(1000)`
  makes it about 0.5 MB.
- The series of `pns.safe.levels` add at most about 4/3 of the raw size of the
  envelope: about 6 MB for one hour at the 10 µs raster. A sequence that
  repeats compresses much more.

Costs at 10⁶ blocks (`CHANGELOG.md` of `v0.1.0rc3`, with the read of the
file, about 3.7 s): the fast checks together take 4.28 s. All six checks
take 24.54 s, and 24.41 s with `analyses=["pns.safe.levels"]`: the analysis
result costs no measurable time, because `pns.safe` runs SAFE already.

`pulseq-checks` `v0.1.0rc3` depends on `pulseq-analysis` `v0.1.0rc2` by
direct git reference (`allow-direct-references`). All three repositories pin
the same pypulseq fork commit (T12 of the `pulseq-analysis` design).

### 3.4 The changes of `v0.1.0rc4` (checked on 2026-10-04)

`pulseq-analysis` `v0.1.0rc4` (tag commit `0afc759`) and `pulseq-checks`
`v0.1.0rc4` (tag commit `e38bf5c`). `pulseq-checks` `v0.1.0rc4` pins
`pulseq-analysis` `v0.1.0rc4`. All three repositories still pin the pypulseq
fork commit `a74ab06`.

**The series (`pulseq-analysis` `v0.1.0rc3`).** Each `Series` has a
coordinate with its own unit. The names changed:

| `v0.1.0rc2` | `v0.1.0rc3` |
|---|---|
| none | `coord_unit` (necessary, for example `"s"` or `"Hz"`) |
| `t0_s`, `step_s`, `end_s` | `coord_start`, `coord_step`, `coord_end` |
| `POINTS` array `time_s` | `coord` |
| `RUNS` arrays `start_s`, `end_s` | `start`, `end` |

The field `unit` (the unit of the values), the array `peak_time_s` and the
`meta` keys `dt_s` and `peak_time_s` keep their names. The series of
`pns.safe.levels` have `coord_unit` `"s"`. A result JSON with a series of
`v0.1.0rc3` and one of `v0.1.0rc4` cannot read each other. `encode_array` and
`decode_array` did not change. At version 3, pulseq-reports read no `Series`
field, so the change touches only the plan for the PNS card and lane.

**The gradient spectrum (`pulseq-analysis` `v0.1.0rc4`).** The module
`grad_spectrum` of pulseq-reports moved to
`pulseq_analysis.grad_spectrum`, with the method of pypulseq
`calculate_gradient_spectrum` and its defaults (`max_frequency_hz=2000.0`,
`window_s=0.05`, `frequency_oversampling=3.0`, 301 frequencies).

- The values are in Hz/m/√Hz, with no gamma. To get mT/m/√Hz, multiply by
  `1e3 / gamma`. The conversion is exact to float rounding.
- `GradientSpectrum` has no resonances and no band peaks. Its arrays are
  read-only.
- The analysis `gradient.spectrum` (version 1, cost "slow", `params=()`)
  gives one `SAMPLES` series, `gradient_spectrum`: unit `"Hz/m/sqrt(Hz)"`,
  `coord_unit` `"Hz"`, `coord_start` 0.0, `coord_step` the frequency step,
  the arrays `value` (the RSS of the axes), `x`, `y` and `z` (float64), and
  `meta` with the three arguments. A sequence with no gradient event gives no
  series.
- `pulseq-checks` gives the analysis no binding: it is available for each
  target. Each target reads the file with its own `Opts`, so each target has
  its own calculation. In one target, the check and the analysis share one
  calculation.
- 12.1 s at 10⁶ blocks (Apple M1 Max).

**The check `acoustic.resonance-energy` (`pulseq-checks` `v0.1.0rc4`).**
Input `acoustic.resonances`, cost "slow", analysis `gradient.spectrum` with
the defaults only. The value is the percent of the energy of the spectrum
(`rss ** 2`) that is in the bands of the target, all bands together. The
band of a pair `(f, bw)` is `[f - bw/2, f + bw/2]`. The limit is the constant
30 %, unit `"%"`, and the location is none. A fail has one finding,
`ACOUSTIC_BAND_ENERGY`. Each result has `limit=30.0`:

| Condition | State |
|---|---|
| The target gives no `acoustic.resonances` | not evaluated |
| A band reaches above 2000 Hz | not evaluated |
| No gradient event, or an empty list of resonances | pass, 0 % |
| At or below 30 % | pass |
| Above 30 % | fail |
| The rotation extension | error |

The profile reader refuses a resonance pair that is not finite and above 0.

**Costs at 10⁶ blocks** (`pulseq-checks` `v0.1.0rc4`, with the read of the
file): the fast checks together take 4.27 s, the check
`acoustic.resonance-energy` 16.38 s, and all seven checks 36.88 s.

**`ResultMatrix`** has no method that gives one check result. A card selects
the `Result` of a check and a target from `results` by `check_id` and
`target`.

### 3.5 The changes of `v0.1.0rc5` (checked on 2026-10-04)

`pulseq-analysis` `v0.1.0rc5` (tag commit `8043553`, plan
`docs/plans/gamma-free-units.md`) and `pulseq-checks` `v0.1.0rc5` (tag commit
`369fd65`, plan `docs/plans/pulseq-analysis-rc5.md`). `pulseq-checks`
`v0.1.0rc5` pins `pulseq-analysis` `v0.1.0rc5`. All three repositories still
pin the pypulseq fork commit `a74ab06`.

**`pulseq-analysis`: no value uses a gamma.** Section 8 of its
`docs/usage.md` gives the rule: each value is a magnitude, so divide it by
\|γ\| in Hz/T to get the unit with tesla.

| What | `v0.1.0rc4` | `v0.1.0rc5` |
|---|---|---|
| `seq_utils.GAMMA` | 42.576e6 Hz/T | removed: the package has no gamma value |
| `gradient_limits`, `block_gradient_values` | argument `gamma`, values in mT/m and T/m/s | no `gamma`; values in Hz/m and Hz/m/s |
| The names of `grad_limits` | `*_mt_per_m`, `*_t_per_m_per_s` | `*_hz_per_m`, `*_hz_per_m_per_s` (only the unit part changes) |
| PNS values (`PnsLevels`, `PnsInterval`, `PnsPrediction`) | a fraction of the stimulation limit, with `seq.system.gamma` | Hz/T: the fraction times \|γ\|; names `*_hz_per_t` (`peak_hz_per_t`, `axis_peaks_hz_per_t`, `level_min_hz_per_t`, `level_max_hz_per_t`) |
| PNS thresholds (an input) | `thresholds=(PNS_LIMIT,)` | `thresholds_hz_per_t=()`: no default threshold. For a fraction f, give `f * abs(gamma)` |
| The series of `pns.safe.levels` | unit `"1"`, `pns_above_1` | unit `"Hz/T"`, `pns_above_<k>` by the position k of the threshold; `meta["threshold"]` gives it in Hz/T |
| The analyses `gradient.limits`, `gradient.blocks` | parameter `gamma` | no parameters |
| `PnsLevels`, `GradientSpectrum` | `==` by identity, or `ValueError` | `==` by value; arrays read-only |

`PNS_LIMIT` stays 1.0, the limit as a fraction. `pns_prediction(seq, *,
gradient_asc=None)` and `peak_tr_window` do not change their arguments.

**`pulseq-checks`: \|γ\| of the target.**

- `bindings.gamma(ctx)` stays signed. The new
  `bindings.gamma_magnitude(ctx)` is `abs(gamma(ctx))`, and the checks
  convert only with it. Both take a `RunContext`, so pulseq-reports cannot
  call them. For a caller, `docs/usage.md` of `pulseq-checks` gives
  `abs(target.make_opts().gamma)`.
- `TargetProfile.hardware_limits` (mT/m, T/m/s) and the limits from a
  `Sequence` object use \|γ\|. A negative gamma gives the results of its
  magnitude (the fix of the false pass of `v0.1.0rc4`).
- The binding of `pns.safe.levels` gives the one threshold
  `PNS_LIMIT * |γ|` (`bindings.pns_threshold_hz_per_t`). Thus the series are
  `pns_total` and `pns_above_0`. The percent of a value `v` of either series
  is `100 * v / meta["threshold"]` of `pns_above_0` (`docs/usage.md` of
  `pulseq-checks`, section 6).
- The result JSON does not give the gamma of a target (its decision D3).
- A result JSON of `v0.1.0rc4` still reads, because the format is 1, but its
  PNS values are fractions (unit `"1"`) and its runs are `pns_above_1`.
- The profile reader has no rule for the gamma. A gamma that is not finite
  reads. A gamma of 0 reads when the profile does not give both limits;
  with both limits, the division by 0 gives a `ProfileError`. A gamma of 0
  gives the threshold 0, which `pulseq-analysis` refuses, so `pns.safe`
  gives "error".
- The results of the checks do not change for a positive gamma. Costs at
  10⁶ blocks: the fast checks 4.27 s, all seven checks 37.18 s.

**pulseq-reports at `2a516b4`.** It imports `GAMMA` in `registry.py`,
`targets.py`, `diagram_data.py`, `waveforms.py`, `rf_exposure.py` and
`cards/diagram.py`. It reads the `*_mt_per_m` names of `grad_limits` in
`cards/gradient_limits.py`, and the fraction names of `pns` and `pns_levels`
in `cards/pns.py` and `cards/diagram.py`. `cards/rf_profile.py` and
`rf_profiles.py` change a `ppm` offset into Hz with `abs(seq.system.gamma)`,
but pypulseq uses the signed gamma for it (`Sequence` and `write_seq`).

## 4. Design

### 4.1 The inputs of a report

A report has three new inputs:

| Input | Command line | Python |
|---|---|---|
| Target profiles | `--target PROFILE`, more than one time | `targets=` (a list of `TargetProfile`) |
| A check configuration | `--check-config FILE` | read it with `read_check_config` |
| The results of an earlier run | `--check-results FILE.json` | `check_results=` (a `ResultMatrix`) |

The flags mirror `pulseq-check`. The report's own configuration file can name
a check configuration. The targets of a check configuration are also the
targets of the cards. The targets feed both the cards (section 4.4) and the
check summary (section 4.3). More than 6 targets is an error of the arguments
(decision P28).

`build_cards(seq, *, targets=..., check_results=...)` never runs checks
(decision P26). `ReportContext` gives the targets and the result matrix to
each card. The card options `limits`, `gradient_asc`, `coil` and
`check_norms` go away.

### 4.2 The checks in a report

- **The command runs the checks when targets are given.** `pulseq-report`
  calls `run_checks` with the path of the file, the targets, and the
  `select`, `required` and `fast_only` of the check configuration. Without a
  check configuration, all installed checks run and no check is required, as
  in `pulseq-check --target`. When the PNS card or the PNS lane is on the
  page, it also asks for the analysis `pns.safe.levels`. When the gradient
  spectrum card is on the page, it also asks for the analysis
  `gradient.spectrum`. It gives the matrix to `build_cards`.
- **A Python caller runs the checks itself.** It calls `run_checks` and gives
  the matrix to `build_cards` (`check_results=`). With targets and no matrix,
  the check summary says that no checks were run, and the PNS card and lane
  show a note (principle 9).
- **Results of an earlier run replace the run.** With `--check-results`, the
  command runs no checks and shows the given matrix. The targets of the matrix
  must be the targets of the report. `ResultMatrix.from_json` of the pinned
  `pulseq-checks` reads the file. A file that it refuses (for example a
  result of `v0.1.0rc3`) is an error of the run. A file that it reads, but
  that has a series of `pns.safe.levels` with a unit other than `"Hz/T"` (a
  result of `v0.1.0rc4`), is also an error of the run (decision P39): no code
  reads the older form. A matrix without the analysis `pns.safe.levels` gives
  no PNS (principle 9). A matrix without the analysis `gradient.spectrum`
  gives no spectrum (principle 10).
- **Findings.** The report keeps at most 100 findings of each result
  (`with_max_findings`), and shows `findings_omitted`. `pulseq-report
  --max-findings N` changes the number, as in `pulseq-check`. A matrix from
  `--check-results` keeps its own limit, or gets the smaller one (decision
  P18). For all the findings, use the JSON result of `pulseq-check`.
- **A `Sequence` object.** `run_checks` accepts a `Sequence` object only with
  exactly one target. A Python caller with a `Sequence` object and several
  targets runs the checks on the file, or gets no check summary.
- **The exit status of `pulseq-report`.** 0 when each page is written and
  has no error card. 1 when a page has an error card: the page is written,
  but the report is not complete (decision P14). With `--fail-on-check`, the
  status is also `ResultMatrix.exit_status()` (0, 2 or 1), the same as
  `pulseq-check`. When two statuses apply, the status is 1. An error of the
  run (`ProfileError`, `ConfigError`, `RunError`) is an error of the
  arguments: status 1, and no page.

### 4.3 The check summary card

A new card, near the top of the page. It has the legend of the target
colors. For each target:

- the name and the source of each value (the profile file or the `.asc`
  file), and the sections that no check used,
- for each check: the state, the value and the limit with the unit, the
  detail, the location, a mark for a required check, and the link to the
  specification,
- for each check, a closed element "What this check promises" with the three
  texts of its `CheckPromise` (decision P24),
- each "not evaluated" and "error" result, with its reason, and each analysis
  result that is not "done", with its reason. The reader must see what was
  not asserted, not only what passed,
- for each result with findings: the number of findings, with the number
  that the report omitted. The cards list the findings (section 4.6).

A location in a result can go to the diagram (the `goto` message), as the
"Show" buttons of the gradient limits card do. A `Location` gives the
pypulseq block ID, and a `goto` message gives the play index (from 0). The
card changes one into the other with `SequenceIndex.block_id`.

Without targets and without results, the summary card is not on the page.

### 4.4 The cards

| Card | Targets | Without a target that gives the value | With several targets |
|---|---|---|---|
| `timing` | All | The card is not on the page (it has no data). | One part for each target. The card shows only `pulseq-checks` results (section 4.5). |
| `gradient-limits` | All (for the percent columns) | The peaks, with no percent columns. A note says that no target gives limits. | One percent column for each target that gives `max_grad` and `max_slew`, in the color of the target. The peaks are measured one time, in Hz/m, with `pulseq_analysis.grad_limits`. Each percent column converts with \|γ\| of its target. The peaks show in the gamma of the selected target (P36). |
| `pns` | All that give SAFE parameters | No PNS. A note says that no target gives SAFE parameters, or that the matrix has no PNS (principle 9). | One part for each target, from its analysis result `pns.safe.levels`: the peak, its time, the axis peaks and the hardware name, in percent of `meta["threshold"]` (P38). |
| `diagram` (PNS lane) | All that give SAFE parameters | No PNS lane. | One PNS lane, in percent. The envelope `pns_total` of each target, in percent of its `meta["threshold"]` (P38), is overlaid in the color of the target. The runs of `pns_above_0` are marked in the color of the target (decision P22). The exact PNS of a zoomed view uses the SAFE parameters of the target profile and \|γ\| of the target. |
| `diagram` (gradient and RF lanes) | All (for the gamma) | The gamma of `seq.system` (principle 8). | The gamma of the selected target (P36): the gradient lanes with γ, \|B1\| with \|γ\|. The RF phase does not change. |
| `gradient-spectrum` | All (for the spectrum), all that give acoustic resonances (for the bands) | The spectrum, with no resonance bands. A note says that no target gives resonances. Without a matrix, or without the analysis `gradient.spectrum`: a note and no chart (principle 10). | One spectrum line for each group of targets with the same \|γ\| and the same spectrum, in mT/m/√Hz with that \|γ\| (decision P37). The bands of each target, in the color of the target. One line for each target with the result of `acoustic.resonance-energy` (decision P30). |
| `rf-profile` | All (for the gamma), all that give B0 (for a `ppm` offset) | A pulse with a `ppm` offset shows a note that its offset cannot be changed into Hz. The other pulses do not change. | The profiles of each group of targets with the same γ and B0 overlaid, in the color of the first target of the group. A `ppm` offset changes into Hz with γ and B0. \|B1\| uses \|γ\|. |
| `rf-exposure` | All (for the gamma) | The gamma of `seq.system` (principle 8). | \|B1\| and the energy in the gamma of the selected target (P36). |
| `definitions` | None | No change. | No change. |
| `blocks` | None | No change. | No change. |

The `coil` option, `GradientCoil`, `AcousticResonance` and `PRISMA_AS82` go
away. pulseq-reports does not ship the resonances of a real coil, because
they are vendor information. A target profile gives them.

### 4.5 The timing card

The timing card shows only `pulseq-checks` results. It does not call
`check_timing`. For each target, it shows the result of `timing.pypulseq` and
a table of its findings: one row for each error, with the code, the message,
the block and the time. A row can go to the block in the diagram (the `goto`
message). The card also shows the findings of `timing.rasters`, and the
number of findings that the report omitted (decision P18).

### 4.6 The findings and the analysis runs in the cards

Each mark comes from a check result, a finding or an analysis result
(principle 1):

| Where | What |
|---|---|
| Check summary | The number of findings of each result, and the number that the report omitted. |
| `timing` | A list of the findings of `timing.pypulseq` and `timing.rasters` for each target, with a "Show" button for each row (section 4.5). |
| `gradient-limits` | A list of the findings of `gradient.amplitude.axis`, `gradient.slew.axis` and `gradient.amplitude.any-orientation` for each target, with a "Show" button for each row. |
| `diagram` (PNS lane) | The runs of the series `pns_above_0` of each target, marked in the color of the target. They are complete: the findings limit does not apply to them. They use the threshold of `pns.safe` (`PNS_LIMIT * |γ|`), so they agree with the check (decision P22). |
| `gradient-spectrum` | For each target, the state, the value and the limit of `acoustic.resonance-energy`, or its reason. The card does not calculate a share of the energy or a peak in a band (decision P30). |

The percent columns of the gradient limits card convert the peak and the
limit of a target with \|γ\| of that target, as the gradient checks do
(decision D1 of the `pulseq-checks` plan `docs/plans/pulseq-analysis-rc5.md`).
Thus the card and the check use the same numbers.

### 4.7 What goes away

- `Check`, `Card.checks` and the exit status 2 of the command.
- The options `limits`, `gradient_asc`, `coil` and `check_norms`, and their
  flags and configuration keys.
- `GradientCoil`, `AcousticResonance`, `PRISMA_AS82` and
  `PRISMA_AS82_RESONANCES`.
- The module `grad_spectrum` of pulseq-reports, with `BandPeak`, the band
  peaks and the `bands` of the page data of the spectrum card. It moved to
  `pulseq-analysis` (section 3.4).
- The warning about default limits.
- The failed check of an error card. An error card stays, with its message,
  and it gives exit status 1 (decision P14).
- The copies of the moved modules, and the private names
  `_default_limits` and `_index_dtype`. The old import paths (for example
  `pulseq_reports.grad_limits` and `pulseq_reports.pns`, in `docs/usage.md`
  section 6) go away with them. `CHANGELOG.md` names the new paths in
  `pulseq-analysis` (decision P15).
- `diagram_data.encode_tables`, if `pulseq_analysis.series.encode_array`
  gives the same text. The implementation plan confirms it.
- The proton rule (P21, version 5): the `ValueError` of `build_cards` for a
  `Sequence` object with another gamma, the "supported" targets, and the
  imports of `pulseq_analysis.seq_utils.GAMMA`, which `pulseq-analysis`
  `v0.1.0rc5` removed. The item "Use the gyromagnetic ratio of the sequence"
  of `TODO.md` is done by this work.
- `gradScale` of the PNS entry of the diagram. The browser divides by
  \|γ\| of the target.

`HardwareLimits` stays a public name of pulseq-reports. It is exported again
from `pulseq-checks` (decision 8 of version 1).

### 4.8 The gamma in the cards

This table gives each conversion (principle 8). "Selected" is the gamma of
the target that the control of the card selects (P36), or `seq.system.gamma`
without targets.

| Card | Value | Source unit | Gamma |
|---|---|---|---|
| `diagram` | Gradient lanes (mT/m) | Hz/m | selected γ (signed) |
| `diagram` | RF magnitude (µT) | Hz | selected \|γ\| |
| `diagram` | RF phase (rad) | the file | none |
| `diagram` | PNS lane (%) | Hz/T | `meta["threshold"]` of each target (P38) |
| `diagram` | Exact PNS of a zoomed view (%) | Hz/m samples, SAFE model in the browser | \|γ\| of each target |
| `gradient-limits` | Peaks, slew rates, RMS | Hz/m, Hz/m/s | selected \|γ\| |
| `gradient-limits` | Percent of a limit | Hz/m and `hardware_limits` | \|γ\| of each target |
| `pns` | Peak and axis peaks (%) | Hz/T | `meta["threshold"]` of each target (P38) |
| `gradient-spectrum` | Spectrum (mT/m/√Hz) | Hz/m/√Hz | \|γ\| of each group (P37) |
| `rf-profile` | `ppm` offset (Hz) | ppm | γ (signed) and B0 of each target |
| `rf-profile` | \|B1\| (µT) | Hz | \|γ\| of each target |
| `rf-profile` | Bloch simulation | Hz, Hz/m | none |
| `rf-exposure` | \|B1\| (µT), energy | Hz | selected \|γ\| |

The control of P36 lists one entry for each value of the gamma that the
values of the card depend on: the signed γ for the diagram, and \|γ\| for
the RF exposure card and the peaks of the gradient limits card. The label of
an entry names its targets. With one entry, the card shows no control. A
chart card (the diagram) keeps the units of the file (Hz/m and Hz) in the
data of the page, and the browser changes them with the selected gamma. A
card with a table (the RF exposure card, the peaks of the gradient limits
card) has one table for each entry, and the control shows the table of the
selected entry.

## 5. Release

One release does all of this work: `0.2.0rc3`. It depends on
`pulseq-checks` `v0.1.0rc5` and on `pulseq-analysis` `v0.1.0rc5` (decision
P34; version 4: `v0.1.0rc4`, P29; version 3: `v0.1.0rc3` and `v0.1.0rc2`), by direct git references, as `pulseq-checks` does. The `pulseq-analysis` tag must be the
tag that the pinned `pulseq-checks` pins, or the resolver cannot satisfy
both. `uv.lock` records the commit of each tag. A tag of these repositories
was moved once, so a relock that changes a commit of a pinned tag is a reason
to stop and ask the user.

`0.2.0` final comes after a final release of `pulseq-checks` and of
`pulseq-analysis`. Thus callers get one breaking release, and a final
release never depends on a release candidate.

`0.2.0rc3` breaks the API of `0.2.0rc2`. No project uses the library yet.
`CHANGELOG.md` lists each removed name and each removed option, and the
target or the package that replaces it.

## 6. What pulseq-reports needs from the other packages

Nothing is open. Both requests of version 2 are done: the findings of each
check (`pulseq-checks` `v0.1.0rc2`), and a documented measurement API
(`pulseq-analysis` `v0.1.0rc2`, `docs/usage.md` sections 1 to 4).

Later, not in this work:

- **The other measurement modules of pulseq-reports** (`rf_exposure`,
  `rf_sim`, `profile_metrics` and `waveforms`) move to `pulseq-analysis` when
  a second package needs them (section 8 of the `pulseq-analysis` design).
  `grad_spectrum` moved in `pulseq-analysis` `v0.1.0rc4`.
- **One calculation for all targets.** `pulseq-checks` calculates
  `gradient.spectrum` one time for each target, also when the result is the
  same for all targets. A change in `pulseq-checks` can share it. Since
  `v0.1.0rc5`, two targets with the same SAFE hardware and two gammas also
  run the SAFE model two times.
- **A gamma that is 0 or not finite** in a profile. `pulseq-checks`
  `v0.1.0rc5` does not refuse it. pulseq-reports refuses it (principle 8).
  A check of the profile reader of `pulseq-checks` is a separate change.
- **Series of the gradient analyses.** When `gradient.blocks` gives `POINTS`
  series (section 8 of the `pulseq-analysis` design), the gradient limits card
  can read them from the matrix.

## 7. Order of work

A high-level order. The implementation plan gives the phases.

1. **Remove the verdicts and the defaults** (decision P25). Remove `Check`,
   `Card.checks`, the exit status 2, `check_norms`, the `seq.system` default
   limits, the example SAFE hardware and the default coil `PRISMA_AS82`. This
   step needs neither package. Until step 4, a card without the old option
   shows no percent columns, no PNS or no resonance bands.
2. **Depend on `pulseq-checks` and `pulseq-analysis`.** Pin the tags of
   section 5. Delete the copies of the moved modules, and import the
   documented names. Make the dtype of the index columns in pulseq-reports.
3. **The inputs and the matrix.** Add the target inputs (section 4.1), the
   target colors and the legend, the gamma rule (principle 8), and the
   result matrix: `run_checks` in the command, `--check-config`,
   `--check-results` and `check_results=`.
4. **The cards on targets.** Change each card as section 4.4 says. Remove
   the scanner options.
5. **The check summary and the findings.** Add the summary card,
   `--max-findings` and `--fail-on-check`. Change the timing card to use the
   results. Add the findings lists and the PNS runs (section 4.6).
6. **Documents and release.** `docs/usage.md`, `README.md`, `TESTS.md`,
   `CHANGELOG.md`, and the example report with two example targets (decision
   P27). Then `0.2.0rc3`.

## 8. Rules for the implementation plan

- The rules of `CLAUDE.md` apply: one branch and one pull request for each
  change, and the checks before each pull request.
- Do not change `pulseq-checks` or `pulseq-analysis` from this plan. A need
  in one of them is a request to the user.
- Do not add a dependency other than `pulseq-checks` and `pulseq-analysis`.
- All three repositories pin the same pypulseq fork commit (T12 of the
  `pulseq-analysis` design).
- Do not test what `pulseq-checks` or `pulseq-analysis` tests. Test that
  pulseq-reports passes the correct inputs and shows the results.
- The example report uses two target profiles that say that they are
  examples (decision P27). They contain no vendor values (decision P9): the
  SAFE parameters of the example hardware of pypulseq, labeled "not a real
  scanner", and resonance bands that are invented and labeled so.

## 9. Decisions

### 9.1 Decisions of version 1

Decisions 1 to 12 of version 1 (2026-09-30) stay, with these changes:

- **Decision 1** (remove `Card.checks` before `0.2.0` final): it stays.
  Decision P1 adds that the same release adopts `pulseq-checks`.
- **Decision 4** (the limits of the sequence): `pulseq-checks` made it more
  strict. The opt-in is only a keyword argument, for a `Sequence` object. The
  report follows `pulseq-checks` (principle 3).
- **Decision 6** (the profile format): `pulseq-checks` decides it. The
  profile file can give the SAFE parameters and the acoustic resonances
  directly.

Decision 2 (`--fail-on-check`), decision 8 (`HardwareLimits` exported again)
and decision 9 (each package has its own command line) apply to this work.
Decisions 3, 5, 7, 10, 11 and 12 are for `pulseq-checks`.

### 9.2 Decisions of version 2

The user made these decisions on 2026-09-30. Do not open them again. Version
3 changes the decisions marked so.

| # | Decision | Answer | Where |
|---|---|---|---|
| P1 | The release | One release does all of the work: `0.2.0rc3`. `0.2.0` final comes after a final release of the packages that it depends on (version 3). | 5 |
| P2 | The timing card | Keep it. It shows only `pulseq-checks` results. | 4.5 |
| P3 | The details of the timing results | Done: the findings of `pulseq-checks` `v0.1.0rc2`. | 4.5 |
| P4 | Scanner context for the cards | The cards read the target profile format of `pulseq-checks`. Each card selects its targets: several, one or none. | 2, 4.4 |
| P5 | Defaults in the cards | As in `pulseq-checks`: defaults are used, and shown, only where `pulseq-checks` uses them. Where that rule is not clear for a card, ask the user. | 2, 4.4 |
| P6 | The gradient limits card | A percent column for each target that gives limits. | 4.4 |
| P7 | The PNS card and the PNS lane | The card shows each target that gives SAFE parameters. The one PNS lane overlays the targets, each in its color. | 4.4 |
| P8 | The gradient spectrum card | Resonance bands only from targets. The `coil` option, `GradientCoil` and `PRISMA_AS82` go away. | 4.4 |
| P9 | The Prisma resonances | Do not ship them, also not as an example profile: they are vendor information. | 4.4, 8 |
| P10 | The RF profile card | The profiles for the B0 of each target, overlaid, each in its color. | 4.4 |
| P11 | The imports of measurement names | Only documented names. Version 3: they come from `pulseq-analysis`, which documents them. | 2, 6 |
| P12 | The inputs of a report | Flags that mirror `pulseq-check`: `--target`, `--check-config`, `--check-results`. | 4.1 |
| P13 | Checks in a report | The report runs the checks when targets are given. A check configuration can select the checks. Given results replace the run. Version 3: the command runs them, not `build_cards` (P26). | 4.2 |
| P14 | The exit status for an error card | 1. The page is written, but the report is not complete. | 4.2, 4.7 |
| P15 | The old import paths of the moved modules | Remove them. `CHANGELOG.md` names the new paths (in `pulseq-analysis`, version 3). Only `HardwareLimits` is exported again (decision 8). | 4.7 |
| P16 | Gamma | Replaced by P21. | 2 |
| P17 | The colors of the targets | By the order of the targets, in the arguments or in the check configuration. A profile does not give a color. | 2 |
| P18 | The number of findings in a report | At most 100 for each result, and the number omitted. `--max-findings N` changes it. A matrix from `--check-results` keeps its own limit, or gets the smaller one. | 4.2 |
| P19 | Where the findings show | The summary gives the counts. The timing card lists the timing findings, and the gradient limits card lists the gradient findings, each with a "Show" button. Version 3: the PNS lane marks the analysis runs, not the findings (P22). | 4.6 |
| P20 | Gamma in the percent columns of the gradient limits card | Replaced by P21. | 2 |
| P21 | Other nuclei | Version 5: replaced by P35. pulseq-reports supports only the proton gamma, also where `pulseq-checks` supports other gammas. The cards leave out a target with another gamma, with a note. `build_cards` refuses a `Sequence` object with another gamma. `TODO.md` keeps the list of the functions to change for other nuclei. | 2 |

### 9.3 Decisions of version 3

The user made these decisions on 2026-10-04. Do not open them again.

| # | Decision | Answer | Where |
|---|---|---|---|
| P22 | The marks of the PNS lane | Version 5: the series is `pns_above_0` (P34). The runs of the series `pns_above_1` of the analysis result `pns.safe.levels`. They are complete and exact, and use the threshold of `pns.safe`. Not the `pns.safe` findings, which the report limits to 100. | 4.4, 4.6 |
| P23 | A report with targets and no result matrix | The PNS card and the PNS lane show a note: no analysis results were given. They do not run the SAFE model. The matrix is the only source of the PNS in a report. | 2, 4.2 |
| P24 | The promise of a check in the summary | A closed element "What this check promises" for each check, with the three texts of its `CheckPromise`. | 4.3 |
| P25 | The first step | Remove the verdicts and the defaults first, with no dependency on the other packages. | 7 |
| P26 | How the Python API gets the results | `build_cards` takes `check_results=` and never runs checks. The command runs `run_checks` and gives the matrix to `build_cards`. A Python caller does the same. | 4.1, 4.2 |
| P27 | The targets of the example report | Two target profiles that say that they are examples, with different limits and B0, the SAFE parameters of the example hardware of pypulseq (labeled "not a real scanner"), and resonance bands that are invented and labeled so. | 7, 8 |
| P28 | The number of targets | At most 6, with a palette of 6 color tokens for light and dark mode. More targets is an error of the arguments (status 1). | 2, 4.1 |

### 9.4 Decisions of version 4

The user made these decisions on 2026-10-04. Do not open them again.

| # | Decision | Answer | Where |
|---|---|---|---|
| P29 | The pins | Version 5: the tags are `v0.1.0rc5` (P34). `pulseq-checks` `v0.1.0rc4` and `pulseq-analysis` `v0.1.0rc4`. The work continues from the phases that are done. It does not do them again. | 3.4, 5 |
| P30 | The gradient spectrum card for each target | The bands of the target in its color, and one line with the result of `acoustic.resonance-energy` (state, value and limit, or the reason). The card does not calculate band peaks or the share of the energy in the bands, because the check gives that comparison. This does not change P6: the gradient limits card keeps its percent columns. | 4.4, 4.6 |
| P31 | The source of the spectrum | Only the analysis result `gradient.spectrum` in the result matrix. Without it, the card shows a note and no chart. A report has no default target: a default target, if one is added later, also goes through `pulseq-checks` and `pulseq-analysis`. | 2, 4.2, 4.4 |
| P32 | The spectrum with several targets | Version 5: changed by P37. One spectrum: the analysis result of the first supported target with the state "done". The bands of each supported target. If the spectrum of another target is different, a note names that target. | 4.4 |

### 9.5 Decisions of version 5

The user made these decisions on 2026-10-04. Do not open them again.

| # | Decision | Answer | Where |
|---|---|---|---|
| P33 | A negative gamma | Valid. Where a value is a magnitude, the conversion uses \|γ\|. A signed value uses γ. | 2 (principle 8), 4.8 |
| P34 | The pins | `pulseq-checks` `v0.1.0rc5` and `pulseq-analysis` `v0.1.0rc5`. | 3.5, 5 |
| P35 | Other nuclei (replaces P21) | Each card uses the gamma of each target. A target without `opts.gamma` has the default of pypulseq, as in `pulseq-checks`. Without targets, the cards use `seq.system.gamma`. `build_cards` accepts a `Sequence` object with any gamma that is finite and not 0. A gamma that is 0 or not finite is an error of the arguments. | 2 (principle 8), 4.7 |
| P36 | Sequence-only cards with several gammas | A control on the card selects the target. It has one entry for each gamma that the values of the card depend on, and is not on the card when there is one entry. The units change in the browser: a chart keeps the data in Hz/m and Hz and rescales it, and a card with a table shows the table of the selected entry (section 4.8). | 2 (principle 8), 4.4, 4.8 |
| P37 | The spectrum with several gammas (changes P32) | One line for each group of targets with the same \|γ\| and the same spectrum, in mT/m/√Hz with that \|γ\|. | 4.4 |
| P38 | The PNS percent | `100 * v / meta["threshold"]` of `pns_above_0`, as `pulseq-checks` documents. The card reads no gamma for it, and the value agrees with `pns.safe`. | 4.4, 4.8 |
| P39 | A result file of `pulseq-checks` `v0.1.0rc4` | An error of the run (status 1, no page) when a series of `pns.safe.levels` has a unit other than `"Hz/T"`. | 4.2 |

## 10. Terms

- **Target** or **target profile.** One scanner and its Pulseq interpreter,
  in the format of `pulseq-checks` (`TargetProfile`).
- **Analysis.** A calculation of `pulseq-analysis` that takes a sequence and
  explicit physical parameters, and gives a derived value with no verdict.
- **Analysis result.** The series of one analysis for one target, in the
  result matrix (`AnalysisResult`).
- **Result matrix.** The results of all checks, and the kept analysis
  results, for all targets of one sequence (`ResultMatrix`).
- **Finding.** One problem that a check found, with a code, a message, a
  location and data (`Finding`). A result can have many findings. They do not
  change its state.
- **Check summary card.** The card that shows a result matrix.
- **Scanner context.** The values of a target that a descriptive card uses:
  the limits, the SAFE parameters, the acoustic resonances and B0.
- **Verdict.** Pass, fail, not evaluated or error. Only a `pulseq-checks`
  result gives a verdict.
- **Gamma of a target.** `target.make_opts().gamma`, in Hz/T. It can be
  negative. \|γ\| is its magnitude.
