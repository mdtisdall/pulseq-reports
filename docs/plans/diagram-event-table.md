# Plan: a sequence diagram for files of up to 10^7 blocks

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: not started. The plan was written on 2026-09-19.

## 1. Goal

Change the sequence diagram card so that it works for each `.seq` file of up to
10^7 blocks:

1. In each view of each file, the chart shows the exact waveform points when
   the view has few enough points. There are no pre-selected windows and no
   point budget.
2. In a view with too many points, the chart shows the exact minimum and the
   exact maximum of each lane in each of the plot's time bins. No peak and no
   event is lost.
3. The page size grows approximately as the compressed `.seq` file, not as the
   expanded waveform.
4. Zoom and pan are interactive (section 2.6 has the numbers).

The page stays one self-contained HTML file. The page does not read a `.seq`
file when a person views it.

This plan changes the diagram card only. The other cards (PNS, RF exposure,
gradient limits, gradient spectrum) can have problems at 10^7 blocks. Each of
them must find its own solution in a different plan (section 2.8).

This plan does not support the Pulseq rotation extension. A separate plan adds
it. Until then, the cards that use gradients refuse a sequence with rotations
(phase 6, section 2.10).

After this plan, the user tags `v0.1.0` (phase 5).

## 2. Read this first (context for the executing agent)

### 2.1 The state of the repository

- Repository: `~/dev/pulseq-reports`, GitHub `mdtisdall/pulseq-reports`
  (public). The default branch is `main`.
