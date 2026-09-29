# Plan: the dead code, simplifications, speed-ups and comments of the code review of 2026-09-28

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: ready. The plan was written on 2026-09-29. The user answered the
questions of section 7 on the same day (decisions 12 to 20 of section 2.2).

## 1. Goal

Remove the dead code, make the simplifications and the speed-ups, and correct
the code comments of the review (`docs/reviews/2026-09-28-code-review.md`,
sections 4 to 7). The phases are refactors. The reports and the analysis
results do not change, except the text changes that section 3.5 lists. The
user set the scope on 2026-09-29.

| Kind | Findings in this plan |
|---|---|
| Dead code (review, section 4) | D4, D6 to D21 |
| Simplifications (section 5) | S1, S3 to S6, S8 to S16, S18 |
| Time and memory (section 6) | P1 to P5. P6: a measurement against the budget of decision 14 (task 8.2) |
| Code comments (section 7) | C13 to C20 and C22 to C27, without the parts that #71 and #74 fixed. Each goes into the phase that edits its file. |

The check of section 2.3 found new cases of some findings. They are in this
plan, in the phase that edits their file:

- S14: `tests/test_rf_profile_card.py` copies the builders of
  `tests/test_rf_profiles.py`. S16: `_run_rf_profile` is a fifth runner that
  does not read `pns_lanes`. (The user named both.)
- C22: "interface doc" is also in `tests/js/test_pns_lanes.js` and in
  `TESTS.md` section 2.25.
- C25: "the pre-phase-4 code" in `grad_limits.py` (four places), "as before"
  in `g_lanes.js`, and "Renamed from the prototype's" in `pns_lanes.js`.

A finding that asks for a change of the output or for a new test:

- C13: the comment fix and the new `aria-label` are in (decision 13).
- C14: the docstring fixes are in. The card is to show the fields (decision
  18), but that changes the card's output, so it is a later feature: phase 8
  adds its `TODO.md` item.
- C15: the comment fixes are in. There is no test that ties the Python and
  JavaScript constants (decision 19).

These items are not in this plan:

- D3, S2 and S7: they overlap the API decisions A1, A2 and A8. A later API
  plan does them.
- `_pulse_table` of `cards/rf_profile.py`: its last cell is a button, and
  `html_table` escapes every cell.
- L1, L2 and L3: they change model details. They are not cleanup.
- The A and F findings: API and features, for other plans.
- C3 to C8, C10 and C12: user documentation. C7 goes with the version change
  to `0.2.0rc2`.
- D5, S17 and C11: they no longer apply. #55 deleted `scripts/vb_parity.py`.
- The words of C17 in `docs/plans/diagram-lanes.md`, section 4.1, item 3
  (decision 11).
- A change for P6. The preliminary numbers pass the budget of decision 14.
  If task 8.2 fails it, stop and tell the user.
- Showing the gradient limits locations on the card (C14, decision 18): a
  `TODO.md` item of phase 8.

## 2. Read this first (context for the executing agent)

### 2.1 The state of the repository

