# Plan: fix the bugs B1 to B6 of the code review of 2026-09-28

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: complete (2026-09-29). The results are in section 8. The plan was
written on 2026-09-29. The user answered the questions of section 7 on the
same day (decisions 9 to 14 of section 2.2). The same day, the user revised
decision 9: a new pypulseq pin fixes B4, and phase 4 adds its regression
tests.

## 1. Goal

Fix the bugs of section 1 of `docs/reviews/2026-09-28-code-review.md` (the
review). Each fix gets its own branch, its own pull request and a regression
test (the review, section 10, item 2). B4 is the exception: the pypulseq pin
fixes it (decision 9), so its phase adds only the regression tests.

| Bug | What is wrong | Where (`main` at `4e17c66`) |
|---|---|---|
| B1 | Gradient limits with a window: the slew and `slew_block` can come from a block junction before the window. A window with no gradient then gets `reason=None` and a slew that is not 0. | `grad_limits.py:409-438`, `451-455` |
| B2 | Sequence diagram, minimum/maximum view: a bin shows the ADC on when no ADC plays in it. | `assets/seq_lanes.js:1036-1052` |
| B3 | The \|G\| lane stops the diagram card for a file with about 1.2 × 10^5 gradient events or more. | `assets/g_lanes.js:432-435`, `assets/cards/diagram.js:237-254`, `285-328`, `351-407` |
| B4 | An oversampled arbitrary gradient gives wrong values in the gradient cards. Fixed by the pypulseq pin (decision 9). | `seq_utils.py:65-67`, `rf_profiles.py:844`, `1228` |
| B5 | The spectrum card does not escape `scanner_label` in its note. | `cards/spectrum.py:150` |
| B6 | The gradient limits card's note describes the old slew. | `cards/gradient_limits.py:126-128`, `grad_limits.py:19-23` |

These items are not in this plan:

- The other findings of the review (A, F, D, S, P, C and L). Where a fix
  touches the lines of another finding, section 4 names that finding in one
  line. Do not fix it on the branch of this plan.
- The release `0.2.0rc2`. In the review's order, these fixes come before it
  (section 10, items 2 and 3). The user asks for the release separately.
- A fix of B4 in the code of this library. The pin fixes it (decision 9).
- The move of the pin. The branch `chore/pypulseq-pin-release-base` does it,
  in its own PR.

## 2. Read this first (context for the executing agent)

### 2.1 The state of the repository

- Read `docs/plans/pulseq-reports.md`, `docs/plans/cards-at-scale.md` and
  `docs/plans/diagram-lanes.md`. Their workflow rules apply to this plan.
  `docs/plans/rf-profiles.md` added the `goto` message, which is a third path
  to B3.