- The first plan, `docs/plans/pulseq-reports.md`, is complete (PRs #1 to #10).
  Read its section 2 for the project decisions and its section 3 for the
  workflow. Those rules apply to this plan too, except where this plan
  changes them.
- `v0.1.0` is not tagged. No consumer uses the library yet. Thus this plan can
  change the public API of the diagram card.
- `TODO.md` has the item "Draw the sequence diagram from the event table in
  the browser". This plan is that item. Phase 5 deletes the item.

### 2.2 The current diagram (what this plan replaces)

Read these files before you start:

- `src/pulseq_reports/waveforms.py`:
  - `_BlockEvents`, `_block_events`, `_timed_blocks`, `_events_in_range`:
    the diagram content of one block, and the blocks in play order.
  - `file_lanes(seq, start_s, end_s)`: the exact lanes. With no range, it
    gives the same lanes as vb-pulseq `sequence_data` (parity is checked).
    **This function is the reference for the new JavaScript.** Keep it.
  - `block_rows`, `duration_s`, `TimeWindow`, `first_adc_window`,
    `full_window`: keep them.
  - `DIAGRAM_POINT_BUDGET`, `point_count`, `_Envelope`, `file_envelope`:
    phase 4 removes them.
- `src/pulseq_reports/cards/diagram.py`: `diagram_card(seqs, windows,
  card_id, point_budget)` with "lane sets". Phase 4 replaces the data and
  removes `point_budget`.
- `src/pulseq_reports/assets/cards/diagram.js`: the card script. Phase 4
  replaces it.
- `src/pulseq_reports/assets/lane_chart.js`: `PulseqReport.laneChart`. The
  lanes are fixed data. Phase 3 adds a lane provider.
- `src/pulseq_reports/assets/page.js`: it calls `init(section, data)` and
  expects a synchronous function. Phase 3 lets `init` return a promise.
- `src/pulseq_reports/page.py`: the script order is `chart_math.js`,
  `lane_chart.js`, card scripts, `extra_scripts`, `page.js`. Phase 2 adds
  `seq_lanes.js` after `lane_chart.js`.

### 2.3 Decisions that are already made

Do not open these decisions again. The user made them or approved them.

1. **Target: 10^7 blocks in each file.** The budgets in section 2.6 are for one
   file. A page with N files costs approximately N times that. There is no
   limit on the total page size.
2. **Remove the old API.** Remove `point_budget`, `DIAGRAM_POINT_BUDGET`,
   `point_count`, `file_envelope`, `_Envelope` and the lane sets. Keep
   `file_lanes` and `block_rows`. Windows stay as shortcut buttons.
3. **RF phase lane:** when zoomed out, show the minimum and the maximum of
   the phase in each bin, as for the other lanes.
4. **Release:** tag `v0.1.0` after this plan, in phase 5, only after the user
   approves.
5. **Other cards:** this plan does not make them work at 10^7 blocks. Phase 5
   adds a `TODO.md` item for them.
6. **No new dependency.** Use Python `gzip` and `base64` (standard library).
   In the browser, use `DecompressionStream("gzip")` (built in). In the Node
   test harness, use `zlib` (built in). Do not add a JavaScript dependency or
   a build step. Decision 9 of the first plan still applies.
7. **No DOM tests.** Node tests cover only pure functions. Check each chart in
   a real browser with the `dev-workflow:browser-check-localhost` skill.
8. **Rotation extension: a separate plan.** This plan only reserves the names
   in the data format (section 4.6) and adds a guard (phase 6). The separate
   plan uses these decisions:
   - The diagram shows the rotated gradient axes first, with a button for the
     logical events as they are stored.
   - Rotations come from pypulseq (section 2.10), not from a `.seq` reader of
     this library.
9. **Refuse rotations until they are supported.** Each card that uses the
   gradients (diagram, gradient spectrum, PNS, gradient limits) raises an error
   for a sequence with a rotation extension. Do not draw unrotated gradients
   as if they were correct.

### 2.4 Facts about pypulseq 1.5.0.post1 (verified on 2026-09-19)

- `seq.block_events[block_id]` is a numpy array of 7 integers:
  `[delay, rf, gx, gy, gz, adc, ext]`. A value of 0 means "no event". The
  delay column is a legacy column. The block duration is in
  `seq.block_durations[block_id]` (seconds, float).
- The event libraries are `seq.rf_library`, `seq.grad_library`,
  `seq.adc_library` and `seq.shape_library`. `gx`, `gy` and `gz` share
  `grad_library`. `grad_library.type[id]` is `"t"` (trapezoid) or `"g"`
  (arbitrary or extended trapezoid). One library row fully defines one event.
  A gradient with a different amplitude is a different row.
- `seq.get_block(block_id)` decompresses the shapes of the block. It costs
  about 18 µs for each block (0.7 s for 39,304 blocks).
- The extensions in `get_block` are triggers, labels and soft delays. None of
  them changes the RF, gradient or ADC events. There is no rotation extension
  in this version (section 2.10). The diagram shows the durations that are in the file (soft
  delays can change them on the scanner).
- An RF event with a different phase offset or frequency offset is a different
  library row, also when its shape is the same. RF spoiling makes one row for
  each phase value.
- Thus the expanded points of an event depend only on (library, event ID).
  Expand each unique event one time. To expand an event, call `get_block` on
  the first block that uses it, and take the event from that block.

### 2.5 Measurements (ex-vivo file 0, 39,304 blocks, 2026-09-19)

| Quantity | Value | At 10^7 blocks |
|---|---|---|
| Block table, raw (7 IDs + duration) | 32 B for each block | about 320 MB |
| Block table, gzip | 1.0 B (column-wise) to 2.4 B (row-wise) for each block | about 10 MB to 24 MB |
| Unique events | 24 RF, 75 gradient, 24 ADC, 3 shapes | similar, if the sequence repeats |
| Unique block durations | 8 | |
| `.seq` file | 39 B for each block | about 390 MB |
| `.seq` file, gzip | 7.1 B for each block | about 71 MB (95 MB after base64) |
| Block table as dense 8/16-bit columns (section 4.2), gzip | 0.06 B for each block | about 0.6 MB |
| pypulseq memory for the sequence | about 360 B for each block | about 3.6 GB |
| `pp.Sequence.read` | 0.2 s | about 50 s |

The 32-bit rows of the first two lines use the pypulseq library IDs. The dense
8/16-bit columns of section 4.2 compress much better, because each column is
nearly all repetition.

A shaped RF pulse has many samples (for example, a 6 ms SLR pulse at the
1 µs RF raster has 6000). With RF spoiling, each phase value is a new RF event
with the same shape. Section 4.2 lets events share equal offset and value
arrays, so the page has each shape one time. The phase values are different
for each phase offset, so they are not shared.

The worst case is a sequence with a new event in most blocks (for example,
a new gradient amplitude or a new RF phase in each block). Then the event
tables grow with the number of blocks. Phase 5 measures this case.

### 2.6 Budgets for one file of 10^7 blocks

Phase 5 measures these values. "Repeating" is a sequence like ex-vivo. "Worst
case" is a sequence with a shaped RF pulse, and a new phase-encode amplitude
and a new RF phase in each TR (task 5.1).

| Quantity | Repeating: must be | Worst case |
|---|---|---|
| Page size added by the diagram card | at most 40 MB | record the value |
| Python time to make the card data | at most 120 s | record the value |
| Browser: time from page open to first chart | at most 5 s | record the value |
| Browser: JavaScript memory after load | at most 400 MB | record the value |
| One zoom or pan render (`SeqLanes.lanesFor`, Node benchmark) | at most 50 ms (95th percentile) | at most 50 ms |

If a "must be" value fails, stop and tell the user. Do not change a budget
yourself.

### 2.7 Why the design has this form

1. **Why send tables, not points.** A sequence repeats a small set of events.
   The block table compresses to about 0.06 B for each block (section 2.5).
   The expanded points do not repeat in time, and they do not compress in the
   same way.
2. **Why not put the `.seq` file in the page.** The `.seq` file has the same
   information, but:
   - It is about 100 times larger after gzip (7.1 B against 0.06 B for each
     block, section 2.5). At 10^7 blocks, it alone is more than the page
     budget.
   - The browser would need a second `.seq` reader and event expander (shape
     decompression, arbitrary gradients and extended trapezoids with time
     shapes, RF time shapes and offsets, raster units, file versions). With
     the tables, pypulseq is the only decoder: Python expands each unique
     event one time, and the browser only adds times.
   - A JavaScript reader would compute times from integer raster counts and
     decimal text, not from the pypulseq floats. Then the golden test could
     not require exact equality with `file_lanes`.
   - The library API takes `pp.Sequence` objects. A consumer does not have
     to write a `.seq` file.
3. **Why the offsets are separate from the delay.** The Python reference
   computes an event point time as `(block_start + delay) + offset`. If the
   browser does the same float operations in the same order, the result is
   bit-for-bit equal. Thus the golden test (phase 4) can require exact
   equality, with no tolerance. For this reason:
   - Phase 1 changes `seq_utils.gradient_points` and `waveforms._block_events`
     so that they use a helper that returns `(delay, offsets, values)`. The
     results stay bit-for-bit equal (the arithmetic is the same).
   - The block start times come from the same sequential sum as
     `waveforms._timed_blocks`: `start += duration`, in play order, from 0.0.
4. **Why checkpoints for the start times.** A `Float64Array` of 10^7 start
   times is 80 MB. The page sends the start time of each 1024th block. The
   browser adds the durations from the nearest checkpoint. This is the same
   sequential sum, so the result is bit-for-bit equal.
5. **Why a tree over groups of blocks.** A zoomed-out render must find the
   minimum and the maximum of about 10^7 blocks in each of about 800 bins,
   in less than 50 ms. The browser makes a tree of minimum and maximum values
   over groups of 64 blocks. Then each bin costs O(log N), plus the blocks of
   two partial groups, plus a scan of at most 1024 durations to find the block
   at each edge (section 4.4, item 5).
6. **The lane is a polyline.** `file_lanes` makes each line lane (RF |B1|,
   Gx, Gy, Gz) one polyline: a zero point at time 0, all event points in play
   order, and a zero point at the end of the file. The chart draws straight
   lines between the points, also across blocks with no event. Thus, the
   minimum and the maximum of a lane in a bin are at a point in the bin, or at
   one of the two bin edges (linear interpolation). There is no other case.
   The RF phase lane is different: it has one segment for each RF pulse, and
   no line between pulses.

### 2.8 Other cards at 10^7 blocks (out of scope)

These problems are known. Do not fix them in this plan. Phase 5 records them
in `TODO.md`.

- **PNS:** pypulseq `calculate_pns` uses the whole sampled waveform. A 1 h
  file is about 3.6 × 10^8 samples for each axis, so several GB. It needs a
  chunked or windowed method.
- **RF exposure and gradient limits:** they call `get_block` for each block.
  At 10^7 blocks this takes minutes. They can use the tables of phase 1.
- **Gradient spectrum:** it is chunked. Its time grows with the duration, not
  the number of blocks (about 50 s for 1 h).
- **Block table card:** it reads only the rows that it shows. No problem.

### 2.9 Terms

- **Tables.** The data that phase 1 makes: the block table and the event
  tables of one file.
- **Block table.** For each block: the duration index and the RF, Gx, Gy, Gz
  and ADC event indexes.
- **Event tables.** For each unique event: its delay, its offsets and its
  values.
- **Model.** The JavaScript object that `SeqLanes.decode` makes from the
  tables of one file.
- **Exact view.** A view where the chart shows the exact points.
- **Min/max view.** A view where the chart shows the minimum and the maximum
  in each bin.
- **Bin.** One of the equal time intervals of a min/max view.
- **Worker.** A sub-agent that the executing agent starts with the Agent tool.

### 2.10 The rotation extension (status on 2026-09-19)

- The Pulseq format has a rotation extension. MATLAB Pulseq (`mr.makeRotation`,
  the 1.5.1 branch) keeps a library of unit quaternions, with at most one
  rotation in each block. The gradient events in the library are logical. The
  rotation is applied to the gradients of the block when the waveforms are made
  (`mr.rotate3D`). A radial or PROPELLER sequence can thus use a few gradient
  events and a different rotation in each block.
- pypulseq 1.5.0.post1 (the latest release on PyPI) has no rotation
  extension. `pp.rotate` makes new, rotated gradient events; it is not the
  extension.
- pypulseq discussion #184 (https://github.com/pulseq/pypulseq/discussions/184)
  plans the extension. Draft PR #372 ("[v1.5.1] Add rotation extension", by
  mcencini, open, last updated 2026-05-07) adds `make_rotation`, a
  `seq.rotation_library` of scalar-first quaternions, and a call of `rotate3D`
  on the gradients of a block that has a rotation. Related open PRs: #302 and
  #378 (`rotate3D`), #341 (a refactor of `get_block`).
- It is not known what pypulseq 1.5.0.post1 does when it reads a `.seq` file
  with a rotation section (it can ignore it, or raise an error). Task 6.1 finds
  out.
- Consequence: at present, a sequence with rotations can give unrotated
  gradients in each card without a warning. Phase 6 prevents that.

## 3. How to execute this plan

### 3.1 Workflow

Use the dev-workflow Claude Code plugin skills, as in the first plan.

