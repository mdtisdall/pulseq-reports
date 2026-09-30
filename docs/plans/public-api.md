# Plan: the public API before 0.2.0rc2 (one sequence per card, A1 to A8, card plugins and a command line)

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: complete (2026-09-29). The results are in section 8. The plan was
written on 2026-09-29. The user answered the questions of section 7 on the
same day, in five rounds; section 4 uses the answers.

## 1. Goal

Make the public API of `pulseq-reports` small, consistent and documented
before the next release candidate, `0.2.0rc2`. The review
(`docs/reviews/2026-09-28-code-review.md`, section 2) says: "0.2.0 is the
first release that consumers pin, so a change that breaks a caller costs least
before it". No project uses the library yet (section 2.1).

The user decided (2026-09-29) that **each card shows one sequence**. A report
is for one `.seq` file; a caller with several files (for example the segment
files of one acquisition) makes one report for each file. The multi-file
cards came from vb-pulseq's review of the segmented ex-vivo acquisition. Only
two cards computed anything across files: the RF exposure card's "All files"
B1+rms, which assumed the files play one after another with no gap (on the
scanner, each file is a separate measurement), and the spectrum card's
maximum over the files, which only put the files' own spectra in one chart.
No analysis function keeps the cross-file B1+rms.

| Kind | Findings and changes in this plan |
|---|---|
| One sequence per card and per page (the user) | Every card builder takes one `pp.Sequence`, and a page shows one sequence. `NamedSequence` and `TimeWindow.file_index` go. The diagram and the RF profile card lose their file lists and their file switching; `laneChart`'s `setWindow` goes. The messages between cards lose their `file` fields and their addresses: a card never names another card (decision 21). `grad_spectrum.combine` and the RF exposure "All files" table go. |
| API (review, section 2) | A1, A3, A4, A6, A7, A8. A2 is decided by the line above: `pns_card` keeps one sequence, as every card does now. A5 is fixed by a button of the PNS card (decision 19), not by a helper. |
| Deferred to this plan by `docs/plans/review-cleanup.md` (section 1) | D3 (the PNS card's unused data: the card gets a script, and its data becomes what the script reads), S7 (the `pns` / `pns_levels` import loop). S2 has no subject after phase 1: the "All files" code goes. |
| Changes since `v0.2.0rc1` that a caller sees | D18 (decision 17 of `docs/plans/review-cleanup.md`), and the other changes of section 2.4. `CHANGELOG.md` records them. |
| User documentation that depends on the API | C3, C4, C5, C6. |
| Card plugins and a command line (the user) | F1 (a command line, with flags and an optional JSON or TOML config file) and F2 (the standard cards in one call), on one card interface: each card declares its options, its assets and its order in a `CardSpec`, and is found through the entry-point group `pulseq_reports.cards`. The library's own nine cards use the same interface (dogfooding), so every run of the tests exercises it. |
| Checks with an exit status (the user) | A part of F3: a card can report its checks (`Card.checks`), and the command line exits with 2 when a check of a written page failed. The library's checks: the timing check, the peak amplitude and peak slew of each gradient axis against 100 % of the limits (and, with `check_norms`, the |G| peak), and a PNS peak of 100 % or more. |

These items are not in this plan:

- A9 and A10: #65 fixed them. (Phase 4 removes the reserved card script
  names of A10: each card gives its own scripts.)
- F3 to F7, except the part of F3 above. The rest of F3 (a status line in
  each card, a limit column for PNS and RF exposure, a B1+rms limit that the
  caller gives) is not in this plan.
- A check of the vector slew-rate norm: the library does not compute it yet.
  The `TODO.md` item "Study the two definitions of the gradient slew rate"
  gets a note (section 4.4, item 8).
