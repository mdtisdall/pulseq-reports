# Design: pulseq-reports on pulseq-checks

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: design, version 2, written on 2026-09-30. The user made the
decisions of section 9.2 on the same day. This is not an implementation plan.
It gives the goals, the principles and the design decisions for the work in
pulseq-reports. An implementation plan comes next.

Version 1 of this document (commit `475a1eb`) gave the design of both
packages. The part for `pulseq-checks` moved to that repository, in
[`docs/plans/pulseq-checks.md`](https://github.com/mdtisdall/pulseq-checks/blob/main/docs/plans/pulseq-checks.md),
and `pulseq-checks` `v0.1.0rc1` implements it. This version gives only the
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
   comes only from a `pulseq-checks` `Result`. A card that marks a value
   against a limit (for example a percent above 100) takes the mark from the
   result of the check, not from its own comparison. Thus a card and the
   summary cannot disagree. (In version 1, the PNS card failed from 99.995 %
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

## 3. The state of the code

### 3.1 pulseq-reports (`main` at `475a1eb`, version `0.2.0rc2`)

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
- The RF raster in the RF profile card and in `rf_exposure.py`, and the
  gradient raster in `grad_spectrum.py`. This is a separate bug (principle
  7). It is not a part of this work.

The copies of the moved modules: `grad_limits`, `pns`, `pns_levels`, `asc`,
`extensions`, `sampling`, `seq_index` and `seq_utils`. They are in both
packages. The copies in `pulseq-checks` are changed: `pns_levels` and
`pns_levels_for` take a SAFE hardware struct (`hardware=`), and
`gradient_limits` refuses the rotation extension. pulseq-reports also uses
two private names of these modules: `grad_limits._default_limits` and
`seq_index._index_dtype`.

`PRISMA_AS82` (in `grad_spectrum.py`) contains the published acoustic
resonances of a Siemens coil. It is in the public repository, its history,
the released tags and the example report.

### 3.2 pulseq-checks (`v0.1.0rc1`)

What pulseq-reports can use:

- `read_profile(path) -> TargetProfile`. A profile gives `hardware_limits`
  (a `HardwareLimits`, or `None`), `opts` (with B0 and gamma, when given),
  `models["pns.safe"]` (the SAFE parameters), `acoustic_resonances`,
  `sources` (the source of each value) and `name`.
- `read_check_config(path) -> CheckConfig`: the targets, `select`,
  `required` and `fast_only`.
- `run_checks(sequence, targets, *, select, required, fast_only,
  limits_from_sequence) -> ResultMatrix`. With a path, it reads the file one
  time for each target, with the `Opts` of that target. With a `Sequence`
  object, it accepts exactly one target.
- `ResultMatrix`: `results`, `targets` (with the source of each value),
  `exit_status()` (0, 2 or 1), `to_json()` and `from_json()`.
- `Result`: the check ID and spec version, the target, the state, the value,
  the limit and the unit, the location (block ID and time), the model, the
  reason and the link to the specification.
- `HardwareLimits`, exported.
- The measurement functions that the plugin documentation names:
  `seq_index.sequence_index`, `grad_limits.gradient_limits` and
  `pns.pns_levels_for`.

Costs at 10⁶ blocks (`pulseq-checks` plan, section 8.3): the read of the file
takes 3.6 s. The fast checks together take 4.2 s with the read. `pns.safe`
and `timing.pypulseq` take about 14 s each with the read. All six checks take
about 24 s.

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
  must be the targets of the report.
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
  see what was not asserted, not only what passed.

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
| `rf-profile` | All that give B0 | A pulse with a `ppm` offset shows a note that its offset cannot be changed into Hz. The other pulses do not change. | The profiles of each target overlaid, in the color of the target. They differ only for pulses with a `ppm` offset. Gamma is the proton gamma, and the card says so (decision P16). |
| `rf-exposure` | None | No change. | No change. |
| `definitions` | None | No change. | No change. |
| `blocks` | None | No change. | No change. |

The `coil` option, `GradientCoil`, `AcousticResonance` and `PRISMA_AS82` go
away. pulseq-reports does not ship the resonances of a real coil, because
they are vendor information. A target profile gives them.

### 4.5 The timing card

The timing card shows only `pulseq-checks` results. It does not call
`check_timing`. A `Result` of `timing.pypulseq` in `v0.1.0rc1` gives only the
count of the errors and the first error. `pulseq-checks` `v0.1.0rc2` adds an
API for the details of a result, which is in progress in that repository.
The card shows the full error table from that API. The timing card waits for
`v0.1.0rc2`.

### 4.6 What goes away

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

One release does all of this work: `0.2.0rc3`. It depends on `pulseq-checks`
`v0.1.0rc2` (section 6), by git URL and tag. `0.2.0` final comes after a
`pulseq-checks` final release. Thus callers get one breaking release, and a
final release never depends on a release candidate.

`0.2.0rc3` breaks the API of `0.2.0rc2`. No project uses the library yet.
`CHANGELOG.md` lists each removed name and each removed option, and the
target that replaces it.

## 6. What pulseq-reports needs from pulseq-checks

`pulseq-checks` is stable for this work. These requests go to that repository
for `v0.1.0rc2`. The user decides how that repository does them.

1. **The details of a result** (in progress). The full error list of
   `timing.pypulseq`, for the timing card (section 4.5).
2. **A documented measurement API.** pulseq-reports uses more of the moved
   modules than the plugin documentation names:

   | Module | What pulseq-reports uses |
   |---|---|
   | `seq_index` | `sequence_index`, `SequenceIndex`, `grad_events`, `rf_events`, `adc_events`, `block_cache_off`, and the dtype of the index (now the private `_index_dtype`) |
   | `seq_utils` | `GAMMA`, `TIME_TOLERANCE`, `gradient_points`, `gradient_offsets`, `hold_samples` |
   | `sampling` | `GradientSampler` |
   | `grad_limits` | `gradient_limits`, `GradientLimits`, `HardwareLimits` |
   | `pns`, `pns_levels` | `pns_levels_for`, `PnsLevels`, `pns_prediction`, `peak_tr_window` |
   | `extensions` | `refuse_rotations` |

   The implementation plan confirms this list. pulseq-reports does not adopt
   `pulseq-checks` until these names are documented (principle 6).
3. **No defaults for reports either.** The moved modules keep defaults that
   `pulseq-checks` never uses (`EXAMPLE_HARDWARE`, `seq.system` in
   `gradient_limits`). pulseq-reports also does not use them (principle 3).
   No change in `pulseq-checks` is necessary.

## 7. Order of work

A high-level order. The implementation plan gives the phases.

1. **Wait for `pulseq-checks` `v0.1.0rc2`** (section 6).
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

The user made these decisions on 2026-09-30. Do not open them again.

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
| P14 | The exit status for an error card | 1. The page is written, but the report is not complete. | 4.2, 4.6 |
| P15 | The old import paths of the moved modules | Remove them. `CHANGELOG.md` names the new paths. Only `HardwareLimits` is exported again (decision 8). | 4.6 |
| P16 | Gamma | The proton gamma, as now. The cards that use gamma say so. Other nuclei are the item in `TODO.md`. | 4.4 |
| P17 | The colors of the targets | By the order of the targets, in the arguments or in the check configuration. A profile does not give a color. | 2 |

## 10. Terms

- **Target** or **target profile.** One scanner and its Pulseq interpreter,
  in the format of `pulseq-checks` (`TargetProfile`).
- **Result matrix.** The results of all checks for all targets of one
  sequence (`ResultMatrix`).
- **Check summary card.** The card that shows a result matrix.
- **Scanner context.** The values of a target that a descriptive card uses:
  the limits, the SAFE parameters, the acoustic resonances and B0.
- **Verdict.** Pass, fail, not evaluated or error. Only a `pulseq-checks`
  result gives a verdict.