1. Each phase is one branch, one worktree and one pull request.
2. Start each phase with the `dev-workflow:start-task` skill, from the latest
   `origin/main`. The branch prefix is `feature/`, `fix/`, `docs/` or
   `chore/`. The worktree script refuses `feat/`.
3. Run `nix develop --command scripts/check` before each PR.
4. Open each PR with the `dev-workflow:ship` skill.
5. Show the commit message to the user and wait for approval before
   `git commit`. The user usually approves several commits at one time.
6. Merge only when the user tells you to. Use `dev-workflow:finish-task`. The
   user approves the cleanup of the branch and the worktree separately, unless
   they say otherwise.
7. Give work to workers with the `dev-workflow:parallel-agents` skill. Workers
   do not run git write commands. You review each diff.
8. The user wants at most three PRs open at one time.
9. `TESTS.md` must have one entry for each test (`scripts/check_tests_md.py`).
   A PR that adds, removes or changes a test changes `TESTS.md`.

### 3.2 Worker model tiers

| Tier | Model | Use it when |
|---|---|---|
| H | `haiku` | The task is a mechanical copy, rename or removal with an exact file list. It needs no design decision. |
| S | `sonnet` | The task writes new code or tests from a full specification in this plan. It needs local decisions only. |
| O | the executing Opus agent, not a worker | The task sets an interface, needs judgment about exactness or performance, or reviews other work. |

Rules for workers:

1. Give each worker the full paths of the files that it owns, the files that
   it may read, and the files that it must not edit.
2. Give each worker the exactness rule (section 3.5) when it changes
   `seq_utils.py`, `waveforms.py` or `seq_lanes.js`.
3. A tier H or S worker that finds a design problem stops and reports it. It
   does not change the data format of section 4.
4. Workers put scratch files in the session scratchpad directory, not in the
   worktree.

### 3.3 Order and parallel work

```
Phase 0 (TESTS.md skeleton) ──┬─► Phase 1 (Python tables)          ─┐
                              ├─► Phase 2 (JavaScript SeqLanes)    ─┼─► Phase 4 (card, golden test) ─► Phase 5 (scale, release)
                              ├─► Phase 3 (chart hook, async init) ─┘
                              └─► Phase 6 (rotation guard) ──────────────────────────────────► (before Phase 5)
```

- Phase 0 is first. It is small.
- Phases 1, 2 and 3 can run in parallel after phase 0 is merged. They edit
  different files (section 3.4). Phase 2 does not need the code of phase 1:
  it uses the data format of section 4, and its unit tests make small tables
  by hand.
- Phase 6 can run in parallel with phases 1, 2 and 3 after phase 0 is merged.
  It must be merged before phase 5. Phase 6 makes the guard function; phase 4
  uses it in the diagram card. If phase 4 starts before phase 6 is merged,
  phase 4 adds the guard call after phase 6 is merged (rebase).
- The user wants at most three PRs open at one time. Phases 1, 2, 3 and 6 are
  four PRs: start phase 6 when one of the others is merged, or ask the user.
- Phase 4 starts after phases 1, 2 and 3 are all merged.
- Phase 5 starts after phases 4 and 6 are merged.

### 3.4 File ownership

Each file has one owner phase at a time. Package root:
`src/pulseq_reports/`. Tests: `tests/`.

| Phase | Files that the phase creates or edits |
|---|---|
| 0 | `TESTS.md` (only: add four placeholder sections, see task 0.1), this plan file (only if it is not on `main` yet) |
| 1 | `seq_utils.py`, `waveforms.py` (only the helper changes of tasks 1.1 and 1.2; not the removals of phase 4), `diagram_data.py` (new), `tests/test_seq_utils.py`, `tests/test_diagram_data.py` (new), `TESTS.md` sections 2.1 and 2.18 |
| 2 | `assets/seq_lanes.js` (new), `page.py`, `tests/js/test_seq_lanes.js` (new), `tests/test_page.py`, `TESTS.md` sections 2.3 and 2.19 |
| 3 | `assets/lane_chart.js`, `assets/page.js`, `assets/chart_math.js`, `tests/js/test_chart_math.js`, `TESTS.md` section 2.4 |
| 4 | `cards/diagram.py`, `assets/cards/diagram.js`, `waveforms.py` (the removals), `tests/test_waveforms.py`, `tests/test_diagram_card.py`, `tests/test_seq_lanes_golden.py` (new), `tests/js/golden_seq_lanes.js` (new), `docs/usage.md`, `scripts/vb_parity.py`, `TESTS.md` sections 2.15, 2.16 and 2.20 |
| 5 | `scripts/diagram_scale.py` (new), `TODO.md`, this plan file (status only), `README.md` (only if a sentence about the diagram is wrong) |
| 6 | `extensions.py` (new), `cards/spectrum.py`, `cards/pns.py`, `cards/gradient_limits.py`, `tests/test_extensions.py` (new), `tests/data/` (new, only if task 6.4 needs a `.seq` file), `TESTS.md` section 2.21, `docs/usage.md` (only a short "Rotation extension" section) |

Rules:

1. A phase edits only its own files.
2. If a phase needs a change to a file of another open phase, stop. Tell the
   user. Make the change in the owner phase, or wait until it is merged.
3. `TESTS.md`: phase 0 adds the placeholder sections. Each later phase
   replaces only the placeholder lines and entries in its own sections. An
   unchanged heading line separates each pair of sections, so git merges the
   edits without a conflict. If a rebase gives a conflict in `TESTS.md`, keep
   both sides.
4. `waveforms.py` is in phases 1 and 4. They do not run at the same time
   (phase 4 starts after phase 1 is merged).
5. `docs/usage.md` is in phases 4 and 6. Phase 6 adds only a new section at
   the end of the file. Phase 4 changes the diagram text. If phase 4 is rebased
   on phase 6, keep both.

### 3.5 The exactness rule

The Python function `waveforms.file_lanes` is the reference. The JavaScript
must give the same numbers, bit for bit, for the exact view. To keep this
true:

1. Transmit every float as IEEE 754 float64 (a `Float64Array` in the page).
   Do not round, and do not use JSON numbers for table data.
2. Compute each point time as `(blockStart + delay) + offset`, in that order.
3. Compute each block start as the sequential sum `start += duration` in play
   order, from the checkpoint at or before the block (section 4.3).
4. Convert seconds to ms as `t * 1000` at the output, not before.
5. Do not change the arithmetic of `file_lanes` (phase 1 changes only where
   the arithmetic is, not what it is). Check this with a byte-for-byte test
   against the current `main` (task 1.1, item 4).

## 4. The data format (set by this plan)

Phases 1, 2 and 4 use this format. Do not change it without the user's
approval. If a phase finds a problem, stop and report it.

### 4.1 Card data

`diagram_card` writes this JSON as the card data:

```json
{
  "format": 1,
  "files": [
    {
      "name": "segment_0.seq",
      "duration_s": 369.92,
      "num_blocks": 39304,
      "lanes": [ {"id": "rf_mag", "title": "RF |B1|", "unit": "µT", "color": "rf",
                  "kind": "line", "domain": [0, 14.3], "ticks": [0, 13], "tick_labels": ["0", "13"],
                  "empty": false, "fill": 0.0}, "... six lanes in file_lanes order, without segments or windows ..."],
      "tables": { "<table name>": {"dtype": "uint16", "length": 39304, "data": "<base64 of gzip>"}, "..." }
    }
  ],
  "windows": [ {"label": "First ADC (0–3.22 ms)", "file": 0, "view_ms": [0.0, 3.223]} ]
}
```