- `main` is at `4850c68` (2026-09-29): the bugs B1 to B6 are fixed (#69 to
  #74), and #76 marked them in the review's status. The facts of section 2.3
  were measured on `4850c68`.
- Read `docs/plans/review-bugs.md` (the plan before this one), and section 3
  of `docs/plans/cards-at-scale.md`. Their workflow rules apply here.
- The review's line numbers are for an older state. Use the line numbers of
  section 2.3. After other phases merge, the lines move: search for the text.
- `docs/examples/gre.html` on `main` is the output of
  `examples/gre_report.py` on `4850c68`, byte for byte (checked).
- The pypulseq pin is the fork's tag `pulseq-reports-pin-1` (`a74ab06`).
  `pyproject.toml` requires `pypulseq>=1.5.0.post1`.
- The scripts of section 9 are copies of the session scratchpad scripts of
  2026-09-29 (`cleanup-plan/`). The scratchpad is not permanent.

### 2.2 Decisions that are already made

Do not open these decisions again.

1. **The scope** is the user's (2026-09-29, section 1). Do not add or remove
   a finding. A new case of a finding in a file that a phase owns is in
   scope. Record it in section 8.
2. **Refactors keep the behavior.** Use the method of the
   `dev-workflow:parallel-agents` skill ("Refactors that must not change
   behavior"), with the comparison set of section 3.5. A difference that
   section 3.5 does not list stops the phase.
3. **Block starts in JavaScript are forward sums** (`SeqLanes.blockStart`: a
   group start plus the durations after it). Never subtract a duration from a
   later start (decision 5 of `docs/plans/review-bugs.md`).
4. **No test that only checks that a fixed text is in the output** (the user,
   2026-09-29). D4 renames its test. It does not put the assertion back.
5. **Lean on pypulseq.** Test only the computations of this library.
6. **No DOM tests** (decision 10 of `docs/plans/pulseq-reports.md`). A
   browser check covers a change to a script that the page runs.
7. **The library is sequence-agnostic.**
8. **`docs/examples/gre.html` is rebuilt one time, in phase 8** (as decision
   12 of `docs/plans/review-bugs.md`). The page has a copy of every script, so
   an edit in each phase gives conflicts between parallel phases.
9. **Branch prefixes:** `refactor/` for phases 1 to 7, `chore/` for phase 8.
10. **Git.** The user approves each commit message. Merge only when the user
    tells you to. To bring a branch up to date, merge `origin/main` into it.
    Auto mode refuses `git rebase`.
11. **This plan does not change the text of other plans.** The words of
    C17 in `docs/plans/diagram-lanes.md` stay: that plan records its own
    time. (A completed plan can still get a note, as earlier plans did; this
    plan needs none.)
12. **At most five PRs open at one time** (the user, question 1). Phases 1 to
    5 start together (section 3.3).
13. **C13: the diagram's `aria-label` lists every lane** (question 2):
    "…, Gx, Gy, Gz and |G| against time", and "…, Gx, Gy, Gz, |G| and PNS
    against time" with PNS data (section 4.1, item 14).
14. **P6 budget** (question 3, option B): at 10^5 distinct gradient events,
    the PNS and \|G\| lanes together add at most 400 MB of JavaScript memory
    and at most 3 s before the first chart. The numbers at 10^6 are only
    recorded.
15. **D12: the test-only functions leave `pns_lanes.js`** (question 4): test
    code does not go in the page's JavaScript files.
16. **Order:** the speed-ups and S9 get the most review time (question 5,
    option A).
17. **D18: `BlockTiming` and `iter_blocks` move to `tests/oracles/blocks.py`**
    (question 6, option B). The API plan takes this into account later.
18. **C14: the card is to show `peak_block`, `slew_block` and the peak times**
    (question 7, option B), as a later feature: this plan fixes the
    docstrings, and phase 8 adds the `TODO.md` item of section 5, task 8.3.
19. **C15: no test** ties the Python and JavaScript constants (question 8).
20. **S12: the shared helpers go in `ChartMath`** (question 9).

### 2.3 Facts (2026-09-29)

Each finding was checked on `4850c68` before this plan used it. "Confirmed":
the claim holds. "Partly": a part of the claim holds, and the plan uses only
that part. No claim was wrong. Paths are under `src/pulseq_reports/` unless
they start with `tests/`, `scripts/` or `TESTS.md`. A `.js` name with no
directory is under `src/pulseq_reports/assets/` (`diagram.js` is
`assets/cards/diagram.js`).

| ID | Where on `4850c68` | Result | Evidence |
|---|---|---|---|
| D4 | `tests/test_diagram_card.py:180-190`, `TESTS.md` 3313-3316, 3445-3459 | Confirmed | `_ZOOM_HELP_SENTENCE` has no reader. The test name and `TESTS.md` still say that the test checks the sentence. |
| D6 | `scripts/check:23-29`, `33-39`, `43-48`, `scripts/check_tests_md.py:18-20`, `89`, `94`, `TESTS.md` 138-140, 157-159 | Partly | The three skip branches never run now, and no caller gives `root`. But Node 24 `node --test` with a pattern that matches no file runs 0 tests and exits 0 (checked in an empty directory). Thus the node guard must become an error, not go away (section 4.7). |
| D7 | `assets/seq_lanes.js:183-200` | Confirmed | `_blockRange` has no caller in `src/` or `tests/`, and the module does not export it. |
| D8 | `seq_lanes.js:1088-1090`, `1160` | Confirmed | The `map` callback declares its own `inBin` (1154). The outer one has no reader. `take` reads only `out`, which is the same array for each bin. |
| D9 | `seq_lanes.js:960-982` | Confirmed | `start` (964, 970) is written and never read. |
| D10 | `seq_lanes.js:661`, `667` | Confirmed | The only caller (1167) gives `laneCols`. The two branches of 667 are both `from`. |
| D11 | `pns_lanes.js:763-771` | Confirmed | Only `_plainRecursion` and `sampleRangeFor` have readers (`tests/js/test_pns_lanes.js`). With D12, the moved code needs `eventEntry` (section 4.3). |
| D12 | `pns_lanes.js:184-274` | Confirmed | Only `_plainRecursion` calls `_runBlockSamples`, and only the test calls `_plainRecursion`. The two functions are 3,881 bytes of the 519,891 bytes of the example page (0.75 %). |
| D13 | `pns_lanes.js:144`, `475` | Confirmed | The only caller of `_powPair` (`_applyBlockMap`, 176) returns first for `n === 0` (157). `numBlocks === 0` gives `numSamples === 0`, so `count <= 0` is already true. |
| D14 | `grad_spectrum.py:105`, `112-115`, `121`, `130` | Confirmed | After the `NO_GRADIENTS` return, `nt >= 1`, so `n = nt + 2 * (nwin // 2) >= nwin` for an odd or an even `nwin`. Each chunk then has `nwin` samples or more, so each chunk gives the same frequencies. |
| D15 | `pns_levels.py:78`, `94-97`, `158`, `171-177`, `179`, `183`, `199-200`, `207` | Confirmed | After `_has_gradients`, a block with a gradient lasts one raster time or more, so `num_samples >= 1`, and each chunk has one sample or more. `ceil(0 / b)` is 0 anyway. Only `tests/test_pns_levels.py` gives `chunk_samples`. |
| D16 | `sampling.py:236-239`, `251-253`, `pns_lanes.js:86` | Confirmed (both) | `searchsorted(side="right") - 1` and the JavaScript `while (... <= t) p++` both stop with `t0 <= t < t1`, so `t1 > t0`. Instrumented runs: `step` was true 0 times in 948 evaluations (14 sequences, 42 `block_samples` calls). The 19 tests of `test_pns_lanes.js` pass with the JavaScript branch made to throw. Also, `event_samples(k, 0)` runs before the `continue`. |
| D17 | `rf_exposure.py:94` | Confirmed | With no RF block, the expression gives a float64 array of shape (0,), as `np.empty(0)` does (checked). |
| D18 | `seq_utils.py:15-33`, `waveforms.py:52`, `134` | Confirmed | No library caller. The readers are `tests/oracles/grad_limits.py`, `tests/oracles/rf_exposure.py`, `tests/test_seq_utils.py`, `tests/test_waveforms.py` and `TESTS.md` 190, 209, 3244. The names are public (decision 17). |
| D19 | `seq_utils.py:65` | Confirmed | pypulseq 1.5.0.post1 or later: `get_block` (`block.py:445-447`), `make_arbitrary_grad` and `make_extended_trapezoid` always set `first`, `last` and `shape_dur`. |
| D20 | `tests/synthetic.py:43-47`, `57`, `64` | Confirmed | No caller gives either parameter. `(sign * 1.0) * x` and `3.0 / w` equal `sign * x` and `3 / w` exactly, so the sequences do not change. |
| D21 | `waveforms.py:240-242`, `305-309` | Confirmed | `_lanes` has one caller, `file_lanes`. |
| S1 | `cards/timing.py:21-76` | Confirmed | `_error_table_html(errors) == html_table(headers, rows)` for 4 error sets (a real check failure, a message, floats and extra keys, `<` and `&`). |
| S3 | `diagram_data.py:217-299`, `waveforms.py:189-237` | Confirmed | `lane_meta` writes the titles, units, colors, domains and ticks of `_value_lane`, `_phase_lane` and `_adc_lane` a second time. Its key order is that of `lanes_json` without `segments` and `windows`. |
| S4 | `diagram_data.py:194-199` | Confirmed | Python's `round` is correctly rounded, so it is monotonic and odd. Thus `max(abs(round(v, d)))` equals `round(max(abs(v)), d)`. 0 differences in 20,000 random arrays, with exact binary ties and near ties. |
| S5 | `assets/cards/diagram.js:172-185`, `269`, `350-363` | Confirmed | `laneChart` calls `render()` before it returns (`lane_chart.js:484`). With `lanesFor` and `groups`, `render` replaces `lanes` and sets the height (152-154). `setWindow` does the same (510-511). |
| S6 | `rf_exposure.py:211`, `217` | Confirmed | The same `_before(self.first[pulses] + length)` call, two times. |
| S8 | `grad_limits.py:319-321`, `538-545` | Confirmed | For 88 ranges with no event (12 sequences, windows in delay blocks, a sequence with no block), `_range_result` gives the zero result, with and without its `n == 0` return. The plan keeps that return (section 4.1). |
| S9 | `seq_lanes.js:465-489`, `960-982`, clamps at `469`, `600`, `607`, `963`, `972` | Confirmed | For `N > 0`, `_blockAtStart` always gives an index in `[0, N - 1]`, and its start equals `blockStart(model, i)`: the same group start and the same forward sum. |
| S10 | `pns_lanes.js:731-752`, `diagram.js:66-73`, `290-292` | Confirmed | The only caller (`diagram.js:71`) calls `statusText` only with a result. |
| S11 | `g_lanes.js:261`, `337`, `373`, `406`, `451` | Confirmed | Also, the `decode` comment (429-431) says that the peak is the root of the tree, but the code calls `_rangeGMinMax` over the whole file. |
| S12 | `g_lanes.js:61-111`, `520-535`, `544-546`, `pns_lanes.js:603-618`, `727-729`, `seq_lanes.js:239-265`, `753-769` | Partly | `_segTree` is a copy. The zigzag loop of `GLanes.lanesFor` is `_zigzag` of `pns_lanes.js` (which scales the values by 100). `_fmt` equals `_fmtBinMs`. But the bounds of `seq_lanes.js` have other arguments (`oAt`, `base`), and `ChartMath.fmt` is not `_fmt`: it gives "0" below 5e-4 and a U+2212 minus sign. |
| S13 | `seq_lanes.js:125-129`, `178` | Confirmed | Used 50 lines before its definition. No error: `decode` runs after the module body. |
| S14 | `tests/test_seq_index.py:36-43`, `tests/test_grad_spectrum.py:199-206`, `scripts/cards_scale.py:124`, `tests/test_pns_levels.py:33-52`, `tests/test_pns_lanes_golden.py:75-96`, `tests/test_rf_profile_card.py:36-129` | Confirmed | The copies are the same code. The RF card test copies 9 builders of `tests/test_rf_profiles.py:25-133` (its `_readout` gives 2 values, not 3). The copy in `scripts/cards_scale.py` stays: a script does not import from `tests/`. |
| S15 | `tests/test_pns_lanes_golden.py:184-200` | Confirmed | The payload equals `_pns_entry` of `cards/diagram.py` (40-60) field by field. |
| S16 | `scripts/cards_scale.py:121`, `173-199`, `295-299` | Confirmed | Five runners do not read `pns_lanes`, `_run_rf_profile` included. |
| S18 | `rf_exposure.py:147`, `152` | Confirmed | `_windowed_energy` returns first for `duration <= 0` (257), and the card returns first for `total_duration <= 0` (`cards/rf_exposure.py:131`). Thus `period` is None or above 0 at each call. |
| P1 | `waveforms.py:312-324` | Confirmed | The index form of section 4.2 gave the same `TimeWindow` for 12 sequences, 2 of them read from a `.seq` file. It needs `float(index.start_s[p])`: `round` of a numpy.float64 uses the rounding of numpy. At 2 × 10^5 blocks with no ADC: 1.41 s, and 200,000 blocks in pypulseq's block cache. |
| P2 | `waveforms.py:133-138`, `cards/diagram.py:104` | Confirmed | `duration_s`, `index.end_s` and `seq.duration()[0]` have the same bits for the 12 sequences. After `Sequence.read`, the durations are numpy.float64, so `duration_s` gave a numpy.float64, and `round(x * 1e3, 4)` used numpy's rounding. Python's `round` gave the same value for 143,000 sums of durations on a 1 µs raster. |
| P3 | `pns.py:157` | Confirmed | The same bits (P2). 0.21 s at 2 × 10^5 blocks. One difference: for a sequence with no block and a peak time that the caller gives, `seq.duration()` raises `StopIteration`, and the new form returns None. |
| P4 | `waveforms.py:162-167` | Confirmed | The early exit gave the same rows and totals in 174 cases: the whole file, ranges, instants at block starts, and `max_rows`. |
| P5 | `seq_lanes.js:203-214` | Confirmed | `SeqLanes.decode` of 2 × 10^6 blocks, Node, a fresh process each: 224, 225 and 229 ms before, 157, 160 and 162 ms with `_blockPoints` unrolled. The point counts are equal. |
| P6 | `pns_lanes.js:118-134`, `g_lanes.js:235-307` | Measured | Preliminary numbers: the table below. |
| C13 | `cards/diagram.py:174-178`, `196-197` | Confirmed | The label leaves out \|G\| (drawn unless `GLanes.decode` fails) and PNS. No test pins the string. |
| C14 | `grad_limits.py:54-59`, `74-78`, `250-252`, `297-301` | Confirmed | A window in a delay gives `reason` set and a whole-file RMS of 9.62 mT/m on x. The tie: two equal trapezoids, and a window from 0.05 ms to 1.9 ms that cuts block 1. The code gives `peak_block` 2, the oracle gives 1. No card reads `peak_block`, `slew_block`, `peak_time_s` or `vector_peak_time_s`. |
| C15 | `pns_levels.py:34-38`, `118-119` | Confirmed | 960 − 128 − 20 = 812 (`lane_chart.js:13-14`). `gradient_limits`, `gradient_spectrum` and `rf_exposure` leave `refuse_rotations` to their cards. The functions of `rf_profiles.py` call it themselves. |
| C16 | `grad_spectrum.py:98` | Confirmed | Python 3.12's `sum` is compensated. With `build_repeating`, `sum(...)` differs from `index.end_s` at 10^4 and 10^5 blocks, and `ceil(... / dt)` differs by one sample at 10^4 blocks. |
| C17 | `sampling.py:146-149` | Confirmed | `add_block` accepts a junction step up to `max_slew * grad_raster_time` (the repro of B1 used 0.9 of it). |
| C18 | `waveforms.py:38` | Confirmed | The times are in s, not in ms. |
| C19 | `diagram_data.py:72-75`, `132`, `136`, `seq_index.py:5-6` | Confirmed | `index.rf` already has the dtype `_index_dtype(index.rf_first.size)` (`seq_index.py:105`). `index.adc` too. |
| C20 | `assets/chart_math.js:1`, `4-9`, `11`, `21`, `45-46` | Confirmed | Node: `2 * centre - start !== end` in 998,010 of 1,624,000 bins (61 %). |
| C22 | `pns_lanes.js:9`, `19-20`, `50`, `62`, `225-226`, `332-335`, `454`, `466`, `621`, `tests/js/test_pns_lanes.js:12`, `16`, `323`, `397`, `TESTS.md` 5646-5647, 5736, 5760, 5774, 5836, 5920 | Confirmed | The tag `archive/pns-lanes-prototype` has `prototypes/pns_lanes/README.md`. No heading of it is "Per-event data". Section 3.5, item 1 of `docs/plans/diagram-lanes.md` is the rule "level against exact view". Section 4.3, item 3 is `EXACT_MAX_S`. |
| C23 | `g_lanes.js:15`, `26-28`, `30-33`, `41-43`, `49-51`, `158-167`, `548-559` | Confirmed | pypulseq's `add_block` refuses a gradient that does not end at 0 before its block end (`block.py:294`). Thus the ramp to 0 after the last point does not occur in a file that pypulseq writes. |
| C24 | `seq_lanes.js:90-97` | Confirmed | `_eventStats` gives `nArr` back unchanged. `decode` makes `groupStart` and `groups`. `pyramids` starts empty. |
| C25 | `lane_chart.js:4`, `59`, `67`, `86`, `251`, `527`, `diagram.js:4`, `59`, `76` | Confirmed | New cases: `grad_limits.py:298-299`, `337`, `379`, `438`, `g_lanes.js:167`, `pns_lanes.js:223`. |
| C26 | `TESTS.md` 3968-3971, 4003-4005, 5656, 5682, 5697, 5815, 5905, `tests/js/test_g_lanes.js:612`, `tests/js/test_pns_lanes.js:259`, `541`, `735`, `829`, `884`, `tests/js/test_seq_lanes.js:84-85`, `633`, `811`, `tests/test_diagram_card.py:316`, `tests/test_rf_exposure.py:186-187` | Confirmed | #71 fixed `g_lanes.js:248`. The rest remain. |
| C27 | `tests/js/test_g_lanes.js:39-45`, `tests/test_rf_exposure_card.py:130-132`, `235`, `scripts/diagram_scale.py:27`, `tests/js/test_seq_lanes.js:382`, `1055`, `1063` (`TESTS.md` 3962, 4442), `tests/test_diagram_data.py:4-6` (`TESTS.md` 3747) | Confirmed | `_assert_combined_data_matches_oracle` compares with `==`. `diagram_scale.py` writes the note to stderr (286-290). |

**P6, preliminary** (Node 24, `main`, section 9.8). Each block lasts 1 ms and
has its own gx event of 4 points. The numbers are the growth of the heap and
the array buffers after garbage collection, and the time of each `decode`.

| Distinct gradient events | `SeqLanes.decode` | `GLanes.decode` | `PnsLanes.decode` |
|---|---|---|---|
| 10^5 | +2 MB, 21 ms | +186 MB, 260 ms | +116 MB, 194 ms |
| 3 × 10^5 | +6 MB, 47 ms | +567 MB, 836 ms | +349 MB, 726 ms |
| 10^6 | +21 MB, 138 ms | +1,850 MB, 2,723 ms | +1,147 MB, 4,492 ms |

**Baselines on `main`** for the measurements of section 2.4:

- `time_js.js` (section 9.7), 10^7 repeating blocks, two runs:
  `SeqLanes.decode` 1085 ms, `GLanes.decode` 220 and 221 ms, the 95th
  percentile of `SeqLanes.lanesFor` 3.8 and 4.1 ms, of `GLanes.minMax` 1.8 ms.
- `time_py.py` (section 9.6), 2 × 10^5 blocks with no ADC:
  `first_adc_window` 1.412 s, `full_window` 0.022 s, `peak_tr_window`
  0.210 s, `block_rows` of the first 10 ms 0.034 s, 200,000 blocks in the
  block cache, peak RSS 338 MB.
- The comparison scripts of section 9 give the same bytes in two runs on
  `main`: `dump_py.py` (288 entries, 16 s) and `dump_js.js` (22,995 entries,
  20 s).
- The S9 check (section 9.5) prints OK on `main`. It prints FAIL for a copy of
  `seq_lanes.js` whose backward walk uses `start - prevDur`: 12 to 192 bad
  starts in each file. The JavaScript dump does not find that change. Thus
  phase 4 needs the S9 check.

### 2.4 Budgets

Run each measurement in a fresh process, on the baseline and on the branch.
Put both results in the PR.

| Phase | Measurement | Budget |
|---|---|---|
| 2 | `scripts/cards_scale.py --card diagram --case repeating --blocks 10000000` | The diagram card makes its data in 120 s or less (`docs/plans/diagram-event-table.md`, section 2.6). About 10 s on `main` (`docs/plans/cards-at-scale.md`, section 8.4). |
| 2 | `scripts/cards_scale.py --card diagram --case repeating --blocks 40000 --tr-s 0.04707` (the 370 s file) | Record the values. |
| 2 | `scripts/diagram_scale.py --case worst --blocks 100000`: `lane_meta_s` (S4) | Record the values (the worst case of `docs/plans/diagram-event-table.md`, section 2.6). |
| 2 | `time_py.py 200000` (section 9.6) | Record the values. |
| 4 | `time_js.js <assets> 10000000` (section 9.7): `SeqLanes.decode`, `lanesFor` | The first chart in 5 s or less at 10^7 blocks. One render, 95th percentile, 50 ms or less (`docs/plans/diagram-event-table.md`, section 2.6). |
| 5, 6 | `time_js.js`: `GLanes.decode`, `GLanes.minMax` | The PNS and \|G\| lanes add 3 s or less before the first chart at 10^7 blocks (`docs/plans/diagram-lanes.md`, section 2.4). |
| 8 | Task 8.2 (P6) | Decision 14: at 10^5 distinct gradient events, the PNS and \|G\| lanes together add at most 400 MB and 3 s. Record 10^6. |

Use `scripts/cards_scale.py` for the time of the diagram card, not
`scripts/diagram_scale.py`. `diagram_scale.py` makes the windows before it
starts the clock. After P1 and P2, the windows build the sequence index, so
its `card_s` gets smaller for a reason that is not a speed-up.

If a budget fails, stop and tell the user. Do not change a budget.

### 2.5 Terms

- **The review.** `docs/reviews/2026-09-28-code-review.md`.
- **Baseline.** The worktree `.worktrees/base` at the commit that the task
  branch last took from `main` (section 3.5, item 1).
- **Comparison set.** The outputs of section 3.5, item 2.
- **Expected difference.** A difference that section 3.5, item 3 lists for
  the phase.
- **Forward sum.** A block start computed as the sum of the durations before
  the block, in play order, from 0 or from a group start. `SeqLanes.blockStart`
  gives it.
- **Backward walk.** The loop of `_forEachBlockInRange` and `_blockSpan`
  (`seq_lanes.js`) that goes from the block of `lo` to the earlier blocks that
  also touch `lo`.
- **Distinct gradient event.** A row of `seq.grad_library` that at least one
  block uses.
- **Comment-only edit.** An edit that changes only comments or docstrings.

## 3. How to execute this plan

### 3.1 Workflow

As in `docs/plans/review-bugs.md`, section 3.1, items 1, 2, 4, 6 and 7. Also:

1. The executing agent makes the baseline one time, before phase 1 (section
   3.5, item 1).
2. Before each PR, the executing agent runs the comparison set and the
   measurements of the phase. Put the results in the PR description: the `cmp`
   results, the output of `page_diff.py`, and the numbers.
3. A phase that edits a test says why in its PR. The golden and oracle tests
   do not change, except where section 4 says so.
4. Each phase ends with a line-by-line review of each worker's diff by the
   executing agent.

### 3.2 Worker model tiers

| Tier | Who | Use it when |
|---|---|---|
| H | a `haiku` worker | The task is a removal, a move or a comment with the exact text or code of section 4. |
| S | a `sonnet` worker | The task writes code or comments from section 4, with local decisions only. |
| O | an `opus` worker | The task changes code whose float results must stay bit-identical and that no output comparison fully covers (S9). |
| X | the executing agent, not a worker | The baseline, the comparisons, the measurements, the browser checks, and the review of every diff. |

Rules 1, 3, 4 and 5 of `docs/plans/cards-at-scale.md`, section 3.2, apply to
the workers. Also:

1. Give each worker its design section (section 4), its files (section 3.4),
   its `TESTS.md` sections, and decisions 2 to 7 of section 2.2.
2. Workers do no git writes, and they do not sync dependencies.
3. A worker that finds that a change alters an output stops and reports. It
   does not look for a different change.

### 3.3 Order and parallel work

```
Wave 1:  Phase 1 (analyses, cards)  Phase 2 (Python core, P1-P4)  Phase 3 (PNS lane)
         Phase 4 (seq_lanes.js, S9)  Phase 5 (|G| lane, comments)
Wave 2:  Phase 7 (tests, scripts), after phase 1
Wave 3:  Phase 6 (shared JavaScript helpers), after phases 3, 4 and 5
Wave 4:  Phase 8 (results and the P6 measurement), after phases 1 to 7
```

- Phases 1 to 5 share no file, except their own `TESTS.md` sections. They can
  run at the same time.
- Phase 7 starts after phase 1 is merged: both edit `tests/test_pns_levels.py`
  and `TESTS.md` section 2.24.
- Phase 6 starts after phases 3, 4 and 5 are merged: it edits their files.
- Phase 8 starts after phases 1 to 7 are merged.
- At most five PRs are open at one time, with the PRs of other plans
  (decision 12). Wave 1 is phases 1 to 5. Phase 7 starts when phase 1 is
  merged.
- Phases 2 and 4 come first: they carry the speed-ups and the riskiest change
  (S9), so they get the longest review (decision 16).

### 3.4 File ownership

Package root: `src/pulseq_reports/`.

| Phase | Branch | Files that the phase edits |
|---|---|---|
| 1 | `refactor/analyses-cleanup` | `grad_spectrum.py`, `rf_exposure.py`, `grad_limits.py`, `pns_levels.py`, `cards/timing.py`, `cards/diagram.py`, `tests/test_pns_levels.py`, `TESTS.md` section 2.24 |
| 2 | `refactor/core-speed` | `seq_utils.py`, `waveforms.py`, `diagram_data.py`, `seq_index.py`, `pns.py`, and for D18 (decision 17) `tests/oracles/grad_limits.py`, `tests/oracles/rf_exposure.py`, `tests/oracles/blocks.py` (new), `tests/test_seq_utils.py`, `tests/test_waveforms.py`, `TESTS.md` sections 2.1 and 2.15 |
| 3 | `refactor/pns-lane-cleanup` | `sampling.py`, `assets/pns_lanes.js`, `assets/cards/diagram.js`, `tests/js/test_pns_lanes.js`, `TESTS.md` section 2.25 |
| 4 | `refactor/seq-lanes-cleanup` | `assets/seq_lanes.js`, `tests/js/test_seq_lanes.js`, `TESTS.md` section 2.19 |
| 5 | `refactor/g-lanes-cleanup` | `assets/g_lanes.js`, `assets/chart_math.js`, `assets/lane_chart.js`, `tests/js/test_g_lanes.js` |
| 6 | `refactor/js-shared-helpers` | `assets/chart_math.js`, `assets/seq_lanes.js`, `assets/g_lanes.js`, `assets/pns_lanes.js` |
| 7 | `refactor/tests-scripts-cleanup` | `scripts/check`, `scripts/check_tests_md.py`, `scripts/cards_scale.py`, `scripts/diagram_scale.py`, `tests/synthetic.py`, `tests/rf_sequences.py` (new), `tests/test_diagram_card.py`, `tests/test_seq_index.py`, `tests/test_grad_spectrum.py`, `tests/test_pns_levels.py` (the border sequence only), `tests/test_pns_lanes_golden.py`, `tests/test_rf_profiles.py`, `tests/test_rf_profile_card.py`, `tests/test_rf_exposure.py`, `tests/test_rf_exposure_card.py`, `tests/test_diagram_data.py`, `TESTS.md` section 1 and sections 2.9, 2.16, 2.18, 2.22, 2.24, 2.26, 2.31, 2.34 |
| 8 | `chore/review-cleanup-results` | `docs/examples/gre.html`, the status of the review, this plan (status and section 8), `TODO.md` (the item of decision 18, and an item for P6 only if the user asks for one) |

Rules:

1. As in `docs/plans/cards-at-scale.md`, section 3.4, rules 1 to 3.
2. `TESTS.md`: each phase edits only its own sections. An unchanged heading
   separates each pair of sections, so git merges the edits of parallel
   phases. If a conflict in `TESTS.md` occurs, keep both sides.
3. A comment-only edit of a test file needs no `TESTS.md` change, unless
   `TESTS.md` has the same words. Then correct them in the same phase.
4. Only phase 8 edits `docs/examples/gre.html` (decision 8).

### 3.5 Behavior preservation

1. **The baseline.** The executing agent makes it one time:
   `git -C /Users/dylan/dev/pulseq-reports worktree add --detach .worktrees/base origin/main`,
   then `nix develop --command uv sync --frozen` in it. Before each comparison,
   run `git -C /Users/dylan/dev/pulseq-reports fetch`, then check out in the
   baseline the commit that the task branch last took from `main`:
   `git -C <main checkout>/.worktrees/base checkout --detach $(git -C <task worktree> merge-base HEAD origin/main)`.
   Sync again only when `uv.lock` changed. After phase 8, remove the baseline
   (`git -C <main checkout> worktree remove .worktrees/base`).
2. **The comparison set.** Run the same command, with the same input, in the
   baseline and in the task worktree. Write the outputs to two directories of
   the session scratchpad. Compare them with `cmp`.
   1. The example page:
      `nix develop --command uv run python examples/gre_report.py <dir>/gre.html`.
      For a phase that changes a page script, also run `page_diff.py`
      (section 9.4) with the names of the changed assets. The rest of the
      page must be equal.
   2. The Python dump: `nix develop --command uv run python <scratch>/dump_py.py <dir>/py.json`
      (section 9.1). It holds every card of the ten files of section 9.1 and
      of a page of four files, and the analysis results: gradient limits, RF
      exposure, the spectrum, the PNS levels, the index, the diagram tables,
      `lane_meta`, `file_lanes`, `block_rows`, the windows, and the sampler.
   3. The JavaScript dump, for phases 3 to 6: run `make_js_input.py`
      (section 9.2) one time in the baseline. Then run
      `nix develop --command node <scratch>/dump_js.js <assets> <scratch>/js_in.json <dir>/js.json`
      (section 9.3) with the `src/pulseq_reports/assets` directory of each
      worktree.
   4. `nix develop --command scripts/check` passes on the branch.
3. **Expected differences.** Any other difference stops the phase.

   | Phase | Example page | Python dump | JavaScript dump |
   |---|---|---|---|
   | 1 | Only the `aria-label` of the diagram (C13, decision 13) | Only the diagram card entries (`*/card/diagram`, `many/diagram`). A diff of one diagram `body_html` shows only the `aria-label`. | Not run |
   | 2 | None | None | Not run |
   | 3 | Only `pns_lanes.js` and `cards/diagram.js` | None | None |
   | 4 | Only `seq_lanes.js` | None | None |
   | 5 | Only `g_lanes.js`, `chart_math.js` and `lane_chart.js` | None | None |
   | 6 | Only `chart_math.js`, `seq_lanes.js`, `g_lanes.js` and `pns_lanes.js` | None | None |
   | 7 | None | None (D20 changes `tests/synthetic.py`, which the dump reads) | Not run |
   | 8 | The sum of the page changes of phases 1, 3, 4, 5 and 6 | Not run | Not run |

   The JavaScript dump keeps only `lane`, `exact`, `binMs` and `gap` of a
   `PnsLanes.lanesFor` result, and it calls `statusText` in the old or in the
   new form (S10). Thus S10 gives no difference there.
4. **The S9 check** (phase 4, section 9.5). It loads a copy of
   `seq_lanes.js` with a check line at three places, and checks that each
   block start that the module hands on equals the forward sum from 0. Run it:
   - on the baseline `seq_lanes.js`: it must print OK,
   - on the branch `seq_lanes.js`: it must print OK,
   - on a scratch copy of the branch file with `start - prevDur` in place of
     `blockStart(model, i - 1)` in `_firstOverlapping`: it must print FAIL.
     This shows that the check still sees the new code.

   If an anchor of the script is not in the new code, the script stops.
   Then change the anchor to the new line, and say so in the PR.

## 4. Design

### 4.1 Phase 1: Python analyses and cards

**`grad_spectrum.py`.**

1. D14. Remove the two `n < nwin` branches and the comment "For a waveform
   shorter than one window, ...". Compute the frequency mask one time:

   ```python
   n = nt + 2 * pad  # n >= nwin: after the NO_GRADIENTS return, nt >= 1
   hop = nwin - nwin // 2
   num_windows = (n - nwin) // hop + 1
   keep = None  # the frequencies to keep: the same for each chunk
   for first in range(0, num_windows, CHUNK_WINDOWS):
       last = min(first + CHUNK_WINDOWS, num_windows)
       start = first * hop
       stop = (last - 1) * hop + nwin
       ...
       for axis in "xyz":
           freq, sxx = _chunk_spectrogram(...)
           if keep is None:
               keep = freq <= MAX_FREQUENCY_HZ + 1e-6
           sxx = sxx[keep]
   freq = freq[keep]
   ```

   Each chunk has `nwin` samples or more, so `spectrogram` gives the same
   frequencies for each chunk (the same `nperseg`, `nfft` and `fs`).
2. C16. Put this comment above line 98. Do not change the line:

   ```
   # Python's `sum` is compensated (Python 3.12), so this total can differ from
   # `index.end_s`, the sequential sum, by one sample. The oracle
   # (tests/oracles/grad_spectrum.py) has the same line, and the oracle tests
   # compare the two. Do not change it to `index.end_s`.
   ```

**`rf_exposure.py`.**

3. D17. `base=index.start_s[blocks] + delay[event],`.
4. S6. Line 211 becomes `lo, end_energy = self._before(self.first[pulses] + length)`.
   Remove the second call at line 217.
5. S18. Line 152 tests `if period is not None`.

**`grad_limits.py`.**

6. S8. `gradient_limits` makes one `GradientLimits` at its end. `reason` is
   None when `has_event` is true, else "no gradient events in the window" or
   "no gradient events in the sequence". `axes` and the two vector fields come
   from `_range_result` as they are. Remove `zero_axes`. Keep the `n == 0`
   return of `_range_result`: without it, the junction code works on empty
   arrays only through a numpy broadcast (`[0.0] - []`).
7. C14. Four docstring fixes:
   - `GradientLimits`: "every numeric field is its zero value" gets "except
     `whole_rms_mt_per_m`, which is the RMS of the whole file when `window` is
     given".
   - `_range_result`: "(at most two, plus a block of zero duration at an
     edge)" becomes "(at most two: a block of zero duration at a range edge is
     skipped)". "makes every block fully inside" becomes "makes every block of
     non-zero duration fully inside (a block of zero duration at 0 or at the
     end is skipped, and it has no gradient)".
   - `_range_result`: add "On an exact tie between a block of the slice and a
     block that the range start cuts, the block of the slice gets the credit,
     not the earlier block. The oracle credits the earlier block (finding L3
     of the review)."
   - `AxisResult`: add "The gradient limits card does not show
     `peak_block`, `slew_block`, `peak_time_s` or
     `GradientLimits.vector_peak_time_s` yet." (Decision 18.)
8. C25, new case. "the implementation before phase 4 of
   `docs/plans/cards-at-scale.md`" (298-299) and "the pre-phase-4 code" (337,
   379, 438) become "the oracle (`tests/oracles/grad_limits.py`)".

