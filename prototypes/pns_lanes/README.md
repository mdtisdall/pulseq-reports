# PNS lanes prototype

Prototype for `docs/plans/pns-lanes-prototype.md` (PR #20). Not library code.
This branch is not merged. The results are at the end of this file.

The ex-vivo file is `data/exvivo_gre_seg_0.seq` (git-ignored, see #19). Do not
commit it or copy it into this directory.

## Task 1: the SAFE model and the assumption (confirmed 2026-09-24)

pypulseq 1.5.0.post1, installed in `.venv/lib/python3.12/site-packages/pypulseq`.

### The model

| Step | Formula | Source |
|---|---|---|
| Raster | `dt = seq.grad_raster_time` (10 µs) | `Sequence/calc_pns.py:45` |
| Gradients | `gw_pp = seq.get_gradients()` (piecewise-linear `PPoly`, Hz/m) | `calc_pns.py:47` |
| Sample times | `nt = ceil((max_t − 1e-10) / dt)`, `t[k] = (k + 0.5) * dt` | `calc_pns.py:53-54` |
| Samples | `g[k] = gw_pp(t[k]) / seq.system.gamma` (T/m) | `calc_pns.py:64`, `:79-81` |
| Padding | `pad1` zeros before, `pad2` zeros after | `utils/safe_pns_prediction.py:315` |
| Difference | `x = diff(padded g) / dt` (T/m/s) | `safe_pns_prediction.py:320` |
| Kept samples | the samples of the real `g` only | `calc_pns.py:84` |
| Filter | `alpha = dt_ms / (tau + dt_ms)`, `y = alpha * convolve(u, (1 − alpha)^k)`, kernel cut at 1e-16 | `safe_pns_prediction.py:264-286` |
| Components | `stim1 = a1 * |LP_tau1(x)|`, `stim2 = a2 * LP_tau2(|x|)`, `stim3 = a3 * |LP_tau3(x)|` | `safe_pns_prediction.py:244-246` |
| Axis value | `(stim1 + stim2 + stim3) / stim_limit * g_scale * 100`, then `* 0.01` | `safe_pns_prediction.py:248`, `calc_pns.py:84` |
| Total | `sqrt(p_x^2 + p_y^2 + p_z^2)` | `calc_pns.py:87` |

Consequences:

1. The kept sample `k` has `x[k] = (g[k] − g[k − 1]) / dt`, with `g[−1] = 0`,
   because the sample before the first real sample is a padding zero.
2. The filter state before the first real sample is 0: the filter sees only
   padding zeros before it.
3. The padding after the file changes no kept sample (the filters are causal).
4. The convolution equals the recursion `y[k] = alpha * u[k] + (1 − alpha) *
   y[k − 1]` up to the kernel cut (1e-16) and float rounding.

### Example hardware (`safe_example_hw()`, `safe_pns_prediction.py:44-87`)

| Axis | tau1, tau2, tau3 (ms) | a1, a2, a3 | stim_limit (T/m/s) | g_scale |
|---|---|---|---|---|
| x | 0.20, 0.03, 3.00 | 0.40, 0.10, 0.50 | 30.0 | 0.35 |
| y | 1.50, 2.50, 0.15 | 0.55, 0.15, 0.30 | 15.0 | 0.31 |
| z | 2.00, 0.12, 1.00 | 0.42, 0.40, 0.18 | 25.0 | 0.25 |

### The assumption of plan section 3.1

Checked with `seq.block_durations` (largest distance of `duration / dt` from a
whole number) and each block's gradient events:

| Sequence | Blocks | Largest distance from a whole sample | Gradients not zero at a block border |
|---|---|---|---|
| `spin_echo_sequence` | 6 | 1.4e-14 | 0 |
| `gre_sequence` | 20 | 2.3e-13 | 0 |
| `arbitrary_gradient_sequence` | 1 | 0 | 1 |
| `empty_sequence` | 1 | 0 | 0 |
| repeating, 2000 TRs | 10,000 | 0 | 0 |
| worst, 2000 TRs | 10,000 | 2.8e-14 | 0 |
| `exvivo_gre_seg_0` | 39,304 | 0 | 0 |

`block_duration_raster` and `grad_raster_time` are both 10 µs in all of them.
The assumption holds: each block holds `n = round(duration / dt)` samples, at
the local times `(j + 0.5) * dt`.

A gradient that ends at 0 at a block border still has a non-zero last sample
(the sample at `border − dt / 2` is on the ramp). So the boundary term
`x[0] = (g[0] − g_prev_last) / dt` of the next block needs the last sample of
the block before, on the same axis.

### Block maps (plan section 3.3)

For one filter with `c = 1 − alpha`, a block of `n` samples, a start state `s`
and a boundary input `u0` (`x[0]`, or `|x[0]|` for the filter of `|x|`):

- `y[j] = c^j * (alpha * u0 + c * s) + h[j]`, `j = 0 ... n − 1`, where `h` is
  the zero-state response to `u[1 ... n − 1]` (`h[0] = 0`).
- `y[n − 1] = c^n * s + c^(n − 1) * alpha * u0 + h[n − 1]`.

`h` depends only on the event, the axis (through `alpha`) and `n`.

## Interface of `pns_lanes.js` (tasks 3 and 5)

A pure module, like `src/pulseq_reports/assets/seq_lanes.js`: one global
`PnsLanes`, and `module.exports = PnsLanes` in Node. No DOM.

```js
// tables: the decoded diagram tables ({name: TypedArray}), as SeqLanes.decode
//   takes them (diagram_data.diagram_tables, section 4.2 of
//   docs/plans/diagram-event-table.md). grad_value is in mT/m.
// opts: {gradRasterS: 1e-5, gamma: 42.576e6, hw: {x: {tau1, tau2, tau3, a1, a2,
//   a3, stim_limit, g_scale}, y: {...}, z: {...}}, groupBlocks: 64}
PnsLanes.decode(tables, opts) -> model

// The exact PNS samples in [t0, t1] (s): the samples k with t0 <= (k + 0.5) * dt
// <= t1. Float64Arrays of the same length.
PnsLanes.exactView(model, t0, t1) -> {t, total, x, y, z}

// Task 5: the min and max of each lane in each of `bins` equal bins of [t0, t1],
// within eps (the same unit as the lanes: 1 = the stimulation limit).
PnsLanes.minMaxView(model, t0, t1, bins, eps, options) -> {edges, lanes, stats}

// Task 5: the exact whole-file peak (ε = 0) and the peak time.
PnsLanes.peak(model, options) -> {peak, peakTimeS, axisPeaks, stats}
PnsLanes.plainPeak(model) -> {peak, peakTimeS, axisPeaks}  // sample recursion, baseline
```

### Data layout of the model

- `numBlocks`, `numSamples` (the sum of the block lengths), `dt`.
- `blockLen` (Uint32Array, N): `round(duration / dt)` of each block.
- For each group of `groupBlocks` blocks: the first sample index (Float64Array,
  exact for the sample counts here), and the checkpoint: 9 filter states and
  the 3 last gradient samples of the block before the group (12 Float64 values
  for each group).
- For each unique gradient event and each axis on which it plays: the samples
  `g[j]` (T/m) for the longest block length that it plays with, and for each of
  the 3 filters of that axis, `h[n − 1]` for each block length that it plays
  with, and `max |h|`. Compute them on demand and keep them in a cache (`Map`
  keyed by event, axis and `n`).
- Task 5 adds, for each group and each filter: the largest `|s|`, the largest
  `alpha * |u0|`, and the largest `max |h|` of its blocks.

## Results (2026-09-24)

Measured on a Mac with 10 cores and 64 GB, Node 24 and Python 3.12, with
`safe_example_hw()`. Raw numbers: `results/*.json`. "Repeating" and "worst"
are the builders of `scripts/diagram_scale.py`; "exvivo" is
`data/exvivo_gre_seg_0.seq` (39,304 blocks, 369.92 s).

### The Python reference (task 2)

`reference.py` (chunked `scipy.signal.lfilter`, the block cache off) equals
pypulseq `calculate_pns` to at most 8e-16 of the peak on 6 sequences, with
identical sample times, peaks and peak times.

| File | Samples per axis | Time | Peak RSS |
|---|---|---|---|
| exvivo | 3.7e7 | 2.9 s | 0.33 GB |
| repeating, 370 s (4e4 blocks) | 3.7e7 | 2.8 s | 0.33 GB |
| repeating, 10^6 blocks | 1.2e8 | 14.6 s (+ 8.7 s build) | 0.79 GB |

Stock `calculate_pns` needs about 260 s and 8 GB for the ex-vivo file.

### Question 1: accuracy

- The block maps against the plain per-sample recursion of the same module:
  at most 3.5e-15 of the peak (task 3).
- The JavaScript against the reference (task 4): at most 1e-13 of the peak
  on the synthetic sequences, but 1.1e-8 (repeating 12 s) to 7.1e-7
  (repeating 370 s) on long files. exvivo: 2.7e-7.
- Cause: pypulseq's gradient breakpoints drift from the 10 µs raster by
  float rounding of its block start times: at most 3.3e-12 s (12 s file),
  3.8e-11 s (exvivo) and 7.1e-11 s (370 s file). pypulseq samples at these
  drifted times, and `dgdt` divides by `dt`. The JavaScript samples at exact
  raster offsets from each block start. So the difference is the drift of
  the reference, not an error of the block maps.
- The difference is at most 7e-7 of the limit. The tolerance of the display
  is 8.6e-3 of the limit.
- Verdict: the plan's 1e-9 target against pypulseq cannot be met by any
  method that samples on exact raster positions. The block maps are exact.

### Question 2: zoomed-in speed

| File | Decode | RSS after decode |
|---|---|---|
| exvivo | 18 ms | 52 MB |
| repeating, 10^6 blocks | 260 ms | 76 MB |
| repeating, 10^7 blocks | 2.5 s | 240 MB |

`exactView`, 100 random places (the same for all three files, within a few
percent):

| View length | Median | 95th percentile |
|---|---|---|
| 1 ms | 0.04–0.2 ms | 0.1–0.4 ms |
| 10 ms | 0.1–0.3 ms | 0.1–0.4 ms |
| 100 ms | 0.8–0.9 ms | 0.9–1.1 ms |
| 1 s | 7.8–8.1 ms | 8.0–8.6 ms |
| 10 s | 78–79 ms | 80–81 ms |

The longest view with a 95th percentile of at most 50 ms is 1 s (not
10 s). The cost is about 80 ns for each sample, independent of the file
size. The inner loop was not optimized (it reads object properties for each
sample and axis), so a faster loop is likely possible, but it was not
measured.

### Question 3: zoomed-out speed (bounds and refinement)

All results were within ε of the brute force (5 views × 4 sequences, with and
without the cache). But the bounds do not prune:

| File | Whole-file render, 812 bins | Samples evaluated |
|---|---|---|
| repeating, 12 s | 475 ms (428 ms with the cache) | 2.4e6 (the file has 1.2e6) |
| exvivo | 2.7 s | 2.9e7 of 3.7e7 |

Random views of exvivo took 2.2 s each (a run of 100 views did not finish in
300 s). The upper bound `|v| + max |h|` of a block is far above its true
maximum, because the decay of the state and the block's own response cancel
in practice. The state cache hits rarely. Verdict: fails.

### Question 4: whole-file peak

| File | Bounds (exact) | Plain recursion | Samples evaluated by the bounds |
|---|---|---|---|
| repeating, 12 s | 91 ms | 134 ms | 5.1e5 of 1.2e6 |
| exvivo | 173 ms | 3.4 s | 9.0e5 of 3.7e7 |

Both give the same peak, bit for bit, and the same peak time. On exvivo the
bounds prune well. On the repeating sequence they evaluate 40% of the
samples, because many TRs come near the peak. At 10^7 repeating blocks this
extrapolates to about 90 s (not measured). Verdict: passes for exvivo, fails
at the 10^7-block target.

### Question 5: slew and |G| (task 6)

92 checks against a brute force: slew exact (equal), |G| equal. At 10^7
blocks: decode and precompute 2.7 s, 275 MB; whole-file render 3–8 ms; zoomed
views 2.6–6.1 ms at the 95th percentile. Verdict: passes. Note: task 6 used
the segment-slope definition of the slew, not the raster difference of the
SAFE model (a later decision of the user may change it).

### Recommendation (plan section 6)

1. **Compute PNS in Python.** The fork change of `safe_tau_lowpass` to
   `lfilter`, in chunks, gives the ex-vivo PNS in about 3 s and 0.3 GB. Python
   gives the summary numbers (peak, peak time, axis peaks) as now (question 4
   fails at 10^7 blocks in the browser).
2. **Zoomed-out PNS lanes from precomputed extrema.** Python stores the exact
   minimum and maximum of each PNS lane in fixed time bins (a pyramid built in
   the browser from the finest level). The bounds method is not used
   (question 3 fails).
3. **Zoomed-in PNS lanes on demand in the browser**, with the block maps of
   `pns_lanes.js`, for views up to about 1 s (question 2). The page needs no
   more data than the diagram tables for these views.
4. **The gap.** Views between the exact limit (1 s) and the finest stored bin
   × 812 bins need a decision in the lanes plan: a finer finest level for
   short files, a faster exact loop, or an envelope at the finest level in
   that range.
5. **Slew and |G| lanes on the fly** in the browser (question 5). The slew
   is also the input of the SAFE model (`dgdt`), and |G| uses the same
   polylines. So one per-event stage (each unique gradient event expanded one
   time) can feed the slew lane, the PNS filters and |G|.
6. **The accuracy target** against pypulseq must allow pypulseq's time drift
   (question 1): about 1e-6 of the peak for long files.
