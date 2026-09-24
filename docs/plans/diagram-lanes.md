# Plan: a PNS lane in the sequence diagram

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: not started. The plan was written on 2026-09-24.

## 1. Goal

Show the PNS prediction as lanes of the sequence diagram, on the same time
axis as the RF, the ADC and the gradients. The goal is for each `.seq` file of
up to 10^7 blocks:

1. One PNS lane: the total (the root-sum-of-squares of the three axis
   values), in percent of the stimulation limit. The per-axis values are not
   lanes (decision 9 of section 2.2).
2. Zoom and pan work on the PNS lane as on the other lanes.
3. When a view is short enough (section 4.5), the PNS lane shows the exact
   values. When it is longer, they show the minimum and the maximum in time
   bins, from values that Python stores in the page.
4. The PNS card keeps only the summary: the peak, the peak time, the axis
   peaks, the hardware and the example-hardware warning. The PNS chart moves
   into the diagram.

A slew lane and a |G| lane are not in this plan, except the optional phase 5
(|G|). A slew lane waits for the `TODO.md` item "Study the two definitions of
the gradient slew rate".

## 2. Read this first (context for the executing agent)

### 2.1 The state of the repository

- Read `docs/plans/pulseq-reports.md`, `docs/plans/diagram-event-table.md` and
  `docs/plans/cards-at-scale.md`. Their workflow rules apply to this plan too.
- `docs/plans/pns-lanes-prototype.md` planned a prototype. Its code and results
  are on the branch `chore/pns-lanes-prototype` (never merged), in
  `prototypes/pns_lanes/`. Read `prototypes/pns_lanes/README.md` there: it has
  the exact SAFE model of pypulseq with line numbers, the block-map formulas,
  and the measurements of section 2.3.
- `docs/plans/cards-at-scale.md` must reach these points before this plan
  starts (section 3.3):
  - Its phase 1: the fork `mdtisdall/pypulseq` with `safe_tau_lowpass` on
    `scipy.signal.lfilter`, pinned in this project.
  - Its phase 2: `seq_index.py` (`SequenceIndex`), `block_cache_off` and
    `sampling.py` (`GradientSampler`).
- The real ex-vivo file is `data/exvivo_gre_seg_0.seq` (git-ignored, linked
  into each worktree). Never commit it or copy it.

### 2.2 Decisions that are already made

Do not open these decisions again. The user made them or approved them.

1. **Lanes, not a card, for values against time.** A quantity that is a
   function of time is a lane of the sequence diagram. Summaries, tables and
   plots against another axis stay cards.