**`pns_levels.py`.**

9. D15. Remove the keyword `chunk_samples`, its `ValueError`, and its words
   in the docstring (item 2). The chunk is always
   `bin_samples * math.ceil(CHUNK_SAMPLES / bin_samples)`. Remove the guards
   `if cumulative.size else 0`, `if num_samples else 0` (two),
   `if axis_frac.size else axis_peak`, `if total.size else 0.0` and
   `if chunk_records:`. Add one comment line at the first of them: "After
   `_has_gradients`, `num_samples >= 1`, and each chunk has one sample or
   more."
10. D15, the tests (`tests/test_pns_levels.py`, `TESTS.md` section 2.24):
    - `test_result_does_not_depend_on_chunk_samples` keeps its name (the golden
      test and `TESTS.md` section 2.26 name it). It sets `CHUNK_SAMPLES` with
      `monkeypatch.setattr` of the module `pulseq_reports.pns_levels` to `1`,
      `bin_samples + 1`, `7 * bin_samples - 1` and
      `bin_samples * (num_samples // bin_samples + 10)`. These give chunks of
      1, 2, 7 and more than all the bins, as before, and they also check that
      a size between two whole numbers of bins goes up. The results must equal
      the reference exactly, as before.
    - Remove `test_chunk_samples_must_be_a_whole_number_of_bins`: the check
      that it tests goes away with the keyword.
    - Remove
      `test_default_chunk_samples_is_the_nearest_whole_number_of_bins_at_or_above_the_fork_size`:
      after D15 the default is the only chunk size, and the result does not
      show it. The test above covers the round-up.