- The version change to `0.2.0rc2`, with C7: a separate chore after this plan.
- C8 (CSS), C10 (`TODO.md`), C12 (`TESTS.md`), L1 to L3.
- The two `TODO.md` items of the review cleanup ("Show where the gradient
  limits happen", "Draw the diagram of a file with very many distinct RF
  events"). Phase 1 changes the number of the diagram data format, and the
  rotation item of `TODO.md` names that number (section 4.1, item 6).
- The text of earlier plans (`docs/plans/rf-profiles.md`,
  `docs/plans/pulseq-reports.md`): they record their own time.

## 2. Read this first (context for the executing agent)

### 2.1 The state of the repository

- `main` is at `3828d2d` (2026-09-29). Its code is the code of `600fd12`: #86
  added only `.claude/agents/`. The facts of section 2.3 were found on
  `600fd12`. The plans `docs/plans/review-bugs.md`
  and `docs/plans/review-cleanup.md` are complete. Read their section 3: their
  workflow rules apply here.
- The tag `v0.2.0rc1` is an annotated tag on `c7a284b` (#46). There is no
  GitHub release and no list of changes. `pyproject.toml` and
  `pulseq_reports.__version__` are `0.2.0rc1`.
- No project uses the library. A search of `/Users/dylan/dev` (the user's
  projects, with their worktrees) found no import of `pulseq_reports` outside
  this repository. The callers of the API are `docs/usage.md`, `README.md`,
  `examples/gre_report.py`, `scripts/`, and the tests.
- `docs/usage.md` says that it describes `main`, and `README.md` pins
  `@v0.2.0rc1`. The release candidate does not have the RF profile card or the
  helpers of #65, so the examples of `docs/usage.md` do not run on it (C7, for
  the version chore).
- Import time: `import pulseq_reports` takes about 0.2 s now. Importing all
  nine card modules takes 0.97 s, and pypulseq alone takes 0.96 s. Every
  caller loads pypulseq, so exports from the package (A6) add almost no time.

### 2.2 Decisions that are already made

Do not open these decisions again.

1. **The scope** is section 1. Do not add or remove a finding. A new case of
   a finding in a file that a phase owns is in scope. Record it in section 8.
2. **One sequence per card, and one sequence per page** (the user). No card,
   analysis function or message keeps a cross-file result. A caller with two
   files makes two pages.
3. **No compatibility names.** No project uses the library (section 2.1), so a
   removed or renamed name is not kept as an alias. `CHANGELOG.md` says what a
   caller of `v0.2.0rc1` changes.
4. **The output of a one-file report does not change, except where section
   3.5 says so.**
5. **No static-text tests** (the user). A test that only checks that a fixed
   sentence is in the output is not added.
6. **No test that only checks a signature.** A `*` in a signature (A3) or a
   renamed parameter has no test of its own: the tests that call the function
   with the new form cover it.
7. **No DOM tests** (decision 10 of `docs/plans/pulseq-reports.md`). A browser
   check covers a change to a card script.
8. **Lean on pypulseq.** Test only the computations of this library.
9. **The library is sequence-agnostic.**
10. **Git.** The user approves each commit message. Merge only when the user
    tells you to. To bring a branch up to date, merge `origin/main` into it.
    Auto mode refuses `git rebase`. Commit with `git -C <path>`, one commit at
    a time.
11. **At most five PRs open at one time.**
12. **Branch prefixes:** `refactor/` for phases 1 to 3, `feature/` for phases
    4 and 5, `docs/` for phase 6, `chore/` for phase 7.
13. **`docs/examples/gre.html` is rebuilt one time, in phase 7.**
14. **The card interface is the only way that `build_cards` and the command
    line reach a card** (the user). The library's own cards are entry points
    of the group `pulseq_reports.cards` in its own `pyproject.toml`, as a
    plugin's cards are. The card builders (for example `timing_card(seq)`)
    stay public for a caller who composes a page by hand.
15. **One option name has one meaning** on the whole page: the rule that A4
    found broken. The card interface checks it at run time (section 4.4,
    item 5). An `Option` object has the name of the builder keyword that it
    stands for, in lowercase (`options.b1rms_window_s`); an uppercase name is
    a default value (`rf_exposure.B1RMS_WINDOW_S = 10.0`).
16. **One hardware for each card** (the user). A PNS card, and a diagram's PNS
    lane, take at most one gradient `.asc` file. A page that shows two systems
    has two cards. The cache keeps one result for each (sequence, hardware),
    so each system is computed one time.
17. **The standard report uses the builders' defaults** (the user). The
    default of an `Option` is the default of its builder keyword. A caller
    that wants more (for example the PNS lane, or more RF profile views)
    gives the option; `examples/gre_report.py` does.
18. **`pns_lane`** (the user): the diagram's option that draws the PNS lane.
    The PNS card is chosen with `cards`/`skip`, not with an option.
19. **The peak-PNS view is a button of the PNS card** (the user). The diagram
    has no peak-PNS window. The PNS card's button sends a `goto` message: to
    the TR that holds the peak, or, with no `TR` definition, to the block that
    holds it.
20. **The workers are the agent types `worker-medium` and `worker-high`**
    (the user), in `.claude/agents/` (#86): Sonnet 5.5
    at `medium` and at `high` effort. Their definitions carry the standing
    rules of a worker (section 3.2). No worker runs at `xhigh` or `max`, and
    no task uses a Haiku worker.
21. **One message hub for each page, and messages by topic only** (the
    user). The page's bus (`PulseqReport.publish`, `subscribe`) is the hub.
    A message has no `target`, and no card filters by `source` or is given
    another card's id. A topic is of one of two kinds:
    - a *state* topic (`sequence`, `cursor`, `anchor`, `view`) has at most one
      publisher on a page;
    - a *request* topic (`goto`) has at most one card that acts on it.
    Each card declares the topics that it publishes and subscribes to, and
    `render_page` checks the two rules (section 4.4, item 7). The check sees
    only message conflicts (for example two diagrams); two cards without
    topics on one page (for example two timing cards of two files) pass it,
    and decision 2 is the caller's rule there.
22. **A button that sends a request is shown only when a card acts on the
    request** (the user). The page decides at run time: the button is hidden
    until the bus has a subscriber for its topic, and hidden again when the
    last one goes. This is so for each "Show" or "go to" button of the
    library (the RF profile card's, the PNS card's) and is the library helper
    for a plugin's buttons (section 4.1, item 11).
23. **The hub is per page load.** Each tab (each load of the page) runs the
    scripts in its own JavaScript realm, with its own `PulseqReport` and its
    own bus, so two tabs of one report never share a message. The library's
    scripts use no API that reaches another tab or window
    (`BroadcastChannel`, storage events, shared or service workers,
    `postMessage`, IndexedDB, cookies); `docs/usage.md` asks a plugin not to.
24. **The browser pane can be hidden.** A browser check compares the base
    page and the branch page with JavaScript snapshots. A card that draws in
    `requestAnimationFrame` (the RF profile card) gets a `setTimeout` shim, and
    the check waits until the card does not change.

### 2.3 Facts (2026-09-29, `main` at `600fd12`)

Paths are under `src/pulseq_reports/` unless they start with `tests/`,
`scripts/`, `docs/`, `examples/` or `README.md`.

**Multi-file code.**

| Where | Fact |
|---|---|
| `cards/timing.py:43-72` | A `"name: "` prefix and one line for each file, only with more than one file. |
| `cards/definitions.py:29-53` | With more than one file: the union of the keys, a column for each file, and a note when no file has definitions. |
| `cards/rf_exposure.py:78-185`; `rf_exposure.py:50-54`, `107-123` | The "All files" table (`_all_files_html`, `_combined_data`, 74 lines) uses the private `_concat_trains` and the `add` field of `_PulseTrain` (the file offset; 0.0 for one file). A one-file card uses the private `_pulse_train` and `_exposure`. |
| `cards/spectrum.py:184-200`; `grad_spectrum.py:187-215` | With more than one file: `combine` (the maximum over the files) and a note. `tests/oracles/grad_spectrum.py:181-209` has a copy of `combine`. |
| `cards/gradient_limits.py:28-56`, `95-120` | A "File" column with more than one file. The note of a file with no gradient is `"name: reason."` for one file too (line 119). |
| `cards/diagram.py:63-123` | `_validate` checks `file_index`. `_diagram_data` lists the files that a window uses, in the order of first use, and puts the file name in front of each window label with more than one file. |
| `cards/blocks.py:56-67` | An `<h3>` with the file name for each file, and the name in front of each window label, only with more than one file. |
| `cards/rf_profile.py:287-399` | The card checks that the names are unique and writes one data entry for each file. The heading "Distinct pulses of each file" is there for one file too; an `<h4>` with each name only with several. Each "Show" button has `data-file="{i}"`. |
| `waveforms.py:26-32`, `325-351` | `TimeWindow(label, file_index, start_s, end_s)`. `first_adc_window(seqs, file_index=0)` and `full_window(seqs, file_index=0)` take the list. |
| `assets/cards/diagram.js` (425 lines) | About 120 lines of multi-file code: a model for each file, decode on first use, the file switch of `showWindow` (307-341, with the only call of `chart.setWindow` at 332), `goto` by `file` or `name` (372-399), and the `file` field of the messages `sequence`, `cursor`, `anchor` and `view` (`{source, file: null}` is the cleared form of `cursor` and `anchor`). |
| `assets/lane_chart.js:500` | `setWindow({lanes, xDomain, extent})` of `laneChart`: documented in `docs/usage.md` (416-440); no test calls it. |
| `assets/lane_chart.js` (`createMessageBus`) | The bus is two `Map`s in a closure: the kept message of each (topic, source), and the subscribers of each topic. No library script uses `BroadcastChannel`, `localStorage`, `sessionStorage`, `postMessage`, a worker, IndexedDB or cookies (checked on 2026-09-29). |
| `assets/cards/diagram.js:424`; `assets/page.js:1-25` | The diagram subscribes to `goto` at the end of its asynchronous start (after it decodes its tables). `page.js` starts each card and does not wait for a card's promise. Thus a card cannot learn at its own start whether a `goto` receiver will come. |
| `assets/cards/rf-profile.js:54`, `205`, `905`; `diagram.js:365` | On `main`, the RF profile card keeps the diagram messages whose `source` is its `diagram_card_id`, and its "Show" buttons send `goto` with `target`; the diagram acts only on a `goto` whose `target` is its own id. |
| `assets/cards/rf-profile.js` (909 lines) | About 80 lines: the files of the card, the match to the diagram's files by name (`fileByName`, the `sequence` handler 205-210, `select` 239-290), caches keyed by file index, and `goto` by `name`. |
| `assets/rf_profiles.js:758-793` | `RfProfiles.fileData(entry, rfTables)` reads one file entry. It has no file index or file list, but it reads `entry.name`: in an error message (762) and in its result (783). `tests/js/test_rf_profiles.js` builds entries with a `name` (164, 996, 1001). |
| `seq_lanes.js`, `pns_lanes.js`, `g_lanes.js`, `chart_math.js`, `map_chart.js`, `page.js` | No file index, file list or file name. |
| `tests/test_rf_profiles_golden.py:728-762`, `848` | The golden test of the RF profiles loads `examples/gre_report.py` by path and calls its `gre_sequence()`; it calls `rf_profile_data(seq, name)`. |
| Data formats | Diagram: `{"format": 1, "files": [{name, duration_s, num_blocks, lanes, tables, pns?}], "windows": [{label, file, view_ms}]}`. RF profile: `{format: 1, diagram_card_id, views, plane, extent_m, files: [...]}`, each entry with `name`. `tests/test_diagram_card.py:60-78` pins the key sets. `scripts/diagram_scale.py:317-368` reads `card.data["files"][0]`. The rotation item of `TODO.md` reserves `"format": 2` of the diagram data. |
| Tests | 18 test functions exist only for more than one file (timing 2, definitions 2, blocks 2, RF exposure 4 with 8 items, spectrum 1, gradient limits 1, diagram 3, extensions 1 with 3 items, `test_grad_spectrum.py` 2), with the helpers of `tests/test_rf_exposure_card.py:125-227`. Two items of `test_rf_profile_card.py::test_value_error_cases` and two tests of that file change. About 63 tests give a list of one sequence or a file index. No test in `tests/js/` and no golden test is multi-file. |

**The file name for one file.** The name reaches the output of a one-file
report in five places: `cards/diagram.py:103` (`files[0].name`, and the
`sequence` message, `diagram.js:130`), `cards/rf_profile.py:213`, `223` and
`259-271` (the data entry and the unlabeled note), `rf-profile.js:78`, `207`,
`249-297`, `905` (the match to the diagram by name, the status line, `goto`),
`rf_profiles.js:762`, `783` (`fileData`), and `cards/gradient_limits.py:119`
(the note). The match by name is the only
use that a card needs, and with one sequence for each page (decision 2) the
RF profile card needs no match at all. Every other output of a one-file
report has no name.

**The page and the packaging.**

| Where | Fact |
|---|---|
| `page.py:24-41` | `Card(id, title, body_html, data=None, script=None, collapsed=False)`. `script` is the name that a card script registers with `PulseqReport.registerCard`. A card has no field for its own script text or CSS. |
| `page.py:129-155` | `render_page` includes `assets/cards/<name>.js` for each distinct `Card.script` for which that file exists (the reserved names of A10: `diagram`, `spectrum`, `rf-profile`), in the order of first use, after the library scripts and before `extra_scripts`. A project card gives its script through `extra_scripts`. |
| `assets/page.js:9` | The page starts each card with `PulseqReport.cards.get(name)`: the function that the card script registered. |
| `pyproject.toml` | No `[project.scripts]` and no `[project.entry-points]`. The package is built by hatchling from `src/pulseq_reports`, with `assets/**` as package data. `uv sync` installs the project in its environment, so its entry points are visible to the tests after a sync. |
| `examples/gre_report.py` | Builds its sequence in Python (`gre_sequence()`); it writes no `.seq` file. |
| pypulseq, `Sequence.write` and `Sequence.read` | The example's sequence, written and read back, keeps its RF use labels (`rf_uses_labeled` is true) and its `TR` definition (0.012 s). A read-back sequence has pypulseq's default system: `max_grad` 1,703,040 Hz/m (40 mT/m). |
| `waveforms.py:325-345` | `first_adc_window` gives the whole file when the file has no ADC. |
| `cards/rf_profile.py:247-251`, `332` | `plane: tuple[str, str] | None`: two different names of `x`, `y`, `z`. |

**The API findings.**

| ID | Where | Fact |
|---|---|---|
| A1 | `pns.py:101`, `131`; `pns_levels.py:76`; `cards/pns.py:18`, `81-83`; `cards/diagram.py:126`, `92`, `109-110` | The gradient `.asc` file has three names: `asc_path` (`pns_levels_for`, `pns_prediction`, `pns_levels`), `gradient_asc` (`pns_data`, `pns_card`), and `pns` (`diagram_card`: `False`, `True` for the example hardware, or a path). `diagram_card` tests `pns is not False`, so `pns=0` or `pns=""` is taken as a path. |
| A1, C4 | `pns.py:94-127` | The cache `_LEVELS_CACHE` is a `WeakKeyDictionary` keyed by the sequence object, with one entry: `(num_blocks, last_block_id, key, PnsLevels)`, where `key = None if asc_path is None else str(Path(asc_path))`. A different key replaces the entry. Thus `pns_card(named, gradient_asc=p)` with `diagram_card(..., pns=True)` runs the SAFE model two times, and the card and the lane show different hardware with no warning. A relative and an absolute spelling of one file are two keys. No test covers the mismatch. `docs/usage.md:137-139` says the two share one computation. |
| D3 | `cards/pns.py:81-107`; `tests/test_pns_card.py:116-125` | `pns_card` sets `data` but has no script, so the page writes a JSON element that no code reads. One test pins the id of that element. |
| A3 | `cards/*.py`, callers | Only `rf_profile_card` has keyword-only options. `diagram_card(seqs, windows, card_id="diagram", pns=False)` has `card_id` before `pns`. `rf_exposure(seq, window_s, periodic)` and `rf_exposure_data(seq, periodic, window_s)` take two options in opposite orders. `render_page` and `write_page` have `extra_scripts` before the `*`. Every card builder call in the tests, examples, scripts and documentation gives its options by keyword. Calls that give an option by position: `cards/pns.py:21`, `100`; `pns.py:126`, `136`; `cards/diagram.py:106`, `110`; `cards/blocks.py:30`; `page.py:183`; `scripts/diagram_scale.py:311`, `335`; `tests/test_page.py:230`, `232`; `tests/test_pns.py:93`, `105`, `137`, `308-314`; `tests/test_pns_levels.py:262`; `tests/test_waveforms.py:104`, `166`, `168`; `tests/test_blocks_card.py:69`, `88`. |
| A4 | `cards/gradient_limits.py:71-111`; `grad_limits.py:526-536` | `gradient_limits_card(..., window: tuple[float, float] | None = None, ...)` takes one `(start_s, end_s)`; `blocks_card` and `diagram_card` take `TimeWindow` objects. `docs/usage.md` does not explain `window`. |
| A4 | `rf_exposure.py:27`, `42-44`, `294`; `grad_spectrum.py:27`; `tests/test_rf_exposure.py:133-137`; `tests/oracles/rf_exposure.py:25-34` | `window_s` of `rf_exposure_card`, `rf_exposure_data` and `rf_exposure` is the length of the B1+rms averaging window. `RfExposure` has the fields `window_s`, `b1rms_window_ut` and `window_used_s`; the oracle's own `RfExposure` has the same names, and `_assert_matches_oracle` compares them field by field. `rf_exposure.WINDOW_S` is 10 s (B1+rms), and `grad_spectrum.WINDOW_S` is 0.05 s (the FFT window). |
| A5 | `docs/usage.md:104-108`; `examples/gre_report.py:126-130`; `pns.py:147-165` | Five lines make the peak-PNS window: `pns_prediction`, `peak_tr_window`, a `None` check, a tuple, and a `TimeWindow` with file index 0. Neither passes a gradient `.asc` file, so a caller with a real scanner gives the file a third time. |
| A6 | `__init__.py`; `cards/__init__.py` | Neither exports a name. The page of `docs/usage.md` section 2 needs 14 imports; `examples/gre_report.py` needs 13. |
| A7 | `cards/gradient_limits.py:74`; `grad_limits.py:37-47`, `104-113` | `limits` has no annotation. With `None`, the limits are `seq.system` (label "pypulseq system limits"): after `Sequence.read`, pypulseq's defaults (40 mT/m, 170 T/m/s). The card note names the label, not the values. `README.md` (quick start) reads a file and calls `gradient_limits_card(seqs)` with no limits, and does not say what the default is. |
| A7 | `grad_limits.py` (`GradientLimits`, `AxisResult`) | Each axis has a peak amplitude and a peak slew. The three-axis vector has a peak (`vector_peak_mt_per_m`) and an RMS, but no slew: the library does not compute a vector slew (`TODO.md`, "Study the two definitions of the gradient slew rate"). |
| A7 | `cards/spectrum.py:162-166`; `grad_spectrum.py:42-62` | `spectrum_card(seqs, resonances=PRISMA_AS82_RESONANCES, scanner_label="MAGNETOM Prisma (AS82)", ...)` takes the coil name apart from its bands. `AcousticResonance(frequency_hz, bandwidth_hz)` has no label and no docstring. |
| A7 | `docs/usage.md`, `README.md` | Neither names `HardwareLimits` or `AcousticResonance`. No test or caller builds a `HardwareLimits`. |
| A8 | `cards/*.py`; `waveforms.py:139` | `pns_data`, `rf_exposure_data`, `spectrum_data`, `timing_errors`, `rf_table` and `rf_profile_data` have public names. Their only callers are their own cards and the tests. `waveforms.block_row` has one caller (`block_rows`). `docs/usage.md` documents `pns_prediction`, `peak_tr_window` and `pns_levels_for`, but not `gradient_limits`, `rf_exposure`, `gradient_spectrum`, their result types, or `Card`. `spectrum_data`'s docstring still says "vb-pulseq parity". |
| S7 | `pns.py:30-31`, `112-116`; `pns_levels.py:29` | `pns_levels.py` imports the module `pns` for `EXAMPLE_HARDWARE`, `read_gradient_asc`, `hardware_name`, `NO_GRADIENTS` and `PEAK_TOLERANCE`, so `pns.py` imports `pns_levels` inside `pns_levels_for`. `tests/test_pns.py:270-274` patches `pns_levels_module.pns_levels`; a move of `pns_levels_for` must keep a patch point. |

### 2.4 Changes since `v0.2.0rc1` that a caller sees

`CHANGELOG.md` (phase 6) starts from this list. The PR of each change is in
brackets.

Python, removed or renamed:

- `seq_utils.BlockTiming` and `seq_utils.iter_blocks` are removed. They are
  in `tests/oracles/blocks.py` now (D18, #79).
- `pns_levels.pns_levels` has no `chunk_samples` keyword (D15, #78).
- `seq_utils.gradient_offsets` needs `first`, `last` and `shape_dur` on a
  gradient that is not a trapezoid (D19, #79). Every gradient that pypulseq
  1.5.0.post1 makes has them.
- `report.css` has no `--col-seq-*` tokens and no rules for vb-pulseq's own
  cards (D1, D2, #65).

Python, added or changed:

- `markup.fmt`, `html_table`, `zoom_controls` and `lanes_json` are public
  (#65). `render_page` and `write_page` take `extra_css`, and raise
  `TypeError` for a `str` in `extra_scripts` or `extra_css` (A9, #65).
  `docs/usage.md` lists the reserved card script names (A10, #65).
- The RF pulse profiles: `rf_profile_card`, and the modules `rf_profiles`,
  `rf_sim` and `profile_metrics` (#57 to #62).
- `waveforms.duration_s` returns a Python `float` (P2, #79).
- `pns.peak_tr_window` returns `None` for a sequence with no block (P3, #79);
  before, it raised `StopIteration`.
- The bug fixes B1 to B6 (#69 to #74) change values or text of the gradient
  limits, the diagram, the |G| lane and the spectrum note.
- The diagram's `aria-label` names every lane (C13, #78).

JavaScript:

- `PnsLanes.statusText(result, onRaster)` is `statusText(result)` (S10, #80).
- `ChartMath` has `colorRamp`, `colorIndex`, `nearestIndex` (#54) and
  `sig3`, `segTree`, `minMaxSegments` (#83).
- `PulseqReport` has `decodeTable`, `createMessageBus`, `publish`,
  `subscribe` (#53) and `mapChart` (#54, #61). `laneChart` takes `onCursor`
  and `onAnchor`.
- `SeqLanes` has `sequenceView` and `GRAD_HZ_PER_VALUE` (#53).
- `RfProfiles` is new (#60, #61). `assets/cards/rf-profile.js` is a new
  reserved card script name (#62).

### 2.5 Terms

- **The review.** `docs/reviews/2026-09-28-code-review.md`.
- **Option.** A keyword-only parameter of a card builder with a default
  value; in phase 4, also the `Option` object that declares it.
- **Keyword-only.** A parameter after `*` in the signature.
- **Card-internal function.** A function that only its own card calls, for
  example `pns_data` (A8).
- **Baseline.** The worktree `.worktrees/base` at the commit that the task
  branch last took from `main` (section 3.5).
- **One-file report.** A page whose cards all show the same one sequence, for
  example `examples/gre_report.py`.
- **Standard windows.** The diagram's windows in the standard report:
  `first_adc_window(seq)` and `full_window(seq)`.

## 3. How to execute this plan

### 3.1 Workflow

As in `docs/plans/review-cleanup.md`, section 3.1. Also:

1. Start each phase with the `dev-workflow:start-task` skill.
2. Each phase that adds, removes or renames a test updates its `TESTS.md`
   section in the same PR. A PR that deletes a test says why.
3. Each PR lists its changes to the public API in its description, in the
   form of `CHANGELOG.md` ("Breaking changes", "Added", "Fixed").
4. Each phase ends with a line-by-line review of each worker's diff by the
   executing agent.
5. A phase that changes `pyproject.toml` (phases 4 and 5) runs
   `nix develop --command uv sync --frozen` again in its worktree after the
   change, so that the installed project has the new entry points. CI makes a
   new environment for each run.

### 3.2 Worker model tiers

| Tier | Who | Use it when |
|---|---|---|
| SM | the agent type `worker-medium` (Sonnet 5.5, `medium` effort) | The plan gives the task exactly: a rename, a move, a removal, a `*` in signatures, or code whose design section 4 gives in full. |
| SH | the agent type `worker-high` (Sonnet 5.5, `high` effort) | The task is hard or long: a card script, an interface with local design decisions, or a large rewrite of documentation. |
| X | the executing agent (Opus 5.5), not a worker | The baseline, the comparisons, the browser checks, and the review of every diff. |

Why these tiers (the Sonnet 5.5 documentation, 2026-09-29):

- For agentic coding, Anthropic's guide starts Sonnet 5.5 at `medium` effort
  for a well-specified task and at `high` for a harder or longer one. At
  `low`, it can report a change as done without a check; at `low` and
  `medium`, it can stop to check in on a long task. At `xhigh` and `max`, it
  starts its own review rounds and can launch reviewer agents: here, the
  executing agent reviews, so no worker runs at those levels.
- At each effort level, Sonnet 5.5 tends to add tests, documents and small
  files that were not asked for. This plan forbids such additions (decisions
  5 and 6, and `TESTS.md`), so the agent definitions tell the worker to add
  nothing that the task does not name, and to report an idea instead.
- The guide recommends an Opus model for the hardest long-horizon work:
  tier X stays with the executing agent.
- In the review cleanup (2026-09-29), the one Haiku worker missed an item
  that its plan gave in full, and wrote a parser of its own to report an
  error. The Sonnet workers' diffs needed only changes of wording. Thus the
  plan has no Haiku tier.

The rules of a worker are in its agent definition (`.claude/agents/`): it
works only in its worktree, does no git writes, does not sync dependencies,
reads the plan sections in the plan file itself (Sonnet 5.5 has a 1M-token
context, so a brief names the sections and does not paraphrase them), writes
only the tests that the task names, runs a real check before it reports a
change as done, and stops and reports when an output would change in a way
that section 3.5 does not list. The brief of each task gives: the task
number, the worktree, the plan file and sections, the files, and the checks
to run.

Claude Code loads the agent types when a session starts. Start this plan in a
session that lists `worker-medium` and `worker-high` as agent types (a session
started after #86 was merged).

### 3.3 Order and parallel work

```
Wave 1:  Phase 1 (one sequence per card: Python, JavaScript, data formats)
Wave 2:  Phase 2 (the PNS API and the PNS card's button)
         Phase 3 (the analyses and the other cards)
Wave 3:  Phase 4 (the card interface, the checks, and the nine cards on it)
Wave 4:  Phase 5 (the command line)
Wave 5:  Phase 6 (exports and documentation)
Wave 6:  Phase 7 (results)
```

- Phase 1 edits every card builder, so it goes first, alone.
- Phases 2 and 3 share no file, except their own `TESTS.md` sections
  (section 3.4). They run at the same time.
- Phase 4 needs the final options of phases 2 and 3: a `CardSpec` declares
  them.
- Phase 5 builds the command line on the interface of phase 4.
- Phase 6 documents the final API, the interface and the command line.

### 3.4 File ownership

| Phase | Branch | Files that the phase edits |
|---|---|---|
| 1 | `refactor/one-sequence-per-card` | `cards/*.py`, `waveforms.py`, `seq_utils.py`, `rf_exposure.py` (`_concat_trains`, `_PulseTrain.add`), `grad_spectrum.py` (`combine`), `assets/cards/diagram.js`, `assets/cards/rf-profile.js`, `assets/rf_profiles.js` (`fileData`), `assets/lane_chart.js` (`setWindow`), `examples/gre_report.py`, `scripts/cards_scale.py`, `scripts/diagram_scale.py`, `TODO.md` (the reserved format number), the tests of these files, `tests/oracles/grad_spectrum.py` (the copy of `combine`), and their `TESTS.md` sections |
| 2 | `refactor/pns-api` | `pns.py`, `pns_levels.py`, `asc.py` (new), `cards/pns.py`, `cards/diagram.py`, `assets/cards/pns.js` (new), `assets/cards/diagram.js` (the `goto` range form), `examples/gre_report.py`, `scripts/cards_scale.py`, `tests/test_pns.py`, `tests/test_pns_levels.py`, `tests/test_pns_card.py`, `tests/test_diagram_card.py`, `tests/test_extensions.py`, `tests/test_pns_lanes_golden.py`, and their `TESTS.md` sections |
| 3 | `refactor/card-api` | `grad_limits.py`, `rf_exposure.py`, `grad_spectrum.py`, `waveforms.py`, `diagram_data.py`, `page.py`, `cards/gradient_limits.py`, `cards/rf_exposure.py`, `cards/spectrum.py`, `cards/timing.py`, `cards/blocks.py`, `cards/rf_profile.py`, `scripts/diagram_scale.py`, the tests of these modules except the phase 2 files, and their `TESTS.md` sections. The oracles (`tests/oracles/*.py`) do not change: a test gives each oracle its own option names and reads its own field names. |
| 4 | `feature/card-interface` | `registry.py` (new: `Option`, `CardSpec`, `ReportContext`, discovery, `build_cards`), `options.py` (new: the shared `Option` objects), `page.py` (`Card.scripts`, `css`, `checks`, `publishes`, `subscribes`; `Check`; `TOPIC_KINDS` and the topic check), `cards/*.py` (a `SPEC`, the assets, the checks and the topics of each card; `check_norms`), `pyproject.toml` (the entry points), `examples/gre_report.py` (`build_cards`), `TODO.md` (the note of section 4.4, item 8), `tests/test_registry.py` (new), `tests/plugin_card.py` (new, a test plugin), the tests of `page.py` and of the cards with checks, and their `TESTS.md` sections |
| 5 | `feature/command-line` | `cli.py` (new), `pyproject.toml` (`[project.scripts]`), `tests/test_cli.py` (new), `TESTS.md` (its new section) |
| 6 | `docs/api-exports-docs` | `__init__.py`, `cards/__init__.py`, `docs/usage.md`, `README.md`, `examples/gre_report.py` (imports), `CHANGELOG.md` (new), `tests/test_exports.py` (new), `TESTS.md` (its new section) |
| 7 | `chore/public-api-results` | `docs/examples/gre.html`, the status of the review, this plan (status and section 8) |

Rules:

1. A phase edits only its files. A call in a file of the other wave-2 phase
   that the change breaks goes into the phase that owns that file, in the new
   form, before the change. One case is known: phase 2 changes
   `lane_meta(seq, tables)` in `cards/diagram.py` to
   `lane_meta(seq, tables=tables)`; both forms work before phase 3.
2. `TESTS.md`: each phase edits only the sections of its test files. If a
   conflict occurs, keep both sides.
3. Between phase 1 and phase 6, `docs/usage.md` and `README.md` show the old
   calls. They have no test. Phase 6 corrects them.
4. `examples/gre_report.py` keeps its function `gre_sequence()`: the golden
   test of the RF profiles imports the example and calls it. Each phase that
   edits the example runs that test.

### 3.5 Behavior preservation

1. **The baseline.** As in `docs/plans/review-cleanup.md`, section 3.5,
   item 1: `git -C <main checkout> worktree add --detach .worktrees/base origin/main`,
   then `nix develop --command uv sync --frozen` in it. Before each
   comparison, check out the merge-base of the task branch in it. Remove it
   after phase 7.
2. **The comparison set.**
   1. The example page: `examples/gre_report.py` on the baseline, and on the
      branch (with the branch's own edits of the example). Compare them with
      the masked page diff of section 9.2: every difference, with the text of
      the changed scripts masked.
   2. The Python dump: `dump_py.py` of `docs/plans/review-cleanup.md`,
      section 9.1, on the baseline; and a copy with its calls in the new form
      on the branch (section 9.1). The branch's copy has no `many/` entries
      (phase 1 removes the multi-file cards). The two JSON files are compared
      entry by entry.
   3. The browser, for phases 1 and 2 (section 9.3): the diagram card, the RF
      profile card and (phase 2) the PNS card of the example page, on the
      baseline and on the branch, in both themes. The console has no error.
   4. `nix develop --command scripts/check` passes on the branch.
3. **Expected differences.** Any other difference stops the phase.

   | Phase | Example page | Python dump | Browser |
   |---|---|---|---|
   | 1 | The scripts `diagram.js`, `rf-profile.js`, `rf_profiles.js` and `lane_chart.js`; the JSON data of the diagram and the RF profile card (the formats of section 4.1, item 6); the RF profile card's heading "Distinct pulses" (was "Distinct pulses of each file"), its buttons without `data-file`, and its data without `diagram_card_id`. | The `data` of `*/card/diagram` and `*/card/rf_profile` (the new formats). The file name in the note of `*/card/limits` for a file with no gradient. No `many/` entries. | None, except the file name in the RF profile card's status line, and the `file` and `target` fields of the messages (compared without them). |
   | 2 | The diagram has no "Peak-PNS TR" window (its button and its `windows` entry); the PNS card has a button, the script `pns.js` and its new data (section 4.2, item 5). | `*/card/pns`: the new `data`. | The PNS card's button: the diagram shows the peak's TR, with the anchor at the peak time, as the "Peak-PNS TR" window of the baseline showed it; the RF profile card follows the anchor. |
   | 3 | Only the note of the gradient limits card (the values of the limits). | `*/card/limits*`: the note. `*/card/limits_win`: the form of a windowed card (section 4.3, item 2). The renamed `RfExposure` fields. | Not run. |
   | 4 | None: `examples/gre_report.py` uses `build_cards`, and the page must equal the baseline's page byte for byte. | The new `Card` fields (`scripts`, `css`, `checks`, `publishes`, `subscribes`) in each card entry; `body_html` and `data` equal. | Not run. |
   | 5 | None | Not run. The command line's page for a `.seq` file equals the page that `build_cards` gives for the same file read by `Sequence.read` (section 4.5). | The pages of task 5.2. |
   | 6 | None | None | Not run. |
   | 7 | The sum of phases 1 to 3, against the committed `docs/examples/gre.html` (the page of `600fd12`) | Not run | The nine cards draw. |

## 4. Design

### 4.1 Phase 1: one sequence per card

1. **The card builders take one `pp.Sequence`**, and `NamedSequence` is
   removed from `seq_utils.py`: no card needs the name (section 2.3). The
   options become keyword-only (A3) in the same change, because every
   signature changes:
   - `timing_card(seq, *, card_id="timing")`
   - `definitions_card(seq, *, card_id="definitions")`
   - `rf_exposure_card(seq, *, periodic=True, window_s=WINDOW_S, card_id="rf-exposure")`
   - `spectrum_card(seq, *, resonances=..., scanner_label=..., card_id="gradient-spectrum")`
   - `pns_card(seq, *, gradient_asc=None, card_id="pns")`
   - `gradient_limits_card(seq, *, window=None, limits=None, card_id="gradient-limits")`
   - `diagram_card(seq, windows, *, pns=False, card_id="diagram")`
   - `blocks_card(seq, *, windows=None, max_rows=500, card_id="blocks")`
   - `rf_profile_card(seq, *, views=("profile",), plane=None, extent_m=None, card_id="rf-profile")`

   Phases 2, 3 and 4 change some options again. The output of a one-file card
   does not change, except the items of section 3.5.
2. **The windows have no file.** `TimeWindow(label, start_s, end_s)`.
   `first_adc_window(seq)` and `full_window(seq)` take the sequence.
   `diagram_card` and `blocks_card` check that each window is inside the
   sequence and has an end after its start (`ValueError` with the label).
3. **The RF exposure card calls `rf_exposure.rf_exposure`**, the public
   function, and then `_to_dict`: it uses no private name of `rf_exposure.py`
   (the point of S2).
4. **Removed:**
   - The multi-file branches of each card (section 2.3), the empty-list
     `ValueError`s, the file name in front of labels, and the unique-name
     check of the RF profile card.
   - The RF exposure "All files" table: `_all_files_html`, `_combined_data`,
     `rf_exposure._concat_trains`, and the `add` field of
     `rf_exposure._PulseTrain` (0.0 for one file, so the arithmetic of one
     file does not change: the dump checks it).
   - `grad_spectrum.combine`, its copy in `tests/oracles/grad_spectrum.py`,
     and the spectrum card's "maximum over the files" note.
   - The definitions card's union of keys and its file columns.
   - `seq_utils.NamedSequence`.
   - `laneChart`'s `setWindow` (`lane_chart.js`): no card calls it after the
     file switch goes. `docs/usage.md` loses it in phase 6.
5. **Texts without the file name:** the gradient limits note of a file with
   no gradient is `"reason."`; the RF profile card's status line and its
   unlabeled note have no name; its heading is "Distinct pulses".
6. **The data formats.**
   - Diagram: `{"format": 2, "file": {duration_s, num_blocks, lanes, tables, pns?}, "windows": [{label, view_ms}]}`.
     The rotation item of `TODO.md` then reserves `"format": 3`.
   - RF profile: `{"format": 2, views, plane, extent_m, "file": {...}}`, the
     entry of `main` without `name`, and no `diagram_card_id`.
   - `scripts/diagram_scale.py` reads `card.data["file"]`.
7. **`diagram.js`:** one model, decoded at start. No file switch: a window
   button sets the view of the one file. The messages lose `file` (and
   `name`): `sequence {source, view}`, `cursor {source, tS, block, pxS}`,
   `anchor {source, tS, block}`, `view {source, t0S, t1S}`. The cleared form
   of `cursor` and `anchor` is `{source, tS: null}`. `goto {source, block}`
   (no `target`, decision 21): the diagram does what `main` does for a block
   of the file it shows, without the file switch.
8. **`rf-profile.js`:** one file. It takes every `sequence`, `cursor` and
   `anchor` message: a page has one publisher of each (decision 21). Its
   caches use the key of a pulse without a file index. The "Show" buttons
   send `goto {source, block}`, and are shown only while `goto` has a
   subscriber (item 11). `rf_profile_card` has no `diagram_card_id`, and the
   RF profile data has no `diagram_card_id` key. **`RfProfiles.fileData`** (`rf_profiles.js`)
   no longer reads `entry.name`: its error message names no file, and its
   result has no `name`. `rf_profile_data(seq)` takes no name.
   `tests/js/test_rf_profiles.js` builds entries without `name`, and
   `tests/test_rf_profiles_golden.py` calls `rf_profile_data(seq)`.
9. **Tests.** Delete the 18 multi-file tests and their helpers (section
   2.3), and say so in the PR. Adapt the others to one sequence. Rewrite the
   two tests of `tests/test_rf_profile_card.py` that mix files as one-file
   tests of the same behavior. `tests/test_diagram_card.py` pins the new key
   sets of the data. A new test: a window outside the sequence raises
   `ValueError` (the check of item 2), for the diagram and the blocks card.
10. **Callers:** `examples/gre_report.py`, `scripts/cards_scale.py`,
    `scripts/diagram_scale.py`.
11. **The bus tells a card when a topic has a subscriber** (decision 22).
    `createMessageBus` gets `watchSubscribers(topic, fn)`: it calls
    `fn(count)` at once with the number of subscribers of `topic`, then each
    time that number changes; it returns a function that stops the watch.
    `PulseqReport.watchSubscribers` is the page bus's. A helper
    `PulseqReport.requestButton(button, topic)` keeps `button.hidden` true
    while `topic` has no subscriber. New node tests (`tests/js/test_messages.js`):
    the count at once, after a subscribe and after an unsubscribe, and a
    stopped watch. The buttons themselves are checked in the browser.

### 4.2 Phase 2: the PNS API and the PNS card's button (A1, A5, D3, S7, and A3 and A8 for the PNS modules)

1. **One name, `gradient_asc`** (A1). `pns_levels_for`, `pns_prediction`,
   `pns_levels` and `pns_card` take `gradient_asc`, keyword-only. The
   `asc_file` fields of `PnsPrediction` and `PnsLevels` keep their names:
   they hold the file name, a result, not the argument.
2. **`diagram_card(seq, windows, *, pns_lane: bool = False, gradient_asc=None, card_id="diagram")`**
   (A1, decision 18). `gradient_asc` with `pns_lane=False` raises
   `ValueError`. A value of `pns_lane` that is not a `bool` raises
   `TypeError`.
3. **The cache keeps one entry for each hardware** (decision 16). The entry
   of a sequence is a small dict keyed by the hardware key; the key is `None`
   or `str(Path(gradient_asc).resolve())`. A page with two PNS cards for two
   systems, or a PNS card and a PNS lane, runs the SAFE model once for each
   distinct file. A new test: two keys alternated (a, b, a, b) run the model
   two times, not four. The old test that pins "a, a, b, a gives 3 calls"
   changes to 2 calls. The memory is one `PnsLevels` for each (sequence,
   hardware): at most `2 * MAX_BINS` float32 values (16 MB) each.
4. **`pns_card(seq, *, gradient_asc=None, card_id="pns")`** (decision 19).
   When the prediction has a peak, the card has a button under its table and
   the script `assets/cards/pns.js` (`script="pns"`, a new reserved name until
   phase 4). The script sends a `goto` when the button is pressed, and shows
   the button only while `goto` has a subscriber (section 4.1, item 11): on a
   page with no diagram, the button stays hidden. When the prediction has a
   `reason` (no gradients), the card has no button, no script and no data.
5. **The PNS card's data (D3)** is only what its script reads:
   `{"format": 1, "goto": ...}`. With a `TR` definition, `goto` is
   `{"t0S", "t1S", "anchorS"}`: the TR that `peak_tr_window` gives, and the
   peak time. Without one (`peak_tr_window` gives `None`), `goto` is
   `{"block": k}`: the play index of the block that holds the peak time
   (`sequence_index(seq)`). The button text says "Show the peak's TR in the
   diagram" or "Show the peak's block in the diagram". The old summary data
   goes. `test_card_id_is_used_for_the_section_and_data_element` becomes a
   test of the section id and of the new data element. New tests: the data of
   a sequence with a `TR` (the range equals `peak_tr_window`, the anchor
   equals the peak time), without a `TR` (the block holds the peak time), and
   without gradients (no data, no script).
6. **`goto` gets a range form** (`diagram.js`):
   `{source, t0S, t1S, anchorS}`. The diagram sets the view to
   `[t0S, t1S]` (moved inside the file if it reaches past an end) and the
   anchor to `anchorS`. A message with neither a `block` nor a range, or with
   `t1S <= t0S`: a console warning and no change, as for a bad block on
   `main`.
7. **The diagram has no peak-PNS window** (A5, decision 19).
   `examples/gre_report.py` and `docs/usage.md` lose the five lines;
   `peak_tr_window` stays public, for a caller that wants the range.
8. **A8: `pns_data` becomes `_pns_data`.** Its tests call the private name.
9. **S7: a module `asc.py`** holds `read_gradient_asc`, `hardware_name`,
   `EXAMPLE_HARDWARE` and `INCLUDE_LINE`. `NO_GRADIENTS` and
   `PEAK_TOLERANCE` move to `pns_levels.py`. `pns.py` imports `pns_levels` at
   the top, with no function-level import and no `TYPE_CHECKING` block.
   `pns.py` keeps no copies of the moved names (decision 3); the tests import
   them from their new modules. The patch point of
   `tests/test_pns.py:270-274` becomes `pns.pns_levels` (the name that
   `pns.py` imports).
10. **A3** for `pns.py`, `pns_levels.py` and `cards/pns.py`: every option is
    keyword-only.
11. **Callers:** `examples/gre_report.py` (the peak-PNS lines go;
    `pns_lane=True`), `scripts/cards_scale.py`, and the tests of section 3.4.

### 4.3 Phase 3: the analyses and the other cards (A3, A4, A7, A8)

1. **A3: keyword-only options** in every public function of the phase 3
   files that phase 1 did not change: `gradient_limits`, `rf_exposure`,
   `gradient_spectrum`, `block_rows`, `file_lanes` (`start_s`, `end_s`),
   `lane_meta` (`tables`), and `render_page` and `write_page`
   (`extra_scripts`, and `extra_css` as now). The positional callers of
   section 2.3 change to keywords.
2. **A4: the gradient limits card takes `TimeWindow` objects**:
   `gradient_limits_card(seq, *, windows: Sequence[TimeWindow] | None = None, limits: HardwareLimits | None = None, card_id=...)`,
   as `blocks_card`. With `windows=None`, the card is the same as on `main`:
   the whole file. With windows, one table for each window, with an `<h3>`
   of its label. A window outside the sequence raises `ValueError` before any
   computation. The analysis function `gradient_limits(seq, *, window=None, limits=None)`
   keeps its `(start_s, end_s)` tuple. A new test: two windows give two tables
   with the values of `gradient_limits` for each range.
3. **A4: the B1+rms averaging window.** The option is `b1rms_window_s` in
   `rf_exposure_card` and `rf_exposure`. The default constants are
   `rf_exposure.B1RMS_WINDOW_S` and `grad_spectrum.FFT_WINDOW_S`. The
   `RfExposure` fields `window_s` and `window_used_s` become `b1rms_window_s`
   and `b1rms_window_used_s`; the card text does not change.
   `_assert_matches_oracle` compares `ours.b1rms_window_s` with
   `theirs.window_s` (the oracle keeps its names).
4. **A7: the gradient limits.**
   - `limits: HardwareLimits | None` in the card and the function.
   - The card note gives the values of the limits with their label, for
     example "Limits: pypulseq system limits (40 mT/m, 170 T/m/s)". This
     changes the card output (section 3.5).
5. **A7: the gradient coil.** A new frozen dataclass
   `grad_spectrum.GradientCoil(label: str, resonances: tuple[AcousticResonance, ...])`,
   the constant `PRISMA_AS82 = GradientCoil("MAGNETOM Prisma (AS82)", PRISMA_AS82_RESONANCES)`,
   and `grad_spectrum.COILS = {"prisma-as82": PRISMA_AS82}`, the built-in coils
   by the name that the command line's `--coil` takes. `spectrum_card(seq, *, coil: GradientCoil = PRISMA_AS82, card_id=...)`
   replaces `resonances` and `scanner_label`. `gradient_spectrum(seq, *, resonances=...)`
   keeps its resonances: the label is text for the card, not an input of the
   analysis. `AcousticResonance` gets a docstring. The card output does not
   change for the default coil.
6. **A8: card-internal functions become private**: `rf_exposure_data`,
   `spectrum_data`, `timing_errors`, `rf_table`, `rf_profile_data` and
   `waveforms.block_row` get a leading underscore. The tests call the private
   names. `spectrum_data`'s docstring loses "vb-pulseq parity".

### 4.4 Phase 4: the card interface and the checks (F2, a part of F3)

1. **`Option(name, type, default, help, cli=None)`** (`registry.py`). One
   option of one or more cards. `name` is the builder keyword (decision 15);
   the command line uses `--` and the name in `kebab-case`. `type` gives the
   flag: `bool` gives `--name` and `--no-name`; `int`, `float` and `Path` one
   value; `tuple[str, ...]` a comma list (`plane`: a comma pair). `cli` is for
   an option whose value is not one flag: the flags it adds, a function from
   their values to the option's value (section 4.5, item 2), and a function
   from its config value to the option's value (section 4.5, item 5).
2. **`options.py`: the shared options**, one object each, named as the
   keyword: `gradient_asc`, `limits`, `coil`, `periodic`, `b1rms_window_s`,
   `pns_lane`, `views`, `plane`, `extent_m`, `max_rows`, `check_norms`. A
   plugin that uses one of these options imports its object.
3. **`CardSpec(name, order, build, options, publishes=(), subscribes=(), when=None)`.**
   `name` is the card's name (`[a-z][a-z0-9-]*`, also its `card_id` in the
   standard report). `order` is a number. `build(ctx) -> Card` makes the
   card. `options` is the tuple of `Option` objects that `build` reads.
   `publishes` and `subscribes` are the topics of its messages (decision 21);
   the card that `build` makes has the same topics. `when(ctx) -> bool` says
   if the card applies; with `None`, it always applies. The library's specs
   (the diagram publishes `sequence`, `cursor`, `anchor`, `view` and
   subscribes to `goto`; the RF profile card subscribes to `sequence`,
   `cursor`, `anchor` and publishes `goto`; the PNS card publishes `goto`):

   | Order | Name | Options | Context | When |
   |---|---|---|---|---|
   | 10 | `timing` | | | |
   | 20 | `rf-exposure` | `periodic`, `b1rms_window_s` | | |
   | 30 | `diagram` | `pns_lane`, `gradient_asc` | the standard windows | |
   | 40 | `rf-profile` | `views`, `plane`, `extent_m` | | the RF pulses are labeled (`rf_uses_labeled`), and a selected card publishes `anchor` |
   | 50 | `gradient-spectrum` | `coil` | | |
   | 60 | `pns` | `gradient_asc` | | |
   | 70 | `gradient-limits` | `limits`, `check_norms` | | |
   | 80 | `definitions` | | | |
   | 90 | `blocks` | `max_rows` | | |

   The diagram's spec gives `gradient_asc` to `diagram_card` only when
   `pns_lane` is true (so a `gradient_asc` for the PNS card alone does not
   raise the `ValueError` of section 4.2, item 2). The keywords that the
   command line does not set: `card_id`, and the `windows` of the blocks and
   gradient limits cards (the standard report shows the whole file).
4. **`ReportContext`**, made one time for each report: `seq`,
   `ctx.option(option)` (the value, or the option's default; an option that
   the card's spec does not declare raises `ValueError`, so the declarations
   stay complete), `ctx.windows()` (the standard windows, made on first use),
   and `ctx.publishes(topic)` and `ctx.subscribes(topic)`: whether a selected
   card declares the topic. A card never asks for another card by name
   (decision 21).
5. **Discovery.** `registry.discover()` reads the entry points of the group
   `pulseq_reports.cards`; each entry point is a `CardSpec`. It checks:
   - two specs with one name: an error that names both entry points;
   - two options with one name that are not the same `Option` object: an
     error that names both cards and the option (decision 15);
   - a spec whose `build` or `when` is not callable, or whose `name` or
     `order` is not valid: an error.
   These are errors at the start, before any card is built.
6. **`build_cards(seq, *, cards=None, skip=(), **options) -> list[Card]`.**
   It discovers the specs, keeps the names in `cards` (all when `None`) and
   not in `skip`, sorts them by `order`, makes one `ReportContext`, and builds
   each card whose `when` is true. An option that no selected card declares
   raises `TypeError`, as an unknown keyword does. A name in `cards` or `skip`
   that no spec has raises `ValueError`. When a card's `when` or `build`
   raises (also the `NotImplementedError` of a card that refuses a sequence
   with rotations), the card is an error card: `id` the spec's name, title "<name>:
   error", the message in the body, and one failed check. The error, with its
   traceback, goes to the logger `pulseq_reports`. The other cards are built.
7. **The card's own assets and checks.** `Card` gets
   `scripts: tuple[str, ...] = ()` and `css: tuple[str, ...] = ()` (the texts
   that the card needs on the page), and `checks: tuple[Check, ...] = ()`,
   with `Check(name: str, passed: bool, message: str)` in `page.py`, and
   `publishes` and `subscribes` (tuples of topics, decision 21). `render_page`
   raises `ValueError` when two cards publish one state topic or subscribe to
   one request topic (`page.TOPIC_KINDS` lists the library's topics and their
   kinds; a topic that is not in it is not checked while the interface is
   provisional).
   `render_page` includes each distinct text of `scripts` and `css` one time,
   in the order of first use, in the place where the reserved card scripts
   are now; it does not show `checks` (the card's own text says the values).
   The library's card builders set `scripts` from their `assets/cards/*.js`
   file; the reserved-name lookup of `page.py` (A10) is removed. A card built
   by hand (with its builder, not `build_cards`) has its assets and checks
   too. `extra_scripts` and `extra_css` stay, for the page's own scripts and
   CSS. The example page must not change (section 3.5): the script order
   stays the same.
8. **The library's checks:**
   - `timing`: one check, failed when pypulseq's timing check gives errors.
   - `gradient-limits`: one check, failed when the peak amplitude or the
     peak slew of an axis (Gx, Gy, Gz) in a table of the card is above 100 %
     of its limit; the message names the axis, the value and the table. The
     new option `check_norms: bool = False` also fails the check when the |G|
     peak is above 100 % of `max_grad`: a check that does not depend on the
     rotation of the gradients. The library has no vector slew yet: the
     `TODO.md` item "Study the two definitions of the gradient slew rate" gets
     a note that a vector-slew check waits for it.
   - `pns`: one check, failed when the peak is 100 % or more of the
     stimulation threshold.
   The other cards have no check. A card with a `reason` (for example no
   gradients) passes its check.
9. **The nine library cards on the interface.** Each card module gets a
   `SPEC`, and `pyproject.toml` lists the nine entry points of the group
   `pulseq_reports.cards`. `examples/gre_report.py` calls
   `build_cards(seq, pns_lane=True, views=("profile", "z_df"))`, and its page
   equals the baseline's page (the dogfooding check).
10. **Tests** (`tests/test_registry.py`), with a test plugin
    (`tests/plugin_card.py`, not a test file, so pytest does not collect it)
    that a fixture adds to the specs of the installed entry points; the clash
    tests add a second spec with a name or an option name that is taken:
    - discovery finds the nine library cards, in their order;
    - the test plugin's card is in the report, in its order, with its script
      and CSS on the page one time, and it reads a shared option;
    - two specs with one name, and two options with one name, give the
      errors of item 5; a spec that reads an option it does not declare
      raises;
    - a plugin whose `build` raises gives an error card with a failed check,
      and the other cards are built;
    - `cards` and `skip` select cards; an unknown name raises `ValueError`;
      an option of no selected card raises `TypeError`; without the diagram,
      the RF profile card is not built (no selected card publishes
      `anchor`);
    - `render_page` raises for two diagram cards (two publishers of
      `sequence`), and for two cards that subscribe to `goto`; a plugin topic
      is not checked;
    - the checks of the timing, gradient limits and PNS cards: passed for a
      synthetic sequence inside its limits; failed for a sequence with a
      timing error, for limits below its peak, for a |G| peak above
      `max_grad` with each axis below it (`check_norms=True` fails,
      `check_norms=False` passes), and for a PNS peak of 100 % or more (a
      hardware with a low threshold, `tests/conftest.py`'s
      `write_gradient_asc`);
    - each keyword-only parameter of each library builder is a declared
      option of its spec or in the list of item 3, and each declared option
      is a parameter of its builder with the same default (decision 17).
11. **The interface is provisional** in 0.2.0: `docs/usage.md` says that it
    can change in 0.3.0.

### 4.5 Phase 5: the command line (F1)

1. **`pulseq-report FILE.seq [FILE.seq ...] [-o OUT]`**, `cli.py`,
   `[project.scripts] pulseq-report = "pulseq_reports.cli:main"`. For each
   file: `pp.Sequence().read(FILE)`, `build_cards`, `write_page`, with the file
   name as the page title and "pulseq-reports <version>" as the subtitle.
   - One file: `OUT` is the page (default: `<stem>.html` in the current
     directory).
   - Several files: `OUT` is a directory (default: the current directory;
     made if it does not exist), and each page is `<stem>.html` in it. Two
     files with one stem: exit 1 before any page is written.
2. **The flags come from the specs.** One flag (or one flag pair) for each
   distinct `Option` of the discovered specs, in the order of the cards, with
   the option's help text. The structured options:
   - `limits`: `--max-grad` (mT/m) and `--max-slew` (T/m/s), both or neither
     (one alone: exit 1); the label is "command line";
   - `coil`: `--coil`, with the names of `grad_spectrum.COILS`;
   - `gradient_asc`: `--gradient-asc PATH`.
   A plugin's options are on the command line when the plugin is installed.
3. **`--cards NAME,...` and `--skip NAME,...`** select cards, with the
   names of the discovered specs.
4. **`--card-module MODULE:ATTRIBUTE`**: a `CardSpec` from a module that is
   not installed as a plugin (for example a project's own file), added to the
   discovered specs with the same checks. It can be given more than one time.
   Its options are on the command line: the parser reads `--card-module`
   first, then builds the other flags.
5. **`--config FILE`** (the user): a file of option values, read with
   `tomllib` when its name ends in `.toml` and with `json` when it ends in
   `.json` (another suffix: exit 1). Its keys are the option names, as in
   Python; `cards` and `skip` are keys too. The structured values:
   `limits = {max_grad_mt_per_m, max_slew_t_per_m_per_s, label}` (`label`
   optional, default "config file"), `coil = "prisma-as82"`, `views` and
   `plane` as lists, and `gradient_asc` as a path relative to the config
   file's directory. A flag overrides the same key of the file. A key that no
   discovered option has: exit 1 (a typing error). A key of an option that no
   selected card declares: ignored, because a site's file holds values for
   every card. An explicit flag of an option that no selected card declares:
   exit 1, with a message that names the flag and the skipped cards. Each
   `Option` gives the conversion of its config value, as it gives the
   conversion of its flags (section 4.4, item 1).
6. **No limits:** without `--max-grad` and `--max-slew`, the gradient limits
   card uses the sequence's system limits (pypulseq's defaults after
   `Sequence.read`); the command line writes a warning to stderr that names
   the values and says that the gradient check used them, and the card's note
   gives them. A config file's `limits` counts as given.
7. **The exit status:**
   - 0: each page is written, and each check of each card passed;
   - 2: each page is written, and at least one check failed (an error card
     too). The command writes each failed check to stderr: the file, the card
     and the message;
   - 1: an error in the arguments or in the config file, a failed start
     check of section 4.4, item 5 (no page is written), or a file that cannot
     be read (the pages of the other files are written).
   When 1 and 2 both apply, the status is 1.
8. **Tests** (`tests/test_cli.py`), with `main(argv)` called in the test
   process:
   - a `.seq` file written from a synthetic sequence gives a page that equals
     the page of `build_cards` for the same file read back, with the same
     title and subtitle;
   - `--max-grad` and `--max-slew` reach the gradient limits card (the
     values of its table); without them, the warning names the default
     values; one of the two alone exits 1;
   - two files give two pages in the output directory; two files with one
     stem exit 1 and write no page;
   - `--cards` and `--skip`; an unknown card name exits 1;
   - a file with a failed check exits 2 and names the check on stderr; a file
     with no failed check exits 0; an unreadable file with a good file exits 1
     and writes the good file's page;
   - `--card-module plugin_card:SPEC` (the tests directory is on
     `sys.path`) adds the test plugin's card and its option;
   - each option of the discovered specs has its flag in the parser;
   - a TOML and a JSON config file with the same values give the same page
     as the same flags; a flag overrides the file; an unknown key exits 1; a
     key of a skipped card is ignored; an explicit flag of a skipped card
     exits 1; a relative `gradient_asc` is read from the config file's
     directory.

### 4.6 Phase 6: exports and documentation (A6, A8, C3 to C6, F1, F2)

1. **A6.** `pulseq_reports.cards` exports the nine card builders.
   `pulseq_reports` exports `build_cards`, `Card`, `Check`, `render_page`,
   `write_page`, `TimeWindow`, `first_adc_window`, `full_window`,
   `HardwareLimits`, `GradientCoil` and `PRISMA_AS82`. Both `__init__.py`
   files set `__all__`. The imports are eager (section 2.1: they add almost no
   time). `tests/test_exports.py` imports each name of both `__all__` lists
   and checks that it is the object of its module.
2. **`docs/usage.md`:**
   - Section 2: `build_cards` with the exports, one sequence, and how to add
     a project's own card to the list. The README quick start passes
     `limits` (A7).
   - Section 3 "Several files with windows" becomes "Windows and the
     diagram": the text on windows, the diagram's views, the PNS lane, the
     |G| lane and the scale table stay; the multi-file text goes. A short
     paragraph says: one report for each `.seq` file. The PNS card's button
     replaces the peak-PNS window.
   - `laneChart`: no `setWindow`.
   - The messages section: one hub for each page and each page load
     (decisions 21 and 23), the state and request topics, the message forms
     of section 4.1, item 7, the range form of `goto` (section 4.2, item 6),
     `watchSubscribers` and `requestButton` (section 4.1, item 11), and the
     rule that a plugin uses no API that reaches another tab. The
     `Card.publishes` and `Card.subscribes` fields.
   - C4: one PNS computation for each sequence and hardware; one hardware
     for each card.
   - Section 5: the exact signatures, with `*` and `card_id`, and one line
     for each option (C5).
   - A new section "Analysis functions" (A8): `gradient_limits`,
     `rf_exposure`, `gradient_spectrum`, `pns_prediction`, `peak_tr_window`,
     and their result types (`GradientLimits`, `RfExposure`,
     `GradientSpectrum`, `PnsPrediction`) and input types (`HardwareLimits`,
     `GradientCoil`, `AcousticResonance`).
   - A new section "Card plugins": `CardSpec` (with its topics), `Option`,
     `ReportContext`, the shared options of `options.py`, the library's card
     names and topics (part of the provisional interface), the entry-point
     group,
     `Card.scripts`, `Card.css` and `Card.checks`, and a complete example of a
     plugin card with an option, a script and CSS (the test plugin of section
     4.4, item 10). It says that the interface is provisional. The list of
     reserved card script names (A10) goes: `page.py` no longer has them.
   - A new section "Command line": the usage, the files and the output, the
     config file (with an example of a site's file in TOML and in JSON), the
     limits warning, the checks and the exit status (0, 1, 2), and
     `--card-module`. The flags themselves are in `pulseq-report --help`,
     which the specs make.
   - A sentence that defines the public API: the names in `docs/usage.md`.
     Other names can change in a minor release.
   - C3 (what a hidden lane group saves; the numbers for the 10 µs raster)
     and C6 (`file_lanes` is for a short file or a time range).
3. **`README.md`:** one sequence per card; no "several files on one page" in
   the list of what the library does; the command line as the first way in,
   and `build_cards` as the second.
4. **`CHANGELOG.md`**: an entry "0.2.0rc2 (not released)" with the changes of
   section 2.4 and of phases 1 to 5, in three groups: "Breaking changes",
   "Added", "Fixed". Each breaking change says what a caller of `v0.2.0rc1`
   changes. The first breaking change: one sequence per card, and one report
   for each file. "Added" starts with the command line and the card plugins.

### 4.7 Phase 7: results

1. Rebuild `docs/examples/gre.html`. Compare it with the committed page (the
   page of `600fd12`) with the masked page diff (section 9.2): the
   differences are those of section 3.5 for phases 1 to 3. Open it in the
   browser: the nine cards draw, the PNS card's button moves the diagram, and
   the console has no error.
2. The review's status: A1, A3 to A8, D3, S7, C3 to C6, F1 and F2 fixed; F3
   in part; A2 and S2 closed by the one-sequence decision; with their PRs.
3. This plan: status "complete", and section 8.

## 5. Phases

### Phase 1: one sequence per card

Branch: `refactor/one-sequence-per-card`. Wave 1. Section 4.1.

**Task 1.1.** Tier SM. `waveforms.py`, `seq_utils.py`, and the cards
`timing`, `definitions`, `blocks`, `gradient_limits`, `pns`: items 1, 2, 4
and 5 for these files, with their tests and `TESTS.md` sections. Its first
step (the new `TimeWindow`, `first_adc_window`, `full_window`, and the removal
of `NamedSequence`) comes before tasks 1.2 to 1.4 start.

**Task 1.2.** Tier SM. `rf_exposure.py`, `grad_spectrum.py`, the cards
`rf_exposure` and `spectrum`, `tests/oracles/grad_spectrum.py`: items 1, 3
and 4, with their tests.

**Task 1.3.** Tier SH. `cards/diagram.py`, `assets/cards/diagram.js` and
`assets/lane_chart.js`: items 1, 2, 4 (`setWindow`), 6, 7 and 11, with
`tests/test_diagram_card.py`, `tests/test_extensions.py`,
`tests/js/test_messages.js`, `scripts/diagram_scale.py` and `TODO.md`. Its
first step is item 11 (`watchSubscribers`, `requestButton`), before task
1.4 binds the RF profile card's buttons.

**Task 1.4.** Tier SH. `cards/rf_profile.py`, `assets/cards/rf-profile.js`
and `assets/rf_profiles.js`: items 1, 5, 6 and 8, with
`tests/test_rf_profile_card.py`, `tests/js/test_rf_profiles.js` and
`tests/test_rf_profiles_golden.py`.

**Task 1.5.** Tier SM. `examples/gre_report.py` and `scripts/cards_scale.py`
(item 10). After tasks 1.1 to 1.4.

**Task 1.6.** Tier X. The comparison set, with the browser check of section
9.3. The review of each diff.

Checks:

- [ ] The comparison set differs only as section 3.5 says.
- [ ] `scripts/check` passes.

### Phase 2: the PNS API and the PNS card's button

Branch: `refactor/pns-api`. Wave 2. Section 4.2.

**Task 2.1.** Tier SM. `asc.py`, `pns.py`, `pns_levels.py`: items 1, 3, 9
and 10, with the tests of `tests/test_pns.py` and
`tests/test_pns_levels.py`, and the new cache test.

**Task 2.2.** Tier SH. `cards/pns.py`, `assets/cards/pns.js`,
`cards/diagram.py`, `assets/cards/diagram.js`, and the callers
`examples/gre_report.py` and `scripts/cards_scale.py`: items 2, 4 to 8 and
11, with the tests of `tests/test_pns_card.py`, `tests/test_diagram_card.py`,
`tests/test_extensions.py` and `tests/test_pns_lanes_golden.py`. Rule 1 of
section 3.4. After task 2.1.

**Task 2.3.** Tier X. The comparison set, with the browser check of the PNS
card's button (section 9.3), also on a synthetic sequence without a `TR`
definition (the button goes to the peak's block). The review of each diff.

Checks:

- [ ] The comparison set differs only as section 3.5 says.
- [ ] `scripts/check` passes.

### Phase 3: the analyses and the other cards

Branch: `refactor/card-api`. Wave 2, at the same time as phase 2. Section
4.3.

**Task 3.1.** Tier SM. Item 1 (A3) for `waveforms.py`, `diagram_data.py`,
`page.py`, `scripts/diagram_scale.py` and their tests; item 6 (A8) for
`cards/timing.py`, `cards/rf_profile.py` and `waveforms.py`, with their tests
and `tests/test_rf_profiles_golden.py` (it calls `rf_profile_data`).

**Task 3.2.** Tier SM. `grad_limits.py` and `cards/gradient_limits.py`: items
1, 2 and 4, with the new test.

**Task 3.3.** Tier SM. `rf_exposure.py` and `cards/rf_exposure.py`: items 1,
3 and 6, with the tests.

**Task 3.4.** Tier SM. `grad_spectrum.py` and `cards/spectrum.py`: items 1,
3 (`FFT_WINDOW_S`), 5 and 6, with the tests.

Tasks 3.1 to 3.4 edit different files. They run at the same time.

**Task 3.5.** Tier X. The comparison set. The review of each diff.

Checks:

- [ ] The comparison set differs only as section 3.5 says.
- [ ] `scripts/check` passes.

### Phase 4: the card interface and the checks

Branch: `feature/card-interface`. After phases 2 and 3 are merged. Section
4.4.

**Task 4.1.** Tier SH. `registry.py` and `options.py` (items 1 to 6), with the
tests of item 10 that do not need the library's specs, and the test plugin.

**Task 4.2.** Tier SM. `page.py`: `Card.scripts`, `css`, `checks`, `Check`
(item 7), with the tests of `page.py`. At the same time as task 4.1.

**Task 4.3.** Tier SH. The nine `SPEC`s, the assets and the checks of each
card, `check_norms`, the entry points, the `TODO.md` note, and
`examples/gre_report.py` (items 3, 8 and 9), with the rest of the tests of
item 10. After tasks 4.1 and 4.2. Then `uv sync --frozen` again (section
3.1, item 5).

**Task 4.4.** Tier X. The comparison set: the example page byte for byte
(section 3.5). The review of each diff.

Checks:

- [ ] The example page equals the baseline's page.
- [ ] `scripts/check` passes.

### Phase 5: the command line

Branch: `feature/command-line`. After phase 4 is merged. Section 4.5.

**Task 5.1.** Tier SM. `cli.py`, `[project.scripts]` and `tests/test_cli.py`.
Then `uv sync --frozen` again.

**Task 5.2.** Tier X. Write a `.seq` file from the sequence of
`examples/gre_report.py` (`seq.write`, in the session scratchpad) and one of
a synthetic GRE without a `TR` definition. Run `pulseq-report` on them: with
and without `--max-grad`/`--max-slew`, with `--gradient-asc` (a scratch file
of `write_gradient_asc`'s form) and `--pns-lane`, and with `--cards`. Open the
pages in the browser: the cards draw, the PNS card's button moves the
diagram, and the console has no error. Check the exit status and stderr of
each run. The review.

Checks:

- [ ] `scripts/check` passes.

### Phase 6: exports and documentation

Branch: `docs/api-exports-docs`. After phase 5 is merged. Section 4.6.

**Task 6.1.** Tier SM. Item 1 (the exports and their test).

**Task 6.2.** Tier SH. Items 2 to 4 (`docs/usage.md`, `README.md`,
`examples/gre_report.py`, `CHANGELOG.md`).

**Task 6.3.** Tier X. Run every code block of `docs/usage.md` and the README
quick start that can run (with a synthetic sequence in place of
`your_pp_sequence` and of a file), the plugin example, a command-line example,
and `examples/gre_report.py`. The comparison set. The review.

Checks:

- [ ] Each code block runs.
- [ ] `scripts/check` passes.

### Phase 7: results

Branch: `chore/public-api-results`. After phase 6 is merged. Section 4.7.
Tier X, all tasks. Remove the baseline after the merge.

## 6. Summary of parallel work

| Wave | Phases | Condition to start |
|---|---|---|
| 1 | 1 | This plan is merged (the worker agents are, in #86). The baseline exists. |
| 2 | 2, 3 | Phase 1 merged. |
| 3 | 4 | Phases 2 and 3 merged. |
| 4 | 5 | Phase 4 merged. |
| 5 | 6 | Phase 5 merged. |
| 6 | 7 | Phase 6 merged. |

| Phase | Workers | The executing agent |
|---|---|---|
| 1 | SM for task 1.1 (its first step first), then SM for task 1.2 and SH for tasks 1.3 and 1.4, with the rest of 1.1, at the same time, then SM for task 1.5 | Task 1.6 (with the browser check) |
| 2 | SM for task 2.1, then SH for task 2.2 | Task 2.3 (with the browser check) |
| 3 | SM for tasks 3.1 to 3.4, at the same time | Task 3.5 |
| 4 | SH for task 4.1 and SM for task 4.2, at the same time, then SH for task 4.3 | Task 4.4 |
| 5 | SM for task 5.1 | Task 5.2 (with the browser check) |
| 6 | SM for task 6.1 and SH for task 6.2, at the same time | Task 6.3 |
| 7 | None | All tasks |

## 7. Questions still open

None. The user answered on 2026-09-29, in five rounds.

First round:

1. The PNS cache: one entry for each (sequence, hardware). Each card takes one
   `.asc` file; two systems are two cards (decision 16).
2. `NamedSequence`: removed. The card builders take a `pp.Sequence`.
3. The windows: `gradient_limits_card(windows=[TimeWindow, ...])`;
   `b1rms_window_s` in the options, the constant `B1RMS_WINDOW_S` and the
   `RfExposure` fields; `FFT_WINDOW_S`.
4. The peak-PNS window: first `pns.peak_pns_window`; replaced in the second
   round by the PNS card's button (question 22).
5. The hardware defaults: all four parts (the annotation and the
   documentation, `GradientCoil`, the values in the gradient limits note, the
   README quick start with `limits`).
6. The card-internal functions: private names.
7. The exports: eager, with `__all__` and a test.
8. The `.asc` helpers: a new module `asc.py`.
9. The list of changes: `CHANGELOG.md`.
10. C3 and C6: in phase 6.
11. The version change to `0.2.0rc2`: a separate chore, outside this plan.
12. A card whose `build` raises: an error card, and the page is written.
13. The plugin interface: provisional in 0.2.0.
14. `--card-module`: yes.
15. The function: `build_cards`.
16. The command line without limits: the system limits, with a warning.
17. The coil on the command line: the names of the built-in coils only.
18. The exit status: 0, 1, and 2 when a check failed.
19. The command: `pulseq-report`.

Second round (a review of the plan):

20. The standard report uses the builders' defaults (decision 17); the
    example gives `pns_lane=True` and the RF profile views.
21. The diagram's option is `pns_lane` (decision 18).
22. The peak-PNS view is a button of the PNS card that sends the diagram a
    `goto`; the diagram has no peak-PNS window (decision 19).
23. The gradient check: each axis by default; the option `check_norms` adds
    the norm, for a check that does not depend on the rotation.
24. `check_norms` checks the |G| peak now; a vector-slew check waits for the
    `TODO.md` item on the slew definitions.
25. With no `TR` definition, the PNS card's button goes to the block that
    holds the peak.
26. `laneChart`'s `setWindow`: removed.
27. The `Option` objects have the names of their keywords, in lowercase
    (decision 15).

Third round (the workers, after the Sonnet 5.5 documentation):

28. No Haiku tier: the mechanical tasks go to `worker-medium`.
29. Effort for each task: `high` for tasks 1.3, 1.4, 2.2, 4.1, 4.3 and 6.2;
    `medium` for the others; never `xhigh` or `max` for a worker.
30. The two agent types are in the project's `.claude/agents/`, on their own
    branch and PR: #86, merged (decision 20).

Fourth round (a review of the plan):

31. `pns_card`'s `diagram_card_id` defaults to `None`: a card built directly
    has a button only when the caller names the diagram.
32. The command line takes flags and an optional config file with the same
    option names; a flag overrides the file; a config key of a skipped card
    is ignored; an explicit flag of a skipped card exits 1.
33. The config file is JSON or TOML, chosen by its suffix.

Fifth round (how the cards find each other):

34. One hub for each page, messages by topic only, and one sequence for each
    page; each card declares its topics, and `render_page` checks one
    publisher for each state topic and one receiver for each request topic
    (decisions 2 and 21). This replaces answer 31: no card has a
    `diagram_card_id`.
35. A button that sends a request is shown only while the page has a card
    that acts on it, decided at run time; this holds for every "Show" or
    "go to" button (decision 22).
36. Two tabs of one report have two independent hubs (decision 23).

## 8. Results

All phases were done on 2026-09-29.

### 8.1 Pull requests

| Phase | Findings | PR | Merge commit |
|---|---|---|---|
| Plan | | #87 | `b2e7a77` |
| 1 | One sequence per card; A3 (the card builders), A4 (`TimeWindow`); A2 and S2 closed | #88 | `d7df864` |
| 2 | A1, A5, D3, S7; A3 and A8 for the PNS modules | #89 | `1bdb1ce` |
| 3 | A3, A4, A7, A8 | #90 | `ac53f09` |
| 4 | F2, a part of F3 | #91 | `e6cccf0` |
| 5 | F1 | #92 | `5526ee4` |
| 6 | A6, A8 (the documentation), C3 to C6 | #93 | `034e135` |
| 7 | results | this PR | |

### 8.2 Decisions made during the work

1. **`--card-module` stays on a private hook** (the user). `cli.py` wraps
   `registry._load_entry_points` for the run (`_extra_specs`), so a spec
   from `--card-module` gets the checks of `discover`. There is no public
   `discover(extra=...)`.
2. **Phase 1: one window check.** `waveforms._check_windows` is the check of
   the diagram, blocks and (phase 3) gradient limits cards. It allows 1e-7 s
   past the end, because `full_window` rounds its end to 1e-4 ms.
3. **Phase 1: two format numbers.** `diagram.js` checks the card data
   format (2) itself, and gives the table format (1) to `SeqLanes.decode`,
   which is a separate version. The rotation item of `TODO.md` reserves data
   format 3.
4. **Phase 1: tests.** `test_value_error_cases` of the RF profile card lost
   three items, not two: `bad_diagram_card_id` went with the parameter. The
   RF profile card's status line starts with a capital letter now that the
   file name is gone, and its note "The diagram shows ..., which this card
   does not have" is removed (it applied only to several files).
   `tests/test_pns.py`, a phase 2 file, had one `diagram_card` call in the
   new form in phase 1 (decision 1).
5. **Phase 2: `docs/usage.md` waited for phase 6** (section 3.4, rule 3),
   although section 4.2, item 7 names it.
6. **Phase 2: the block of the peak.** Without a `TR` definition, the PNS
   card's `goto` names the first block that ends after the peak time, so a
   block of zero duration is never chosen (as `SeqLanes.blockAt`). The
   button is `hidden` in the markup, so it stays hidden when the script does
   not run. `pns.js` refuses a data format other than 1.
7. **Phase 3 merged after phase 2.** Rule 1 of section 3.4 put the keyword
   call `lane_meta(seq, tables=tables)` in phase 2's `cards/diagram.py`, so
   phase 3's CI could pass only after phase 2. Phase 3 was committed, then
   `origin/main` was merged into it after #89, and its PR was opened. Its
   comparison set ran two times, against `d7df864` (with that call patched
   in a scratch copy) and against `1bdb1ce`: the same entries changed, with
   the same values.
8. **Phase 3: small choices.** `cards.spectrum.spectrum_data` is removed,
   not renamed: it wrapped the private `_spectrum_data` that phase 1 left.
   The internal dict of `_rf_exposure_data` keeps the keys `window_s` and
   `window_used_s` (it is not page data). The gradient limits card resolves
   its limits one time (`grad_limits._default_limits`). Three comments of
   `rf_profiles.js` name the new private function names, although phase 3
   does not own the file.
9. **Phase 4: the interface.** `OptionCli.from_config(value, base_dir)`
   takes the directory of the config file, for `gradient_asc`. Two `Option`
   objects are equal only when they are the same object (`eq=False`), which
   is the rule of decision 15. A `build` that reads an undeclared option
   gives an error card (item 6); `ReportContext.option` raises
   `ValueError`. The gradient limits check has a relative tolerance of 1e-9,
   so a value at its limit passes after the float conversions of the units.
   The PNS card declares `publishes=("goto",)` also without a button. The
   `write_gradient_asc` fixture moved to `tests/conftest.py`.
10. **Phase 4: the entry points.** `uv sync --frozen` installed the entry
    points after the change of `pyproject.toml` (uv rebuilds the project
    when `pyproject.toml` changes). CI makes a new environment for each run.
11. **Phase 5:** an error in the arguments exits 1, not argparse's 2, so 2
    means only "a check failed". `--card-module` imports with the current
    directory at the end of `sys.path`, and then removes that entry.
12. **Phase 6:** `import pulseq_reports` takes about 1 s with the eager
    exports (it took less than 1 ms): it now loads pypulseq, numpy and
    scipy, which every caller loads (section 2.1). A test of the contents of
    `__all__` was not kept (decision 6). The README note on the resonance
    bands names their source (the safety check of the QIS-MRI Pulseq
    workshop), not "published values".
13. **The workers.** Two workers edited `TESTS.md` with a script, not with
    the Edit tool, while other workers edited it; a check after each wave
    found no lost entry. The worker of task 2.2 stalled one time before any
    edit, and went on when it was resumed. The browser checks used
    JavaScript snapshots in the hidden pane (decision 24).

### 8.3 The comparison sets

| Phase | Example page | Python dump | Browser |
|---|---|---|---|
| 1 | Only the changes of section 3.5 | Equal, with the formats of section 4.1 normalized | Diagram equal (11 snapshots, both themes); RF profile card equal except its status line; buttons hidden without a diagram |
| 2 | Only the changes of section 3.5 | Only `*/card/pns`, as section 4.2 says | The PNS button gives the view and anchor of the old window and click; the diagram equal (7 snapshots) |
| 3 | Only the gradient limits note | Equal after the field renames, the note and the window heading | Not run |
| 4 | Byte-equal | Equal without the new `Card` fields | Not run |
| 5 | Byte-equal | Not run; the command line's page equals `build_cards`' page | The command line's pages draw; the PNS button works |
| 6 | Byte-equal | Byte-equal | Not run |
| 7 | The sum of phases 1 to 3 against `600fd12` | Not run | The nine cards draw, in both themes; the PNS button moves the diagram to the peak's TR |

At the end, `scripts/check` has 981 pytest tests (542 `TESTS.md` entries)
and 169 node tests.

## 9. Scripts

### 9.1 The Python dump in the new form

Copy `dump_py.py` of `docs/plans/review-cleanup.md`, section 9.1, to the
session scratchpad. For each phase, make a copy for the branch that changes
only its calls to the new form of that phase, for example:

| `main` | Phase | Branch |
|---|---|---|
| `timing.timing_card(named)` (a list of one) | 1 | `timing.timing_card(seq)` |
| `waveforms.first_adc_window(named)` | 1 | `waveforms.first_adc_window(seq)` |
| `pns_cards.pns_card(named[0])` | 1 | `pns_cards.pns_card(seq)` |
| the `many/` entries | 1 | removed |
| `diagram.diagram_card(named, windows, pns=True)` | 2 | `diagram.diagram_card(seq, windows, pns_lane=True)` |
| `waveforms.block_rows(seq, *win, max_rows=3)` | 3 | `waveforms.block_rows(seq, start_s=win[0], end_s=win[1], max_rows=3)` |
| `waveforms.file_lanes(seq, *win)` | 3 | `waveforms.file_lanes(seq, start_s=win[0], end_s=win[1])` |
| `rf_exposure.rf_exposure(seq, periodic=False, window_s=0.01)` | 3 | `rf_exposure.rf_exposure(seq, periodic=False, b1rms_window_s=0.01)` |
| `gradient_limits_card(named, window=win)` | 3 | `gradient_limits_card(seq, windows=[TimeWindow("w", *win)])` |

Put each pair of copies in the PR description. A renamed field of a result
is renamed back in the branch's dump before the comparison, so that the
comparison shows only a change of value. The baseline's `many/` entries are
left out of the comparison of phase 1.

### 9.2 The masked page diff

`page_diff.py` of `docs/plans/review-cleanup.md`, section 9.4, prints only the
first difference. For this plan, the executing agent uses its `masked`
function and prints every difference: mask the text of each script that the
phase changes (its own file on each side), then a unified diff of the two
pages, line by line. Put the output in the PR description. A JSON data
element that the phase changes shows as one changed line; the dump compares
its content.

### 9.3 The browser checks

With the `dev-workflow:browser-check-localhost` skill, the base page and the
branch page, in both themes (decision 24):

- The diagram: for each window and three zoom levels, the SVG markup and the
  card's text are equal. The messages `sequence`, `cursor`, `anchor` and
  `view` of a scripted hover and click (a subscriber that records them) are
  equal without the `file` and `name` fields.
- The RF profile card: after a "Show" button and after a scripted anchor,
  the finished card (SVG markup and text) is equal, except the file name in
  its status line (phase 1).
- Phase 2: the PNS card's button. On the branch, after the button, the
  diagram's `view` and `anchor` messages equal those that the baseline's
  "Peak-PNS TR" window button and a click at the peak time give; the RF
  profile card then shows the same pulses.
- The request buttons (decision 22): on a page of a PNS card and an RF
  profile card with no diagram, their buttons stay hidden; on the example
  page, they are shown once the diagram has started.