2. **Python computes PNS.** It uses the pypulseq fork, not a copy of the SAFE
   model in this library. The browser does not compute the whole-file PNS
   (the prototype's question 4 failed at 10^7 blocks).
3. **Stored levels.** Python stores the exact minimum and maximum of each PNS
   lane in fixed time bins. The finest bin is 1.2 ms for shorter files, so
   that it meets the longest exact view (section 4.3). Longer files get a
   coarser finest bin, set by a size limit.
4. **Exact short views in the browser.** For short views, the browser
   computes the exact PNS from the diagram tables, with the block maps of the
   prototype. This is a JavaScript copy of the SAFE recursion. It is tested
   against the Python values.
5. **No bounds and no refinement.** The prototype's method of bounds failed
   (question 3). Do not use it.
6. **Lean on pypulseq.** Do not test pypulseq in this project. The tests
   compare this library's output with pypulseq output or with other output of
   this library.
7. **No new dependency.** No JavaScript library, no build step.
8. **Example hardware by default.** Without a gradient `.asc` file, PNS uses
   `safe_example_hw()`. The page then says that it is not a real scanner, as
   the PNS card does now.
9. **Only the total is a lane** (the user, 2026-09-24). Compliance depends on
   the total only (`calculate_pns` returns `ok = all(pns_norm < 1)`). The
   gradient lanes under the PNS lane show which axis causes a peak. The
   per-axis peaks stay as numbers in the PNS summary card. This makes the
   stored level 4 times smaller than with four lanes.

### 2.3 Facts from the prototype (2026-09-24, a Mac with 10 cores and 64 GB)

| Measurement | Value |
|---|---|
| Python PNS with `lfilter` in chunks, ex-vivo file (370 s, 3.7e7 samples per axis) | 2.9 s, 0.33 GB |
| The same, 10^6 repeating blocks (1,198 s) | 14.6 s, 0.79 GB (plus 8.7 s to build the sequence) |
| Stock pypulseq `calculate_pns`, ex-vivo file (extrapolated) | about 260 s, about 8 GB |
| JavaScript block maps against its own per-sample recursion | at most 3.5e-15 of the peak |
| JavaScript against the Python reference, long files | at most 7.1e-7 of the peak (pypulseq's time drift, see item 1 below) |
| JavaScript decode, 10^7 blocks | 2.5 s, 240 MB |
| JavaScript exact view of 1 s, any file size | about 8 ms (95th percentile) |
| JavaScript exact view of 10 s | about 80 ms (95th percentile) |

1. pypulseq's gradient breakpoints drift off the 10 µs raster by float
   rounding of its block start times: up to 7.1e-11 s in a 370 s file. The
   SAFE model divides by `dt`, so the drift changes PNS by up to about 1e-6 of
   the peak. A method that samples on exact raster positions (the prototype's
   JavaScript, and `GradientSampler` if it samples each block at exact local
   offsets) does not have this drift.
2. The exact view costs about 80 ns for each sample. The inner loop of the
   prototype is not optimized.

### 2.4 Budgets (proposed: the user approves them with this plan)

For one file. "Added" means more than the diagram card without PNS.

| Quantity | 370 s file | 10^7 repeating blocks |
|---|---|---|
| Python time added to the diagram card | at most 10 s | at most 600 s |
| Python peak RSS added | at most 1 GB | at most 2 GB |
| Page size added | at most 4 MB | at most 20 MB |
| Browser: time added before the first chart | at most 1 s | at most 3 s |
| Browser: one render of the PNS lane (95th percentile) | at most 50 ms | at most 50 ms |

If a budget fails, stop and tell the user. Do not change a budget yourself.

### 2.5 Terms

- **PNS lane.** The lane "PNS": the total, in percent of the limit.
- **Stored level.** The minimum and the maximum of the PNS total in each bin
  of `binSamples` gradient-raster samples, as Python computes them.
- **Pyramid.** Coarser levels that the browser makes from the stored level,
  each with bins 4 times longer than the level below it.
- **Exact view.** A view of the PNS lane computed in the browser from the
  diagram tables, sample by sample.
- **Fork.** `mdtisdall/pypulseq` (see `docs/plans/cards-at-scale.md`,
  section 3.6).

## 3. How to execute this plan

### 3.1 Workflow

As in `docs/plans/cards-at-scale.md`, section 3.1, with its fork rules
(section 3.6 there). At most three PRs open at one time, together with the
PRs of the other plan.

### 3.2 Worker model tiers

As in `docs/plans/cards-at-scale.md`, section 3.2: H (`haiku`), S (`sonnet`),
O (the executing agent).

### 3.3 Order and parallel work

```
cards-at-scale phase 1 (fork lfilter) ──┐
cards-at-scale phase 2 (sampler) ───────┼─► Phase 0 ─► Phase 1 (fork: streaming) ─► Phase 2 (Python levels) ─┐
                                        │                                                                   ├─► Phase 4 (diagram, card) ─► Phase 6
                                        └────────────────────────────► Phase 3 (JavaScript PNS) ────────────┘
                                                                         Phase 5 (|G| lane, optional) ─► Phase 6
```

- This plan starts after phases 1 and 2 of `docs/plans/cards-at-scale.md` are
  merged. It can run at the same time as phases 3, 4 and 5 of that plan: they
  edit different files (section 3.4).
- Phase 0 first. Then phases 1 and 3 at the same time. Phase 2 after phase 1.
  Phase 4 after phases 2 and 3. Phase 5 (if the user keeps it) after phase 4.
  Phase 6 last.

### 3.4 File ownership

Package root: `src/pulseq_reports/`. Tests: `tests/`.

| Phase | Files that the phase creates or edits |
|---|---|
| 0 | `TESTS.md` (only: add three placeholder sections, task 0.1) |
| 1 | In the fork: `src/pypulseq/utils/safe_pns_prediction.py` (a new streaming function) and one test file of pypulseq's suite. In this project: `pyproject.toml` (only `[tool.uv.sources]`), `uv.lock` |
| 2 | `pns_levels.py` (new), `tests/test_pns_levels.py` (new), `TESTS.md` section 2.24 |
| 3 | `assets/pns_lanes.js` (new), `page.py` (only the script order), `tests/js/test_pns_lanes.js` (new), `tests/test_page.py` (only `test_script_order`), `TESTS.md` sections 2.3 and 2.25 |
| 4 | `cards/diagram.py`, `assets/cards/diagram.js`, `assets/lane_chart.js`, `cards/pns.py`, `assets/cards/pns.js`, `pns.py`, `tests/test_diagram_card.py`, `tests/test_pns_card.py`, `tests/test_pns.py`, `tests/test_pns_lanes_golden.py` (new), `tests/js/golden_pns_lanes.js` (new), `tests/js/test_chart_math.js` and `assets/chart_math.js` (only if lane groups need a pure function), `docs/usage.md`, `scripts/vb_parity.py` (only `ACCEPTED["pns"]` and `ACCEPTED["diagram"]`), `TESTS.md` sections 2.4, 2.11, 2.12, 2.16 and 2.26 |
| 5 | `assets/g_lanes.js` (new), `cards/diagram.py`, `assets/cards/diagram.js`, `tests/js/test_g_lanes.js` (new), `tests/test_diagram_card.py`, `TESTS.md` sections 2.16 and a new section at the end |
| 6 | `scripts/cards_scale.py` (only a `--pns-lanes` option), `TODO.md`, `docs/usage.md`, this plan file (status and results only) |

Rules: as in `docs/plans/cards-at-scale.md`, section 3.4. Of the other plan,
only phase 1 edits `pns.py` and `tests/test_pns.py`. This plan starts after
that phase is merged. The former phase 6 of the other plan (PNS in chunks)
moves to phases 1, 2 and 4 of this plan. So no phase of the other plan edits
the PNS files at the same time as this plan.

### 3.5 The exactness rule

1. The stored level and the exact view both sample each block at exact
   raster offsets from the tables. They must agree to a relative 1e-12 of the
   peak (float rounding only). The golden test of phase 4 checks this.
2. Against stock pypulseq `calculate_pns`, allow 1e-6 of the peak (item 1 of
   section 2.3). Write the reason in each test that uses this tolerance.
3. `scripts/vb_parity.py`: the PNS card data changes (section 4.6). Each
   change is an accepted difference that the user approves.

## 4. Design

### 4.1 PNS in Python (phases 1 and 2)

1. **The fork (phase 1).** Add a streaming function to
   `safe_pns_prediction.py`:
   - It takes gradient samples in chunks: shape `(n, 3)`, T/m, on the raster
     `dt`.
   - It keeps the 9 filter states and the last sample between chunks.
   - It gives the per-axis values of each chunk.
   - On the chunks of a whole file, it gives the values of `safe_gwf_to_pns`
     on the whole file, within 1e-12 of the peak. The padding stays at the two ends of the file. See
   `docs/plans/cards-at-scale.md`, former phase 6, task 6.1, for the method.
2. **`pns_levels.py` (phase 2).** `pns_levels(seq, hw=None, index=None) ->
   PnsLevels`:
   - It gets the gradient samples from `GradientSampler`, block by block, at
     the exact local times `(j + 0.5) * dt` of each block. So it has no time
     drift (section 2.3, item 1).
   - It sends the samples through the fork function in chunks of about 2^20
     samples.
   - It keeps the minimum and the maximum of the total in each bin of
     `binSamples` samples (section 4.2).
   - It keeps the summary: the peak of the total, the peak of each axis, and
     the peak time. The peak time is the time of the first sample at or above
     `peak * (1 − 1e-6)`, as in `PnsPrediction.peak_time_s` now.
   - Memory is bounded by the chunk size and the stored level.

### 4.2 The stored level and its size

- `dt` is the gradient raster (10 µs). `nt` is the number of samples.
- `EXACT_MAX_S = 1.0`: the longest exact view (section 4.3).
- `binSamples = max(floor(EXACT_MAX_S / 812 / dt), ceil(nt / MAX_BINS))`, with
  `MAX_BINS = 2,000,000`. At 10 µs, the first term is 123 samples (1.23 ms).
- Size: 2 (minimum, maximum) × float32 = 8 bytes for each bin, before
  compression. At most 16 MB for each file.

| File | `nt` | `binSamples` | Bin | Bins | Size before compression |
|---|---|---|---|---|---|
| 370 s | 3.7e7 | 123 | 1.23 ms | 3.0e5 | 2.4 MB |
| 10^6 repeating blocks (1,198 s) | 1.2e8 | 123 | 1.23 ms | 9.7e5 | 7.8 MB |
| 10^7 repeating blocks (11,980 s) | 1.2e9 | 599 | 6.0 ms | 2.0e6 | 16 MB |

A file longer than about 2,460 s (41 minutes: 2,000,000 bins of 1.23 ms)
has a gap. In that
file, views from 1 s to `812 × bin` show the stored bins, and each stored bin
is wider than one pixel. The
status line says so (section 4.5). The page-size budget of section 2.4 is for
the compressed data. Phase 2 measures the compressed size. If it fails, stop
and tell the user (question 4 of section 7).

### 4.3 The exact view in the browser (phase 3)

1. `assets/pns_lanes.js` (`PnsLanes`): the prototype's `pns_lanes.js`, made
   into library code. Required changes:
   - Numeric cache keys and typed arrays in the inner loop. The prototype used
     string keys and object properties.
   - `decode` reads the diagram tables and the hardware values of section 4.4.
2. `exactView(model, t0, t1, bins)`: the exact samples in `[t0, t1]`. When
   there are more than `2 × bins` samples, it gives the exact minimum and
   maximum of the total in each of `bins` bins, from the exact samples. It
   computes the three axis values, because the total needs them, but it does
   not return them.
3. `EXACT_MAX_S = 1.0` (section 4.2). Phase 3 measures the optimized loop.
   An exact view of 10 s can take at most 50 ms at the 95th percentile. Then
   tell the user, because the gap of section 4.2 can become smaller (question
   5).

### 4.4 The data in the page

The diagram card data (format 1, `docs/plans/diagram-event-table.md`,
section 4.1) gets an optional key `pns` in each file entry:

```json
"pns": {
  "hardware": "pypulseq example hardware (not a real scanner)",
  "example": true,
  "hw": {"x": {"tau1": 0.2, "tau2": 0.03, "tau3": 3.0, "a1": 0.4, "a2": 0.1,
               "a3": 0.5, "stim_limit": 30.0, "g_scale": 0.35}, "y": {}, "z": {}},
  "dtS": 1e-05,
  "binSamples": 123,
  "summary": {"peak": 0.8659, "peak_time_s": 0.001955, "axis_peaks": {"x": 0.1, "y": 0.2, "z": 0.3}},
  "levels": {"min": {"dtype": "float32", "length": 300000, "data": "<base64 of gzip>"},
             "max": {"dtype": "float32", "length": 300000, "data": "<base64 of gzip>"}}
}
```

- `levels` has the 2 arrays `min` and `max` of the total, encoded as
  `diagram_data.encode_tables` encodes tables. Add `float32` to the dtypes that `encode_tables` and the
  card script accept.
- `SeqLanes.decode` does not read this key, so its rule "refuse unknown
  tables" does not change.

### 4.5 The lanes in the browser (phase 4)

1. **Which data draws a view.** For a view `[t0, t1]` with 812 bins:
   - If `t1 − t0 ≤ EXACT_MAX_S`: `PnsLanes.exactView` (exact).
   - Else: the pyramid level with the longest bin that is at most half a
     display bin. Each display bin takes the minimum and the maximum of the
     stored bins that overlap it. So no peak is lost, and a peak can move by
     at most one stored bin (at most half a display bin). If even the stored
     level has bins longer than half a display bin (the gap of section 4.2),
     use the stored level.
2. **The status line** says which data draws the view:
   - "PNS: exact".
   - "PNS: minimum and maximum in bins of X ms".
   - In the gap: "PNS: minimum and maximum in bins of X ms (zoom in to 1 s or
     less for the exact values)".
3. **Lanes and lane groups.** The diagram has these groups: RF (|B1|, phase),
   ADC, gradients (x, y, z), PNS (the total). Buttons above the chart
   show or hide each group. A hidden group costs no computation. The PNS
   group is on by default when the file has PNS data.
4. **Units and scale.** The PNS lane is in percent. The domain is
   `[0, 1.1 × max(100, peak %)]`, with ticks at 0 and 100, as the PNS card
   has now. The tooltip shows the minimum and the maximum of a bin, as the
   other lanes do.

### 4.6 The PNS card becomes a summary (phase 4)

- `pns_card` keeps the status line, the table of peaks and the hardware note.
  It loses the chart and the "peak TR" view.
- The peak-TR view becomes a diagram window: the caller adds
  `pns.peak_tr_window` to the diagram windows, as `docs/usage.md` shows now
  for the vb-pulseq layout.
- `pns_card` and the PNS lane of the diagram use the same `PnsLevels` of one
  sequence. Compute it one time for each sequence object (a cache keyed as
  `sequence_index` is, `docs/plans/cards-at-scale.md` section 4.1, item 4).
- The public API changes (`PnsPrediction` loses its whole arrays). This is
  question 2 of `docs/plans/cards-at-scale.md`, section 7, which moves here
  (question 1 of section 7).

### 4.7 The API (phase 4)

```python
diagram_card(seqs, windows, card_id="diagram", pns=False)
```

`pns` is `False` (no PNS lane), `True` (the example hardware), or the path of
a gradient `.asc` file. The default is question 2 of section 7.

## 5. Phases

---

### Phase 0: TESTS.md skeleton

Branch: `docs/diagram-lanes-tests-skeleton`. Tier: H. Review: O.

**Task 0.1.** At the end of `TESTS.md`, after the sections of
`docs/plans/cards-at-scale.md`, add three placeholder sections. Each has its
heading and the line "Phase N of `docs/plans/diagram-lanes.md` adds the
entries.":

```
### 2.24 PNS levels (`test_pns_levels.py`)
### 2.25 PNS lane in JavaScript (`test_pns_lanes.js`)
### 2.26 PNS lane against Python (`test_pns_lanes_golden.py`)
```

If the numbers 2.22 and 2.23 are not yet used, keep these numbers anyway.

---

### Phase 1: the streaming SAFE function in the fork

Branch in the fork: `pns-chunks` (from `pns-lfilter`, the branch of
`docs/plans/cards-at-scale.md` phase 1). Branch in this project:
`chore/pypulseq-fork-pns-chunks`. Tier: O for the interface, S for the code.

**Task 1.1: The interface.** Tier O. Read `calc_pns.py` and
`safe_gwf_to_pns`. Write the function signature and its docstring in the
fork, with the formulas and the pypulseq line of each.

**Task 1.2: The code and the fork test.** Tier S.

1. The fork test uses random gradient input and the samples of a few pypulseq
   sequences. The chunks must give the values of `safe_gwf_to_pns` on the
   whole input, within 1e-12 of the peak.
2. Use the chunk sizes 1, 7, 1000 and one larger than the input.
3. Run the whole test suite of the fork.

**Task 1.3: Commit, push and pin.** Tier O. Show each commit message to the
user and wait for approval. Pin the new fork commit in this project.

Acceptance: the fork suite passes. `scripts/check` passes with the new pin.

---

### Phase 2: the stored level in Python

Branch: `feature/pns-levels`. Tier: S. Review: O.

**Task 2.1: `pns_levels.py`.** Tier S. Section 4.1, item 2, and section 4.2.
The dataclass `PnsLevels` holds `bin_samples`, `dt_s`, the 8 arrays, the
summary and the hardware name.

**Task 2.2: Tests.** Tier S. `tests/test_pns_levels.py`:

1. Use the synthetic sequences and a "border" sequence, with gradients that
   are not zero at a block border. The peak, the peak time and the axis peaks
   equal stock pypulseq `calculate_pns` within 1e-6 of the peak (section 3.5,
   item 2).
2. Each stored bin equals the minimum and the maximum of stock
   `calculate_pns` values in that bin, within the same tolerance, on the
   synthetic sequences.
3. `binSamples` follows the formula of section 4.2 for short and long
   (synthetic, built on the fly) sequences.
4. The result does not change with the chunk size.
5. `TESTS.md` section 2.24.

**Task 2.3: Measure.** Tier S. The time, the peak RSS and the compressed size
of the stored level, for the ex-vivo file, 10^6 and 10^7 repeating blocks, and
10^5 worst-case blocks. Compare with section 2.4.

---

### Phase 3: PNS in JavaScript

Branch: `feature/pns-lanes-js`. Tier: S, with O review of the inner loop.

**Task 3.1: `assets/pns_lanes.js`.** Tier S. Section 4.3. Start from
`prototypes/pns_lanes/pns_lanes.js` on the prototype branch.

**Task 3.2: The pyramid.** Tier S.

1. `PnsLanes.levels(model, stored)` makes the pyramid (factor 4) from the
   decoded stored level.
2. `PnsLanes.lanesFor(model, viewMs, bins)` chooses the data as section 4.5,
   item 1 says. It returns the PNS lane in the lane JSON form, with
   `minmax: true` when not exact, and the kind of view for the status line.

**Task 3.3: Page order.** Tier H. `page.py`: add `pns_lanes.js` after
`seq_lanes.js`. Update `test_script_order` and its `TESTS.md` entry.

**Task 3.4: Node tests.** Tier S. `tests/js/test_pns_lanes.js`, on hand-made
tables:

1. The block maps equal the plain recursion of the same module.
2. The exact minimum and maximum in bins equal a brute force.
3. The pyramid.
4. The choice of section 4.5, item 1.
5. A gradient that is not zero at a block border.

`TESTS.md` section 2.25.

**Task 3.5: Measure.** Tier S. Measure the decode time and the memory at
10^7 blocks, the exact view at 1 s and 10 s (95th percentile), and one render
from the pyramid. Apply section 4.3, item 3.

---

### Phase 4: the diagram, the lane groups and the PNS summary card

Branch: `feature/pns-lanes`. Tier: S, with O for the golden test design and
the review.

**Task 4.1: The card in Python.** Tier S. Sections 4.4 and 4.7: the `pns`
argument, the `pns` key of each file entry, `refuse_rotations` as now.

**Task 4.2: Lane groups.** Tier S. Section 4.5, item 3, in `lane_chart.js` and
the card script. Review O line by line: without groups, `laneChart` must work
as now for the other cards.

**Task 4.3: The card script.** Tier S. Section 4.5: decode the PNS data of
each file with its tables, `lanesFor` for the PNS group, the status line, the
units and the tooltip.

**Task 4.4: The PNS summary card.** Tier S. Section 4.6. The card uses the
same `PnsLevels` as the diagram.

**Task 4.5: The golden test.** Tier O for the design, S for the code.
Write `tests/test_pns_lanes_golden.py` with `tests/js/golden_pns_lanes.js`, as
the golden test of the diagram does. Compare Python `pns_levels` and
JavaScript `exactView` on the synthetic sequences, the "border" sequence and
repeating sequences with more than one checkpoint group. The exact values must agree within 1e-12 of
the peak (section 3.5, item 1). The pyramid bins must equal the minimum and
the maximum of the exact values. `TESTS.md` section 2.26.

**Task 4.6: Tests and documents.** Tier S. `tests/test_diagram_card.py`,
`tests/test_pns_card.py`, `tests/test_pns.py`: the new data, the `pns`
argument, the summary card. `docs/usage.md`: the PNS lane, the lane groups,
the `pns` argument, the summary card, the gap of section 4.2.
`scripts/vb_parity.py`: record each changed value of the PNS card as an
accepted difference, after the user approves it.

**Task 4.7: Browser check.** Tier O. Use the
`dev-workflow:browser-check-localhost` skill.

1. Pages: a synthetic file, the ex-vivo file, and 10^6 repeating blocks. The
   page of the ex-vivo file stays in the scratchpad. Never commit it.
2. Check each lane group on and off.
3. Zoom from the whole file to one block and back: exact below 1 s, the
   pyramid above.
4. Check the status line, the tooltips, both themes, and that there is no
   console error.

Acceptance: `scripts/check` passes, with the golden test. The budgets of
section 2.4 pass for the 370 s file. The browser check passes.

---

### Phase 5: a |G| lane (optional)

Branch: `feature/g-lane`. Tier: S. The user decides whether to keep this
phase (question 3 of section 7).

**Task 5.1.** `assets/g_lanes.js` from the prototype's `slew_g.js`
(`gMagMinMax` only): the exact minimum and maximum of |G| in each bin, from
the diagram tables, on demand. A "|G|" lane in the gradients group.

**Task 5.2.** Node tests against a brute force, as the prototype's
`run_slew_g.js`. Browser check.

---

### Phase 6: scale check and documents

Branch: `chore/pns-lanes-scale`. Tier: O, with H for the documents.

**Task 6.1.** Measure the diagram card with the PNS lane for the ex-vivo file,
10^6 and 10^7 repeating blocks, and 10^5 worst-case blocks: all budgets of
section 2.4. A browser check of the 10^7-block page.

**Task 6.2.** `docs/usage.md` final text. This plan: status "complete", the PR
numbers, the fork commits, the decisions made during the work and the
results. `TODO.md`: add an item for a faster exact view if the gap of section
4.2 matters to the user.

## 6. Summary of parallel work

| Wave | Phases | Condition to start |
|---|---|---|
| 1 | 0 | Phases 1 and 2 of `docs/plans/cards-at-scale.md` merged. |
| 2 | 1, 3 | Phase 0 merged. |
| 3 | 2 | Phase 1 merged. |
| 4 | 4 | Phases 2 and 3 merged. |
| 5 | 5 (optional) | Phase 4 merged. |
| 6 | 6 | Phases 4 and 5 merged. |

Workers inside a phase:

| Phase | Parallel workers |
|---|---|
| 1 | The executing agent writes the interface. One S worker for the code and the fork test. |
| 2 | One S worker for task 2.1, then one S worker for tasks 2.2 and 2.3. |
| 3 | One S worker for tasks 3.1 and 3.2, and one H worker for task 3.3, at the same time. Task 3.4 after 3.2. |
| 4 | Task 4.1 (S) and task 4.2 (S) at the same time. Task 4.3 after both. Task 4.4 (S) at the same time as 4.3. The executing agent designs task 4.5 and gives the code to an S worker. Task 4.6 after 4.3 and 4.4. |
| 5 | One S worker. |
| 6 | The executing agent. One H worker for the documents with the exact text. |

## 7. Questions still open

1. **The PNS arrays.** `PnsPrediction` has the whole arrays `t_s`, `norm` and
   `axes` now. Proposal: remove them. A caller that wants the samples of a
   short sequence can use the fork's streaming function. This changes the
   public API of `v0.1.0`.
2. **The default of `pns`** in `diagram_card`. Proposal: `False`, so that a
   caller asks for the PNS lane and its cost (about 3 s for a 370 s file).
3. **Phase 5 (|G| lane).** Keep it, or drop it.
4. **The size limit** `MAX_BINS = 2,000,000` (16 MB before compression for each
   file). The user can change it, or accept a lossy float16 or uint16 form if
   the compressed size is too large.
5. **A faster exact view.** If phase 3 measures a much faster loop, the user
   decides whether `EXACT_MAX_S` grows and the stored level gets smaller.