11. C15. "as the other gradient cards do" becomes "as the gradient cards and
    the functions of `rf_profiles.py` do". The comment of `DISPLAY_BINS`
    becomes "The number of display bins of the diagram chart: `PLOT_W` of
    `assets/lane_chart.js` (960 − 128 − 20). Keep the two equal." The comment
    of `EXACT_MAX_S` gets "Keep the two equal." No test (decision 19).

**`cards/timing.py`.**

12. S1. One function for both forms:

    ```python
    _HEADERS = ["Block", "Event", "Field", "Error", "Value (s)", "Limits (s)"]
    _MAIN_KEYS = ("block", "event", "field", "error_type", "value", "message")


    def _timing_html(errors: list[dict], name: str | None = None) -> str:
        """The timing check body of one sequence: a status paragraph, and an error table
        when there are errors. With `name`, the status line starts with the file name
        (HTML-escaped). Without it, the output is the same as vb-pulseq `_timing_html`."""
        prefix = "" if name is None else f"{html.escape(name)}: "
        if not errors:
            return (
                f'<p class="status good"><span aria-hidden="true">✓</span> {prefix}'
                "Timing check passed: pypulseq reported no errors.</p>"
            )
        head = (
            f'<p class="status bad"><span aria-hidden="true">✕</span> {prefix}'
            f"Timing check failed: {len(errors)} error{'s' if len(errors) != 1 else ''}.</p>"
        )
        return head + html_table(_HEADERS, [_error_row(e) for e in errors])
    ```

    `_error_row(e)` gives the six cells of the old loop, unchanged. Remove
    `_error_table_html` and `_status_line`. `timing_card` calls
    `_timing_html(timing_errors(named.seq), named.name)` for more than one
    file. `tests/test_timing_card.py` calls `_timing_html(errors)` and does not
    change.

**`cards/diagram.py`.**

13. C13, the comment. Remove the comment at lines 174-178. The docstring
    already says it.
14. C13, the label (decision 13). The `aria-label` becomes
    "Sequence diagram: RF magnitude and phase, ADC, Gx, Gy, Gz and |G| against
    time", or with PNS data "Sequence diagram: RF magnitude and phase, ADC, Gx,
    Gy, Gz, |G| and PNS against time".

### 4.2 Phase 2: Python core and speed

**`waveforms.py` and `diagram_data.py`: D21 and S3.** The lane builders take
their peak and their "has events" value from the caller, so that `file_lanes`
and `lane_meta` build their lanes with the same functions:

```python
def _value_lane(lane_id, title, unit, color, segments, peak, symmetric, has_events, fill=0.0):
    """One line lane. `peak` is the largest absolute value of its rounded points."""
    domain, ticks, labels = _value_domain(peak, symmetric)
    return Lane(
        id=lane_id,
        title=title,
        unit=unit,
        color=color,
        segments=segments,
        domain=domain,
        ticks=ticks,
        tick_labels=labels,
        empty=not has_events,
        fill=fill,
    )


def _lanes(segments: dict, windows: list, peaks: dict, has_events: dict) -> list:
    """The six lanes in their page order. `segments` has the segments of "rf_mag",
    "rf_phase", "gx", "gy" and "gz". `windows` has the ADC windows. `peaks` has the peak
    of "rf_mag", "gx", "gy" and "gz". `has_events` has one bool for each of the six ids."""
```

1. `_phase_lane(segments, has_events)` and `_adc_lane(windows, has_events)` get
   the same kind of argument. The ADC lane's `empty` is `not has_events`.
2. `file_lanes` joins the parts itself (D21: no `joined` callback). It gives
   `has_events` from its lists, as now (`bool(rf_mag)`, `bool(rf_phase)`,
   `bool(adc_windows)`, `bool(grads[axis])`). It gives each peak as
   `max((abs(v) for seg in segments for _, v in seg), default=0.0)` of the
   joined segments, as `_value_lane` does now.
3. `lane_meta` calls `waveforms._lanes` with empty segments and windows, its
   own peaks and `has_events`, and drops the `segments` and `windows` keys of
   `lanes_json(...)`. The key order is then the old order (section 2.3, S3).
4. The Python dump compares `lane_meta` and `file_lanes` of each file, and the
   diagram card data, byte for byte.

**`diagram_data.py`: S4 and C19.**

```python
def _rounded_peak(values: np.ndarray, digits: int = 4) -> float:
    """The largest absolute value of `values`, rounded as `markup._points` rounds a lane
    value (`round(float(v), digits)`). Python's `round` is monotonic and odd, so this
    equals the largest absolute value of the rounded values."""
    if values.size == 0:
        return 0.0
    return round(float(np.max(np.abs(values))), digits)
```

5. C19. Remove "(as the per-block dict of the former loop matched them)"
   (72-75). Lines 132 and 136 become `index.rf.copy()` and `index.adc.copy()`
   (the index already has the smallest dtype), with the comment of line 85
   ("A copy, not a view: the index is kept for the sequence").

**`waveforms.py`: P1, P2, P4 and C18.**

```python
def duration_s(seq: pp.Sequence) -> float:
    """The end of the last block (s): the sum of the block durations in play order
    (`seq_index.SequenceIndex.end_s`)."""
    return sequence_index(seq).end_s


def first_adc_window(seqs: Sequence[NamedSequence], file_index: int = 0) -> TimeWindow:
    """vb-pulseq's "First ADC" view of one file: from 0 to 1.1 times the end of the first
    ADC window, or the whole file when that is shorter or there is no ADC. Reads only the
    block of the first ADC, with the block cache off."""
    seq = seqs[file_index].seq
    index = sequence_index(seq)
    duration_ms = round(index.end_s * 1e3, 4)
    window_ms = duration_ms
    if index.adc_first.size:
        play = int(index.adc_first[0])  # the first block with an ADC, in play order
        with block_cache_off(seq):
            adc = seq.get_block(int(index.block_id[play])).adc
        # The float operations of `_block_events`: (block start + delay) + length. A
        # Python float, so that `round` is Python's and not numpy's.
        a0 = float(index.start_s[play]) + adc.delay
        window_ms = min(duration_ms, 1.1 * round((a0 + adc.num_samples * adc.dwell) * 1e3, 4))
    window_ms = round(window_ms, 4)
    return TimeWindow(f"First ADC (0–{window_ms:.3g} ms)", file_index, 0.0, window_ms / 1e3)
```

6. P4. `block_rows` gets `if end_s is not None and t > end_s: break` at the
   start of its loop, as `_events_in_range` has it. Block starts do not go
   down, so no later block is in the range.
7. C18. The `_BlockEvents` docstring becomes "The diagram content of one
   block: times in s, and values in µT, rad and mT/m."
8. D18. The docstrings of `duration_s` and `_timed_blocks` no longer name
   `iter_blocks` (it moves to the tests, decision 17). They name the rule
   instead: the block start is the sum of the durations before the block, in
   play order.

**`seq_utils.py`: D18 and D19.**

9. D18 (decision 17): move `BlockTiming` and `iter_blocks` to a new
   `tests/oracles/blocks.py`. The two oracles and `tests/test_waveforms.py`
   import them from there. Remove the two `iter_blocks` tests of
   `tests/test_seq_utils.py` and their `TESTS.md` entries (section 2.1), and
   correct `TESTS.md` section 2.15, line 3244. `tests/oracles/` has no
   `__init__.py` (a namespace package); import the new module as the oracles
   import each other.
10. D19. Remove the `hasattr` test. The `else` branch always adds the first
    and the last point:
    `offsets = np.concatenate([[0.0], np.asarray(g.tt, dtype=float), [g.shape_dur]])`,
    and the same for `amp` with `g.first` and `g.last`.

**`seq_index.py`: C19.** Lines 5-6 become "It numbers the unique RF, gradient
and ADC events from 1, in the order of their first use in play order. The
diagram tables and the analyses use these numbers."

**`pns.py`: P3.** `peak_tr_window` uses `sequence_index(seq).end_s` in place
of `seq.duration()[0]`. The one difference is in section 2.3 (P3). Say it in
the PR.

### 4.3 Phase 3: the PNS lane and the diagram card script

**`sampling.py`.**

1. D16. In `event_samples`, remove `step`, the `np.errstate` block and the
   `np.where`:

   ```python
   # t0 <= t < t1 here: `searchsorted(side="right") - 1` gives the last point at or
   # before t, so t1 > t0. At a step (two points at one time), p is the later point.
   samples[mid] = v0_mid + (v1_mid - v0_mid) / (t1_mid - t0_mid) * (t_mid - t0_mid)
   ```

   In the loop over the pairs, test `if count_n == 0: continue` before the
   call of `event_samples`.
2. C17. The last two sentences of the first paragraph of the `block_samples`
   docstring become: "It differs from `sample` at a step at a block junction
   (`add_block` accepts a step up to `max_slew * grad_raster_time`), and by
   the float drift of the block start sums (`tests/test_sampling.py`)."

**`assets/pns_lanes.js`.**

3. D16. Line 86 becomes
   `g[j] = v0 + (v1 - v0) / (t1 - t0) * (t - t0);`, with the comment "The
   `while` above stops with t0 <= t < t1, so t1 > t0."
4. D13. `_powPair`: `const cn1 = Math.pow(c, n - 1);`, with the comment "n >=
   1: `_applyBlockMap` returns first for n === 0." `exactView`: the test is
   `if (count <= 0)`.
5. D12 (decision 15). Move `_runBlockSamples` and `_plainRecursion`
   to `tests/js/test_pns_lanes.js` as `runBlockSamples` and `plainRecursion`.
   They read the per-event samples through
   `PnsLanes._internal.eventEntry(model, axis, ev, n).g`, and the model fields
   `alpha`, `c`, `aCoef`, `axisFactor`, `blockLen`, `tables`, `numBlocks` and
   `dt`. `collectPlainRecursion` calls the local `plainRecursion`. The comment
   of `exactView` (457) no longer names `_runBlockSamples`.
6. D11. `_internal` keeps only `eventEntry` and `sampleRangeFor`.
7. S10. Each of the three `return` objects of `lanesFor` gets
   `onRaster: model.onRaster`. `statusText(result)` reads `result.onRaster`.
   Its comment says what it reads, without the "passed separately" reason.
8. C22. Correct each reference:
   - Lines 9 and 19-20: "the prototype, `prototypes/pns_lanes/pns_lanes.js`
     and its README in the tag `archive/pns-lanes-prototype`".
   - Line 50: name a heading that is in the README at that tag, or remove the
     reference.
   - "interface doc" and "interface note" (62, 454, 621): "the README's
     'Interface of `pns_lanes.js`' section at the tag
     `archive/pns-lanes-prototype`".
   - Lines 225-226: the item of `docs/plans/diagram-lanes.md` that sets the
     per-sample recursion as the reference of the block maps. If no item says
     it, remove the reference.
   - Line 466: "plan section 4.3, item 1".
   - Lines 332-335: remove "(item 2, gap = true)". `gap` does not depend on
     `onRaster`.
   - `_applyBlockMap`: add the block map formula
     `s_n = c^n·s + c^(n-1)·α·u0 + h[n-1]`, with `u0` the boundary input.
9. C25, new case. Line 223: remove "Renamed from the prototype's
   `wholeFileRecursion`". With D12 the sentence moves to the test file
   without these words.

**`assets/cards/diagram.js`.**

10. S5. Pass `lanes: []` to `laneChart` and to `setWindow`, with one comment
    line: "`lanesFor` and `groups` are given, so `laneChart` never draws
    `lanes` (lane_chart.js)." Remove `initialLanes` and its comment
    (172-185), and the comment at 350-355.
11. S10. `showStatus(exact, bins, pnsResult, gError)` calls
    `PnsLanes.statusText(pnsResult)`. The `lanesFor` hook no longer reads
    `current.pns.model.onRaster`. Correct the comment of `showStatus`.
