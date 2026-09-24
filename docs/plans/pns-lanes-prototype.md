# Plan: a prototype of PNS lanes in the sequence diagram

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: not started. The plan was written on 2026-09-23.

## 1. Goal

The user wants PNS as lanes of the sequence diagram, on the same time axis as
the RF and the gradients. The slew rate and |G| can be lanes too. This
prototype finds out whether the browser can compute PNS lanes on demand. The
browser uses only the tables that the diagram already sends, for files of up
to 10^7 blocks.

The prototype answers five questions with measurements:

1. **Accuracy.** Do filter states that jump from block to block (section 3.3)
   give the same PNS values as pypulseq `calculate_pns`?
2. **Zoomed-in speed.** How long does an exact PNS view take in JavaScript at
   10^7 blocks? What is the longest view that takes at most 50 ms?
3. **Zoomed-out speed.** How tight are the bounds of section 3.4? How many
   blocks must the refinement evaluate for one render? How long does one
   render take?
4. **Whole-file peak.** How long does JavaScript take to find the exact peak
   of the whole file, and the time of the peak, at 10^7 blocks?
5. **Slew and |G|.** Does the current diagram data give their exact minimum
   and maximum in each time bin, fast enough? (A small check.)

The answers choose the design of a later plan (section 6). The prototype does
not change the library.

## 2. Read this first

### 2.1 Context

- The diagram card (`cards/diagram.py`, `assets/seq_lanes.js`) sends compact
  block and event tables. The browser computes each view from them: exact
  points when few enough, else the exact minimum and maximum in each time bin.
  See `docs/plans/diagram-event-table.md`.
- The PNS card calls pypulseq `Sequence.calculate_pns`. It is slow: 97% of the
  time is in the SAFE filters, which use `np.convolve`. A 370 s file takes
  more than 3 minutes and more than 5 GB. See
  `docs/plans/cards-at-scale.md`, sections 2.2 and 2.3.
- The user decided to lean on pypulseq and not to test pypulseq in this
  project. The prototype compares its results with pypulseq output. It does
  not test pypulseq.
- The prototype is only for decisions. The user decides later whether any
  prototype code becomes library code.

### 2.2 The SAFE model as pypulseq 1.5.0.post1 computes it

Read the installed files to confirm this section before you write code:
`pypulseq/Sequence/calc_pns.py` (`calc_pns`) and
`pypulseq/utils/safe_pns_prediction.py` (`safe_gwf_to_pns`, `safe_pns_model`,
`safe_tau_lowpass`). Record each line number in the prototype README.

1. **Sampling.** `dt` is `seq.grad_raster_time` (10 µs by default). The
   sample times are `t[k] = (k + 0.5) * dt` for `k = 0 ... nt - 1`, with
   `nt = ceil((end − 1e-10) / dt)`. The gradient `g[k]` of each axis is the
   `PPoly` of `seq.get_gradients()` at `t[k]`, in Hz/m, divided by
   `seq.system.gamma` (T/m).
2. **Difference.** `x[k] = (g[k] − g[k − 1]) / dt` (T/m/s), with
   `g[−1] = 0`. The zero padding before the first sample gives this `g[−1]`
   and a filter state of zero. The padding after the last sample does not
   change a returned value, because `calc_pns` removes those samples and the
   filters are causal.
3. **Filters.** There is one filter for each axis and each of the three time
   constants `tau` (ms). Each filter uses `alpha = dt_ms / (tau + dt_ms)`,
   with `dt_ms = dt * 1000`. It computes
   `y[k] = alpha * u[k] + (1 − alpha) * y[k − 1]`, with `y[−1] = 0`.
   pypulseq computes this with a convolution that it cuts where
   `(1 − alpha)^n` is below 1e-16.
4. **Components.** For one axis with the hardware `hw.x` (or `.y`, `.z`):
   `stim1 = a1 * |LP_tau1(x)|`, `stim2 = a2 * LP_tau2(|x|)`,
   `stim3 = a3 * |LP_tau3(x)|`.
5. **Axis value.** `p_axis = (stim1 + stim2 + stim3) / stim_limit * g_scale`
   (pypulseq multiplies by 100, and `calc_pns` multiplies by 0.01).
6. **Total.** `p = sqrt(p_x^2 + p_y^2 + p_z^2)`. The value 1 is the
   stimulation limit.

### 2.3 Terms

- **Filter state.** The value `y` of one filter. There are 9 filters: 3 axes ×
  3 time constants.
- **Block map.** The change of one filter state over one block (section 3.3).
- **Checkpoint.** The 9 filter states at the start of a group of blocks.
- **Bound.** A number that the true PNS value cannot exceed (upper bound) or
  that PNS reaches (lower bound).