- `main` is at `501b064` (2026-09-29): `4e17c66`, then the review (#64),
  then the public card helpers (#65). The tag `v0.2.0rc1` is on `c7a284b`.
  The facts of section 2.3 were measured on `4e17c66`. #64 changed no code,
  and #65 changed none of the lines of section 2.3.
- The review is `docs/reviews/2026-09-28-code-review.md`. Its line numbers
  are for an older state (`a6ec78b` plus `5a2ae35`). Use the line numbers of
  this plan.
- On 2026-09-29, B1 to B6 were all open. No test covers any of them.
- PR #65 (`feature/public-card-helpers`, merged as `501b064` on 2026-09-29)
  is step 1 of the review's order. It renames helpers of `markup.py` (`_table` to
  `html_table`, `_fmt` to `fmt`, `_zoom_controls` to `zoom_controls`), and it
  fixes the review findings D1, D2, A9, A10, C1 and C2. It also edits
  `page.py`, `report.css`, `lane_chart.js` (one comment), `docs/usage.md`,
  `TESTS.md`, `tests/test_page.py` and `docs/examples/gre.html`. It does not
  edit the lines that this plan changes. Phases 5 and 6 edit card files that
  import these helpers; they start from `origin/main`, which has #65.
- The pypulseq pin was commit `20b9e5e` of the fork `mdtisdall/pypulseq`
  (branch `pns-chunked`, on upstream `master` `f2c582b`) when this plan was
  written. The facts of section 2.3 were measured with it. The branch
  `chore/pypulseq-pin-release-base` moves the pin to the fork's tag
  `pulseq-reports-pin-1` (`a74ab06`): the release 1.5.0.post1 with four
  cherry-picks, one of them the fix of PR #424 (decision 9, `TODO.md`). A project that installs pulseq-reports with uv
  gets the fork too, because uv applies the `[tool.uv.sources]` of a git
  dependency (finding C9 of the review). A project that installs with pip
  gets stock pypulseq 1.5.0.post1 from PyPI. A project that pins its own
  pypulseq gets that version.
- The repro scripts of section 2.3 are in the session scratchpad of
  2026-09-29 (`bugs-plan/`). The scratchpad is not permanent. Section 9 has
  copies of the scripts.

### 2.2 Decisions that are already made

Do not open these decisions again.

1. **One branch, one pull request and one regression test for each bug**
   (the review, section 10, item 2). For B4, the pin is the fix, and phase
   4 adds only the tests (decision 9).
2. **The fixes of B1, B2, B3, B5 and B6 are the "Change" of the review**,
   with the details of section 4.
3. **At most three PRs open at one time** (the user). A PR of another plan
   counts.
4. **Lean on pypulseq.** Do not test what pypulseq asserts (for example the
   slew check of `add_block`, or event decoding). Test the computations of
   this library. Build each test sequence with pypulseq's `make_*`
   functions, within the real limits of the system. Note:
   `make_arbitrary_grad(oversampling=True)` checks the slew rate 4 times too
   leniently (draft 01 of `github.com/mdtisdall/pypulseq-issues`, upstream
   PR #422). A test must keep an oversampled waveform within `max_slew` by
   itself.
5. **Block starts in JavaScript come from `SeqLanes.blockStart` and forward
   sums.** Never compute a block start by subtracting a duration from a later
   block start.
6. **No DOM tests** (decision 10 of `docs/plans/pulseq-reports.md`). Node
   tests cover pure functions. A browser check covers a change to a card
   script.
7. **Upstream analyses stand alone.** A consequence for this library goes
   into `TODO.md` or into a plan of this project.
8. **The release `0.2.0rc2` is made only when the user asks.**
9. **The pypulseq pin fixes B4** (the user, 2026-09-29). The bug is
   pypulseq issue #423, with the fix in PR #424 (draft 02 of
   `github.com/mdtisdall/pypulseq-issues`; both open on 2026-09-29, no review
   yet).
   - First answer to question 1: option D, wait for a pypulseq release or an
     upstream fix.
   - Revised the same day: a fork pin from the release, with the fix. The
     fork's tag `pulseq-reports-pin-1` (branch `pulseq-reports-pin`, commit
     `a74ab06`) is `v1.5.0.post1` with four cherry-picks: the two PNS commits
     of the old pin, the fix of PR #424, and upstream #359. It is option C,
     but on the release and not on upstream `master`, so a project that uses
     uv also builds its sequences with the release (`TODO.md`, "Move from the
     pypulseq fork to a pypulseq release").
   - This library gets no work-around (option B) and no refusal (option A).
   - Phase 4 adds tests 2 and 3 of section 4.4, after the pin PR
     (`chore/pypulseq-pin-release-base`) is merged.
10. **B5 and B6 are on separate branches** (question 2).
11. **Order:** wave 1 is phases 1, 2 and 3; wave 2 is phases 4, 5 and 6;
    wave 3 is phase 7 (question 3, section 3.3).
12. **`docs/examples/gre.html` is rebuilt one time, in phase 7** (question 4).
13. **B3: the status line says why the \|G\| lane is not drawn** (question
    5, section 4.3).
14. **B1: a junction at the window start counts, and a junction at the
    window end does not** (question 6, section 4.1, item 3).

### 2.3 Facts (2026-09-29)

Each bug was reproduced on `main` at `4e17c66`. Each proposed change was
applied to a copy in the scratchpad, not to a worktree, and fixed the repro.

**B1.** The sequence has two blocks (section 9.1). Block 1 is an extended
trapezoid on x, from 0 to 0.9 of the largest step that `add_block` accepts
(0 to 0.2 ms). Block 2 is a delay of 1 ms.

| Window (ms) | Before the change | After the change |
|---|---|---|
| 0.5 to 1.0 (inside the delay) | `reason` None, Gx slew 135 T/m/s, `slew_block` 2, peak 0 | `reason` "no gradient events in the window", slew 0, `slew_block` None |
| 0.2 to 1.0 (starts at the junction) | slew 135 T/m/s, `slew_block` 2 | the same |
| whole file | slew 135 T/m/s, `slew_block` 2 | the same |

With the change, the 224 tests of `test_grad_limits.py` and
`test_gradient_limits_card.py` pass. The oracle comparisons do not find B1:
their random events start and end at 0, so no junction has a step.

**B2.** 400 blocks of 1 ms, and one ADC window in block 64, from 64.0 to
64.5 ms (section 9.2). For the view from 64.7 to 264.7 ms in one bin,
`minMaxLanes` gives the ADC window `[[64.7, 264.7]]`, and `exactLanes` gives
`[]`. With `gFrom = Math.floor(first / GROUP_BLOCKS)`, `minMaxLanes` gives
`[]`. With the change, the 42 tests of `test_seq_lanes.js` pass.

- The bug needs three conditions. The bin's first block is the first block
  of a group. The ADC of that block ends before the bin starts. The bin
  reaches at least two groups past the group before, with no other ADC.
- `buildRandomModel` puts an ADC in 20 % of the blocks, so it never meets
  these conditions. Random models with 0.2 % to 1 % ADC blocks did not meet
  them in 16 views either. A hand-made model does (section 4.2).
- `seq_lanes.js` has two lines that compute `gFrom` from `from`. Line 663
  (`_rangeMinMax`) is correct: its `from` is part of the range. Change only
  line 1038 (`_adcOverlaps`).

**B3.** The model has 150,000 gradient events, 5 block durations and 300
blocks (section 9.3). `SeqLanes.decode` succeeds. `GLanes.decode` throws
"the per-(triple, duration) cache key of this file would exceed 2^53".

- With the key in two levels (section 4.3), `GLanes.decode` succeeds, and
  the whole-file peak equals a brute force from the tables. The 11 tests of
  `test_g_lanes.js` pass.
- After the change, the limit is `M^2 < 2^53`: about 9.5 × 10^7 gradient
  events. Then memory is the next limit (finding P6).
- Time of `GLanes.decode` in Node for 10^7 repeating blocks (three runs):
  163 ms before, 224 ms after. The 95th percentile of `minMax` (812 bins):
  2.3 to 2.8 ms before, 2.6 to 3.0 ms after.
- The three paths in `diagram.js`:
  1. First file: `lanesFor` runs in the first render inside `laneChart`. The
     init function throws, so `page.js` shows "This card could not be
     drawn".
  2. Later file: `showWindow` calls `setButtonsDisabled(true)`, sets
     `current`, and then `chart.setWindow` renders and throws. The buttons
     stay disabled, and the status stays "Loading…".
  3. `goto` (the "Show" buttons of the RF profile card): `handleGoto` calls
     `gotoBlock`, which calls `showWindow`. `handleGoto` catches the error
     and writes it to the console, but the buttons stay disabled.
- `GLanes` is a plain object, not frozen. `page.py` loads the
  `extra_scripts` after `g_lanes.js` and before `page.js`. Thus a scratch
  page can replace `GLanes.decode` for a browser check (task 3.5).

**B4.** The pinned `get_block` (`Sequence/block.py:428`) sets
`t_end = (len(g) + 1) * grad_raster_time` for time shape ID -1.
`make_arbitrary_grad` sets `(len + 1) * 0.5 * grad_raster_time`. The block
durations come from `add_block` and are correct.

- `gradient_offsets` puts the last point of an arbitrary gradient at
  `g.shape_dur`. Every path of this library that reads gradient points goes
  through it.
- The reach was measured with three blocks (section 9.4), with `SYSTEM` of
  `tests/synthetic.py`:
  1. An oversampled ramp of 21 samples at 50 % of `max_slew`. It ends at a
     value that is not 0.
  2. An extended trapezoid down to 0.
  3. A trapezoid.

| Function | Card | Result |
|---|---|---|
| `seq_utils.gradient_offsets` | all the rows below | last offset 0.22 ms in a block of 0.11 ms |
| `GradientSampler.sample` | gradient spectrum. Also the PNS levels fallback for a file that is not on the raster. | largest error 40.5 % of the peak |
| `GradientSampler.block_samples` | PNS card, PNS lane | not affected (1.4e-15 of the peak): the sample count is odd, so no raster centre falls in the last segment |
| `grad_limits.gradient_limits` | gradient limits | Gx RMS 8.8558 mT/m, correct value 8.3424 mT/m (+6.2 %). The peak is correct. The slope of the last segment is too small (in this case not the largest slew). |
| `diagram_data.diagram_tables` | diagram (Gx, Gy, Gz and \|G\| lanes), and the RF profile card in the browser, which reads these tables | the last point of the event is 0.11 ms after the block end |
| `rf_profiles` (Python) | the reference of the RF profile card, and its pulse list | the interval gradients are wrong where an RF plays during the extra last segment. Also, `_plays_during` and `_fill_gradient_spans` read `pp.calc_duration(g)`, which uses the doubled `shape_dur`. So a gradient that ends before the RF counts as a gradient of the pulse (section 9.6: a 0.11 ms triangle, then an RF at 0.16 ms in the same block gives `gradient_kind` "one", `select_kind` "z", a `gz` id in the pulse key, and a mean gradient of 8261 Hz/m during the RF; correct: "none", no id, 0) |
| `waveforms.file_lanes` | no card (golden tests) | last point after the block end |
| `waveforms.block_rows` | block table | not affected: event names only |

- Through `Sequence.read`, with the pinned pypulseq (draft 04 of the
  pypulseq-issues project):
  - `write()` with its default `remove_duplicates=True` raises
    `KeyError(-1)`. `write(remove_duplicates=False)` works.
  - `read()` with its default `remove_duplicates=True` raises
    `KeyError(np.float64(-1.0))`. `README.md` shows the default read.
  - `read(path, remove_duplicates=False)` works. Then `get_block` gives
    `shape_dur` 0.22 ms, and `gradient_limits` gives the same wrong RMS.
- Thus an oversampled arbitrary gradient reaches this library in two ways
  only: a sequence that the caller builds in the same Python process, and a
  `.seq` file read with `remove_duplicates=False`. No pypulseq example uses
  `oversampling=True`. A pypulseq version that fixes draft 04 but not issue
  #423 lets every `.seq` file with an oversampled gradient through the
  default read, with the wrong `shape_dur`.
- Draft 03 (`waveforms()` leaves out the first and the last point of an
  oversampled gradient) does not reach this library. No card calls
  `get_gradients` or `waveforms()`.
- Upstream: issue #423, PR #424 open and not merged. The fork branch
  `fix-oversampled-get-block` (`6db882b`, on `f2c582b`) has the one-line fix
  and a test. The pin does not have it. No pypulseq release came after
  1.5.0.post1.
- The local correction of option B (section 4.4), on a copy:
  - Every value of the table above equals the value from the events as
    added (sampler error 0.0 %, RMS 8.3424 mT/m).
  - The corrected offsets equal `[0, *g.tt, g.shape_dur]` of
    `make_arbitrary_grad` bit for bit, for 5, 21, 101 and 301 samples. The
    amplitudes differ by up to 4.9e-8 relative, from the shape compression
    of pypulseq. The correction does not change them.
  - With a patched `get_block` that has the fix of PR #424, the correction
    does not change the value.
  - With the correction, and with `rf_profiles` reading the gradient end
    from `gradient_offsets` in place of `pp.calc_duration(g)`, the block of
    section 9.6 gives `gradient_kind` "none", no `gz` id in the key, and 0
    Hz/m during the RF.
  - The 295 tests of `test_seq_utils.py`, `test_sampling.py`,
    `test_grad_limits.py`, `test_diagram_data.py` and `test_seq_index.py`
    pass.
- With the new pin (`pulseq-reports-pin-1`, decision 9), and no change to
  this library: section 9.4 prints a sampler error of 0.0 %, the RMS 8.3424
  mT/m, and a last diagram offset of 0.11 ms. Section 9.6 prints
  `_plays_during: False`, `gradient_kind: none`, 0 for each gradient id of
  the key, and 0 Hz/m during the RF. The default `write()` and `read()` still
  raise `KeyError` (draft 04 is not in the pin).

**B5.** With `scanner_label="Coil <A&B>"`, the note has the raw label one
time. The table header and the `aria-label` have the escaped label (section
9.5). The default label has no `<` and no `&`, so the default output does not
change.

**B6.** No test pins the text of the note. `docs/examples/gre.html` has the
old note. It also has a copy of every script, so B2 and B3 change it too.

### 2.4 Budgets

B3 can change one budget of `docs/plans/diagram-lanes.md`, section 2.4:
"Browser: time added before the first chart". For 10^7 repeating blocks, the
PNS lane and the \|G\| lane together may add at most 3 s. Phase 6 of that
plan measured 1.2 s for the PNS lane and 0.23 s for the \|G\| lane. The change
of B3 adds about 60 ms (section 2.3). If a budget fails, stop and tell the
user. Do not change a budget.

### 2.5 Terms

- **The review.** `docs/reviews/2026-09-28-code-review.md`.
- **Junction step.** For an axis, `|last(i) − first(i + 1)|` divided by
  `grad_raster_time`, at the start of block `i + 1`. A block with no event on
  the axis gives 0. Before the first block, the "last" value is 0. The step
  is credited to the block after the junction.
- **Processed block** (B1). A block that overlaps the range `[lo, hi]`
  (`processed = ~skip`, `grad_limits.py:326`).
- **Group** (B2, B3). 64 consecutive blocks (`GROUP_BLOCKS`). `adcCount` is
  the prefix count of the ADC blocks in the groups.
- **`first`, `last`** (B2). The blocks that hold the edges `e0` and `e1` of a
  bin.
- **`M`, `D`** (B3). `M` is the number of gradient events plus 1. `D` is the
  number of distinct block durations.
- **Oversampled arbitrary gradient** (B4). An event of
  `make_arbitrary_grad(oversampling=True)`. It has an odd number `n` of
  samples at `k × 0.5 × grad_raster_time`, `k = 1 … n`. Its `first` point is
  at 0, and its `last` point is at
  `shape_dur = (n + 1) × 0.5 × grad_raster_time`. pypulseq stores it with the
  time shape ID -1 (`time_id`).
- **Added event** (B4). The object that a `make_*` function returns, before
  `add_block`. B4 tests use it as the reference, not the `get_block` result.
- **Reach** (B4). The functions and cards that give a wrong value, and the
  ways in which a sequence gets to them.

## 3. How to execute this plan

### 3.1 Workflow

As in `docs/plans/cards-at-scale.md`, section 3.1, items 1 to 8. Item 9 does
not apply: `scripts/vb_parity.py` was removed (#55). Also:

1. Start each phase with the `dev-workflow:start-task` skill, from the
   latest `origin/main`. The worktree is `.worktrees/<short-name>`.
2. Run `nix develop --command uv sync --frozen` one time in each new
   worktree, before a worker starts.
3. For each bug, write the regression test first. Run it on the current code.
   It must fail. Then make the change. Then the test must pass.
4. Run `nix develop --command scripts/check` before each PR.
5. Put the repro of section 9 and its output before and after the change in
   the PR description.
6. Each phase that adds or changes a test updates its `TESTS.md` section
   (section 3.4).
7. Show the commit message to the user. Wait for approval before
   `git commit`. Merge only when the user tells you to.

### 3.2 Worker model tiers

As in `docs/plans/cards-at-scale.md`, section 3.2: H (`haiku`), S
(`sonnet`), O (the executing Opus agent, not a worker). Rules 1 to 4 of that
section apply. Also:

1. Give each worker its design section (section 4), its repro (section 9),
   its test names, and its `TESTS.md` section.
2. Workers do no git writes. The main agent reviews each diff line by line.
3. A worker whose change does not fix the repro stops and reports. It does not
   try a different fix.

### 3.3 Order and parallel work

```
Phase 1 (B1) ──► Phase 6 (B6) ────┐
Phase 2 (B2) ─────────────────────┤
Phase 3 (B3) ─────────────────────┼─► Phase 7 (results)
Phase 4 (B4, tests) ─────────────┤
Phase 5 (B5) ─────────────────────┘

Wave 1: phases 1, 2 and 3. Wave 2: phases 4, 5 and 6, as PR slots become free.
```

- There is no phase 0. Each test file of this plan already has its
  `TESTS.md` section.
- Wave 1: phases 1, 2 and 3 at the same time. They edit different files.
  B3 stops a card, and B1 and B2 show wrong values, so they come first.
- Wave 2: phases 4, 5 and 6, each when a PR slot is free.
  - Phase 6 starts after phase 1 is merged. Both edit `grad_limits.py`.
  - Phase 4 starts after the pin PR (`chore/pypulseq-pin-release-base`) is
    merged.
  - Phase 5 has no condition.
- Phase 7 starts after phases 1 to 6 are merged.
- At most three PRs are open at one time, together with the PRs of other
  plans (decision 3).

### 3.4 File ownership

Package root: `src/pulseq_reports/`. Tests: `tests/`.

| Phase | Files that the phase edits |
|---|---|
| 1 | `grad_limits.py` (`_range_result` only: the junction code and its two comments), `tests/test_grad_limits.py` (one new test), `TESTS.md` section 2.13 |
| 2 | `assets/seq_lanes.js` (`_adcOverlaps` only), `tests/js/test_seq_lanes.js` (one new builder, one new test), `TESTS.md` section 2.19 |
| 3 | `assets/g_lanes.js` (the cache key, the check in `decode`, and their comments), `assets/cards/diagram.js` (the \|G\| build and `showStatus`), `tests/js/test_g_lanes.js` (one new builder, one new test), `TESTS.md` section 2.27 |
| 4 | `tests/test_sampling.py` (one new test), `tests/test_rf_profiles.py` (one new test), `TESTS.md` sections 2.23 and 2.31 |
| 5 | `cards/spectrum.py` (the note only), `tests/test_spectrum_card.py`, `TESTS.md` section 2.10 |
| 6 | `cards/gradient_limits.py` (the note only), `grad_limits.py` (the module docstring, lines 19-23 only), `tests/test_gradient_limits_card.py`, `TESTS.md` section 2.14 |
| 7 | `docs/examples/gre.html` (rebuilt), this plan file (status and section 8) |

Rules:

1. As in `docs/plans/cards-at-scale.md`, section 3.4, rules 1 to 3.
2. `TESTS.md`: each phase edits only its own sections. An unchanged heading
   separates each pair of sections, so git merges the edits of parallel
   phases without a conflict. If a conflict in `TESTS.md` occurs, keep both
   sides.
3. `grad_limits.py` is in phases 1 and 6. Phase 6 starts after phase 1 is
   merged.
4. Only phase 7 edits `docs/examples/gre.html`. The page has a copy of every
   script and note, so an edit in each phase gives a conflict between
   parallel phases.
5. To bring a branch up to a newer `main`, merge `origin/main` into it (with
   the user's approval of the merge commit). Auto mode refused `git rebase`
   on 2026-09-29. The PR is squash-merged, so the merge commit does not stay
   in `main`.

## 4. Design

### 4.1 B1: only the junctions inside the window

In `_range_result` (`grad_limits.py`), use a junction only when its block
starts at or after the range start:

```python
    # The junction steps (decision 6 of section 2.5): for each axis, the step at the
    # incoming junction of each processed block that starts at or after the range
    # start (0 before the very first block of the file, or where either side has no
    # event on the axis). The junction of a block that the range start cuts is before
    # the range, so it is not used. A junction at the range end belongs to the block
    # after it, which is not processed.
    junction_in_range = processed & (start_s >= lo)
    ...
        if np.any(junction_in_range):
            masked = np.where(junction_in_range, steps, -np.inf)
```

1. Put `junction_in_range` once, before the loop over the axes. Replace
   `processed` in the guard (line 429) and in the `np.where` (line 430).
2. The comment at lines 451-454 gives the example "a window that starts right
   after a gradient event that ends outside it". After the change, that
   junction does not count. Change the example to "a window that starts at
   the junction after a gradient event that ends at a value that is not 0".
3. The rule at the window edges: a junction at the window start counts. A
   junction at the window end does not count, because its block (the credited
   block) is after the window. This is the result of the review's change.
   Decision 14 confirms it.
4. The whole-file result does not change: `lo = 0`, so `start_s >= lo` is
   true for each block.
5. Not in this fix: the tie rule and the docstring of `_range_result` (C14,
   L3).

### 4.2 B2: the group of `first` is an end group

In `_adcOverlaps` (`seq_lanes.js`), line 1038:

```js
    // One block before the bin's first: its window can reach into the bin.
    const from = Math.max(0, first - 1);
    // The group of `first`, not of `from`: block `first` holds e0, so its ADC
    // window can end before the bin. Its group is an end group: scanned block
    // by block, never answered by the prefix count.
    const gFrom = Math.floor(first / GROUP_BLOCKS);
```

1. The first `scan(from, (gFrom + 1) * GROUP_BLOCKS - 1)` then covers
   `first - 1` to the end of the group of `first`: at most 65 blocks.
2. Change the function comment (lines 1015-1023) to say which blocks the two
   end scans cover.
3. `scan` does not change. It starts at `blockStart(model, a)` and adds
   durations forward, as decision 5 requires.
4. The regression test is a new test, not a new case of
   `test_min_max_lanes_matches_brute_force_for_adc_windows`. That test loops
   over the arguments of `buildRandomModel`, and the bug needs a different
   model (section 2.3).
   - New builder `buildSparseAdcModel(nBlocks, adcBlocks)`: blocks of 1 ms,
     no RF and no gradient, an ADC window of 0.5 ms at the start of each
     block in `adcBlocks`. The form is `emptyTables` of section 9.2.
   - New test
     `test_min_max_lanes_adc_off_after_a_window_in_the_first_block_of_a_group`:
     `buildSparseAdcModel(400, [64])`, and `adcLaneProblems` must be `[]` for
     the views `[0.0647, 0.2647, 1]`, `[0.0647, 0.2647, 3]` and
     `[0, 0.4, 40]`. The first two views fail before the change (checked).

### 4.3 B3: a key in two levels, and a \|G\| failure removes only the \|G\| lane

**`g_lanes.js`.** The cache `evCache.triple` becomes a `Map` of `Map`s. The
outer key is `kx * M + ky`. The inner key is `kz * D + durIdx`. Return the two
keys as fields of the object of `_tripleKeyOf`, so that a block makes no extra
object (checked in the scratchpad):

```js
  function _tripleGeometry(tb, kx, ky, kz, dur, evCache, outerKey, innerKey) {
    let inner = evCache.triple.get(outerKey);
    if (inner === undefined) {
      inner = new Map();
      evCache.triple.set(outerKey, inner);
    }
    let g = inner.get(innerKey);
    if (g !== undefined) return g;
    ...
    inner.set(innerKey, g);
    return g;
  }

  function _tripleKeyOf(tb, i, M, D) {
    ...
    return { kx, ky, kz, dur, outerKey: kx * M + ky, innerKey: kz * D + durIdx };
  }
```

1. The two callers (`_blockGRange`, `_exactBlockGRange`) pass `t.outerKey`
   and `t.innerKey`.
2. The check in `decode` becomes
   `if (M * M - 1 > Number.MAX_SAFE_INTEGER || M * D - 1 > Number.MAX_SAFE_INTEGER)`.
3. Change the comments that give the old key (lines 243-254, 298-299, and
   the `decode` comment at 420-426).

**`diagram.js`.** Build the \|G\| model in a `try`/`catch`. One place covers
the three paths of section 2.3, because each of them fails in `lanesFor`:

```js
  // The |G| lane's {model, laneMeta, error} for one file. A GLanes failure (for
  // example no memory) removes only the |G| lane: `model` is null, and the status
  // line says why. The other lanes and the window buttons keep working. It is
  // built one time for each file: a failure is not tried again on each render.
  function buildGLane(seqModel) {
    try {
      const model = GLanes.decode(seqModel);
      return { model, laneMeta: GLanes.laneMeta(model), error: null };
    } catch (error) {
      console.error(`diagram card "${section.id}": the |G| lane is not drawn:`, error);
      return { model: null, laneMeta: null, error };
    }
  }
```

1. In `lanesFor`: `if (!current.g) current.g = buildGLane(current.seq);`.
   Append the lane only when `current.g.model` is not null.
2. `showStatus` gets a fifth argument, the error or null. With an error, it
   adds the sentence `The |G| lane is not drawn: ${error.message}` to the
   status text (decision 13).
3. `laneChart` sets the SVG height from the lanes of each render, so a render
   without the \|G\| lane is correct (`lane_chart.js`, `render`).
4. Change the comment of `decodeFile` (lines 66-79) and the file comment
   (lines 11-22) where they describe `g`.
5. Not in this fix: memory for many distinct events (P6).

**Tests.** A new builder `buildManyEventsTables(numEvents, nBlocks)` in
`test_g_lanes.js` (the form of section 9.3: 4-point events, 5 durations,
`Uint32Array` event columns, event indexes near `numEvents`). A new test
`test_decode_accepts_more_gradient_events_than_one_numeric_key_allows`:
150,000 events and 300 blocks. `GLanes.decode` must not throw, and `minMax`
must match `bruteMinMax` within 1e-12 of the peak (`assertMinMaxMatches`) for
the views `[0, durationS, 37]`, `[0, durationS, 211]` and
`[starts[10], starts[280], 17]`. Before the change, the test fails with the
2^53 error (checked). `diagram.js` has no Node test (decision 6). Task 3.5
checks it in a browser.

### 4.4 B4: an oversampled arbitrary gradient

The user chose a fork pin from the release, with the fix (decision 9): option
C on the release. Options A, B, C and D stay below as the record of the choice.
The tests of option B are the tests of phase 4.

**Option A: refuse the sequence**, as `extensions.refuse_rotations` refuses a
rotation. A new `extensions.refuse_oversampled_gradients(seq)` raises
`NotImplementedError` when an arbitrary gradient of `seq.grad_library` has
the time shape ID -1 (`type == "g"` and `data[4] == -1`). Call it next to each
call of `refuse_rotations`.

- For: no report shows a wrong value. The check reads no block (its cost is
  the number of distinct gradient events). It uses no arithmetic of a
  pypulseq internal.
- Against: a caller with such a sequence gets none of the gradient cards.
  The change edits eight source files, and two of them are also in phases 5
  and 6. When pypulseq fixes `get_block`, the check still refuses. A
  `TODO.md` item must remove it.

**Option B: correct `shape_dur` in this library** (recommended). In
`seq_utils.py`:

```python
def _shape_dur(g) -> float:
    """`g.shape_dur` of one arbitrary gradient event, corrected for pypulseq issue #423.

    pypulseq 1.5.0.post1 (and the pinned fork) `get_block` gives an oversampled
    arbitrary gradient (time shape ID -1) twice the `shape_dur` that
    `make_arbitrary_grad` sets, `(n + 1) * 0.5 * grad_raster_time`. That value equals
    `g.tt[-1] + g.tt[0]` to rounding. This halves a value that is more than 1.5 times it, so it
    does not change a correct value (a pypulseq with the fix of PR #424). Halving is
    exact in binary floating point, so the result equals the value of
    `make_arbitrary_grad` bit for bit.
    """
    if getattr(g, "time_id", None) == -1 and g.shape_dur > 1.5 * (g.tt[-1] + g.tt[0]):
        return 0.5 * g.shape_dur
    return g.shape_dur
```

`gradient_offsets` uses `_shape_dur(g)` in place of `g.shape_dur`. After
`read`, `time_id` is the float -1.0, and `== -1` is true for it.

`rf_profiles.py` reads the end of a gradient event from `pp.calc_duration(g)`
in two places (`_plays_during` and `_fill_gradient_spans`). That value also
uses the doubled `shape_dur`. Add a function to `seq_utils.py`, and use it in
those two places:

```python
def gradient_end(g) -> float:
    """The end (s) of one gradient event in its block: its delay plus its last offset
    (`gradient_offsets`). For a correct event this equals `pp.calc_duration(g)`; for an
    oversampled arbitrary gradient it uses the corrected `shape_dur`."""
    delay, offsets, _ = gradient_offsets(g)
    return float(delay + offsets[-1])
```

For a trapezoid, the last offset is `rise_time + flat_time + fall_time`. For
an extended trapezoid or an arbitrary gradient, it is `shape_dur`. So
`gradient_end` equals `pp.calc_duration(g)` for every event that `get_block`
gives correctly, and the existing tests of `test_rf_profiles.py` do not
change.

- For: correct values for each caller. This includes the pinned fork (uv
  consumers get it too), stock pypulseq from PyPI (pip consumers, and a
  project that pins its own pypulseq), and a pypulseq that has the fix. Every
  path goes through `gradient_offsets`, directly or through `gradient_end`,
  so two small functions fix every row of the reach table. The change has
  about 20 lines. The tests check computations of this library.
- Against: a work-around of a pypulseq bug in this library. It knows the
  flag -1 and the wrong factor. A `TODO.md` item must remove it after a
  pypulseq release has the fix.

**Option C: add the fix to the pin.** Make a fork branch from `pns-chunked`.
Add `6db882b` (the fix of PR #424) to it. Pin its commit.

- For: no work-around in this library. The code is the code of the upstream
  PR.
- Against: it corrects the values only for a project that installs with uv
  and uses the pin. A project that installs with pip, or that pins its own
  pypulseq, keeps the wrong values. The fork rule is "one change, one commit, one branch"
  (`docs/plans/cards-at-scale.md`, section 3.6, item 3). Thus the pin needs
  a new branch that joins two changes, or a second change on `pns-chunked`.
  Each fork commit needs the user's approval. The pin moves, so every open
  phase rebases. A test of `shape_dur` in this library would test pypulseq
  (decision 4). Only the sampler test of option B is allowed.

**Option D: wait for a pypulseq release with PR #424.**

- For: no work.
- Against: the wrong values stay (section 2.3) for a sequence built in
  Python and for a file read with `remove_duplicates=False`. There is no
  date for a release.

**The choice.** The draft of this plan recommended option B: it is the only
option that corrects the values for every consumer, whatever pypulseq it
installs. The user first chose option D, then the pin of decision 9. The reach
is small (section 2.3), the upstream fix exists (PR #424), and this library
gets no work-around of a pypulseq bug. A project that uses uv gets the pin, and
with it the fix. A project that uses pip, or that sets its own pypulseq, does
not (`docs/usage.md`, section 1).

**Tests of option B.** Phase 4 adds tests 2 and 3 (decision 9). With the fix
in the pin, test 1 checks only pypulseq's `get_block` (decision 4), so it is
not added. Build the sequence of section 9.4 in each
test. The
sampler test uses all three blocks. The reference is the added events, not
`get_block` and not `get_gradients`. `get_gradients` leaves out the first and
the last point of an oversampled gradient (draft 03). In the measurement of
section 2.3, that difference was 3.3 % of the peak.

1. `test_seq_utils.py`:
   `test_gradient_offsets_oversampled_arbitrary_gradient_ends_at_its_shape_dur`.
   The offsets of `gradient_offsets(seq.get_block(1).gx)` equal
   `[0.0, *g.tt, g.shape_dur]` of the added event exactly
   (`numpy.array_equal`). The last offset equals `seq.block_durations[1]`.
2. `test_sampling.py`:
   `test_sample_matches_the_added_events_for_an_oversampled_arbitrary_gradient`.
   Sample `GradientSampler.sample("gx", t)` at 4000 times over the file. Build
   the reference with `numpy.interp` on the polyline of the added events. The
   block starts come from `numpy.cumsum` of the block durations. The two must
   agree within 1e-12 of the peak (`docs/plans/cards-at-scale.md`, section
   3.5, item 2). Before the change, the error is 40 % of the peak.
3. `test_rf_profiles.py`:
   `test_oversampled_gradient_that_ends_before_the_rf_is_not_a_gradient_of_the_pulse`.
   Build the block of section 9.6: an oversampled triangle on z (21 samples,
   first and last 0) and a block pulse with `use="excitation"` whose delay is
   50 µs after the end of the added gradient event, then an ADC block.
   `block_pulse(seq, 0)` has `gradient_kind` "none", a `grad_hz_per_m` of all
   zeros, and 0 for each gradient id in its key. Before the change, it has
   "one", a z gradient during the RF and the `gz` id in the key.

**Tests of option A.** In `test_extensions.py`, as the rotation tests do:

1. The check raises for an oversampled gradient.
2. The check accepts the synthetic sequences.
3. Each gradient card raises (parametrized).

Not in this fix: the `hasattr` guard of `gradient_offsets` that is always
true (D19).

### 4.5 B5: escape the label in the note

`cards/spectrum.py:150`: `{scanner_label}` becomes
`{html.escape(scanner_label)}`. `html` is already imported.

New test in `test_spectrum_card.py`: `test_scanner_label_is_escaped_in_the_note`.
With `scanner_label="Coil <A&B>"`, `card.body_html` does not contain
`Coil <A&B>`, and it contains
`the acoustic resonances of the Coil &lt;A&amp;B&gt; gradient coil`.

### 4.6 B6: the note and the docstring describe the junction step

1. `cards/gradient_limits.py:127-128`: the sentence becomes "Max slew is the
   largest rate of change between neighbouring points of one gradient event,
   or the step at a block junction divided by the gradient raster time, as
   pypulseq's add_block checks it." Put `add_block` in a `<code>` element, as
   the spectrum note does for `calculate_gradient_spectrum`.
2. `grad_limits.py:19-23`: the paragraph becomes:

   ```
   The peak slew rate is the largest of two kinds of value (decision 6 of section 2.5 of the
   plan): the slope of each straight segment of each gradient event, and the step at each block
   junction divided by `grad_raster_time` (`Sequence.add_block` checks this step). The step uses
   0 for a block with no event on the axis, and 0 before the first block.
   ```
3. New test in `test_gradient_limits_card.py`:
   `test_note_says_max_slew_includes_block_junction_steps`. The card body
   contains "or the step at a block junction divided by the gradient raster
   time".
4. Not in this fix: the other docstrings of `grad_limits.py` (C14).

## 5. Phases

---

### Phase 1: B1, the junctions of a window

Branch: `fix/grad-limits-window-junction`. Tier: S. Review: O. Wave 1.

**Task 1.1: The test.** Tier S. In `tests/test_grad_limits.py`, after the
three junction tests, add
`test_window_inside_a_block_with_no_gradient_ignores_the_junction_before_it`.
Use `_RASTER` and `_MAX_STEP` of that file.

1. Build the sequence of section 9.1: an extended trapezoid on x, times
   `[0, 100e-6, 200e-6]`, amplitudes `[0, s, s]` with `s = 0.9 * _MAX_STEP`,
   then `pp.make_delay(1e-3)`.
2. Window `(0.5e-3, 1.0e-3)`: `reason` is "no gradient events in the
   window", the x slew is 0.0, and `slew_block` is None.
3. Window `(0.2e-3, 1.0e-3)`, which starts at the junction: `reason` is
   None, the x slew is `s / _RASTER / GAMMA` (`pytest.approx`), and
   `slew_block` is the ID of the delay block.
4. Run the test. Item 2 must fail on the current code.

**Task 1.2: The change.** Tier S. Section 4.1, items 1 and 2.

**Task 1.3: `TESTS.md`.** Tier S. Section 2.13: one entry for the new test
(Checks, How, Assumptions). Add "a window that starts inside a block after a
junction step" to the list of the section's second paragraph.

**Task 1.4: Repro.** Tier O. Run section 9.1 before and after. Put both
outputs in the PR.

Checks:

- [ ] The new test fails before the change and passes after it.
- [ ] Section 9.1 prints the "after" column of section 2.3.
- [ ] `scripts/check` passes.

---

### Phase 2: B2, the ADC in the minimum/maximum view

Branch: `fix/seq-lanes-adc-min-max`. Tier: S. Review: O. Wave 1.

**Task 2.1: The test.** Tier S. In `tests/js/test_seq_lanes.js`, add the
builder `buildSparseAdcModel` after `buildAdcCloseModel`, and the test of
section 4.2, item 4, after
`test_min_max_lanes_matches_brute_force_for_adc_windows`. Run it. It must
fail on the current code.

**Task 2.2: The change.** Tier S. Section 4.2, items 1 and 2, on line 1038
only. Do not change line 663.

**Task 2.3: `TESTS.md`.** Tier S. Section 2.19: one entry for the new test.
Add `buildSparseAdcModel` to the list of hand-built models in the section's
introduction.

**Task 2.4: Review.** Tier O. Run section 9.2 before and after. Check that
no block start is computed by a subtraction (decision 5).

Checks:

- [ ] The new test fails before the change and passes after it.
- [ ] Section 9.2 prints "OK: no ADC in the bin".
- [ ] `scripts/check` passes.

---

### Phase 3: B3, the \|G\| lane of a file with many gradient events

Branch: `fix/g-lanes-many-events`. Tier: S (two workers). Review: O. Wave 1.

**Task 3.1: The test and the key.** Tier S (worker A). In
`tests/js/test_g_lanes.js`, add `buildManyEventsTables` and the test of
section 4.3. Run it. It must fail with the 2^53 error. Then make the
`g_lanes.js` change of section 4.3, items 1 to 3.

**Task 3.2: `diagram.js`.** Tier S (worker B), at the same time as task 3.1.
Section 4.3, "`diagram.js`", items 1 to 4.

**Task 3.3: `TESTS.md`.** Tier S (worker A). Section 2.27: one entry for the
new test. Add `buildManyEventsTables` to the list of builders in the
section's introduction.

**Task 3.4: Time.** Tier O. Run section 9.3's timing script for 10^7 blocks,
three times each, on `main` and on the branch. Put the numbers in the PR. Check
the budget of section 2.4.

**Task 3.5: Browser check.** Tier O. Use the
`dev-workflow:browser-check-localhost` skill. Make three scratch pages with
`render_page`, in the session scratchpad. Each page has the diagram card for
two files (the example GRE of `examples/gre_report.py` and
`tests/synthetic.spin_echo_sequence()`), and the RF profile card for the same
two files.

1. Page 1 has no extra script. It must look and work as on `main`. The
   \|G\| lane is drawn for both files.
2. Page 2 has this extra script. It makes the second `GLanes.decode` call
   throw:

   ```js
   (() => {
     const decode = GLanes.decode;
     let calls = 0;
     GLanes.decode = seqModel => {
       calls += 1;
       if (calls >= 2) throw new Error("forced failure for the browser check");
       return decode(seqModel);
     };
   })();
   ```

   - The first file draws with its \|G\| lane.
   - A window button of the second file: the chart shows the second file
     without the \|G\| lane. The status line says "The |G| lane is not drawn:
     forced failure for the browser check". The buttons work.
   - Reload the page. A "Show" button of the RF profile card for a pulse of
     the second file (the `goto` path): the same result.
3. Page 3: the stub throws on every call. The card draws the first file
   without the \|G\| lane, not "This card could not be drawn".
4. Both themes. No console error except the logged \|G\| failure.

Checks:

- [ ] The new test fails before the change and passes after it.
- [ ] Section 9.3 prints "GLanes.decode: ok" and "(match)".
- [ ] The time of task 3.4 is inside the budget of section 2.4.
- [ ] The browser check of task 3.5 passes.
- [ ] `scripts/check` passes.

---

### Phase 4: B4, the regression tests

Branch: `fix/oversampled-gradient-tests`. Tier: S. Review: O. Wave 2, after
the pin PR (`chore/pypulseq-pin-release-base`) is merged. Decision 9.

**Task 4.1: The tests.** Tier S. Tests 2 and 3 of section 4.4, "Tests of
option B". They must pass on the new pin with no change to the library code.
Then run them with the old pin (`uv run --with-editable` of a pypulseq
checkout at `20b9e5e`). They must fail there. Report both results.

**Task 4.2: `TESTS.md`.** Tier S. Sections 2.23 and 2.31: one entry each. The
entry of section 2.23 says why its reference is the added events and not
`seq.get_gradients()` (section 4.4). Each entry says that the test needs the
fix of pypulseq PR #424, which the pin has.

**Task 4.3: Repro.** Tier O. Run sections 9.4 and 9.6 on the branch. They
must print the correct values of section 2.3 (sampler error 0.0 %, RMS 8.3424
mT/m, `_plays_during: False`, `gradient_kind: none`). The default `write()`
and `read()` still raise `KeyError` (draft 04, not in the pin). Put the
outputs in the PR.

Checks:

- [ ] The new tests pass on the new pin and fail on `20b9e5e`.
- [ ] `scripts/check` passes.

---

### Phase 5: B5, the label in the spectrum note

Branch: `fix/spectrum-label-escape`. Tier: H. Review: O. Wave 2.

**Task 5.1: The test.** Tier H. The test of section 4.5, after
`test_custom_scanner_label_and_resonances_appear`. Run it. It must fail.

**Task 5.2: The change.** Tier H. Section 4.5.

**Task 5.3: `TESTS.md`.** Tier H. Section 2.10: one entry.

Checks:

- [ ] The new test fails before the change and passes after it.
- [ ] Section 9.5 prints "raw label in body: False".
- [ ] `scripts/check` passes.

---

### Phase 6: B6, the slew note

Branch: `fix/gradient-limits-slew-note`. Tier: H. Review: O. Wave 2, after
phase 1 is merged.

**Task 6.1: The test.** Tier H. The test of section 4.6, item 3, after
`test_no_gradients_adds_a_reason_note`. Run it. It must fail.

**Task 6.2: The change.** Tier H. Section 4.6, items 1 and 2, with the exact
text.

**Task 6.3: `TESTS.md`.** Tier H. Section 2.14: one entry.

Checks:

- [ ] The new test fails before the change and passes after it.
- [ ] `scripts/check` passes.

---

### Phase 7: results

Branch: `chore/review-bugs-results`. Tier: O. After phases 1 to 6 are merged.

**Task 7.1: The example report.** Rebuild `docs/examples/gre.html` with
`nix develop --command uv run python examples/gre_report.py`. Check the diff.
It must have only the script changes of phases 2 and 3, the note of phase 6,
and the changes of other merged work. Open the page in the browser. It must
show no console error.

**Task 7.2: This plan.** Status "complete". Section 8: the PR numbers, the
decisions made during the work, and the measurements of task 3.4.

**Task 7.3: Tell the user** that B1, B2, B3, B5 and B6 are fixed, and that
the pin fixes B4 (with its tests). Do not start the
release `0.2.0rc2` (decision 8).

Checks:

- [ ] `scripts/check` passes.

## 6. Summary of parallel work

| Wave | Phases | Condition to start |
|---|---|---|
| 1 | 1, 2, 3 | This plan is merged. |
| 2 | 4, 5, 6 | A free PR slot. Phase 4: the pin PR merged. Phase 6: phase 1 merged. |
| 3 | 7 | Phases 1 to 6 merged. |

Workers inside a phase:

| Phase | Workers |
|---|---|
| 1 | One S worker for tasks 1.1 to 1.3. The executing agent does task 1.4 and reviews. |
| 2 | One S worker for tasks 2.1 to 2.3. The executing agent does task 2.4. |
| 3 | S worker A for tasks 3.1 and 3.3, and S worker B for task 3.2, at the same time. The executing agent does tasks 3.4 and 3.5. |
| 4 | One S worker for tasks 4.1 and 4.2. The executing agent does task 4.3 and reviews. |
| 5 | One H worker for tasks 5.1 to 5.3, with the exact texts of section 4.5. |
| 6 | One H worker for tasks 6.1 to 6.3, with the exact texts of section 4.6. |
| 7 | The executing agent. |

## 7. Questions still open

None. The user answered all six questions on 2026-09-29:

1. B4: option D, wait for a pypulseq release or an upstream fix. Revised the
   same day: a fork pin from the release, with the fix (decision 9). The plan
   had recommended option B.
2. B5 and B6: separate branches (decision 10).
3. Order: B1, B2 and B3 first, then B4, B5 and B6, then phase 7 (decision
   11).
4. The example report: rebuilt one time, in phase 7 (decision 12).
5. B3: the status line says why the \|G\| lane is not drawn (decision 13).
6. B1: a junction at the window start counts, and one at the window end
   does not (decision 14).

## 8. Results

All phases were done on 2026-09-29.

### 8.1 Pull requests

| Phase | Bug | PR | Merge commit |
|---|---|---|---|
| Plan | | #66, revised by #68 | `e8358a6`, `c025570` |
| Pin (decision 9) | B4 | #67 | `bcf1f23` |
| 1 | B1 | #69 | `b318bcb` |
| 2 | B2 | #70 | `6e57c58` |
| 3 | B3 | #71 | `d05a708` |
| 4 | B4 (tests) | #72 | `0f6d214` |
| 5 | B5 | #73 | `2b369ec` |
| 6 | B6 | #74 | `b985209` |
| 7 | results | this PR | |

Before the plan: #64 committed the review, and #65 (step 1 of the review's
order) made the card helpers public and fixed D1, D2, A9, A10, C1 and C2.

### 8.2 Decisions made during the work

1. **B4: the pin, not a change in this library** (decision 9, revised). The
   fork's tag `pulseq-reports-pin-1` (`a74ab06`, #67) is the release
   1.5.0.post1 with four cherry-picks: the two PNS commits, the fix of
   pypulseq PR #424 and upstream #359. The pin is on the release, so a
   project that uses uv also builds its sequences with the release. The user
   left out upstream #386 (hexadecimal values in `readasc`): on the release, a
   hexadecimal line of an `.asc` file is skipped, and the SAFE fields are
   decimal, so the PNS values do not change. #67 also corrected review
   finding C9 in `docs/usage.md`: uv applies the `[tool.uv.sources]` of a git
   dependency (checked with uv 0.12.11).
2. **B6: no test** (the user). A test that only checks that a fixed sentence
   is in the note tests no computation, and it fails on any rewording. The
   second commit of #74 removed it. Decision 1 ("one regression test for each
   bug") does not apply to a text bug.
3. **Phases 4 and 5 ran at the same time as phases 1 to 3** (the user). Five
   PRs were open at one time, more than the three of decision 3.
4. **B3:** the status sentence uses `gError.message || String(gError)`, so a
   thrown value that is not an `Error` also gives a message.
5. **Merges:** the PRs of a wave all edit `TESTS.md`, in different sections.
   GitHub merged them in order with no conflict. After each later merge,
   `cleanup-merged.sh` reports that `TESTS.md` differs from the PR head; each
   PR's added lines were checked on `main`.

### 8.3 Measurements

- **B3, time** (task 3.4): `GLanes.decode` for 10^7 repeating blocks, in
  Node, three runs each: 222, 168 and 168 ms on `main`; 224, 227 and 230 ms
  with the fix. The peak is the same (26.627). The PNS and |G| lanes then add
  about 1.5 s before the first chart, inside the 3 s budget of section 2.4.
- **B3, browser** (task 3.5): pages with the diagram and the RF profile cards
  for the example GRE and a synthetic spin echo.
  - With no stub, both files draw the |G| lane.
  - With `GLanes.decode` forced to fail from its second call, the second file
    has no |G| lane and the status sentence, through a window button and
    through "Show" (`goto`). No button stays disabled, and the first file
    keeps its |G| lane.
  - With every call failing, the card draws the first file without |G|. The
    same page from `main` shows "This card could not be drawn".
  - The dark theme renders. The only console errors are the logged failures.
- **B4 on the old pin** (`20b9e5e`): the sampler test has 1012 of 3999
  samples outside the tolerance (about 40 % of the peak), and the
  `rf_profiles` test gets the gradient kind "one". On the new pin, sections
  9.4 and 9.6 print the correct values of section 2.3.
- **The pin** (#67): the fork's suite gives 1477 passed and 24 skipped (1375
  and 21 on plain `v1.5.0.post1`). This project's 917 tests pass, the example
  report is byte-identical, and the PNS card of the 370 s ex-vivo file gives
  the same output in 2.9 s and 0.15 GB on both pins.
- **`main` after phase 6:** `scripts/check` passes with 921 pytest tests,
  166 node tests and 503 `TESTS.md` entries.
- **The example report** (task 7.1): the rebuild changes only the scripts of
  B2 and B3 and the slew note of B6; no card data changes. In the browser,
  the nine cards draw, the diagram has the |G| and PNS lanes, and the console
  has no error.

### 8.4 Not in this plan

- The default `Sequence.write` and `Sequence.read` still raise `KeyError` for
  an oversampled arbitrary gradient (draft 04 of
  `github.com/mdtisdall/pypulseq-issues`; not in the pin).
- The other findings of the review (A, F, D, S, P, C and L), except those
  that #65 fixed.

## 9. Repro scripts

Run each script from the root of a worktree. The Python scripts:
`nix develop --command uv run python <script>`. The JavaScript scripts:
`nix develop --command node <script>`. The scripts write no file in the
worktree.

### 9.1 B1

```python
"""B1: a window inside a block with no gradient, after a gradient that ends non-zero."""

import sys

import pypulseq as pp

sys.path.insert(0, "tests")
from synthetic import SYSTEM  # noqa: E402

from pulseq_reports.grad_limits import gradient_limits  # noqa: E402

step = 0.9 * SYSTEM.max_slew * SYSTEM.grad_raster_time
gx = pp.make_extended_trapezoid(
    channel="x", times=[0.0, 100e-6, 200e-6], amplitudes=[0.0, step, step], system=SYSTEM
)
seq = pp.Sequence(SYSTEM)
seq.add_block(gx)  # 0 to 0.2 ms, ends at 0.9 of the largest step
seq.add_block(pp.make_delay(1e-3))  # 0.2 to 1.2 ms, no gradient

for window in [(0.5e-3, 1.0e-3), (0.2e-3, 1.0e-3), None]:
    r = gradient_limits(seq, window=window)
    x = r.axes["x"]
    print(
        window,
        "reason:",
        r.reason,
        "x slew T/m/s:",
        round(x.max_slew_t_per_m_per_s, 3),
        "slew_block:",
        x.slew_block,
        "peak mT/m:",
        x.peak_mt_per_m,
    )
```

### 9.2 B2

```js
// B2: node <this file> [path/to/seq_lanes.js]
const path = require("node:path");
const SeqLanes = require(path.resolve(process.argv[2] ||
  path.join("src", "pulseq_reports", "assets", "seq_lanes.js")));

function emptyTables(n, adcBlocks) {
  const adc = new Uint8Array(n);
  for (const i of adcBlocks) adc[i] = 1;
  const checkpoints = new Float64Array(Math.ceil(n / 1024));
  for (let c = 0; c < checkpoints.length; c++) checkpoints[c] = c * 1024 * 1e-3;
  const f = () => new Float64Array(0), u = () => new Uint32Array(0);
  return {
    duration_index: new Uint8Array(n), durations: Float64Array.from([1e-3]), checkpoints,
    rf: new Uint8Array(n), gx: new Uint8Array(n), gy: new Uint8Array(n),
    gz: new Uint8Array(n), adc,
    rf_delay: f(), rf_mag_n: u(), rf_mag_offset_at: u(), rf_mag_at: u(),
    rf_mag_offset: f(), rf_mag: f(), rf_phase_n: u(), rf_phase_offset_at: u(),
    rf_phase_at: u(), rf_phase_offset: f(), rf_phase: f(),
    grad_delay: f(), grad_n: u(), grad_offset_at: u(), grad_at: u(),
    grad_offset: f(), grad_value: f(),
    adc_delay: Float64Array.from([0]), adc_length: Float64Array.from([0.5e-3]),
  };
}
const meta = ["rf_mag", "rf_phase", "adc", "gx", "gy", "gz"].map(id => ({
  id, title: id, unit: "", color: id, kind: id === "adc" ? "gate" : "line",
  domain: [-1, 1], ticks: [0], tick_labels: ["0"], empty: false,
  fill: id === "rf_phase" ? null : 0.0,
}));
// 400 blocks of 1 ms. One ADC window in block 64 (the first block of group 1):
// 64.0 to 64.5 ms. The view starts at 64.7 ms, inside block 64, after the ADC.
const model = SeqLanes.decode(1, emptyTables(400, [64]), meta);
const k = meta.findIndex(m => m.id === "adc");
const mm = SeqLanes.minMaxLanes(model, 0.0647, 0.2647, 1)[k].windows;
const ex = SeqLanes.exactLanes(model, 0.0647, 0.2647)[k].windows;
console.log("minMaxLanes ADC windows:", JSON.stringify(mm));
console.log("exactLanes  ADC windows:", JSON.stringify(ex));
console.log(JSON.stringify(mm) === "[]" ? "OK: no ADC in the bin" : "BUG: bin marked on");
```

### 9.3 B3

The repro. The timing script is below it.

```js
// B3: node <this file> [dir that holds g_lanes.js and seq_lanes.js]
const path = require("node:path");
const dir = path.resolve(process.argv[2] || path.join("src", "pulseq_reports", "assets"));
const SeqLanes = require(path.join(dir, "seq_lanes.js"));
const GLanes = require(path.join(dir, "g_lanes.js"));

const NUM_EVENTS = 150000, N = 300;
const grad_at = new Uint32Array(NUM_EVENTS), grad_value = new Float64Array(4 * NUM_EVENTS);
for (let e = 0; e < NUM_EVENTS; e++) {
  grad_at[e] = 4 * e;
  const a = ((e * 7919) % 2001 - 1000) / 40; // -25 to 25 mT/m
  grad_value.set([0, a, a, 0], 4 * e);
}
let s = 12345;
const rnd = () => (s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
const duration_index = new Uint8Array(N);
const gx = new Uint32Array(N), gy = new Uint32Array(N), gz = new Uint32Array(N);
for (let i = 0; i < N; i++) { // event indexes near NUM_EVENTS
  duration_index[i] = Math.floor(rnd() * 5);
  gx[i] = rnd() < 0.3 ? 0 : NUM_EVENTS - Math.floor(rnd() * 50);
  gy[i] = rnd() < 0.3 ? 0 : NUM_EVENTS - Math.floor(rnd() * 50);
  gz[i] = rnd() < 0.3 ? 0 : NUM_EVENTS - Math.floor(rnd() * 50);
}
const f = () => new Float64Array(0), u = () => new Uint32Array(0);
const tables = {
  duration_index, durations: Float64Array.from([2e-4, 3.5e-4, 6e-4, 9e-4, 1.2e-3]),
  checkpoints: new Float64Array(1), rf: new Uint8Array(N), adc: new Uint8Array(N), gx, gy, gz,
  rf_delay: f(), rf_mag_n: u(), rf_mag_offset_at: u(), rf_mag_at: u(), rf_mag_offset: f(),
  rf_mag: f(), rf_phase_n: u(), rf_phase_offset_at: u(), rf_phase_at: u(),
  rf_phase_offset: f(), rf_phase: f(), adc_delay: f(), adc_length: f(),
  grad_delay: new Float64Array(NUM_EVENTS), grad_n: new Uint32Array(NUM_EVENTS).fill(4),
  grad_offset_at: new Uint32Array(NUM_EVENTS), grad_at,
  grad_offset: Float64Array.from([0, 5e-5, 1.5e-4, 2e-4]), grad_value,
};
const meta = ["rf_mag", "rf_phase", "adc", "gx", "gy", "gz"].map(id => ({
  id, title: id, unit: "", color: id, kind: id === "adc" ? "gate" : "line",
  domain: [0, 1], ticks: [0], tick_labels: ["0"], empty: false,
  fill: id === "rf_phase" ? null : 0.0,
}));
const seqModel = SeqLanes.decode(1, tables, meta);
console.log("SeqLanes.decode: ok,", seqModel.numBlocks, "blocks");
let g;
try {
  g = GLanes.decode(seqModel);
} catch (error) {
  console.log("GLanes.decode THREW:", error.message);
  process.exit(0);
}
// Every event is a trapezoid from the block start: the peak is the vector sum of
// the three flat values, which overlap from 5e-5 to 1.5e-4 s.
const amp = k => (k === 0 ? 0 : grad_value[4 * (k - 1) + 1]);
let peak = 0;
for (let i = 0; i < N; i++) peak = Math.max(peak, Math.hypot(amp(gx[i]), amp(gy[i]), amp(gz[i])));
console.log("GLanes.decode: ok, wholeFileMax =", g.wholeFileMax.toFixed(4),
  "brute force =", peak.toFixed(4),
  Math.abs(peak - g.wholeFileMax) < 1e-12 * peak ? "(match)" : "(MISMATCH)");
```

The timing script. Run it in a new process for each run:
`node <this file> <assets dir> 10000000`.

```js
const path = require("node:path");
const dir = path.resolve(process.argv[2]);
const N = Number(process.argv[3] || 1e7);
const SeqLanes = require(path.join(dir, "seq_lanes.js"));
const GLanes = require(path.join(dir, "g_lanes.js"));
const PATTERN = [[1, 0, 2, 0], [0, 3, 0, 1], [4, 5, 6, 2], [0, 0, 0, 0], [1, 3, 0, 1], [0, 0, 2, 2]];
const duration_index = new Uint8Array(N);
const gx = new Uint8Array(N), gy = new Uint8Array(N), gz = new Uint8Array(N);
const durations = Float64Array.from([1e-3, 2.5e-3, 4e-3]);
const checkpoints = new Float64Array(Math.ceil(N / 1024));
let t = 0;
for (let i = 0; i < N; i++) {
  const p = PATTERN[i % PATTERN.length];
  gx[i] = p[0]; gy[i] = p[1]; gz[i] = p[2]; duration_index[i] = p[3];
  if (i % 1024 === 0) checkpoints[i / 1024] = t;
  t += durations[p[3]];
}
const f = () => new Float64Array(0), u = () => new Uint32Array(0);
const tables = {
  duration_index, durations, checkpoints, rf: new Uint8Array(N), adc: new Uint8Array(N),
  gx, gy, gz, rf_delay: f(), rf_mag_n: u(), rf_mag_offset_at: u(), rf_mag_at: u(),
  rf_mag_offset: f(), rf_mag: f(), rf_phase_n: u(), rf_phase_offset_at: u(), rf_phase_at: u(),
  rf_phase_offset: f(), rf_phase: f(), adc_delay: f(), adc_length: f(),
  grad_delay: new Float64Array(6), grad_n: new Uint32Array(6).fill(4),
  grad_offset_at: new Uint32Array(6), grad_at: Uint32Array.from([0, 4, 8, 12, 16, 20]),
  grad_offset: Float64Array.from([0, 1e-4, 6e-4, 7e-4]),
  grad_value: Float64Array.from([0, 15, 15, 0, 0, -22, -22, 0, 0, 9, 9, 0,
    0, 5, 5, 0, 0, -8, -8, 0, 0, 12, 12, 0]),
};
const meta = ["rf_mag", "rf_phase", "adc", "gx", "gy", "gz"].map(id => ({
  id, title: id, unit: "", color: id, kind: id === "adc" ? "gate" : "line", domain: [0, 1],
  ticks: [0], tick_labels: ["0"], empty: false, fill: id === "rf_phase" ? null : 0.0,
}));
const seqModel = SeqLanes.decode(1, tables, meta);
const t0 = performance.now();
const g = GLanes.decode(seqModel);
console.log(`N=${N} GLanes.decode ${(performance.now() - t0).toFixed(0)} ms,`,
  `peak ${g.wholeFileMax.toFixed(3)}`);
```

### 9.4 B4

```python
"""B4: the values for an oversampled arbitrary gradient, and the Sequence.read paths."""

import os
import sys
import tempfile
import warnings

import numpy as np
import pypulseq as pp

sys.path.insert(0, "tests")
from synthetic import SYSTEM  # noqa: E402

from pulseq_reports.diagram_data import diagram_tables  # noqa: E402
from pulseq_reports.grad_limits import gradient_limits  # noqa: E402
from pulseq_reports.sampling import GradientSampler  # noqa: E402
from pulseq_reports.seq_index import sequence_index  # noqa: E402
from pulseq_reports.seq_utils import GAMMA  # noqa: E402

warnings.simplefilter("ignore")
dt = SYSTEM.grad_raster_time
step = 0.5 * SYSTEM.max_slew * dt / 2  # 50 % of the real max_slew over half a raster
n = 21
g_os = pp.make_arbitrary_grad(
    "x",
    step * np.arange(1, n + 1),
    first=0.0,
    last=step * (n + 1),
    oversampling=True,
    system=SYSTEM,
)
g_down = pp.make_extended_trapezoid(
    "x", times=[0.0, 20 * dt], amplitudes=[step * (n + 1), 0.0], system=SYSTEM
)
g_trap = pp.make_trapezoid("x", amplitude=0.4 * SYSTEM.max_grad, duration=0.5e-3, system=SYSTEM)
seq = pp.Sequence(SYSTEM)
for g in (g_os, g_down, g_trap):
    seq.add_block(g)
print("added shape_dur:", g_os.shape_dur, "get_block shape_dur:", seq.get_block(1).gx.shape_dur)

# The correct polyline, from the added events (not from get_block).
starts = np.concatenate([[0.0], np.cumsum([seq.block_durations[i] for i in (1, 2, 3)])])
ts, vs = [], []
for g, t0 in zip((g_os, g_down, g_trap), starts):
    if g.type == "trap":
        off = np.cumsum([0.0, g.rise_time, g.flat_time, g.fall_time])
        amp = np.array([0.0, g.amplitude, g.amplitude, 0.0])
    else:
        off = np.concatenate([[0.0], g.tt, [g.shape_dur]])
        amp = np.concatenate([[g.first], g.waveform, [g.last]])
    ts.append(t0 + g.delay + off)
    vs.append(amp)
tt, vv = np.concatenate(ts), np.concatenate(vs)
keep = np.concatenate([[True], tt[1:] > tt[:-1] + 1e-9])
tt, vv = tt[keep], vv[keep]
grid = np.linspace(0, starts[-1], 4001)[1:-1]
truth = np.interp(grid, tt, vv)
peak = np.abs(truth).max()

sampler = GradientSampler(seq, sequence_index(seq))
print(f"sampler error: {np.abs(sampler.sample('gx', grid) - truth).max() / peak:.1%} of peak")
d, a, b = np.diff(tt), vv[:-1], vv[1:]
rms = np.sqrt(np.sum(d * (a * a + a * b + b * b) / 3) / starts[-1]) / GAMMA * 1e3
print(f"Gx RMS: {gradient_limits(seq).axes['x'].rms_mt_per_m:.4f} mT/m, correct {rms:.4f}")
tb = diagram_tables(seq)
print(
    "diagram last offset of event 1:",
    tb["grad_offset"][tb["grad_offset_at"][0] + tb["grad_n"][0] - 1],
)

with tempfile.TemporaryDirectory() as folder:
    path = os.path.join(folder, "os.seq")
    for label, call in [
        ("write()", lambda: seq.write(path)),
        (
            "read()",
            lambda: (seq.write(path, remove_duplicates=False), pp.Sequence(SYSTEM).read(path)),
        ),
    ]:
        try:
            call()
            print(label, "ok")
        except KeyError as error:
            print(label, repr(error))
    r = pp.Sequence(SYSTEM)
    r.read(path, remove_duplicates=False)
    print(
        "read(remove_duplicates=False): shape_dur",
        r.get_block(1).gx.shape_dur,
        f"RMS {gradient_limits(r).axes['x'].rms_mt_per_m:.4f} mT/m",
    )
```

### 9.5 B5

```python
"""B5: the spectrum card note puts scanner_label in the HTML without escaping."""

import sys

sys.path.insert(0, "tests")
from synthetic import spin_echo_sequence  # noqa: E402

from pulseq_reports.cards.spectrum import spectrum_card  # noqa: E402
from pulseq_reports.seq_utils import NamedSequence  # noqa: E402

label = "Coil <A&B>"
body = spectrum_card([NamedSequence("a.seq", spin_echo_sequence())], scanner_label=label).body_html
print("raw label in body:", label in body)
print("escaped label count:", body.count("Coil &lt;A&amp;B&gt;"))
```

### 9.6 B4 in `rf_profiles`

```python
"""B4 in rf_profiles: pp.calc_duration of an oversampled gradient uses the doubled shape_dur."""

import sys
import warnings

import numpy as np
import pypulseq as pp

sys.path.insert(0, "tests")
from synthetic import SYSTEM  # noqa: E402

from pulseq_reports import rf_profiles  # noqa: E402

warnings.simplefilter("ignore")
dt = SYSTEM.grad_raster_time
step = 0.5 * SYSTEM.max_slew * dt / 2
n = 21
k = np.arange(1, n + 1)
wave = step * np.minimum(k, n + 1 - k)  # a triangle that starts and ends at 0
g_os = pp.make_arbitrary_grad("z", wave, first=0.0, last=0.0, oversampling=True, system=SYSTEM)
g_end = g_os.delay + g_os.shape_dur
rf = pp.make_block_pulse(
    np.pi / 2, duration=0.2e-3, delay=g_end + 50e-6, system=SYSTEM, use="excitation"
)
adc = pp.make_adc(10, dwell=10e-6, system=SYSTEM)
seq = pp.Sequence(SYSTEM)
seq.add_block(rf, g_os)
seq.add_block(adc)
b = seq.get_block(1)
print(
    "added end (s):",
    g_end,
    " get_block calc_duration:",
    pp.calc_duration(b.gz),
    " rf start:",
    rf.delay,
)
print("_plays_during:", rf_profiles._plays_during(b.gz, rf.delay, rf.delay + rf.shape_dur))
p = rf_profiles.block_pulse(seq, 0)
print("gradient_kind:", p.gradient_kind, " select_kind:", p.select_kind)
print("key:", p.key)
print("max |mean gradient| during the RF (Hz/m):", float(np.max(np.abs(p.grad_hz_per_m))))
```

Output on `4e17c66`:

```
added end (s): 0.00011  get_block calc_duration: 0.00022  rf start: 0.00016
_plays_during: True
gradient_kind: one  select_kind: z
key: ((1250.0, 1.0, 2.0, 3.0, 9.999999999999999e-05, 0.00016, 0.0, 0.0), 'e', (0, 0, 1))
max |mean gradient| during the RF (Hz/m): 8260.670391284351
```
