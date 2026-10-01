# Design: pulseq-reports on pulseq-checks

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: design, version 2, written on 2026-09-30, and updated for
`pulseq-checks` `v0.1.0rc2` on the same day. The user made the decisions of
section 9.2 on the same day, with P18 to P21 for the update to
`v0.1.0rc2`. This is not an implementation plan.
It gives the goals, the principles and the design decisions for the work in
pulseq-reports. An implementation plan comes next.

Version 1 of this document (commit `475a1eb`) gave the design of both
packages. The part for `pulseq-checks` moved to that repository, in
[`docs/plans/pulseq-checks.md`](https://github.com/mdtisdall/pulseq-checks/blob/main/docs/plans/pulseq-checks.md),
and `pulseq-checks` implements it: `v0.1.0rc1` has the checks, and
`v0.1.0rc2` adds the findings of each check and fixes of the gradient checks.
This version gives only the
work in pulseq-reports. `pulseq-checks` is stable for this work, except for
the requests in section 6. The section numbers of version 1 are not kept.
The `pulseq-checks` design refers to version 1 by commit, so its links still
work.

## 1. Goal

Remove all check behavior from pulseq-reports. pulseq-reports gets each
verdict from the services of `pulseq-checks`.

After this work:

- **A card describes. A card does not decide.** No card calculates a pass or
  a fail. The only verdicts on a page come from a `pulseq-checks` result.
- **A report shows the results of the checks.** A summary card near the top
  of the page shows the result matrix: what passed, what failed, and what was
  not asserted. The report gets the matrix from `run_checks`, the same
  function that `pulseq-check` uses, or from a result file of an earlier run.
- **The cards read target profiles.** A card that needs scanner context (the
  limits, the SAFE parameters, the acoustic resonances, B0) reads it from the
  same target profile format as `pulseq-checks`. The card options for scanner
  context go away.
- **No hidden defaults.** A report uses defaults as `pulseq-checks` does. A
  value that no target gives is not replaced by a default. The card says what
  is missing.
- **No duplicate code.** pulseq-reports deletes its copies of the modules
  that moved to `pulseq-checks`, and imports them from `pulseq-checks`.

The main goal of a report is still to describe the sequence. A report with
no targets is complete. It has no verdicts and no check summary.

## 2. Principles

1. **One source of verdicts.** A verdict (pass, fail, not evaluated, error)
   comes only from a `pulseq-checks` `Result`. A card that marks a value or a
   place against a limit (for example a percent above 100, or a block above
   the slew limit) takes the mark from the result of the check or from its
   findings, not from its own comparison. Thus a card and the summary cannot
   disagree. (In version 1, the PNS card failed from 99.995 %
   because it rounded, and `pns.safe` failed from 100 %.)
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
5. **One color for each target.** The page gives each target one color. Each
   card that shows targets uses that color for that target, and the page has
   one legend for the targets.
6. **Only documented names of `pulseq-checks`.** pulseq-reports imports only
   what `pulseq-checks` documents. It does not import a private name (a name
   that starts with `_`). Section 6 gives what pulseq-reports needs that
   `pulseq-checks` does not document yet.
7. **The file gives the rasters.** A card does not read a value from
   `seq.system` that the file does not give. `seq.read` keeps the rasters of
   the file in `seq.grad_raster_time` and the other raster attributes, and
   leaves `seq.system` at the `Opts` of the caller. Values that a file does
   not give (limits, B0, dead times) come from a target, or they are missing.
   A file older than format 1.4.0, or a damaged file, can leave out a raster.
   Then pypulseq uses its own default. A card does not: it mirrors R8 of the
   `pulseq-checks` design, and uses the raster of a target, or shows a note
   that names the missing raster.
8. **Only the proton gamma.** pulseq-reports changes Hz into T, and Hz/m into
   T/m, only with the proton gamma (`GAMMA`, 42.576 MHz/T). It does this also
   where `pulseq-checks` uses the gamma of a target (R9). pulseq-reports does
   not support other nuclei (decision P21):
   - A target that gives a gamma other than `GAMMA` (`opts.gamma`): each card
     leaves the target out, with a note. The check summary still shows the
     results of that target, because `pulseq-checks` supports it.
   - A `Sequence` object with a `seq.system.gamma` other than `GAMMA`:
     `build_cards` raises `ValueError`. A file that `seq.read` reads has the
     proton gamma of pypulseq, because a `.seq` file does not give a gamma.

   The item "Use the gyromagnetic ratio of the sequence" of `TODO.md` is the
   list of the functions to change for other nuclei. A change that adds a
   conversion with gamma adds its function to that list.

## 3. The state of the code

### 3.1 pulseq-reports (`main` at `4fa7e6d`, version `0.2.0rc2`)

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
  change Hz/m into mT/m. Only the proton gamma is supported (principle 8).

The rasters already follow principle 7:

- #105 makes `grad_spectrum.py`, `rf_exposure.py`, `rf_profiles.py` and the
  RF profile card use the rasters of the file (`seq.grad_raster_time`,
  `seq.rf_raster_time`), not the rasters of `seq.system`.
- #106 makes `gradient_limits` divide the step at a block junction by the
  gradient raster of the file. It is a port of `pulseq-checks` #28 and #30.
  It also gives `_default_limits` a `gamma` argument.

The copies of the moved modules: `grad_limits`, `pns`, `pns_levels`, `asc`,
`extensions`, `sampling`, `seq_index` and `seq_utils`. They are in both
packages. Compared with `pulseq-checks` `v0.1.0rc2`:

| Module | Difference |
|---|---|
| `asc`, `sampling`, `seq_index`, `seq_utils` | None. |
| `grad_limits` | `gradient_limits` of `pulseq-checks` refuses the rotation extension. pulseq-reports calls `refuse_rotations` from the card. `pulseq-checks` adds `block_gradient_values` and `BlockGradientValues` (the gradient values of each block, for the findings). After #106, there is no other difference. |
| `pns`, `pns_levels` | `pns_levels` and `pns_levels_for` of `pulseq-checks` take a SAFE hardware struct (`hardware=`). `pulseq-checks` adds `PnsInterval` and `PnsLevels.above_limit` (the intervals at or above 100 %, for the findings). |
| `extensions` | Text only: the docstring and the error message name the package. |

#106 followed decision R7 of the `pulseq-checks` design: the change came to
`pulseq-checks` first. pulseq-reports also uses two private names of these
modules: `grad_limits._default_limits` and `seq_index._index_dtype`.

`PRISMA_AS82` (in `grad_spectrum.py`) contains the published acoustic
resonances of a Siemens coil. It is in the public repository, its history,
the released tags and the example report.

### 3.2 pulseq-checks (`v0.1.0rc2`)

What pulseq-reports can use:

- `read_profile(path) -> TargetProfile`. A profile gives `hardware_limits`
  (a `HardwareLimits`, or `None`), `opts` (with B0 and gamma, when given),
  `rasters`, `models["pns.safe"]` (the SAFE parameters),
  `acoustic_resonances`, `sources` (the source of each value) and `name`. A
  profile that gives `max_grad` and `rise_time` and no `max_slew` gives the
  slew limit `max_grad / rise_time`.
- `read_check_config(path) -> CheckConfig`: the targets, `select`,
  `required` and `fast_only`.
- `run_checks(sequence, targets, *, select, required, fast_only,
  limits_from_sequence) -> ResultMatrix`. With a path, it reads the file one
  time for each target, with the `Opts` of that target. With a `Sequence`
  object, it accepts exactly one target.
- `ResultMatrix`: `results`, `targets` (with the source of each value),
  `exit_status()` (0, 2 or 1), `with_max_findings(n)`, `to_json()` and
  `from_json()`.
- `Result`: the check ID and spec version, the target, the state, the value,
  the limit and the unit, the location (block ID and time), the model, the
  reason, the link to the specification, `findings` and `findings_omitted`.
- `Finding`: one problem that a check found. It has a `code` (the kind of
  problem), a `message` for a person, a `location` (block ID and time, or
  none) and `data` (the values, by name, in SI units). Findings do not change
  the state of a result or the exit status. Each check of `v0.1.0rc2` gives
  findings:

  | Check | One finding for each | Codes |
  |---|---|---|
  | `timing.pypulseq` | error of `check_timing`, in the play order of the blocks | the error type of pypulseq |
  | `timing.rasters` | raster with a problem | `RASTER_NOT_DECLARED`, `RASTER_INVALID`, `RASTER_MISMATCH` |
  | `gradient.amplitude.axis`, `gradient.slew.axis`, `gradient.amplitude.any-orientation` | block (and axis) above the limit, only for a fail | `AMPLITUDE_ABOVE_LIMIT`, `SLEW_ABOVE_LIMIT`, `JUNCTION_SLEW_ABOVE_LIMIT`, `VECTOR_AMPLITUDE_ABOVE_LIMIT` |
  | `pns.safe` | interval of samples at or above 100 % | `PNS_ABOVE_LIMIT` |

- `HardwareLimits`, exported.
- The measurement functions that the plugin documentation names:
  `seq_index.sequence_index`, `grad_limits.gradient_limits` and
  `pns.pns_levels_for`. The `CHANGELOG.md` of `v0.1.0rc2` names
  `grad_limits.block_gradient_values`, `pns_levels.PnsInterval` and
  `PnsLevels.above_limit` as public.

Rules of `v0.1.0rc2` that the cards mirror (principles 3 and 7):

- **Rasters (R8).** The measurements use the rasters of the file. For a
  raster that the file does not declare, they use the raster of the target.
  When the target does not give it either, a check that uses that raster is
  "not evaluated". It never uses a pypulseq default.
- **Gamma (R9).** The gradient checks convert the values of the file with the
  gamma of the target (`opts.gamma`, or 42.576 MHz/T), the same gamma as the
  limits.

Two facts about the result JSON:

- The JSON of `v0.1.0rc2` and the JSON of `v0.1.0rc1` cannot read each
  other, although both are format 1. In the release candidates, the format
  and each specification stay at version 1.
- A sequence with many problems gives many findings. On 10⁶ blocks with an
  error in each TR, `timing.pypulseq` gives 4 × 10⁵ findings, and the JSON
  result is about 200 MB. `with_max_findings(1000)` makes it about 0.5 MB, and
  `findings_omitted` gives the number of the others.

Costs at 10⁶ blocks (`CHANGELOG.md` of `v0.1.0rc2`, with the read of the
file, which takes about 3.6 s): the fast checks together take 4.28 s, or
7.63 s on a file that fails the three gradient checks in each TR. All six
checks take 24.65 s. `timing.pypulseq` with 4 × 10⁵ errors takes 17.9 s.

Both packages pin the same pypulseq fork commit (`a74ab06`). They must keep
the same pin.

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
check summary (section 4.3).

`ReportContext` gives the targets to each card. The card options `limits`,
`gradient_asc`, `coil` and `check_norms` go away.

### 4.2 The checks in a report

- **When targets are given, the report runs the checks.** It calls
  `run_checks` with the path of the file, the targets, and the `select`,
  `required` and `fast_only` of the check configuration. Without a check
  configuration, all installed checks run and no check is required, as in
  `pulseq-check --target`.
- **Results of an earlier run replace the run.** With `--check-results`, the
  report runs no checks and shows the given matrix. The targets of the matrix
  must be the targets of the report. `ResultMatrix.from_json` of the pinned
  `pulseq-checks` reads the file. A file that it refuses (for example a
  result of `v0.1.0rc1`) is an error of the run.
- **Findings.** The report keeps at most 100 findings of each result
  (`with_max_findings`), and shows `findings_omitted`. `pulseq-report
  --max-findings N` changes the number, as in `pulseq-check`. A matrix from
  `--check-results` keeps its own limit, or gets the smaller one (decision
  P18). For all the findings, use the JSON result of `pulseq-check`.
- **A `Sequence` object.** `run_checks` accepts a `Sequence` object only with
  exactly one target. A Python caller with a `Sequence` object and several
  targets gives `check_results`, or gets no check summary. The report does
  not make a temporary file.
- **The exit status of `pulseq-report`.** 0 when each page is written and
  has no error card. 1 when a page has an error card: the page is written,
  but the report is not complete (decision P14). With `--fail-on-check`, the
  status is also `ResultMatrix.exit_status()` (0, 2 or 1), the same as
  `pulseq-check`. When two statuses apply, the status is 1. An error of the
  run (`ProfileError`, `ConfigError`, `RunError`) is an error of the
  arguments: status 1, and no page.

### 4.3 The check summary card

A new card, near the top of the page. For each target:

- the name and the source of each value (the profile file or the `.asc`
  file), and the sections that no check used,
- for each check: the state, the value and the limit with the unit, the
  detail, the location, a mark for a required check, and the link to the
  specification,
- each "not evaluated" and "error" result, with its reason. The reader must
  see what was not asserted, not only what passed,
- for each result with findings: the number of findings, with the number
  that the report omitted. The cards list the findings (section 4.6).

A location in a result can go to the diagram (the `goto` message), as the
"Show" buttons of the gradient limits card do. The implementation plan must
confirm that the block ID of a `Location` and the block of a `goto` message
are the same index.

Without targets and without results, the summary card is not on the page.

### 4.4 The cards

| Card | Targets | Without a target that gives the value | With several targets |
|---|---|---|---|
| `timing` | All | The card is not on the page (it has no data). | One part for each target. The card shows only `pulseq-checks` results (section 4.5). |
| `gradient-limits` | All (for the percent columns) | The peaks, with no percent columns. A note says that no target gives limits. | One percent column for each target that gives `max_grad` and `max_slew`, in the color of the target. The peaks are measured one time. |
| `pns` | All that give SAFE parameters | No PNS. A note says that no target gives SAFE parameters. | One part for each target that gives SAFE parameters. |
| `diagram` (PNS lane) | All that give SAFE parameters | No PNS lane. | One PNS lane. The levels of each target are overlaid in the color of the target. One SAFE calculation for each target, shared with the PNS card. |
| `gradient-spectrum` | All that give acoustic resonances | The spectrum, with no resonance bands. A note says that no target gives resonances. | The bands of each target, in the color of the target. |
| `rf-profile` | All that give B0 | A pulse with a `ppm` offset shows a note that its offset cannot be changed into Hz. The other pulses do not change. | The profiles of each target overlaid, in the color of the target. They differ only for pulses with a `ppm` offset. |
| `rf-exposure` | None | No change. | No change. |
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
number of findings that the report omitted (decision P18). `pulseq-checks`
`v0.1.0rc2` gives these findings (decision P3).

### 4.6 The findings in the cards

Each mark comes from a finding (principle 1, decision P19):

| Where | What |
|---|---|
| Check summary | The number of findings of each result, and the number that the report omitted. |
| `timing` | A list of the findings of `timing.pypulseq` and `timing.rasters` for each target, with a "Show" button for each row (section 4.5). |
| `gradient-limits` | A list of the findings of `gradient.amplitude.axis`, `gradient.slew.axis` and `gradient.amplitude.any-orientation` for each target, with a "Show" button for each row. |
| `diagram` (PNS lane) | The intervals of the `pns.safe` findings of each target, marked in the color of the target. |

The percent columns of the gradient limits card use the proton gamma, as all
the cards do (principle 8). A target with another gamma is not in the card,
so the card and the check cannot disagree on it.

### 4.7 What goes away

- `Check`, `Card.checks` and the exit status 2 of the command.
- The options `limits`, `gradient_asc`, `coil` and `check_norms`, and their
  flags and configuration keys.
- `GradientCoil`, `AcousticResonance`, `PRISMA_AS82` and
  `PRISMA_AS82_RESONANCES`.
- The warning about default limits.
- The failed check of an error card. An error card stays, with its message,
  and it gives exit status 1 (decision P14).
- The copies of the moved modules, and the private names
  `_default_limits` and `_index_dtype`. The old import paths (for example
  `pulseq_reports.grad_limits` and `pulseq_reports.pns`, in `docs/usage.md`
  section 6) go away with them. `CHANGELOG.md` names the new paths in
  `pulseq-checks` (decision P15).

`HardwareLimits` stays a public name of pulseq-reports. It is exported again
from `pulseq-checks` (decision 8 of version 1).

## 5. Release

One release does all of this work: `0.2.0rc3`. It depends on a
`pulseq-checks` tag, by git URL. The tag must be `v0.1.0rc2` or later:
`v0.1.0rc1` does not have the findings (section 4.5) or the fix of #106. The
tag must also document the measurement API that pulseq-reports uses
(principle 6, section 6). `v0.1.0rc2` does not document all of it, so the
release waits for a later tag. `0.2.0` final comes after a
`pulseq-checks` final release. Thus callers get one breaking release, and a
final release never depends on a release candidate.

`0.2.0rc3` breaks the API of `0.2.0rc2`. No project uses the library yet.
`CHANGELOG.md` lists each removed name and each removed option, and the
target that replaces it.

## 6. What pulseq-reports needs from pulseq-checks

`pulseq-checks` is stable for this work. These requests go to that
repository. The user decides how that repository does them.

1. **The details of a result.** Done in `v0.1.0rc2`: the findings of each
   check (section 3.2).
2. **A documented measurement API.** Open. pulseq-reports uses more of the
   moved modules than the plugin documentation names:

   | Module | What pulseq-reports uses |
   |---|---|
   | `seq_index` | `sequence_index`, `SequenceIndex`, `grad_events`, `rf_events`, `adc_events`, `block_cache_off`, and the dtype of the index (now the private `_index_dtype`) |
   | `seq_utils` | `GAMMA`, `TIME_TOLERANCE`, `gradient_points`, `gradient_offsets`, `hold_samples` |
   | `sampling` | `GradientSampler` |
   | `grad_limits` | `gradient_limits`, `GradientLimits`, `HardwareLimits` |
   | `pns`, `pns_levels` | `pns_levels_for`, `PnsLevels`, `pns_prediction`, `peak_tr_window` |
   | `extensions` | `refuse_rotations` |

   The implementation plan confirms this list. The cards take their marks
   from the findings (decision P19), so they do not need
   `block_gradient_values` or `PnsLevels.above_limit`. pulseq-reports does
   not adopt `pulseq-checks` until these names are documented (principle 6).
3. **No defaults for reports either.** The moved modules keep defaults that
   `pulseq-checks` never uses (`EXAMPLE_HARDWARE`, `seq.system` in
   `gradient_limits`). pulseq-reports also does not use them (principle 3).
   No change in `pulseq-checks` is necessary.

## 7. Order of work

A high-level order. The implementation plan gives the phases.

1. **Wait for a `pulseq-checks` tag that documents the measurement API**
   (section 6). `v0.1.0rc2` has the findings, but not the documentation.
2. **Depend on `pulseq-checks`.** Pin the tag. Delete the copies of the moved
   modules, and import the documented names.
3. **Targets as card context.** Add the target inputs (section 4.1) and the
   target colors. Change each card as section 4.4 says. Remove the scanner
   options.
4. **Remove the verdicts.** Remove `Check`, `Card.checks`, the exit status 2
   and the default limits.
5. **The check summary and the timing card.** Add the summary card,
   `--check-results` and `--fail-on-check`. Change the timing card to use the
   results.
6. **Documents and release.** `docs/usage.md`, `README.md`, `TESTS.md`,
   `CHANGELOG.md`, and the example report. Then `0.2.0rc3`.

## 8. Rules for the implementation plan

- The rules of `CLAUDE.md` apply: one branch and one pull request for each
  change, and the checks before each pull request.
- Do not change `pulseq-checks` from this plan. A need in `pulseq-checks` is
  a request (section 6).
- Do not add a dependency other than `pulseq-checks`.
- Do not test what `pulseq-checks` tests. Test that pulseq-reports passes the
  correct inputs and shows the results.
- The example report uses a target profile that says it is an example. It
  contains no vendor values (decision P9).

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

The user made these decisions on 2026-09-30. P18 to P21 come from the update
for `pulseq-checks` `v0.1.0rc2`. Do not open them again.

| # | Decision | Answer | Where |
|---|---|---|---|
| P1 | The release | One release does all of the work: `0.2.0rc3`. `0.2.0` final comes after a `pulseq-checks` final release. | 5 |
| P2 | The timing card | Keep it. It shows only `pulseq-checks` results. | 4.5 |
| P3 | The details of the timing results | `pulseq-checks` `v0.1.0rc2` adds an API for them. The card waits for it. | 4.5, 6 |
| P4 | Scanner context for the cards | The cards read the target profile format of `pulseq-checks`. Each card selects its targets: several, one or none. | 2, 4.4 |
| P5 | Defaults in the cards | As in `pulseq-checks`: defaults are used, and shown, only where `pulseq-checks` uses them. Where that rule is not clear for a card, ask the user. | 2, 4.4 |
| P6 | The gradient limits card | A percent column for each target that gives limits. | 4.4 |
| P7 | The PNS card and the PNS lane | The card shows each target that gives SAFE parameters. The one PNS lane overlays the targets, each in its color. | 4.4 |
| P8 | The gradient spectrum card | Resonance bands only from targets. The `coil` option, `GradientCoil` and `PRISMA_AS82` go away. | 4.4 |
| P9 | The Prisma resonances | Do not ship them, also not as an example profile: they are vendor information. | 4.4, 8 |
| P10 | The RF profile card | The profiles for the B0 of each target, overlaid, each in its color. | 4.4 |
| P11 | The imports from `pulseq-checks` | Only documented names. `pulseq-checks` documents the measurement API that pulseq-reports needs. | 2, 6 |
| P12 | The inputs of a report | Flags that mirror `pulseq-check`: `--target`, `--check-config`, `--check-results`. | 4.1 |
| P13 | Checks in a report | The report runs the checks when targets are given. A check configuration can select the checks. Given results replace the run. | 4.2 |
| P14 | The exit status for an error card | 1. The page is written, but the report is not complete. | 4.2, 4.7 |
| P15 | The old import paths of the moved modules | Remove them. `CHANGELOG.md` names the new paths. Only `HardwareLimits` is exported again (decision 8). | 4.7 |
| P16 | Gamma | Replaced by P21. | 2 |
| P17 | The colors of the targets | By the order of the targets, in the arguments or in the check configuration. A profile does not give a color. | 2 |
| P18 | The number of findings in a report | At most 100 for each result, and the number omitted. `--max-findings N` changes it. A matrix from `--check-results` keeps its own limit, or gets the smaller one. | 4.2 |
| P19 | Where the findings show | The summary gives the counts. The timing card lists the timing findings, and the gradient limits card lists the gradient findings, each with a "Show" button. The PNS lane marks the `pns.safe` intervals of each target. | 4.6 |
| P20 | Gamma in the percent columns of the gradient limits card | Replaced by P21. | 2 |
| P21 | Other nuclei | pulseq-reports supports only the proton gamma, also where `pulseq-checks` supports other gammas. The cards leave out a target with another gamma, with a note. `build_cards` refuses a `Sequence` object with another gamma. `TODO.md` keeps the list of the functions to change for other nuclei. | 2 |

## 10. Terms

- **Target** or **target profile.** One scanner and its Pulseq interpreter,
  in the format of `pulseq-checks` (`TargetProfile`).
- **Result matrix.** The results of all checks for all targets of one
  sequence (`ResultMatrix`).
- **Finding.** One problem that a check found, with a code, a message, a
  location and data (`Finding`). A result can have many findings. They do not
  change its state.
- **Check summary card.** The card that shows a result matrix.
- **Scanner context.** The values of a target that a descriptive card uses:
  the limits, the SAFE parameters, the acoustic resonances and B0.
- **Verdict.** Pass, fail, not evaluated or error. Only a `pulseq-checks`
  result gives a verdict.