- **Refinement.** The exact evaluation of the blocks whose bounds are too
  loose.
- **Reference.** The result of pypulseq `calculate_pns`. For files too long
  for it, a scratch Python version that is first checked against it (task 2).
- **Tolerance ε.** The largest error that the display can show without a
  visible change: half a pixel of the lane height (decision 2 of section
  7).

## 3. The design to test

### 3.1 Assumption: blocks start on the gradient raster

The block map needs each block to hold a whole number of samples, at the same
offsets from its start. This is true when each block duration is a multiple
of `grad_raster_time`. pypulseq sets `block_duration_raster` to 10 µs by
default, the same as `grad_raster_time`. Task 1 checks each test sequence.
If a sequence breaks the assumption, record it and do not use the block map
for that sequence.

### 3.2 Per-event data (computed one time for each unique event)

For each unique gradient event and each block length (in samples) that it
plays with:

1. The samples `g[j]` at `t = (j + 0.5) * dt` from the block start, for
   `j = 0 ... n − 1`.
2. The differences inside the block, `x[j] = (g[j] − g[j − 1]) / dt` for
   `j ≥ 1`. The first difference `x[0]` needs the last sample of the block
   before. It is a boundary term (section 3.3).
3. For each filter: the response `h[j]` of the filter to `x[1 ... n − 1]` from
   a zero state, and its largest absolute value.

A block with no event on an axis has `g = 0` on that axis.

### 3.3 Block maps and checkpoints (exact)

Each filter is linear. For one block of `n` samples that starts with the state
`s`:

- `y[j] = (1 − alpha)^j * (alpha * x[0] + (1 − alpha) * s) + h[j]` for
  `j ≥ 0`, where `h[0] = 0`.
- For the filter of `|x|` (stim2), use `|x[0]|` and the response to `|x|`.
- The state at the end of the block is `y[n − 1]`. This is the block map
  `s_end = D * s + B * x0 + R`. `D` depends only on `n`, `R` only on the
  event, and `B * x0` on the boundary term.

The maps compose in order, so a scan over the blocks gives the state at each
block start. Keep only the 9 states at the start of each group of 64 blocks
(the checkpoints). At 10^7 blocks this is about 1.6 × 10^5 × 9 float64 values,
or 11.5 MB.

An exact view starts at the checkpoint before the view. It applies the block
maps up to the first block in the view. Then it runs the sample recursion for
the blocks in the view. The view gives the four lanes (total, x, y, z) as
points at the sample times.

### 3.4 Bounds and refinement (for zoomed-out views)

1. **Block bounds.** In one block, `|y[j]| ≤ |alpha * x[0] + (1 − alpha) * s|
   + max |h|` for each filter. Each stim component, each axis value and the
   total increase when the absolute values of the filter states increase. So
   the bounds of the filters give an upper bound of the total in the block.
   The exact value at one sample of the block (for example the first) is a
   lower bound of the maximum.
2. **Group bounds.** During the scan of section 3.3, keep for each group and
   each filter the largest `|s|` and the largest `alpha * |x0|` of its blocks.
   With the largest `max |h|` of the events in the group, these give an upper
   bound for the group. The reason:
   `|alpha * x0 + (1 − alpha) * s| ≤ alpha * |x0| + |s|`. A tree over the groups gives an upper bound for any range of
   groups.
3. **Refinement.** For one time bin: start from the groups in the bin. Replace
   the group with the largest upper bound by its blocks, and a block by its
   exact samples. Stop when the largest remaining upper bound is at most the
   best exact value found plus ε. The result is the maximum of the bin within
   ε.
4. **The minimum of a bin.** An exact sample value is an upper bound of the
   minimum. A lower bound of each filter in a block is
   `max(0, (1 − alpha)^(n − 1) * |alpha * x0 + (1 − alpha) * s| − max |h|)`.
   The refinement is the same as item 3, with the two bounds exchanged. PNS
   is never below 0, so 0 is always a lower bound.
5. **Cache (a variant).** In a repeating sequence the filter states repeat. A
   cache keyed by the event ids and the states rounded to ε can give the exact
   maximum of a block without its samples. Measure with and without the
   cache.
6. **Bin edges.** A block that a bin edge cuts is always evaluated exactly on
   the samples inside the bin.

### 3.5 Whole-file peak

Use section 3.4 with one bin that holds the whole file and ε = 0. The result
is the exact peak. Then find the peak time. It is the first sample whose value is
at least `peak × (1 − 1e-6)`, as in `pns.PnsPrediction.peak_time_s`. Walk
the groups in play order, and evaluate only those whose upper bound reaches
that value.