- `lanes` is `file_lanes(seq)` without the `segments` and `windows` keys.
  Thus the lane titles, colours, domains and ticks are equal to vb-pulseq for
  the whole file, and the y axis does not change when the view changes.
- `dtype` is one of `uint8`, `uint16`, `uint32`, `float64`. The data is the
  little-endian bytes of the array, compressed with gzip (level 6), then
  base64. Each table is compressed separately, so that each decompressed
  buffer is aligned for its typed array.
- A window label has the file name at the start when there is more than one
  file, as now.

### 4.2 The tables of one file

`N` is the number of blocks. Indexes are dense and start at 1. The value 0
means "no event". The width of an index column is the smallest of `uint8`,
`uint16`, `uint32` that holds the largest value.

| Table | dtype | Length | Content |
|---|---|---|---|
| `duration_index` | uint8/16/32 | N | index into `durations` (0-based) |
| `durations` | float64 | number of unique durations | the unique values of `seq.block_durations`, in first-seen order |
| `checkpoints` | float64 | ceil(N / 1024) | start time (s) of block 0, 1024, 2048, ... |
| `rf` | uint8/16/32 | N | dense RF event index, 0 = none |
| `gx`, `gy`, `gz` | uint8/16/32 | N | dense gradient event index, 0 = none (one gradient index space for the three axes) |
| `adc` | uint8/16/32 | N | dense ADC event index, 0 = none |
| `rf_delay` | float64 | R | `rf.delay` of each RF event |
| `rf_mag_n` | uint32 | R | the number of magnitude points of each RF event |
| `rf_mag_offset_at` | uint32 | R | where the event's offsets start in `rf_mag_offset` |
| `rf_mag_at` | uint32 | R | where the event's values start in `rf_mag` |
| `rf_mag_offset` | float64 | pool | offset arrays `[0, rt..., rt[-1]]` (s) |
| `rf_mag` | float64 | pool | value arrays `[0, |B1| (µT)..., 0]` |
| `rf_phase_n`, `rf_phase_offset_at`, `rf_phase_at` | uint32 | R each | the same, for the phase points |
| `rf_phase_offset` | float64 | pool | offset arrays `rt[keep]` (s) |
| `rf_phase` | float64 | pool | phase arrays (rad) |
| `grad_delay` | float64 | G | the gradient delay of each gradient event |
| `grad_n`, `grad_offset_at`, `grad_at` | uint32 | G each | the same, for the gradient points |
| `grad_offset` | float64 | pool | offset arrays of `seq_utils.gradient_offsets` (s) |
| `grad_value` | float64 | pool | amplitude arrays (mT/m) |
| `adc_delay` | float64 | A | `adc.delay` of each ADC event |
| `adc_length` | float64 | A | `adc.num_samples * adc.dwell` of each ADC event (s) |

Event `k` (1-based) of a kind has `n = *_n[k - 1]` points. Its offsets are
`*_offset[*_offset_at[k - 1] + p]` and its values are `*[*_at[k - 1] + p]`, for
`p = 0 ... n - 1`. A pool holds each distinct array one time: two events with
equal arrays (equal bytes) point to the same place. The offsets and the values
are shared separately (for example, phase-encode gradients share their offsets
but not their amplitudes).

The event values are exactly the values that `waveforms._block_events`
computes for that event (after the refactor of task 1.1): the same `mag`,
`phase` and `keep` arrays, and the same gradient amplitudes in mT/m.

### 4.3 How the browser computes times

- Start of block `i` (0-based): take `c = floor(i / 1024)`, start from
  `checkpoints[c]`, and add `durations[duration_index[j]]` for
  `j = 1024·c, ..., i − 1`, one at a time.
- End of the file: the start of block `N − 1` plus its duration. This equals
  `duration_s` of the file data and `waveforms.duration_s(seq)`.
- Point `p` of RF magnitude event `k` in block `i`:
  `t = (start_i + rf_delay[k−1]) + rf_mag_offset[p]`.
- Gradient and RF phase points: the same form, with their own delay and
  offsets.
- ADC window: `a0 = start_i + adc_delay[k−1]`, `a1 = a0 + adc_length[k−1]`.
- Output times in ms: `t * 1000`.

### 4.4 The JavaScript API (`assets/seq_lanes.js`)

One global object `SeqLanes`, and `module.exports = SeqLanes` in Node, as in
`chart_math.js`. All functions are pure (no DOM, no network).

```js
SeqLanes.decode(format, tables, lanesMeta)  // tables: {name: TypedArray}; returns a model
SeqLanes.blockStart(model, i)       // s
SeqLanes.blockAt(model, t)          // the block with start ≤ t < start + duration (s); see item 4
SeqLanes.exactLanes(model, t0, t1)  // lanes (file_lanes JSON form) for [t0, t1] (s)
SeqLanes.minMaxLanes(model, t0, t1, bins)
SeqLanes.pointsIn(model, t0, t1)    // the number of event points in [t0, t1] (see item 3)
SeqLanes.lanesFor(model, viewMs, bins)  // {lanes, exact: bool}: the lanes for laneChart
SeqLanes.EXACT_POINT_LIMIT          // 20000 (phase 5 can tune it, with the user's approval)
```

Behavior:

1. **`exactLanes`.** For each line lane (RF |B1|, Gx, Gy, Gz): one segment
   with the points of the whole-file polyline (section 2.7, item 6) whose time
   is in [t0, t1], and also the last point before t0 and the first point after
   t1, when they exist. The whole-file polyline includes the zero point at
   time 0 and the zero point at the end. For RF phase: one segment for each
   RF pulse that has a phase point in [t0, t1], with all the phase points of
   that pulse. A pulse with no phase point (a pulse with zero amplitude) gives
   no segment; `file_lanes` gives an empty segment for it, and the golden test
   removes empty segments from the reference before the comparison. For the ADC lane: the windows that overlap [t0, t1]. Times in
   ms. The lane metadata comes from `lanesMeta`.
2. **`minMaxLanes`.** The bin edges are `e_k = t0 + (t1 − t0) · k / bins`, for
   `k = 0 ... bins`, computed with this formula in seconds. The output times
   are `e_k * 1000` and `(e_k + (e_(k+1) − e_k) / 2) * 1000`. The Python
   reference of the golden test uses the same formulas. A point at time `t` is
   in bin `k` when `e_k ≤ t < e_(k+1)`. A point at `t1` is in the last bin.
   - Line lanes: the minimum and the maximum in bin `k` are the minimum and
     the maximum of (the points in the bin) and (the polyline value at `e_k`
     and at `e_(k+1)`). The polyline value at an edge is linear
     interpolation between the neighbouring points, with the formula of
     `numpy.interp`: `fp[j] + (fp[j+1] − fp[j]) / (xp[j+1] − xp[j]) · (x − xp[j])`.
     The lane has one segment: `(e_k, min_k), (centre_k, max_k)` for each bin,
     in ms.
   - RF phase: the same, with the points of the phase segments only. An edge
     value exists only when the edge is between two points of one pulse. A
     bin with no value ends the segment. The next bin with a value starts a
     new segment.
   - ADC: a bin is "on" when an ADC window overlaps `[e_k, e_(k+1))`. The lane
     has one window for each run of "on" bins, from the first edge to the last
     edge of the run.
   - Each lane gets the key `"minmax": true`. The chart's tooltip then shows
     the minimum and the maximum of the bin at the cursor (task 3.1).