12. C25. Line 4: "There are no lane sets and no point budget:" (no "Unlike the
    old card"). Line 59: remove "as it was before this lane existed". Line 76:
    remove "(as before)".

**Tests (`tests/js/test_pns_lanes.js`, `TESTS.md` section 2.25).**

13. D12: the two moved functions. `TESTS.md` names the test file's own
    `plainRecursion` in place of `_internal._plainRecursion` (5653, 5679 and
    the other places).
14. S10: the `statusText` calls give `onRaster` in the result object. A test
    that compares a whole `lanesFor` result gets the new key.
15. C22: lines 12, 16, 323 and 397, and `TESTS.md` 5646-5647 and the
    "interface doc" lines, as in item 8.
16. C26: "the worker spec" (259, 541, 735, 829, 884, and `TESTS.md` 5656,
    5682, 5697, 5815, 5905) becomes the plan section that gives the rule, or
    goes away.

### 4.4 Phase 4: the sequence lanes

All in `assets/seq_lanes.js`. One O worker owns the file.

1. D7. Remove `_blockRange` (183-200).
2. D8. Remove the outer `inBin` (1088-1090). Move `const take` (1160) above
   the loop over the bins.
3. S9 and D9. One helper for the backward walk:

   ```js
   // The first block whose closed interval [start, start + duration] overlaps
   // [lo, hi], and its start: `_blockAtStart(model, lo)`, then a walk back over the
   // earlier blocks that also overlap (the block before, when lo is exactly its end,
   // and blocks of zero duration at the same instant). Each earlier start comes from
   // `blockStart` (a forward sum from its group start), never from `start - duration`:
   // the subtraction is a different sequence of float64 operations (section 4.3 of
   // docs/plans/diagram-event-table.md). The model must have a block.
   function _firstOverlapping(model, lo, hi) {
     const tb = model.tables;
     let [i, start] = _blockAtStart(model, lo);
     while (i > 0) {
       const prevDur = tb.durations[tb.duration_index[i - 1]];
       const prevStart = blockStart(model, i - 1);
       if (prevStart + prevDur < lo || prevStart > hi) break;
       i--;
       start = prevStart;
     }
     return [i, start];
   }
   ```

   - `_forEachBlockInRange` starts its forward loop from
     `_firstOverlapping(model, lo, hi)`.
   - `_blockSpan` takes `first` from `_firstOverlapping`, and
     `[last, lastStart]` from `_blockAtStart(model, hi)`. It has no `start`
     variable (D9).
   - `_lineSegment` takes `[a, aStart]` from `_blockAtStart(model, t0)` and
     from `_blockAtStart(model, t1)`, in place of `blockAt` and `blockStart`.
   - Remove the clamps `Math.min(Math.max(..., 0), N - 1)`. Each caller
     already returns for `N === 0`.
   - Keep the comment about the subtraction (now at the helper).
4. D10. `_rangeMinMax(model, laneId, from, to, cols)`: `cols` is required (no
   `|| _laneArrays(...)`). The scan starts at `from`.
5. S13. Move `GROUP_BLOCKS` and its comment next to `CHECKPOINT_BLOCKS`.
6. P5. `_blockPoints` reads `tb.gx[i]`, `tb.gy[i]` and `tb.gz[i]` into three
   constants and tests each one. No array per call.
7. C24. The `decode` comment lists what `decode` computes: `durationS`,
   `lastNonZeroBlock`, `groupStart`, the minimum and the maximum of each event
   (`rf`, `grad`), and `groups` (the group summaries and their trees). The
   point counts are the `*_n` tables as given. `pyramids` starts empty and
   gets a pool's pyramid on the first render that needs it.
8. Tests (comment-only edits and one rename, `TESTS.md` section 2.19):
   - C26: "the scratchpad's `validate_minmax.js`" (84-85, 633, 811, and
     `TESTS.md` 3968-3971, 4003-4005) becomes the plan section that set these
     models and views (`docs/plans/diagram-event-table.md`), or goes away.
   - C27: rename `buildPointBudgetModel` to `buildEightPointModel` (every
     block has exactly 8 points), also in `TESTS.md` 3962 and 4442.

### 4.5 Phase 5: the |G| lane and the chart comments

**`assets/g_lanes.js`.**

1. S11. The helpers take the model:
   `_blockGRange(model, i)`, `_exactBlockGRange(model, i, loAbs, hiAbs)`,
   `_rangeGMinMax(model, from, to)` and `_buildGGroups(model)`.
   `_tripleGeometry(tb, t, evCache)` takes the object of `_tripleKeyOf`.
   Rename the argument `tb` of `_quadRangeExtrema` to `tEnd`.
2. S11, `decode`. Make the model object first, with the same field names
   (`seqModel`, `tables`, `evCache`, `M`, `D`, `numBlocks`). Then set
   `model.gTree = _buildGGroups(model)` and
   `model.wholeFileMax = N > 0 ? model.gTree.max.query(0, model.gTree.max.n) : 0`.
   The maximum over the groups is the maximum over the blocks, with no
   rounding, so the value does not change. The comment of `decode` is then
   true.
3. C23:
   - `_axisValueAt` and the module doc (26-28): add "The pieces are linear
     between the union times, so after an event's last point the axis goes
     linearly to 0 at the next union time. pypulseq's `add_block` refuses a
     gradient that does not end at 0 before its block end, so this occurs only
     in a file that pypulseq does not write." Remove "as before" (167, C25).
   - `laneMeta` (548-559): the domain `[0, 1.1 * peak]` is the style of the RF
     \|B1\| lane (`symmetric=False`). The gx, gy and gz lanes are symmetric.
     `empty` is true when the whole-file peak is 0, which includes a file
     whose gradient events are all 0.
   - Line 15: point to the module doc lines about the quadratic (19-24).
   - Lines 30-33: only `decode` builds the caches and the tree.
   - `GROUP_BLOCKS` (49-51): a bin touches at most two partial groups and
     O(log G) nodes of the tree.
   - Lines 41-43: remove the reason for `typeof require` over `typeof module`.
     In a browser, both are undefined.

**`assets/chart_math.js`: C20.**

4. Line 1: "loaded before lane_chart.js".
5. One comment for `fmt` (3 significant digits, "0" below 5e-4, "—" for no
   value, a U+2212 minus sign), for `niceTicks`, and for `valueAt` (the value
   at `t`, linear in a segment, and `lane.fill` where no segment covers `t`).
6. `minMaxAt`: "which is exact" becomes "which equals the bin's end up to
   rounding".

**`assets/lane_chart.js`: C25.** Keep the statement of what the code does,
without the history: lines 4 and 527 ("moved here from ..."), 59, 67 and 86
("as it did before ... existed"), 251 ("as before").

**Tests (comment-only edits).** C26: `tests/js/test_g_lanes.js:612` loses
"the worker spec". C27: the comment at 39-45 names `durationOptions`, not
`TEMPLATE_DUR`.

### 4.6 Phase 6: the shared JavaScript helpers (S12)

`ChartMath` (`chart_math.js`) gets the shared pure helpers (decision 20). The page loads `chart_math.js` first.

1. `segTree(values, n, isMin)`: the `_segTree` of `seq_lanes.js`, moved
   unchanged. `seq_lanes.js` and `g_lanes.js` call it.
2. `minMaxSegments(edges, bins, binAt)`: `_zigzag` of `pns_lanes.js`, with the
   values of `binAt(k)` used as they are. `pns_lanes.js` scales them by 100 in
   its `binAt`, so the float operations stay the same. `GLanes.lanesFor` calls
   it with `binAt = k => (max[k] === -Infinity ? null : [min[k], max[k]])`.
3. `sig3(v)`: `Number(v.toPrecision(3)).toString()`. `g_lanes.js` (`_fmt`) and
   `pns_lanes.js` (`_fmtBinMs`) call it. `fmt` calls it too:
   `sig3(v).replace("-", "−")`.
4. The bounds stay in their modules. They have different arguments (section
   2.3, S12).
5. In Node, `seq_lanes.js`, `g_lanes.js` and `pns_lanes.js` load the module
   as `g_lanes.js` loads `SeqLanes`:
   `if (typeof require === "function") global.ChartMath = require("./chart_math.js");`.
   The tests and the golden scripts then need no change.

### 4.7 Phase 7: tests and scripts

1. D6, `scripts/check`. The pytest and `TESTS.md` steps run with no guard. A
   missing `tests/` makes pytest fail. The node step fails when no file
   matches, because `node --test` alone passes then (section 2.3, D6):

   ```bash
   js_tests=(tests/js/test_*.js)
   if [ ! -e "${js_tests[0]}" ]; then
     echo "error  node: no JavaScript tests in tests/js" >&2
     exit 1
   fi
   node --test "${js_tests[@]}"
   ```

2. D6, `scripts/check_tests_md.py`. `javascript_tests()` has no `root`
   argument. It reads `ROOT / "tests" / "js"`. Remove "`root` may not exist
   yet ...". The example heading becomes
   ``### 2.1 Shared sequence helpers (`test_seq_utils.py`)``.
3. D6, `TESTS.md` section 1. Remove the bullet "`scripts/check` skips both
   the pytest run and this check, ..." (138-140). Lines 157-159 become "When
   the pattern matches no file, the step fails."
4. D4 (`tests/test_diagram_card.py`, `TESTS.md` section 2.16). Remove
   `_ZOOM_HELP_SENTENCE`. Rename the test to
   `test_diagram_card_has_zoom_controls_directly_before_its_chart`. Remove
   "Phases 4 (gradient spectrum) and 5 (PNS) are not merged into this branch
   ..." from its docstring. In `TESTS.md`: the new name, no "help text exactly
   once" in Checks and How, and no "phases 4 and 5 are not merged" (3313-3316
   and 3453).
5. D20 (`tests/synthetic.py`). Remove `crusher_2_cycles` and
   `prephaser_fraction`. Use `area=sign * balance` and `area=3 / WIDTH`.
6. S14:
   - `tests/synthetic.py` gets `load_diagram_scale()` (from
     `tests/test_seq_index.py`) and `border_sequence()` (from
     `tests/test_pns_levels.py`). The four test files import them.
   - A new `tests/rf_sequences.py` gets `SYSTEM`, `W`, `CRUSHER_AREA`,
     `_sinc`, `_hard`, `_readout` (the form with 3 values), `_trap`, `_new`,
     `_turning_gradients` and `_gre` of `tests/test_rf_profiles.py`, with the
     same names. Thus `tests/test_rf_profiles_golden.py` (`cases._gre`,
     `cases._hard`, `cases._new`, `cases.W`) does not change.
     `tests/test_rf_profiles.py` and `tests/test_rf_profile_card.py` import
     them. The card test's own `_spin_echo` stays and takes
     `gx, adc, _ = _readout()`.
   - `TESTS.md`: section 2.24 (5443: `synthetic.border_sequence()`), 2.26 (the
     border sequence is shared through `tests/synthetic.py`), 2.9 and 2.22
     ("through `synthetic.load_diagram_scale`"), 2.31 and 2.34 (the builders
     of `tests/rf_sequences.py`, not "copied, not imported").
7. S15 (`tests/test_pns_lanes_golden.py`). `pns_payload = _pns_entry(seq, levels)`,
   imported from `pulseq_reports.cards.diagram`. The payload does not change
   (section 2.3). `TESTS.md` section 2.26: `_run_golden` takes the `pns`
   object from `cards.diagram._pns_entry`, the function that makes it for the
   page.
8. S16 (`scripts/cards_scale.py`). Only `_run_diagram` takes `pns_lanes`.
   `CARD_NAMES = tuple(CARD_RUNNERS)`, after `CARD_RUNNERS`. `--pns-lanes`
   with a card other than `diagram` or `all` is an `argparse` error. `--card all
   --pns-lanes` gives `--pns-lanes` only to the diagram subprocess. The JSON
   name has "-pns-lanes" only for the diagram card and for the combined file.
   The docstrings of the module and of `_run_all` say so.
9. C26 and C27, Python:
   - `tests/test_diagram_card.py:316`: remove "(worker spec)".
   - `tests/test_rf_exposure.py:186-187`: remove the sentence about the
     scratch comparison.
   - `tests/test_rf_exposure_card.py`: 235 says "exactly" (the helper
     compares with `==`). Lines 130-132 no longer point at a docstring that
     does not say it.
   - `scripts/diagram_scale.py:27`: "on stderr".
   - `tests/test_diagram_data.py:4-6` and `TESTS.md` 3747: "a later phase"
     becomes `test_seq_lanes_golden.py`.

## 5. Phases

---

### Phase 1: Python analyses and cards

Branch: `refactor/analyses-cleanup`. Wave 1. Section 4.1.

**Task 1.1.** Tier H. `grad_spectrum.py`, `rf_exposure.py`,
`cards/timing.py`, `cards/diagram.py`: section 4.1, items 1 to 5 and 12 to
14.

**Task 1.2.** Tier S. `grad_limits.py`: items 6 to 8.

**Task 1.3.** Tier S. `pns_levels.py`, `tests/test_pns_levels.py`, `TESTS.md`
section 2.24: items 9 to 11.

**Task 1.4.** Tier X. The comparison set (section 3.5). Review each diff.

Checks:

- [ ] The example page and the Python dump are equal, or differ only as
      section 3.5, item 3 says.
- [ ] The oracle tests of `test_grad_limits.py`, `test_grad_spectrum.py` and
      `test_rf_exposure.py` pass with no change.
- [ ] `scripts/check` passes.

---

### Phase 2: Python core and speed

Branch: `refactor/core-speed`. Wave 1. Section 4.2.

**Task 2.1.** Tier S. `waveforms.py` and `diagram_data.py`: D21, S3, S4, C19
(`diagram_data.py`), P1, P2, P4, C18 and the D18 docstring. One worker,
because S3 edits both files.

**Task 2.2.** Tier H. `seq_utils.py`, `seq_index.py`, `pns.py`: D18 (decision
17: `seq_utils.py`, `tests/oracles/`, `tests/test_seq_utils.py`,
`tests/test_waveforms.py` and their `TESTS.md` sections), D19, C19
(`seq_index.py`), P3.

**Task 2.3.** Tier X. The measurements of section 2.4 (phase 2 rows), before
and after. The comparison set. Review each diff.

Checks:

- [ ] The example page and the Python dump are equal.
- [ ] The budget of section 2.4 passes. The numbers are in the PR.
- [ ] `scripts/check` passes.

---

### Phase 3: the PNS lane and the diagram card script

Branch: `refactor/pns-lane-cleanup`. Wave 2 (wave 1 with five PRs). Section
4.3.

**Task 3.1.** Tier S. `pns_lanes.js`, `tests/js/test_pns_lanes.js`, `TESTS.md`
section 2.25: items 3 to 9 and 13 to 16. One worker, because D12 and S10 edit
both the module and its test.

**Task 3.2.** Tier S. `cards/diagram.js`: items 10 to 12. It starts at the
same time as task 3.1, with the `statusText(result)` form of item 7.

**Task 3.3.** Tier H. `sampling.py`: items 1 and 2.