Also measure the plain method for comparison: the sample recursion over the
whole file, in JavaScript.

### 3.6 Slew and |G|

1. Slew: the gradient is a polyline, so the slew is constant on each segment.
   The minimum and the maximum of each unique event come from its segments.
   The tree of `seq_lanes.js` then gives the exact extremes of each bin.
2. |G|: compute the extremes for each distinct triple of events (gx, gy,
   gz). On a straight segment, |G| is convex, so its maximum is at an end of
   the segment. The minimum can be inside a segment. Compute it in closed
   form.

## 4. Where the work is done

1. **Branch and worktree.** `chore/pns-lanes-prototype`, in
   `.worktrees/pns-lanes-prototype`, made with the `dev-workflow:start-task`
   skill.
2. **Directory.** `prototypes/pns_lanes/` on that branch:
   - `README.md`: the formulas of section 2.2 with pypulseq line numbers, how
     to run each script, and the results.
   - `reference.py`: the Python reference (task 2).
   - `pns_lanes.js`: the JavaScript prototype (tasks 3 and 5).
   - `run_*.js`, `run_*.py`: the measurement scripts.
   - `results/`: the JSON output of each measurement.
3. **Not merged.** The branch is not merged to `main`. The user decides at the
   end (section 6). Push the branch only with the user's approval, so that
   the work is not lost.
4. **Library code.** Read only. Import `pulseq_reports.diagram_data`
   (`diagram_tables`, `encode_tables`) and `scripts/diagram_scale.py` (the
   builders). Do not edit `src/`, `tests/`, `TESTS.md` or `scripts/`.
5. **Limits of each run.** One fresh process for each measurement. Stop a run
   after 5 minutes or at 8 GB of RSS. The 10^7-block repeating sequence takes
   about 90 s and 3.8 GB to build. Build it one time for each process. Do not
   run the worst case above 10^5 blocks.

## 5. Tasks

Tiers as in `docs/plans/cards-at-scale.md`, section 3.2: H (`haiku`), S
(`sonnet`), O (the executing agent).

### Task 1: Confirm the model and the assumption. Tier O.

1. Read the pypulseq files of section 2.2. Confirm each formula, or correct
   section 2.2 in the README. Record the line numbers.
2. For each test sequence (section 5, task 4), check the assumption of section
   3.1. Record the result.
3. Write the block map formulas (section 3.3) with the boundary term, for the
   filters of `x` and of `|x|`, in the README.

### Task 2: The Python reference. Tier S. Review O.

1. `reference.py`: the model of section 2.2 on the whole sampled file, in
   chunks, with `scipy.signal.lfilter` and the state carried from one chunk to
   the next. Sample the gradients with `seq.get_gradients()`, with the block
   cache off (`seq.use_block_cache = False`, restored after).
2. Check it against pypulseq `calculate_pns` on the synthetic sequences of
   `tests/synthetic.py` and on repeating sequences of 12 s and 60 s. Record
   the largest difference relative to the peak, for the total and each axis.
3. Record its time and memory at 12 s, 60 s, 120 s and 370 s, and on the
   ex-vivo file. Stock pypulseq `calculate_pns` needs about 4 minutes and
   8 GB for the ex-vivo file, so do not run it there: use the reference.

### Task 3: The JavaScript prototype, exact part. Tier O for the design, S for the code.

1. `pns_lanes.js`, a pure module like `seq_lanes.js` (no DOM). The executing
   agent writes the interface and the data layout first. An S worker writes
   the code.
2. Input: the decoded diagram tables (as `SeqLanes.decode` takes them), the
   gradient raster, gamma, and the SAFE hardware values of
   `safe_example_hw()` (as JSON from Python).
3. Decode: the per-event data (section 3.2), the scan and the checkpoints
   (section 3.3), and the group bounds (section 3.4, item 2). Record the time
   and the memory.
4. `exactView(t0, t1)`: the four lanes as points (section 3.3).

### Task 4: Accuracy and zoomed-in speed. Tier S.

1. A Node harness, as `tests/js/golden_seq_lanes.js` does: Python writes the
   tables and the hardware values to JSON, Node runs the prototype.
2. Test sequences:
   - The synthetic sequences of `tests/synthetic.py`.
   - One sequence with extended trapezoids and arbitrary gradients that are
     not zero at block borders, made with pypulseq `make_*` functions.
   - Repeating sequences of 12 s, 60 s and 370 s. For the 370 s one, with
     about 4 × 10^4 blocks, give the builder a longer TR.
   - Repeating sequences of 10^6 and 10^7 blocks, and the worst case at
     10^5 blocks.
   - The ex-vivo file `data/exvivo_gre_seg_0.seq` (decision 1 of section 7).
     Its block durations are on the 10 µs gradient raster.