3. **`lanesFor`.** `pointsIn` counts the RF magnitude, RF phase and gradient
   points of the blocks that overlap [t0, t1], and 2 for each ADC window. It
   does not count the zero points or the neighbour points. It uses the point
   totals of the groups (section 4.5), so it costs O(log N + 64), not O(blocks
   in the view). If
   `pointsIn(model, t0, t1) ≤ EXACT_POINT_LIMIT`, return `exactLanes`. Else
   return `minMaxLanes` with `bins`. `viewMs` is in ms; convert it to s with
   `/ 1000`.
4. **`blockAt`.** It returns the index of the block with
   `start ≤ t < start + duration`. Blocks of zero duration are never returned.
   For `t` equal to the end of the file, it returns the last block with a
   duration above zero. For `t` outside [0, end], it returns 0 or that last
   block.
5. **Cost.** `decode` is O(N). `lanesFor` is O(bins · (log N + 64 + 1024))
   for a min/max view, and O(log N + points) for an exact view. The block
   table of the model uses 6 to 11 B for each block when the event indexes fit
   in `uint8` or `uint16` (section 4.2). The memory budget is in section 2.6.

### 4.5 The model and the tree (design for phase 2)

- Keep the block table columns as typed arrays. Do not make a start time
  array of length N.
- For each event, compute at decode time: the minimum and the maximum of its
  values, and its number of points.
- Groups: 64 blocks in each group. For each group and each value lane
  (RF |B1|, RF phase, Gx, Gy, Gz): the minimum, the maximum (`Float64Array`),
  and "has an event" (`Uint8Array`). For each group: the total number of
  points (`Uint32Array`) and "has an ADC window". Make a binary tree (or a
  sparse table) over the groups for range queries.
- A min/max bin: find the first and the last block that overlap the bin
  (`blockAt`). Use the tree for the whole groups. Use the per-event minimum
  and maximum for whole blocks in the partial groups. Use the exact points
  only for the blocks that the bin edges cut. Add the two edge values.
- The two zero points of a line lane (at time 0 and at the end of the file)
  belong to no event. For the tree and for `exactLanes`, treat the first one
  as a point of block 0 and the last one as a point of block N − 1.
- An edge value on a lane needs the neighbouring points. They can be in a
  block far from the edge (a lane with no events for a long time). Find the
  previous and the next block with an event on that lane with the tree
  ("has an event"), in O(log N).

### 4.6 Names reserved for the rotation extension

The separate rotation plan will use these names. This plan does not make
them.

- The format number: `"format": 2` for data with rotations.
- Tables: `rotation` (uint8/16/32, length N, dense rotation index, 0 = none)
  and `rotations` (float64, 9 values for each rotation: the rotation matrix,
  row by row).
- `SeqLanes.decode` must raise an error for a `format` other than 1, and for
  a table name that it does not know. Then a page with new data does not show
  wrong waveforms with an old script.

## 5. Phases

Each phase lists its tasks and sub-tasks. Each item has a tier (section 3.2).

---

### Phase 0: TESTS.md skeleton

Branch: `docs/diagram-tests-skeleton`. Parallel: no. Tier of the phase: H.
Review: O.

**Task 0.1: Add four placeholder sections.** Tier H.

1. At the end of `TESTS.md`, after section 2.17, add these four sections in
   this order. Each has only its heading and one placeholder line:
   ```
   ### 2.18 Diagram tables (`test_diagram_data.py`)

   Phase 1 of `docs/plans/diagram-event-table.md` adds the entries.

   ### 2.19 Sequence lanes (`test_seq_lanes.js`)

   Phase 2 of `docs/plans/diagram-event-table.md` adds the entries.

   ### 2.20 Sequence lanes against Python (`test_seq_lanes_golden.py`)

   Phase 4 of `docs/plans/diagram-event-table.md` adds the entries.

   ### 2.21 Sequence extensions (`test_extensions.py`)

   Phase 6 of `docs/plans/diagram-event-table.md` adds the entries.
   ```
2. Commit this plan file in the same PR if it is not on `main` yet.

Acceptance: `scripts/check` passes. The sections exist.

---

### Phase 1: the tables in Python

Branch: `feature/diagram-tables`. Parallel: yes, with phases 2 and 3. Tier of
the phase: S, with O review of the exactness. Review: O.

**Task 1.1: Move the event arithmetic into helpers.** Tier S. Review O.

1. In `seq_utils.py`, add
   `gradient_offsets(g) -> tuple[float, np.ndarray, np.ndarray]`: the delay,
   the offsets (s) and the amplitudes (Hz/m) of one gradient event. For a
   trapezoid: `g.delay`, `np.cumsum([0.0, rise, flat, fall])`,
   `[0, A, A, 0]`. For an arbitrary gradient: `g.delay`, `g.tt` (and, when it
   has `first` and `shape_dur`: `[0.0, tt..., shape_dur]` with
   `[first, waveform..., last]`).
2. Change `gradient_points(g, t0)` to return `(t0 + delay) + offsets` and the
   amplitudes. The result must be bit-for-bit equal to the current function.
3. In `waveforms.py`, add a helper for one RF event that returns
   `(delay, mag_offsets, mag, phase_offsets, phase)` with the current formulas
   (`mag_offsets = [0, rt..., rt[-1]]`, `phase_offsets = rt[keep]`). Change
   `_block_events` to use it: `start = t + delay`, times `start + offsets`.
   Do not change any other function of `waveforms.py` in this task (task 1.2
   changes `_value_lane`).
4. Exactness check (a scratch script, not committed): for the synthetic
   sequences and one vb-pulseq sequence, `file_lanes`, `block_rows` and
   `gradient_points` give identical output (compare the JSON text, or use
   `numpy.array_equal`) on this branch and on `origin/main`. Use a baseline
   worktree as the `parallel-agents` skill says. Record the result in the PR.

**Task 1.2: Make the tables.** Tier S. Review O.

Write `diagram_data.py` with:

```python
CHECKPOINT_BLOCKS = 1024

def diagram_tables(seq: pp.Sequence) -> dict[str, np.ndarray]
    # the tables of section 4.2, as numpy arrays with the dtypes of section 4.2
def encode_tables(tables: dict[str, np.ndarray]) -> dict[str, dict]
    # {"dtype", "length", "data": base64(gzip(little-endian bytes))}
def decode_tables(encoded: dict[str, dict]) -> dict[str, np.ndarray]
    # the inverse, for the tests
def lane_meta(seq: pp.Sequence) -> list[dict]
    # file_lanes(seq) without "segments" and "windows"
```

1. Do not call `get_block` for each block. Read `seq.block_events` and
   `seq.block_durations` directly, in play order (the order of
   `seq.block_events`, a dict in insertion order), with numpy where possible.
   Build one column at a time (for example with `np.fromiter` and a small
   dtype). Do not build an (N, 7) `int64` array: at 10^7 blocks it is 560 MB.
2. Make the dense indexes: for each kind (RF, gradient, ADC), the unique
   library IDs in first-seen order, and their dense index (1-based).
3. Expand each unique event one time: call `seq.get_block` on the first block
   that uses it. Use the helpers of task 1.1, so the values are exactly those
   of `_block_events`.
4. The checkpoints: the sequential sum of `waveforms._timed_blocks` (the same
   Python float operations), taken at each 1024th block.