**Task 3.4.** Tier X. The comparison set, with `page_diff.py` for
`pns_lanes.js` and `cards/diagram.js`. A browser check with the
`dev-workflow:browser-check-localhost` skill, on the example page of the
branch:

1. The diagram card draws at once, with the right height (S5). The window
   buttons work.
2. Hide and show the Gradients and PNS groups. The height follows.
3. The status line: zoom out to the bins view and in to the exact view. The
   PNS sentence is the same as on the baseline page for the same view.
4. Both themes. No console error.

Checks:

- [ ] The comparison set differs only as section 3.5, item 3 says.
- [ ] The browser check passes.
- [ ] `scripts/check` passes.

---

### Phase 4: the sequence lanes

Branch: `refactor/seq-lanes-cleanup`. Wave 1. Section 4.4.

**Task 4.1.** Tier O. `seq_lanes.js`: items 1 to 7. Give the worker
decision 3 of section 2.2 word for word, and the S9 check (section 9.5). The
worker runs the check and `node --test tests/js/test_seq_lanes.js` before it
reports.

**Task 4.2.** Tier H. `tests/js/test_seq_lanes.js` and `TESTS.md` section
2.19: item 8, with the exact names.

**Task 4.3.** Tier X.

1. The S9 check of section 3.5, item 4: OK on the baseline, OK on the branch,
   FAIL on the mutated copy.
2. Search the diff for a subtraction whose result is a block start. There
   must be none.
3. The comparison set, with `page_diff.py` for `seq_lanes.js`.
4. `time_js.js` at 10^7 blocks, three runs on each side (section 2.4).
5. A browser check: zoom, pan, the window buttons, and the tooltip at a block
   edge, in both themes. No console error.

Checks:

- [ ] Section 3.5, items 3 and 4 hold.
- [ ] The budget of section 2.4 passes. `SeqLanes.decode` is faster (P5).
- [ ] `scripts/check` passes.

---

### Phase 5: the |G| lane and the chart comments

Branch: `refactor/g-lanes-cleanup`. Wave 2 (wave 1 with five PRs). Section 4.5.

**Task 5.1.** Tier S. `g_lanes.js`: items 1 to 3.

**Task 5.2.** Tier S. `chart_math.js`, `lane_chart.js`,
`tests/js/test_g_lanes.js`: items 4 to 6 and the rest of section 4.5.

**Task 5.3.** Tier X. The comparison set, with `page_diff.py` for the three
assets. `time_js.js` at 10^7 blocks (`GLanes.decode`, `GLanes.minMax`). A
browser check of the \|G\| lane and of the tooltips, in both themes.

Checks:

- [ ] The comparison set differs only as section 3.5, item 3 says.
- [ ] The budget of section 2.4 passes.
- [ ] `scripts/check` passes.

---

### Phase 6: the shared JavaScript helpers

Branch: `refactor/js-shared-helpers`. Wave 3, after phases 3, 4 and 5 are
merged. Section 4.6.

**Task 6.1.** Tier S. `chart_math.js`, `seq_lanes.js`, `g_lanes.js`,
`pns_lanes.js`: section 4.6. One worker, because the change edits all four.

**Task 6.2.** Tier X. The comparison set, with `page_diff.py` for the four
assets. The golden tests (`test_seq_lanes_golden.py`,
`test_pns_lanes_golden.py`, `test_rf_profiles_golden.py`), which run Node on
the modules. `time_js.js` at 10^7 blocks. A browser check of the diagram card
and the RF profile card, in both themes.

Checks:

- [ ] The comparison set differs only as section 3.5, item 3 says.
- [ ] The budgets of section 2.4 pass.
- [ ] `scripts/check` passes.

---

### Phase 7: tests and scripts

Branch: `refactor/tests-scripts-cleanup`. Wave 2, after phase 1 is merged.
Section 4.7.

**Task 7.1.** Tier S. D20, S14 and S15: items 5 to 7, with their `TESTS.md`
sections (2.9, 2.22, 2.24, 2.26, 2.31, 2.34).

**Task 7.2.** Tier H. D6, D4, S16, C26 and C27: items 1 to 4, 8 and 9, with
`TESTS.md` section 1 and sections 2.16 and 2.18.

**Task 7.3.** Tier X.

1. The example page and the Python dump are equal. The dump reads
   `tests/synthetic.py`, so this also checks D20.
2. The new node step of `scripts/check`, run in an empty directory, exits 1.
3. `scripts/cards_scale.py --card all --blocks 400 --case repeating --pns-lanes --out <scratch>`
   runs, and only the diagram result has `pns_lanes: true`.
   `--card rf --pns-lanes` gives the `argparse` error.
4. `shellcheck` passes (it is part of `scripts/check`).

Checks:

- [ ] The number of tests does not change: this phase moves helpers and
      renames one test. Each test has its `TESTS.md` entry.
- [ ] `scripts/check` passes.

---

### Phase 8: results

Branch: `chore/review-cleanup-results`. After phases 1 to 7 are merged.

**Task 8.1.** Tier X. Rebuild `docs/examples/gre.html`. Its diff against the
page of `4850c68` has only the script changes of phases 3 to 6 and the label
of C13 (`page_diff.py` with those assets). Open it in the browser: the nine
cards draw, and the console has no error.

**Task 8.2.** Tier X. P6, the measurement against the budget of decision 14:

1. Node: `p6.js` (section 9.8) with 10^5, 3 × 10^5 and 10^6 distinct gradient
   events, a fresh process each.
2. Python: `scripts/cards_scale.py --card pns --case worst --blocks 1000000`,
   and `--card diagram --pns-lanes`, the same file. The worst case makes a new
   phase-encode event for each TR, so 10^6 blocks give about 2 × 10^5
   distinct gradient events. Record the added RSS: the block-sample cache of
   `GradientSampler` keeps one array for each distinct (event, length).
3. Browser: a scratch script writes a page with one diagram card, with
   `pns=True`, for `diagram_scale.build_worst(200000)` (10^6 blocks). It adds
   `diagram_scale._timing_probe_script("diagram")` (the probe of
   `diagram_scale.py --timing-probe`) as an extra script. Open the page with
   the `dev-workflow:browser-check-localhost` skill. Record the time to the
   first chart and `usedJSHeapSize`.
4. Put the numbers in section 8. If the budget of decision 14 fails at 10^5
   events, stop and tell the user. A change for P6 then goes into a new plan
   or a `TODO.md` item, as the user decides.

**Task 8.3.** Tier X. `TODO.md`: add this item (decision 18), after the item
"Validate every card against external references":

```markdown
## Show where the gradient limits happen

**Why.** `grad_limits.gradient_limits` finds where each extreme happens: for
each axis, `peak_block` and `peak_time_s` (the largest amplitude) and
`slew_block` (the largest slew), and for |G|, `GradientLimits.vector_peak_time_s`.
The gradient limits card shows only the values. The RF exposure card already shows
the block of its peak. The user chose to show them (C14 of
`docs/reviews/2026-09-28-code-review.md`, decision 18 of
`docs/plans/review-cleanup.md`).

**What.** Show the block and the time of each peak and of each largest slew on the
card, for each file and window. Check the tie rule first (finding L3 of the review:
on an exact tie, the credited block can be the later one).

**How to check.** `scripts/check`, and a test of the new cells for a sequence whose
peaks are at known blocks and times.

**When.** After this plan. It changes the card's output, so it is a feature, not
cleanup.
```

**Task 8.4.** Tier X. The review's "Status" section: the fixed findings,
with their PR numbers, as #76 did for the bugs.

**Task 8.5.** Tier X. This plan: status "complete", and section 8.

**Task 8.6.** Tell the user what is done, and the answer of task 8.2.

Checks:

- [ ] `scripts/check` passes.

## 6. Summary of parallel work

| Wave | Phases | Condition to start |
|---|---|---|
| 1 | 1, 2, 3, 4, 5 | This plan is merged. The baseline exists. |
| 2 | 7 | Phase 1 merged. |
| 3 | 6 | Phases 3, 4 and 5 merged. |
| 4 | 8 | Phases 1 to 7 merged. |

Workers inside a phase:

| Phase | Workers | The executing agent |
|---|---|---|
| 1 | H for task 1.1, S for task 1.2, S for task 1.3, at the same time | Task 1.4 and the review |
| 2 | S for task 2.1, H for task 2.2, at the same time | Task 2.3 (measurements) and the review |
| 3 | S for task 3.1, S for task 3.2, H for task 3.3, at the same time | Task 3.4 (browser check) and the review |
| 4 | O for task 4.1, H for task 4.2, at the same time | Task 4.3 (the S9 check) and the review |
| 5 | S for task 5.1, S for task 5.2, at the same time | Task 5.3 and the review |
| 6 | S for task 6.1 | Task 6.2 and the review |
| 7 | S for task 7.1, H for task 7.2, at the same time | Task 7.3 and the review |
| 8 | None | All tasks |

## 7. Questions still open

None. The user answered the nine questions on 2026-09-29:

1. PR limit: five (decision 12).
2. C13: yes, the `aria-label` lists every lane (decision 13).
3. P6: option B, the budget at 10^5 events; 10^6 is recorded (decision 14).
4. D12: yes, test code leaves the page's JavaScript (decision 15).
5. Order: option A, the speed-ups and S9 first (decision 16).
6. D18: option B, move to `tests/oracles/blocks.py` (decision 17).
7. C14: option B, show the fields on the card, as a later feature (decision
   18).
8. C15: no test (decision 19).
9. S12: `ChartMath` (decision 20).

## 8. Results

Not started.

## 9. Scripts

Run each script from the root of a worktree. Put the scripts and their
outputs in the session scratchpad. The Python scripts:
`nix develop --command uv run python <script> ...`. The JavaScript scripts:
`nix develop --command node <script> ...`.

### 9.1 `dump_py.py`: the Python dump

```python
"""Dump every card and analysis output of the comparison set to one JSON file.

Run from the root of a worktree: uv run python dump_py.py OUT.json
Run it in the baseline and in the task worktree, then compare the two files with cmp.
"""

import dataclasses
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import warnings

import numpy as np
import pypulseq as pp

sys.path.insert(0, "tests")
import synthetic  # noqa: E402

from pulseq_reports import (  # noqa: E402
    diagram_data,
    grad_limits,
    grad_spectrum,
    pns,
    pns_levels,
    rf_exposure,
    sampling,
    seq_index,
    waveforms,
)
from pulseq_reports.cards import (  # noqa: E402
    blocks,
    definitions,
    diagram,
    gradient_limits,
    rf_profile,
    spectrum,
    timing,
)
from pulseq_reports.cards import pns as pns_cards  # noqa: E402
from pulseq_reports.cards import rf_exposure as rf_cards  # noqa: E402
from pulseq_reports.seq_utils import NamedSequence  # noqa: E402

warnings.simplefilter("ignore")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_back(seq):
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "x.seq")
        seq.write(path)
        out = pp.Sequence(seq.system)
        out.read(path)
    return out


def labels_and_steps():
    """Zero-duration label blocks between gradient blocks, and a junction step."""
    s = synthetic.SYSTEM
    step = 0.9 * s.max_slew * s.grad_raster_time
    seq = pp.Sequence(s)
    seq.add_block(pp.make_label(type="SET", label="LIN", value=0))
    seq.add_block(
        pp.make_extended_trapezoid("x", times=[0, 1e-4, 2e-4], amplitudes=[0, step, step], system=s)
    )
    seq.add_block(pp.make_label(type="INC", label="LIN", value=1))
    seq.add_block(pp.make_delay(1e-3))
    seq.add_block(pp.make_trapezoid("y", area=200, system=s), pp.make_adc(16, dwell=1e-5))
    return seq


def plain(value):
    """A JSON form that keeps every float bit (repr) and hashes large arrays."""
    if dataclasses.is_dataclass(value):
        return {f.name: plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, np.ndarray):
        if value.size <= 64:
            return [str(value.dtype), [repr(v) for v in value.tolist()]]
        return [str(value.dtype), value.shape, hashlib.sha256(value.tobytes()).hexdigest()]
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return [type(value).__name__, repr(float(value))]
    if isinstance(value, np.integer):
        return int(value)
    return value


out: dict = {}


def record(key, fn):
    """Keep the output of `fn()`, or its error: in full when short, else its SHA-256."""
    try:
        text = json.dumps(plain(fn()))
    except Exception as error:  # the same error must happen in both worktrees
        text = json.dumps(["raised", type(error).__name__, str(error)])
    if len(text) > 2000:
        text = f"sha256 {hashlib.sha256(text.encode()).hexdigest()} length {len(text)}"
    out[key] = text


gre_report = load("examples/gre_report.py", "gre_report")
scale = load("scripts/diagram_scale.py", "diagram_scale")
SEQS = {
    "spin_echo": synthetic.spin_echo_sequence(),
    "spin_echo_after": synthetic.spin_echo_sequence(prephaser_position="after"),
    "gre": synthetic.gre_sequence(),
    "empty": synthetic.empty_sequence(),
    "arbitrary": synthetic.arbitrary_gradient_sequence(),
    "labels_and_steps": labels_and_steps(),
    "example_gre": gre_report.gre_sequence(),
    "repeating": scale.build_repeating(40),
    "worst": scale.build_worst(40),
}
SEQS["example_gre_read"] = read_back(SEQS["example_gre"])

for name, seq in SEQS.items():
    named = [NamedSequence(f"{name}.seq", seq)]
    idx = seq_index.sequence_index(seq)
    end = idx.end_s
    win = (0.3 * end, 0.6 * end)
    k = name + "/"
    record(k + "duration_s", lambda: waveforms.duration_s(seq))
    record(k + "first_adc", lambda: waveforms.first_adc_window(named))
    record(k + "full", lambda: waveforms.full_window(named))
    record(k + "rows", lambda: waveforms.block_rows(seq))
    record(k + "rows_win", lambda: waveforms.block_rows(seq, *win, max_rows=3))
    record(k + "file_lanes", lambda: waveforms.file_lanes(seq))
    record(k + "file_lanes_win", lambda: waveforms.file_lanes(seq, *win))
    record(k + "tables", lambda: diagram_data.diagram_tables(seq))
    record(k + "lane_meta", lambda: diagram_data.lane_meta(seq))
    record(k + "limits", lambda: grad_limits.gradient_limits(seq))
    record(k + "limits_win", lambda: grad_limits.gradient_limits(seq, window=win))
    record(k + "rf_p", lambda: rf_exposure.rf_exposure(seq))
    record(k + "rf_np", lambda: rf_exposure.rf_exposure(seq, periodic=False, window_s=0.01))
    record(k + "spectrum", lambda: grad_spectrum.gradient_spectrum(seq))
    record(k + "levels", lambda: pns_levels.pns_levels(seq))
    record(k + "prediction", lambda: pns.pns_prediction(seq))
    record(k + "peak_tr", lambda: pns.peak_tr_window(seq, pns.pns_prediction(seq).peak_time_s))
    grid = np.linspace(0.0, end, 997)

    def samples():
        s = sampling.GradientSampler(seq, idx)
        dt = seq.system.grad_raster_time
        return [s.sample(a, grid) for a in ("gx", "gy", "gz")] + [
            s.block_samples(a, 0, idx.num_blocks, dt) for a in ("gx", "gy", "gz")
        ]

    record(k + "samples", samples)
    windows = [waveforms.first_adc_window(named), waveforms.full_window(named)]
    cards = {
        "timing": lambda: timing.timing_card(named),
        "rf": lambda: rf_cards.rf_exposure_card(named),
        "diagram": lambda: diagram.diagram_card(named, windows, pns=True),
        "rf_profile": lambda: rf_profile.rf_profile_card(named, views=("profile", "z_df")),
        "spectrum": lambda: spectrum.spectrum_card(named),
        "pns": lambda: pns_cards.pns_card(named[0]),
        "limits": lambda: gradient_limits.gradient_limits_card(named),
        "limits_win": lambda: gradient_limits.gradient_limits_card(named, window=win),
        "definitions": lambda: definitions.definitions_card(named),
        "blocks": lambda: blocks.blocks_card(named, windows),
    }
    for card_name, build in cards.items():
        record(k + "card/" + card_name, build)

many = [NamedSequence(f"{n}.seq", SEQS[n]) for n in ("spin_echo", "gre", "empty", "example_gre")]
many_windows = [waveforms.full_window(many, i) for i in range(len(many))]
record("many/timing", lambda: timing.timing_card(many))
record("many/rf", lambda: rf_cards.rf_exposure_card(many))
record("many/rf_np", lambda: rf_cards.rf_exposure_card(many, periodic=False))
record("many/spectrum", lambda: spectrum.spectrum_card(many))
record("many/limits", lambda: gradient_limits.gradient_limits_card(many))
record("many/diagram", lambda: diagram.diagram_card(many, many_windows, pns=True))
record("many/rf_profile", lambda: rf_profile.rf_profile_card(many))
record("many/blocks", lambda: blocks.blocks_card(many, many_windows))

with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(out, f, indent=1)
print(f"wrote {len(out)} entries to {sys.argv[1]}")
```