3. Accuracy (question 1): compare `exactView` over the whole file with the
   reference, on each sequence where the reference runs. Record the largest
   difference relative to the peak.
4. Speed (question 2): at 10^6 and 10^7 blocks, time `exactView` at 100
   random places for each view length: 1 ms, 10 ms, 100 ms, 1 s and 10 s.
   Record the median and the 95th percentile. Find the longest view with a
   95th percentile of at most 50 ms.

### Task 5: Bounds, refinement and the whole-file peak. Tier O.

1. Add section 3.4 (with and without the cache) and section 3.5 to
   `pns_lanes.js`. Add `minMaxView(t0, t1, bins, eps)`.
2. Check `minMaxView` against a brute force over the exact samples, on the
   sequences where the brute force runs. The difference must be at most ε.
3. Question 3: time `minMaxView` with 812 bins at 10^6 and 10^7 blocks and
   at 10^5 worst-case blocks. Use the whole file and 100 random views that
   are longer than the longest exact view of task 4. Record the median and the
   95th percentile, and the number of blocks and samples evaluated, with and
   without the cache.
4. Question 4: time the exact whole-file peak and the peak time, at the same
   sizes. Also time the plain sample recursion over the whole file. Check the
   peak and the peak time against the reference.

### Task 6: Slew and |G|. Tier S.

1. Add section 3.6 to the prototype. Check the extremes of each bin against a
   brute force on the synthetic sequences.
2. Time one render of 812 bins for the whole file at 10^7 blocks.

### Task 7: Results and recommendation. Tier O.

1. Write the results in the README, with one table for each question.
2. Apply section 6 and write a recommendation for the user.
3. Show the results to the user. The user decides the next step.

### Order and parallel work

- Task 1 first.
- Then task 2 (one S worker, `reference.py`) and task 3 (the executing agent
  designs, one S worker codes `pns_lanes.js`) at the same time. They own
  different files.
- Task 6 (one S worker, its own file `slew_g.js`) can run at the same time as
  tasks 2 and 3.
- Task 4 after tasks 2 and 3. Task 5 after task 3, at the same time as
  task 4.
- Task 7 last.

## 6. How the answers choose the design

| Result | Decision |
|---|---|
| Question 1: the largest difference is at most 1e-9 of the peak | The block map is accurate enough. Else stop and tell the user. |
| Question 2: views of 10 s or longer take at most 50 ms (95th percentile) at 10^7 blocks | Zoomed-in PNS lanes are exact and on demand in the browser. |
| Question 3: a render takes at most 50 ms (95th percentile) at 10^7 blocks, with ε of half a pixel | Zoomed-out PNS lanes use bounds and refinement in the browser. The page carries no PNS data. |
| Question 3 fails | Python stores the exact minimum and maximum of each group of 64 blocks (about 2.5 MB at 10^7 blocks), and the browser refines only the bin edges. |
| Question 4: the exact whole-file peak takes at most 2 s at 10^7 blocks | The page can compute the PNS summary. Python computes PNS (through pypulseq) only for callers that ask for the numbers. |
| Question 4 fails | Python computes the PNS summary through pypulseq (the fork of `docs/plans/cards-at-scale.md`, phases 1 and 6). |
| Question 5: a render takes at most 50 ms at 10^7 blocks | Slew and |G| lanes are exact and on demand. |

The user makes the final decision with the results. Then the executing agent
changes `docs/plans/cards-at-scale.md` and writes a plan for the new diagram
lanes.

## 7. Decisions of the user (2026-09-24)

1. **The ex-vivo file.** The file of section 2.2 of
   `docs/plans/cards-at-scale.md` is file 0 of the ex-vivo GRE protocol of
   another project. The user gave a copy. It is in the git-ignored folder
   `data/` of the main checkout: `data/exvivo_gre_seg_0.seq` (pypulseq file
   format 1.5.0, 39,304 blocks, 369.92 s, 75 unique gradient events, 24 unique
   RF events, SHA-256 `95cae866…68e8`). Read it with `pp.Sequence().read`.
   Use it as the main timing example, together with the synthetic sequences.
   Do not copy it into the repository, into a commit or into a PR.
2. **The tolerance ε** is half a pixel of the lane height of the diagram (the
   lane height in `lane_chart.js`).
3. **The hardware** is `safe_example_hw()`.
4. **The time limit.** Stop the prototype after tasks 1 to 7, or earlier if
   question 1 fails.