5. `lane_meta` must not call `file_lanes(seq)`: that builds the whole point
   list, which costs too much memory at 10^7 blocks. Compute each lane's peak
   from the per-event values, rounded as `markup._points` rounds them
   (`round(float(v), 4)`), because `_value_lane` takes its peak from the
   rounded points: the largest absolute rounded value, and 0 for a lane with
   no event. "Empty" comes from the event counts. Get the domain, ticks and tick
   labels from the same code as `waveforms._value_lane` and `_phase_lane`:
   move that code in `waveforms.py` into a helper that takes the peak, and make
   `_value_lane` call it (the output of `file_lanes` must not change). The
   result must equal `file_lanes(seq)` without `segments` and `windows` (test
   this).
6. Pools: put each distinct offset array and each distinct value array in its
   pool one time. Find equal arrays by their bytes (for example with a `dict`
   from `array.tobytes()` to the position). Do not compare with a tolerance.

**Task 1.3: Tests.** Tier S.

1. `tests/test_diagram_data.py`:
   - Rebuild the whole-file polyline of each lane from the decoded tables with
     numpy (the formulas of section 4.3). It must equal the unrounded points
     of `waveforms._events_in_range(seq, None, None)` exactly
     (`numpy.array_equal`), for the synthetic spin echo, GRE, arbitrary
     gradient and empty sequences.
   - `encode_tables` then `decode_tables` gives the same arrays and dtypes.
   - The index widths: `uint8` up to 255, `uint16` up to 65535, else `uint32`
     (test with small made-up arrays).
   - The checkpoints: equal to the sequential sum at blocks 0, 1024, 2048 (use
     a GRE sequence with more than 2048 blocks, for example
     `gre_sequence(num_trs=600)`, 3000 blocks; check that it is fast enough).
   - `lane_meta(seq)` equals `file_lanes(seq)` without segments and windows.
   - A sequence written with `seq.write` and read with `pp.Sequence.read`:
     the tables of the read sequence rebuild exactly the polylines of
     `waveforms._events_in_range` of the read sequence. The polylines of the
     read sequence and of the original sequence agree within 1e-9 s and a
     relative 1e-9 (the file stores durations as raster counts and decimal
     text, so the floats can differ in the last bits).
   - Two events with the same shape (for example, two RF events that differ
     only in phase offset) share their offset arrays in the pools.
2. `tests/test_seq_utils.py`: add a test for `gradient_offsets` (trapezoid and
   arbitrary).
3. `TESTS.md`: fill section 2.18. Add the new entry in section 2.1.

Acceptance: `scripts/check` passes. The exactness check of task 1.1 passes.

---

### Phase 2: the JavaScript module `SeqLanes`

Branch: `feature/seq-lanes`. Parallel: yes, with phases 1 and 3. Tier of the
phase: S for most tasks, O for the tree and the min/max bins. Review: O.

**Task 2.1: Decode and times.** Tier S.

1. Write `assets/seq_lanes.js` with `SeqLanes.decode`, `blockStart`, `blockAt`
   (section 4.4). `decode` takes typed arrays (already decompressed) and the
   lane metadata. It computes the per-event minimum, maximum and point counts.
   It raises an error for a `format` other than 1 and for a table name that
   it does not know (section 4.6). The caller passes the `format` value of the
   card data.
2. `blockAt(model, t)`: binary search over the checkpoints, then a sequential
   scan of at most 1024 blocks.

**Task 2.2: Exact lanes.** Tier S.

1. `exactLanes` and `pointsIn` as in section 4.4, item 1.
2. The point times follow section 4.3 exactly.

**Task 2.3: The tree and the min/max bins.** Tier O.

1. The groups and the tree of section 4.5.
2. `minMaxLanes` as in section 4.4, item 2.
3. `lanesFor` as in section 4.4, item 3.
4. A Node benchmark (a scratch script, not committed): a model made by hand
   with 10^7 blocks (repeating events) and one with a new gradient event in
   each block. Record `decode` time, memory (`process.memoryUsage()`), and
   `lanesFor` time for 100 random views (95th percentile). The budgets are in
   section 2.6.

**Task 2.4: Include the module in the page.** Tier H.

1. In `page.py`, add `seq_lanes.js` after `lane_chart.js` in the script order.
   Update the docstring of `render_page`.
2. `tests/test_page.py`: update `test_script_order` for the new order.
3. `TESTS.md`: update the entry of `test_script_order` in section 2.3.

**Task 2.5: Node unit tests.** Tier S.

1. `tests/js/test_seq_lanes.js` (`node:test`, `require` of the module, as in
   `test_chart_math.js`). Tables made by hand, with a few blocks, and one
   generated model with more than 2048 blocks. Test:
   - `blockStart` equals a sequential sum from 0.0 (exactly), across
     checkpoints.
   - `blockAt` at block edges and inside blocks.
   - `exactLanes`: a trapezoid block, an arbitrary gradient, an RF pulse with
     phase, an ADC window, a range that cuts a block, a range with no event
     (the neighbouring points still come), the zero points at 0 and at the
     end.
   - `minMaxLanes`: compare each bin with a brute-force computation over the
     exact whole-file points (written in the test). Include a bin with no
     point (edge values only), an RF phase gap, and ADC windows closer than
     one bin.
   - `lanesFor` changes from exact to min/max at `EXACT_POINT_LIMIT`.
   - `decode` raises for `format` 2 and for an unknown table name (for
     example `rotation`).
2. `TESTS.md`: fill section 2.19.

Acceptance: `scripts/check` passes (it runs the Node tests). The Node
benchmark meets the render budget of section 2.6.

---

### Phase 3: the chart hook and asynchronous card start

Branch: `feature/lane-provider`. Parallel: yes, with phases 1 and 2. Tier of
the phase: S, with O line-by-line review. Review: O.

**Task 3.1: A lane provider in `laneChart`.** Tier S. Review O.

1. Add the option `lanesFor(view, bins)`. When it is given, `render` calls it
   at the start of each render, with the current view and `bins = PLOT_W`,
   and draws the lanes that it returns. The number of lanes must stay the
   same. The option `lanes` is then the initial lanes.