No phase changes a name or an argument that this script uses. D15 removes
only `chunk_samples`, which the script does not give.

### 9.2 `make_js_input.py`: the input of the JavaScript dump

```python
"""Write the diagram card's file entries (tables, lanes, pns) of the JS comparison set.

Run it one time, from the root of the baseline worktree:
uv run python make_js_input.py IN.json. Both runs of dump_js.js then read the same IN.json.
"""

import importlib.util
import json
import sys
import warnings

import pypulseq as pp

sys.path.insert(0, "tests")
import synthetic  # noqa: E402

from pulseq_reports.cards.diagram import diagram_card  # noqa: E402
from pulseq_reports.seq_utils import NamedSequence  # noqa: E402
from pulseq_reports.waveforms import full_window  # noqa: E402

warnings.simplefilter("ignore")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def labels_and_steps():
    """Zero-duration label blocks between gradient blocks, and junction steps."""
    s = synthetic.SYSTEM
    step = 0.9 * s.max_slew * s.grad_raster_time
    seq = pp.Sequence(s)
    for i in range(150):
        seq.add_block(pp.make_label(type="SET", label="LIN", value=i))
        seq.add_block(
            pp.make_extended_trapezoid(
                "x", times=[0, 1e-4, 2e-4], amplitudes=[0, step, step], system=s
            )
        )
        seq.add_block(pp.make_label(type="INC", label="LIN", value=1))
        seq.add_block(
            pp.make_extended_trapezoid(
                "x", times=[0, 1e-4, 2e-4], amplitudes=[step, step, 0], system=s
            )
        )
        seq.add_block(pp.make_delay(1e-3 + (i % 3) * 1e-5))
        seq.add_block(pp.make_trapezoid("y", area=200, system=s), pp.make_adc(16, dwell=1e-5))
    return seq


gre_report = load("examples/gre_report.py", "gre_report")
scale = load("scripts/diagram_scale.py", "diagram_scale")
SEQS = {
    "spin_echo": synthetic.spin_echo_sequence(),
    "gre": synthetic.gre_sequence(),
    "arbitrary": synthetic.arbitrary_gradient_sequence(),
    "labels_and_steps": labels_and_steps(),
    "example_gre": gre_report.gre_sequence(),
    "repeating": scale.build_repeating(400),
    "worst": scale.build_worst(400),
}
entries = {}
for name, seq in SEQS.items():
    named = [NamedSequence(name, seq)]
    entries[name] = diagram_card(named, [full_window(named)], pns=True).data["files"][0]
with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(entries, f)
print(f"wrote {len(entries)} file entries to {sys.argv[1]}")
```

### 9.3 `dump_js.js`: the JavaScript dump

```js
// Dump the SeqLanes, GLanes and PnsLanes outputs of the JS comparison set.
// node dump_js.js ASSETS_DIR IN.json OUT.json
// Run it with the assets of the baseline and of the task worktree, on the same IN.json,
// then compare the two OUT files with cmp.
const fs = require("node:fs");
const path = require("node:path");
const zlib = require("node:zlib");
const crypto = require("node:crypto");

const assets = path.resolve(process.argv[2]);
global.ChartMath = require(path.join(assets, "chart_math.js"));
const SeqLanes = require(path.join(assets, "seq_lanes.js"));
const GLanes = require(path.join(assets, "g_lanes.js"));
const PnsLanes = require(path.join(assets, "pns_lanes.js"));

const ARRAYS = {
  uint8: Uint8Array, uint16: Uint16Array, uint32: Uint32Array, int32: Int32Array,
  float32: Float32Array, float64: Float64Array,
};
function decodeTable(t) {
  const raw = zlib.gunzipSync(Buffer.from(t.data, "base64"));
  const copy = new Uint8Array(raw.length);
  copy.set(raw);
  return new ARRAYS[t.dtype](copy.buffer, 0, t.length);
}

// Floats as exact text: -0, the infinities and NaN are kept apart.
function exact(key, v) {
  if (typeof v === "number") {
    if (Object.is(v, -0)) return "-0";
    if (!Number.isFinite(v)) return String(v);
    return v;
  }
  if (ArrayBuffer.isView(v)) return Array.from(v);
  return v;
}

const out = {};
function record(key, fn) {
  let text;
  try {
    text = JSON.stringify(fn(), exact);
  } catch (error) {
    text = JSON.stringify(["raised", String(error && error.message)]);
  }
  if (text !== undefined && text.length > 2000) {
    const hash = crypto.createHash("sha256").update(text).digest("hex");
    text = `sha256 ${hash} length ${text.length}`;
  }
  out[key] = text;
}

let seed = 12345;
const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;

const input = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
for (const [name, file] of Object.entries(input)) {
  const tables = {};
  for (const [k, t] of Object.entries(file.tables)) tables[k] = decodeTable(t);
  const seq = SeqLanes.decode(1, tables, file.lanes);
  const n = seq.numBlocks;
  // Block starts as the forward sum from 0 (the rule of section 4.3), computed here.
  const starts = new Float64Array(n + 1);
  for (let i = 0; i < n; i++) starts[i + 1] = starts[i] + tables.durations[tables.duration_index[i]];
  const dur = seq.durationS;
  const views = [[0, dur], [-1e-3, dur + 1e-3], [dur / 3, dur / 2], [dur, dur]];
  for (let v = 0; v < 40; v++) {
    const a = Math.floor(rnd() * n), b = Math.min(n - 1, a + Math.floor(rnd() * 3 * 64));
    views.push([starts[a], starts[b]], [starts[a], starts[a]]);
    views.push([starts[a] - 1e-9, starts[a + 1]], [(starts[a] + starts[a + 1]) / 2, starts[b + 1]]);
  }
  // Every block start as a view edge: the backward walk of S9 runs at each of them.
  record(`${name}/edges`, () => Array.from({length: n}, (_, a) => {
    const t0 = starts[a], t1 = starts[Math.min(n, a + 2)];
    return [SeqLanes.pointsIn(seq, t0, t1), SeqLanes.exactLanes(seq, t0, t1),
      SeqLanes.minMaxLanes(seq, t0, starts[Math.min(n, a + 70)], 3)];
  }));
  record(`${name}/blockAt`, () => Array.from(starts.subarray(0, n), t => SeqLanes.blockAt(seq, t)));
  record(`${name}/blockStart`, () => Array.from({length: n}, (_, i) => SeqLanes.blockStart(seq, i)));
  const g = GLanes.decode(seq);
  const gMeta = GLanes.laneMeta(g);
  record(`${name}/gMeta`, () => [g.wholeFileMax, gMeta]);
  let pns = null;
  if (file.pns) {
    const levels = {min: decodeTable(file.pns.levels.min), max: decodeTable(file.pns.levels.max)};
    pns = PnsLanes.decode(tables, {...file.pns, levels});
    record(`${name}/pnsMeta`, () => PnsLanes.laneMeta(file.pns.summary));
  }
  const pMeta = file.pns ? PnsLanes.laneMeta(file.pns.summary) : null;
  views.forEach(([t0, t1], vi) => {
    const k = `${name}/view${vi}`;
    record(`${k}/pointsIn`, () => SeqLanes.pointsIn(seq, t0, t1));
    record(`${k}/exact`, () => SeqLanes.exactLanes(seq, t0, t1));
    for (const bins of [1, 3, 812]) {
      const viewMs = [t0 * 1000, t1 * 1000];
      record(`${k}/${bins}/minMax`, () => SeqLanes.minMaxLanes(seq, t0, t1, bins));
      record(`${k}/${bins}/lanesFor`, () => SeqLanes.lanesFor(seq, viewMs, bins));
      record(`${k}/${bins}/g`, () => GLanes.minMax(g, t0, t1, bins));
      record(`${k}/${bins}/gLane`, () => GLanes.lanesFor(g, gMeta, viewMs, bins));
      if (pns) {
        record(`${k}/${bins}/pns`, () => {
          const r = PnsLanes.lanesFor(pns, pMeta, viewMs, bins);
          const text = PnsLanes.statusText.length >= 2
            ? PnsLanes.statusText(r, pns.onRaster) : PnsLanes.statusText(r);
          return [r.lane, r.exact, r.binMs, r.gap, text];
        });
        if (pns.onRaster && t1 - t0 <= PnsLanes.EXACT_MAX_S) {
          record(`${k}/${bins}/pnsExact`, () => PnsLanes.exactView(pns, t0, t1, bins));
        }
      }
    }
  });
}
fs.writeFileSync(process.argv[4], JSON.stringify(out, null, 1));
console.log(`wrote ${Object.keys(out).length} entries to ${process.argv[4]}`);
```

### 9.4 `page_diff.py`: the example page without the changed scripts

```python
"""Compare two report pages except the text of the named assets.

python page_diff.py PAGE_A ASSETS_A PAGE_B ASSETS_B NAME...
NAME is an asset path under src/pulseq_reports/assets, for example seq_lanes.js or
cards/diagram.js. Each page gets the text of its own worktree's asset replaced by a
marker. The rest of the two pages must then be equal. Prints the first difference.
"""

import sys
from pathlib import Path


def masked(page: Path, assets: Path, names: list[str]) -> str:
    text = page.read_text(encoding="utf-8")
    for name in names:
        script = f"<script>\n{(assets / name).read_text(encoding='utf-8')}\n</script>"
        if text.count(script) != 1:
            sys.exit(f"{name}: found {text.count(script)} times in {page}")
        text = text.replace(script, f"<script>@@{name}@@</script>")
    return text


page_a, assets_a, page_b, assets_b, *names = sys.argv[1:]
a = masked(Path(page_a), Path(assets_a), names)
b = masked(Path(page_b), Path(assets_b), names)
if a == b:
    print(f"equal outside {', '.join(names) or 'no asset'}")
    sys.exit(0)
i = next(k for k in range(min(len(a), len(b))) if a[k] != b[k])
print(f"differ at character {i}:\nA: {a[i - 80 : i + 80]!r}\nB: {b[i - 80 : i + 80]!r}")
sys.exit(1)
```