2. The tooltip (`setCursor`) uses the lanes of the last render. For a lane
   with the key `minmax: true`, the tooltip shows the minimum and the maximum
   of the bin at the cursor, as "min – max unit" (for example "−12.3 – 4.56
   mT/m"), not the interpolated value of the zigzag polyline. The bin is the
   pair of points (bin start, minimum), (bin centre, maximum) whose bin holds
   the cursor time. A gate lane is unchanged ("on" or "off"). `ChartMath` gets
   a pure function for this reading, with a Node test.
3. `setWindow` keeps the provider. A card that shows several files keeps the
   current file in a variable that its provider reads. It sets the variable,
   then calls `setWindow` (which renders with the provider).
4. Without `lanesFor`, the behavior is unchanged. Review the diff line by line.

**Task 3.2: Asynchronous `init`.** Tier S. Review O.

1. In `page.js`, when `init` returns a promise, wait for it without blocking
   the other cards. A rejected promise shows the same "could not be drawn"
   note as a thrown error.

**Task 3.3: Browser check.** Tier O.

1. A scratch page with one card whose `lanesFor` returns lanes made from the
   view (for example, a sine with the number of points set by the view), and
   one card with an `async` init that waits 500 ms and one that rejects.
2. Check with `dev-workflow:browser-check-localhost`: zoom, pan, the zoom
   buttons, the tooltip (also the "min – max" reading on a lane with
   `minmax: true`), both themes, and the failure note.

Acceptance: `scripts/check` passes. The browser check passes. The old cards
(spectrum, PNS, the current diagram) still work in a browser page.

---

### Phase 4: the new diagram card

Branch: `feature/diagram-event-table`. Parallel: no. It starts after phases 1,
2 and 3 are merged. Tier of the phase: O for the golden test design, S for the
rest. Review: O.

**Task 4.1: The card in Python.** Tier S.

1. `diagram_card(seqs, windows, card_id="diagram")`: remove `point_budget`.
   The data is section 4.1. For each file that a window uses: `name`,
   `duration_s`, `num_blocks`, `lanes` (`lane_meta`), `tables`
   (`encode_tables(diagram_tables(seq))`). Keep the validation of the
   windows, the HTML, the ids and the help text. Add a status line element
   `{card_id}-mode` under the chart.
2. Remove the envelope note. The status line (task 4.2) replaces it.
3. Call `extensions.refuse_rotations(seq)` (phase 6) for each file, before
   the tables are made.

**Task 4.2: The card script.** Tier S.

1. `assets/cards/diagram.js`: in `init` (async), decode the base64 and
   decompress each table with `DecompressionStream("gzip")`. Make the typed
   arrays and `SeqLanes.decode` for the file of the first window. Decode each
   other file the first time a button selects one of its windows, and keep the
   model (a page with N files then costs N times the memory only when all of
   them were shown). While a file decodes, the status line shows "Loading…"
   and the window buttons are disabled.
2. Keep the current model in a variable `current`. Make one `laneChart` with
   `lanesFor: (view, bins) => { const r = SeqLanes.lanesFor(current, view,
   bins); showStatus(r.exact, bins); return r.lanes; }`, `xDomain` = the first
   window, `extent` = [0, duration of that file in ms].
3. A window button: if its file is the current file, call `setView`. Else set
   `current` to the model of the other file, then call `setWindow` with its
   lanes for the window view (`SeqLanes.lanesFor(...).lanes`), the window
   view and its extent.
4. The status line (`showStatus`) shows "Exact waveform." or "Minimum and
   maximum in each of N time bins. Zoom in to see the exact waveform.".
5. Keep the button and Reset behavior of the current script.

**Task 4.3: Remove the old API.** Tier H.

1. In `waveforms.py`, remove `DIAGRAM_POINT_BUDGET`, `point_count`,
   `_Envelope`, `file_envelope` and `_PAD_POINTS` if it is no longer used.
2. In `tests/test_waveforms.py`, remove their tests. In
   `tests/test_diagram_card.py`, remove the lane-set and budget tests.
3. `TESTS.md`: remove their entries in sections 2.15 and 2.16.

**Task 4.4: The golden test.** Tier O for the design, S for the code.

1. `tests/js/golden_seq_lanes.js` (not a `test_*.js` file, so `node --test`
   does not run it alone): it reads a JSON file with the encoded tables, the
   lane metadata and a list of queries (`exact` or `minmax`, t0, t1, bins).
   It decompresses the tables with `zlib.gunzipSync`, calls `SeqLanes`, and
   writes the results as JSON, with each float written by `JSON.stringify`
   (which gives the shortest round-trip form, so no value changes).
2. `tests/test_seq_lanes_golden.py`: for the synthetic spin echo, GRE (with
   and without enough blocks for two checkpoints), arbitrary gradient and
   empty sequences, and a sequence with a TR definition and ten TRs:
   - write the input file in `tmp_path`; run `node` with `subprocess.run`
     (`check=True`); read the output;
   - `exact` queries: the whole file, one block, a range that cuts a block, a
     range with no event, a range at the end. The JavaScript points must be
     exactly equal to the reference. The reference is the whole-file polyline
     of each line lane: the point (0.0, 0.0), then the points of
     `waveforms._events_in_range(seq, None, None)` in play order (times × 1000),
     then the point (`waveforms.duration_s(seq)` × 1000, 0.0); restricted as in
     section 4.4, item 1. Use `==` on floats, not a tolerance.
   - `minmax` queries with several bin counts: each bin must equal a numpy
     computation of section 4.4, item 2 (use `numpy.interp` for the edges).
     Allow a relative difference of 1e-12 only for the interpolated edge
     values.
   - The whole-file exact lanes must equal `file_lanes(seq)` after the test
     rounds the JavaScript values in Python as `markup._points` does (`round(t,
     4)` on the ms times, `round(v, 4)` on the values, 3 for the phase). The
     JavaScript never rounds. This links the JavaScript to the vb-pulseq
     parity.
3. The test needs `node`. Both devShells have it. If `node` is not found, the
   test fails (do not skip it).
4. `TESTS.md`: fill section 2.20.

**Task 4.5: Tests of the card.** Tier S.

1. `tests/test_diagram_card.py`: the data has the format of section 4.1; the
   tables decode to `diagram_tables(seq)`; two files give two file entries and
   file names in the buttons; a window of a file with no other window adds
   that file; the ids start with `card_id`; the old validation errors; the
   page includes `seq_lanes.js` and `assets/cards/diagram.js` one time.
2. `TESTS.md`: update section 2.16.

**Task 4.6: Documents and the parity script.** Tier S. Review O.

1. `docs/usage.md`: remove `point_budget` and the envelope text. Describe the
   exact and min/max views, the status line, and the limits (10^7 blocks for
   each file, and the other cards, section 2.8). Add `seq_lanes.js` to the
   script order. State the browser requirement: `DecompressionStream`
   (verify the first versions of Chrome, Firefox and Safari on MDN before you
   write them).
2. `scripts/vb_parity.py`: the diagram check compares `lane_meta(seq)` with
   the vb lanes without segments, and `diagram_tables` rebuilt to the
   whole-file polyline (as in task 1.3) with the vb lanes (rounded). Remove
   the point-budget note. Update `ACCEPTED["diagram"]` (the data is now
   tables, not lanes). Run the script against `~/dev/vb_pulseq` at `3a1c7dd`
   and put the output in the PR.

**Task 4.7: Browser check.** Tier O.

1. Pages: one small file (all views exact); vb-pulseq `vb-spin-echo-5mm-bw260`
   (232,898 points: min/max when zoomed out, exact when zoomed in); two files
   with windows in each.
2. Check: each window button, zoom from the whole file down to one block and
   back, pan across the whole file, the status line, the tooltip, the RF
   phase lane in both views, both themes, no console errors.

Acceptance: `scripts/check` passes, including the golden test. The parity
script prints `ok` for each card. The browser check passes.

---

### Phase 5: scale check and release

Branch: `chore/diagram-scale`. Parallel: no. It starts after phases 4 and 6
are merged. Tier of the phase: O, with S for the script. Review: O.

**Task 5.1: The scale script.** Tier S.

1. `scripts/diagram_scale.py` (not in `scripts/check` or CI). Arguments:
   `--blocks N`, `--case repeating|worst`, `--out DIR`. It builds a synthetic
   sequence with pypulseq:
   - `repeating`: a GRE-like TR of 5 blocks (as `tests/synthetic.py`
     `gre_sequence`), repeated with a phase-encode table of 256 values.
   - `worst`: the same, but with a shaped RF pulse (for example a 2 ms sinc
     pulse, about 2000 samples), and a new phase-encode amplitude and a new
     RF phase in each TR, so that the event libraries grow with the TRs.
2. It records: build time and peak memory of the pypulseq sequence; time and
   memory of `diagram_card`; the page size (bytes); the size of each table
   (compressed). It writes the page to `--out` and the numbers as JSON. It does
   not write a `.seq` file (at 10^7 blocks that is about 390 MB and is not
   needed: the card takes the `pp.Sequence`). For the worst case, make the RF
   pulse one time and change its `phase_offset` for each TR, instead of a new
   `make_sinc_pulse` call in each TR.
3. First run it at 10^4, 10^5 and 10^6 blocks. Extrapolate the time and the
   memory to 10^7. If the build of 10^7 blocks would take more than 1 hour, or
   more than half of the RAM of the machine, stop and ask the user before you
   run it.

**Task 5.2: Measure.** Tier O.

1. Run task 5.1 for both cases up to 10^7 blocks (or the size that the user
   approves).
2. Open each page in the browser (browser check skill). Record the load time
   (from `performance.now()` at the start of the card script to the first
   render) and the JavaScript memory (`performance.memory` in Chromium, if it
   exists).
3. Run the Node benchmark of task 2.3 on the decoded real tables of the 10^7
   page.
4. Compare with section 2.6. Put a table of the results in the PR. If a
   "must be" value fails, stop and tell the user.

**Task 5.3: `TODO.md`.** Tier H.

1. Delete the item "Draw the sequence diagram from the event table in the
   browser".
2. Add an item "Make the other cards work at 10^7 blocks", with the problems
   of section 2.8 and the measured numbers of task 5.2 where they help.
3. Add an item "Support the rotation extension", with section 2.10, decisions
   8 and 9 of section 2.3, the reserved names of section 4.6, and the guard of
   phase 6. It says: write a plan first; it waits for rotation support in a
   pypulseq release.

**Task 5.4: Plan status.** Tier H.

1. Set the status line of this file to "complete" and list the PR numbers.
2. Record the decisions that were made during the work, as the first plan
   does.

**Task 5.5: Tag `v0.1.0`.** Tier O.

1. After the PR of phase 5 is merged and CI passes on `main`, ask the user to
   approve the tag. Show the commit.
2. Only after approval: `git tag -a v0.1.0 -m "pulseq-reports 0.1.0"` on that
   commit, and `git push origin v0.1.0`. The tag is public.

Acceptance: the budgets of section 2.6 pass, or the user accepts the measured
values. `TODO.md` and this plan are updated. The tag exists after approval.

---

### Phase 6: refuse sequences with the rotation extension

Branch: `feature/rotation-guard`. Parallel: yes, with phases 1, 2 and 3 (see
the PR limit in section 3.3). Tier of the phase: O for task 6.1, S for the
rest. Review: O.

**Task 6.1: Find how a rotation shows in a `pp.Sequence`.** Tier O.

1. In a scratch environment (not the project environment), install the
   branch of pypulseq PR #372 (`uv run --with
   "pypulseq @ git+https://github.com/mcencini/pypulseq@feat-rotext"`). If it
   does not install, tell the user and use a hand-written `.seq` file with a
   rotation section, as the Pulseq 1.5.1 specification or MATLAB Pulseq
   writes it.
2. Write a small sequence with rotations (the PR has the example
   `examples/scripts/write_radial_gre_rot.py`) to a `.seq` file.
3. Read that file with pypulseq 1.5.0.post1 (the project environment). Record
   what happens: an error, a warning, or no error. If there is no error, find
   what shows the rotations in the `pp.Sequence` (for example
   `seq.extension_string_idx`, an extension type name, or a library). Also
   record what the PR #372 branch has (`seq.rotation_library`).
4. Record the results in the PR description, and choose the detection of task
   6.2 from them. Do not add a dependency on the PR branch.

**Task 6.2: The guard.** Tier S.

1. Write `extensions.py` with `refuse_rotations(seq: pp.Sequence) -> None`. It
   raises `NotImplementedError` with a message that names the rotation
   extension, says that the report does not support it yet, and points to
   `TODO.md`. It detects a rotation with each method that task 6.1 found (for
   example, a non-empty `seq.rotation_library` in a future pypulseq, or a
   rotation extension type in the extension tables).
2. It must not read each block: the cost must not grow with the number of
   blocks, when the detection allows it.
3. If pypulseq 1.5.0.post1 drops the rotations when it reads the file, and no
   trace stays in the `pp.Sequence`, the guard cannot detect them. Then
   `refuse_rotations` cannot help for such files. Tell the user, and write the
   limit in its docstring and in `docs/usage.md`.

**Task 6.3: Use the guard.** Tier S.

1. Call `refuse_rotations` for each sequence at the start of `spectrum_card`,
   `pns_card` and `gradient_limits_card`. (Phase 4 adds the call to
   `diagram_card`.)
2. The RF exposure, timing, definitions and block table cards do not use the
   gradient waveforms. Do not add the guard to them.

**Task 6.4: Tests and documents.** Tier S.

1. `tests/test_extensions.py`: `refuse_rotations` accepts the synthetic
   sequences. It raises for a sequence with a rotation. If the rotation cannot
   be made with pypulseq 1.5.0.post1, make the test sequence with the method of
   task 6.1 (for example, a `.seq` file with a rotation section, stored in
   `tests/data/`, with a short note on how it was made), or with a
   `pp.Sequence` whose extension tables are set by hand. Each of the three cards
   raises for it.
2. `TESTS.md`: fill section 2.21.
3. `docs/usage.md`: add a short section "Rotation extension" at the end: the
   status, the guard and its limits.

Acceptance: `scripts/check` passes. The PR records the results of task 6.1.

## 6. Summary of parallel work

| Wave | Phases | Condition to start |
|---|---|---|
| 1 | 0 | The user approves this plan |
| 2 | 1, 2, 3, 6 | Phase 0 merged. Each phase is a separate branch from `origin/main`. At most three PRs open at one time (section 3.3) |
| 3 | 4 | Phases 1, 2 and 3 merged |
| 4 | 5 | Phases 4 and 6 merged |

Tasks inside a phase that can run as parallel workers:

| Phase | Parallel workers |
|---|---|
| 1 | Task 1.1 first (it sets the helpers). Then task 1.2 and the tests of task 1.3 item 2 can run at the same time. Task 1.3 item 1 follows task 1.2. |
| 2 | Tasks 2.1 and 2.2 (one S worker) and task 2.4 (one H worker) at the same time. The executing agent does task 2.3 after 2.1. Task 2.5 follows 2.2 and 2.3. |
| 3 | One S worker for tasks 3.1 and 3.2. The executing agent reviews and does 3.3. |
| 4 | Task 4.3 (H) and task 4.1 (S) at the same time. Task 4.2 (S) after 4.1. The executing agent designs task 4.4 and gives the code to an S worker. Task 4.5 and 4.6 (S) after 4.1. |
| 5 | One S worker for task 5.1. The executing agent does the rest. |
| 6 | The executing agent does task 6.1. Then one S worker for tasks 6.2 to 6.4. |

## 7. Questions still open

These do not block phases 0 to 4.

1. **The largest real sequence.** The target is 10^7 blocks. A real 1 h scan
   has 10^7 blocks only if the blocks are shorter than about 0.36 ms on
   average. Phase 5 can use a smaller size if the build of 10^7 blocks is too
   slow on the machine (task 5.1, item 3).
2. **Mobile browsers.** The memory budget (400 MB) is for a desktop browser.
   This plan does not test a phone.