### 9.5 `s9_check.js`: the block starts of the backward walk

```js
// S9 check: every block start that seq_lanes.js hands on equals the forward sum from 0.
// node s9_check.js SEQ_LANES_JS IN.json
// Loads a copy of SEQ_LANES_JS with a check line before each anchor below, then runs
// views whose first edge is each block start in turn. Prints OK or FAIL.
const fs = require("node:fs"), os = require("node:os"), path = require("node:path");
const zlib = require("node:zlib");
const CHECK = where => `if (${where[1]} !== global.__STARTS[${where[0]}]) ` +
  `global.__BAD.push(["${where[2]}", ${where[0]}]);\n`;
const HOOKS = [
  // [anchor, block index, start, name]. The check line goes before the anchor.
  ["if (start + duration >= lo) fn(i, start, duration);", "i", "start", "_forEachBlockInRange"],
  ["let i = fromBlock, start = fromStart;\n    while (i >= 0)", "fromBlock", "fromStart", "_prevLinePoint"],
  ["let i = fromBlock, start = fromStart;\n    while (i < N)", "fromBlock", "fromStart", "_nextLinePoint"],
];
let src = fs.readFileSync(process.argv[2], "utf8");
for (const [anchor, i, start, name] of HOOKS) {
  if (src.split(anchor).length !== 2) throw new Error(`anchor of ${name} not found once`);
  src = src.replace(anchor, CHECK([i, start, name]) + anchor);
}
const copy = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "s9-")), "seq_lanes.js");
fs.writeFileSync(copy, src);
const SeqLanes = require(copy);
const TYPES = {uint8: Uint8Array, uint16: Uint16Array, uint32: Uint32Array, float64: Float64Array};
const dec = t => {
  const raw = zlib.gunzipSync(Buffer.from(t.data, "base64"));
  const c = new Uint8Array(raw.length);
  c.set(raw);
  return new TYPES[t.dtype](c.buffer, 0, t.length);
};
let total = 0;
for (const [name, f] of Object.entries(JSON.parse(fs.readFileSync(process.argv[3], "utf8")))) {
  const tables = {};
  for (const [k, t] of Object.entries(f.tables)) tables[k] = dec(t);
  const m = SeqLanes.decode(1, tables, f.lanes);
  const n = m.numBlocks, starts = new Float64Array(n + 1);
  for (let i = 0; i < n; i++) starts[i + 1] = starts[i] + tables.durations[tables.duration_index[i]];
  global.__STARTS = starts;
  global.__BAD = [];
  for (let a = 0; a < n; a++) {
    SeqLanes.exactLanes(m, starts[a], starts[Math.min(n, a + 2)]);
    SeqLanes.exactLanes(m, starts[a], starts[a]);
    SeqLanes.pointsIn(m, starts[a], starts[Math.min(n, a + 2)]);
  }
  total += global.__BAD.length;
  console.log(`${name}: ${n} blocks, starts that are not the forward sum: ${global.__BAD.length}`);
}
console.log(total === 0 ? "OK" : "FAIL");
```

`IN.json` is the output of section 9.2.

### 9.6 `time_py.py`: P1 to P4

```python
"""Times of the functions of P1 to P4 for N blocks with no ADC. A fresh process for each
run: uv run python time_py.py N"""

import resource
import sys
import time

import pypulseq as pp

sys.path.insert(0, "tests")
from synthetic import SYSTEM  # noqa: E402

from pulseq_reports import pns, waveforms  # noqa: E402
from pulseq_reports.seq_index import sequence_index  # noqa: E402
from pulseq_reports.seq_utils import NamedSequence  # noqa: E402

n = int(sys.argv[1])
seq = pp.Sequence(SYSTEM)
g = pp.make_trapezoid("x", area=100, system=SYSTEM)
d = pp.make_delay(1e-3)
for i in range(n // 2):  # no ADC: first_adc_window reads every block before this plan
    seq.add_block(g)
    seq.add_block(d)
seq.set_definition("TR", 2 * 1e-3)
named = [NamedSequence("no-adc", seq)]
sequence_index(seq)  # the first card of a real page builds it; not timed here


def timed(label, fn):
    start = time.perf_counter()
    fn()
    print(f"{label}: {time.perf_counter() - start:.3f} s")


timed("first_adc_window", lambda: waveforms.first_adc_window(named))
timed("full_window", lambda: waveforms.full_window(named))
timed("peak_tr_window", lambda: pns.peak_tr_window(seq, 0.0))
timed("block_rows(first 10 ms)", lambda: waveforms.block_rows(seq, 0.0, 0.01))
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # bytes on macOS
print(f"blocks in pypulseq's block cache: {len(seq.block_cache)}, peak RSS {rss / 1e6:.0f} MB")
```

### 9.7 `time_js.js`: decode and render times

```js
// node time_js.js ASSETS_DIR N: decode times and the 95th percentile of one render,
// for N repeating blocks (a pattern of RF, ADC and three gradient events).
const path = require("node:path");
const dir = path.resolve(process.argv[2]);
const N = Number(process.argv[3] || 1e7);
global.ChartMath = require(path.join(dir, "chart_math.js"));
const SeqLanes = require(path.join(dir, "seq_lanes.js"));
const GLanes = require(path.join(dir, "g_lanes.js"));
const PATTERN = [[1, 0, 2, 0, 1, 0], [0, 3, 0, 1, 0, 1], [4, 5, 6, 2, 0, 0], [0, 0, 0, 0, 0, 0],
  [1, 3, 0, 1, 1, 0]];
const duration_index = new Uint8Array(N), rf = new Uint8Array(N), adc = new Uint8Array(N);
const gx = new Uint8Array(N), gy = new Uint8Array(N), gz = new Uint8Array(N);
const durations = Float64Array.from([1e-3, 2.5e-3, 4e-3]);
const checkpoints = new Float64Array(Math.ceil(N / 1024));
let t = 0;
for (let i = 0; i < N; i++) {
  const p = PATTERN[i % PATTERN.length];
  gx[i] = p[0]; gy[i] = p[1]; gz[i] = p[2]; duration_index[i] = p[3]; rf[i] = p[4]; adc[i] = p[5];
  if (i % 1024 === 0) checkpoints[i / 1024] = t;
  t += durations[p[3]];
}
const tables = {
  duration_index, durations, checkpoints, rf, adc, gx, gy, gz,
  rf_delay: Float64Array.from([1e-4]), rf_mag_n: Uint32Array.from([4]),
  rf_mag_offset_at: Uint32Array.from([0]), rf_mag_at: Uint32Array.from([0]),
  rf_mag_offset: Float64Array.from([0, 1e-4, 2e-4, 2e-4]), rf_mag: Float64Array.from([0, 5, 5, 0]),
  rf_phase_n: Uint32Array.from([2]), rf_phase_offset_at: Uint32Array.from([0]),
  rf_phase_at: Uint32Array.from([0]), rf_phase_offset: Float64Array.from([0, 1e-4]),
  rf_phase: Float64Array.from([0, 0]), adc_delay: Float64Array.from([1e-5]),
  adc_length: Float64Array.from([6.4e-4]), grad_delay: new Float64Array(6),
  grad_n: new Uint32Array(6).fill(4), grad_offset_at: new Uint32Array(6),
  grad_at: Uint32Array.from([0, 4, 8, 12, 16, 20]),
  grad_offset: Float64Array.from([0, 1e-4, 6e-4, 7e-4]),
  grad_value: Float64Array.from([0, 15, 15, 0, 0, -22, -22, 0, 0, 9, 9, 0, 0, 5, 5, 0, 0, -8, -8,
    0, 0, 12, 12, 0]),
};
const meta = ["rf_mag", "rf_phase", "adc", "gx", "gy", "gz"].map(id => ({
  id, title: id, unit: "", color: id, kind: id === "adc" ? "gate" : "line", domain: [0, 1],
  ticks: [0], tick_labels: ["0"], empty: false, fill: id === "rf_phase" ? null : 0.0,
}));
let t0 = performance.now();
const seq = SeqLanes.decode(1, tables, meta);
const seqMs = performance.now() - t0;
t0 = performance.now();
const g = GLanes.decode(seq);
const gMs = performance.now() - t0;
let s = 99;
const rnd = () => (s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
const dur = seq.durationS, seqTimes = [], gTimes = [];
for (let v = 0; v < 200; v++) {
  const span = dur * Math.pow(10, -6 * rnd()); // from the whole file down to 1e-6 of it
  const a = rnd() * (dur - span);
  const viewMs = [a * 1000, (a + span) * 1000];
  let u = performance.now();
  SeqLanes.lanesFor(seq, viewMs, 812);
  seqTimes.push(performance.now() - u);
  u = performance.now();
  GLanes.minMax(g, a, a + span, 812);
  gTimes.push(performance.now() - u);
}
const p95 = xs => xs.slice().sort((x, y) => x - y)[Math.floor(0.95 * xs.length)].toFixed(1);
console.log(`N=${N} SeqLanes.decode ${seqMs.toFixed(0)} ms, GLanes.decode ${gMs.toFixed(0)} ms, ` +
  `lanesFor p95 ${p95(seqTimes)} ms, GLanes.minMax p95 ${p95(gTimes)} ms`);
```

### 9.8 `p6.js`: memory for many distinct gradient events

```js
// P6: memory of the |G| and PNS models for a file with many distinct gradient events.
// node --expose-gc --max-old-space-size=16000 p6.js ASSETS_DIR NUM_EVENTS
// Each block (1 ms, 100 raster samples) plays its own gx event. gy and gz come from a
// small shared set. Prints the growth of the heap and the array buffers for each decode.
const path = require("node:path");
const dir = path.resolve(process.argv[2]);
global.ChartMath = require(path.join(dir, "chart_math.js"));
const SeqLanes = require(path.join(dir, "seq_lanes.js"));
const GLanes = require(path.join(dir, "g_lanes.js"));
const PnsLanes = require(path.join(dir, "pns_lanes.js"));
const M = Number(process.argv[3]), N = M, SHARED = 8, E = M + SHARED;
const mem = () => { global.gc(); const u = process.memoryUsage(); return u.heapUsed + u.arrayBuffers; };
const grad_at = new Uint32Array(E), grad_value = new Float64Array(4 * E);
for (let e = 0; e < E; e++) {
  grad_at[e] = 4 * e;
  const a = ((e * 7919) % 2001 - 1000) / 40;
  grad_value.set([0, a, a, 0], 4 * e);
}
const gx = new Uint32Array(N), gy = new Uint32Array(N), gz = new Uint32Array(N);
for (let i = 0; i < N; i++) { gx[i] = SHARED + i + 1; gy[i] = 1 + (i % SHARED); gz[i] = 1 + ((i * 3) % SHARED); }
const checkpoints = new Float64Array(Math.ceil(N / 1024));
for (let c = 0; c < checkpoints.length; c++) { let t = 0; for (let i = 0; i < c * 1024; i++) t += 1e-3; checkpoints[c] = t; }
const f = () => new Float64Array(0), u = () => new Uint32Array(0);
const tables = {
  duration_index: new Uint8Array(N), durations: Float64Array.from([1e-3]), checkpoints,
  rf: new Uint8Array(N), adc: new Uint8Array(N), gx, gy, gz,
  rf_delay: f(), rf_mag_n: u(), rf_mag_offset_at: u(), rf_mag_at: u(), rf_mag_offset: f(),
  rf_mag: f(), rf_phase_n: u(), rf_phase_offset_at: u(), rf_phase_at: u(), rf_phase_offset: f(),
  rf_phase: f(), adc_delay: f(), adc_length: f(),
  grad_delay: new Float64Array(E), grad_n: new Uint32Array(E).fill(4),
  grad_offset_at: new Uint32Array(E), grad_at,
  grad_offset: Float64Array.from([0, 1e-4, 9e-4, 1e-3]), grad_value,
};
const meta = ["rf_mag", "rf_phase", "adc", "gx", "gy", "gz"].map(id => ({
  id, title: id, unit: "", color: id, kind: id === "adc" ? "gate" : "line", domain: [0, 1],
  ticks: [0], tick_labels: ["0"], empty: false, fill: id === "rf_phase" ? null : 0.0,
}));
const hwAxis = {tau1: 0.2, tau2: 0.03, tau3: 3, a1: 0.4, a2: 0.1, a3: 0.5, stim_limit: 30, g_scale: 0.35};
const bins = Math.ceil(N * 100 / 615);
const pns = {dtS: 1e-5, gradScale: 1, binSamples: 615, hw: {x: hwAxis, y: hwAxis, z: hwAxis},
  levels: {min: new Float32Array(bins), max: new Float32Array(bins)}};
const m0 = mem();
let t = performance.now();
const seq = SeqLanes.decode(1, tables, meta);
const m1 = mem(), tSeq = performance.now() - t;
t = performance.now();
const g = GLanes.decode(seq);
const m2 = mem(), tG = performance.now() - t;
t = performance.now();
const p = PnsLanes.decode(tables, pns);
const m3 = mem(), tP = performance.now() - t;
const MB = x => (x / 1e6).toFixed(0);
console.log(`events=${M}: SeqLanes +${MB(m1 - m0)} MB ${tSeq.toFixed(0)} ms; ` +
  `GLanes +${MB(m2 - m1)} MB ${tG.toFixed(0)} ms; PnsLanes +${MB(m3 - m2)} MB ` +
  `${tP.toFixed(0)} ms (tables ${MB(m0)} MB)`);
if (!g || !p || !seq) throw new Error("unreachable");
```
