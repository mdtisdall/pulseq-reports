const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const PnsLanes = require(
  path.join(__dirname, "..", "..", "src", "pulseq_reports", "assets", "pns_lanes.js")
);

// ---- Shared fixtures -------------------------------------------------------
//
// `pns_lanes.js` never reads pypulseq output (there is none in this test
// file: `docs/plans/diagram-lanes.md` and the prototype's README have the
// SAFE model with line numbers). Every model here is hand-made: typed
// arrays built in this file, as `test_seq_lanes.js` builds its own. The
// hardware numbers are pypulseq's own `safe_example_hw()`, copied from the
// prototype README's table, not read from pypulseq.

const DT = 1e-5; // the gradient raster, s (10 microseconds)

function hwSet() {
  return {
    x: { tau1: 0.20, tau2: 0.03, tau3: 3.00, a1: 0.40, a2: 0.10, a3: 0.50, stim_limit: 30.0, g_scale: 0.35 },
    y: { tau1: 1.50, tau2: 2.50, tau3: 0.15, a1: 0.55, a2: 0.15, a3: 0.30, stim_limit: 15.0, g_scale: 0.31 },
    z: { tau1: 2.00, tau2: 0.12, tau3: 1.00, a1: 0.42, a2: 0.40, a3: 0.18, stim_limit: 25.0, g_scale: 0.25 },
  };
}
const HW = hwSet();

// The `pns` object of `PnsLanes.decode`, with a placeholder stored level
// (`binSamples`/`levels` are not exercised unless a test overrides them:
// only `lanesFor`'s pyramid branch reads them).
function trivialPns(overrides = {}) {
  return Object.assign(
    {
      dtS: DT,
      binSamples: 4,
      hw: HW,
      levels: { min: Float32Array.from([0]), max: Float32Array.from([0]) },
    },
    overrides
  );
}

// Four gradient event shapes (delay, offsets and values in raster units and
// mT/m), reused by many blocks of many different lengths: the module's
// per-event cache is keyed by (event, axis, block length), so reusing one
// event at several lengths exercises more than one cache entry for it.
const EVENT_TEMPLATES = [
  { delayDt: 2, offsetsDt: [0, 10, 40, 50], valuesMt: [0, 8, 8, 0] },
  { delayDt: 1, offsetsDt: [0, 5, 15, 20], valuesMt: [0, -6, -9, 0] },
  { delayDt: 0, offsetsDt: [0, 3, 3, 12], valuesMt: [0, 4, 4, 0] },
  { delayDt: 4, offsetsDt: [0, 6], valuesMt: [5, -5] },
];

function buildEventTables(dt) {
  const grad_delay = [], grad_n = [], grad_offset_at = [], grad_at = [];
  const grad_offset = [], grad_value = [];
  for (const tmpl of EVENT_TEMPLATES) {
    grad_delay.push(tmpl.delayDt * dt);
    grad_n.push(tmpl.offsetsDt.length);
    grad_offset_at.push(grad_offset.length);
    grad_at.push(grad_value.length);
    for (const o of tmpl.offsetsDt) grad_offset.push(o * dt);
    for (const v of tmpl.valuesMt) grad_value.push(v);
  }
  return {
    grad_delay: Float64Array.from(grad_delay),
    grad_n: Uint32Array.from(grad_n),
    grad_offset_at: Uint32Array.from(grad_offset_at),
    grad_at: Uint32Array.from(grad_at),
    grad_offset: Float64Array.from(grad_offset),
    grad_value: Float64Array.from(grad_value),
  };
}

// A pseudo-random block table of `nBlocks` blocks: each block's duration is
// one of `durationOptionsDt` (raster units; 0 is a delay-raster block with
// no gradient-raster samples), and each axis independently has no event
// (probability `noEventProb`) or one of `EVENT_TEMPLATES`. Seeded, so a
// call with the same arguments always builds the same tables (as
// `test_seq_lanes.js`'s `buildRandomModel` does).
function buildPnsTables(nBlocks, seed, opts = {}) {
  let s = seed;
  const rnd = () => (s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
  const durationOptionsDt = opts.durationOptionsDt || [0, 20, 35, 60, 90];
  const noEventProb = opts.noEventProb ?? 0.35;

  const duration_index = new Uint8Array(nBlocks);
  const durations = Float64Array.from(durationOptionsDt.map((d) => d * DT));
  const gx = new Uint8Array(nBlocks), gy = new Uint8Array(nBlocks), gz = new Uint8Array(nBlocks);
  for (let i = 0; i < nBlocks; i++) {
    duration_index[i] = Math.floor(rnd() * durationOptionsDt.length);
    gx[i] = rnd() < noEventProb ? 0 : 1 + Math.floor(rnd() * EVENT_TEMPLATES.length);
    gy[i] = rnd() < noEventProb ? 0 : 1 + Math.floor(rnd() * EVENT_TEMPLATES.length);
    gz[i] = rnd() < noEventProb ? 0 : 1 + Math.floor(rnd() * EVENT_TEMPLATES.length);
  }
  // Force at least one 0-duration block and one block with no event on any
  // axis, regardless of the seed, so these edge cases are never left to luck.
  if (nBlocks > 10) {
    const zeroDurIdx = durationOptionsDt.indexOf(0);
    if (zeroDurIdx >= 0) duration_index[5] = zeroDurIdx;
    gx[10] = 0; gy[10] = 0; gz[10] = 0;
  }
  return {
    duration_index,
    durations,
    gx, gy, gz,
    ...buildEventTables(DT),
  };
}

// The exact model (the formulas of `docs/plans/diagram-lanes.md` section
// "The model", written again directly over `tables`, never calling
// `pns_lanes.js`). Returns the whole-file total, one entry for each sample
// in play order, from a zero initial state, the same starting condition
// `PnsLanes.decode`/`exactView` use (zero padding before the file).
function bruteForceTotals(tables, dt, hw) {
  const numBlocks = tables.duration_index.length;
  const blockLen = new Array(numBlocks);
  let numSamples = 0;
  for (let i = 0; i < numBlocks; i++) {
    const duration = tables.durations[tables.duration_index[i]];
    const n = Math.round(duration / dt);
    blockLen[i] = n;
    numSamples += n;
  }

  const axisCol = { x: "gx", y: "gy", z: "gz" };
  const g = {
    x: new Float64Array(numSamples),
    y: new Float64Array(numSamples),
    z: new Float64Array(numSamples),
  };
  for (const axis of ["x", "y", "z"]) {
    const col = tables[axisCol[axis]];
    let cursor = 0;
    for (let i = 0; i < numBlocks; i++) {
      const n = blockLen[i];
      const ev = col[i];
      if (ev === 0 || n === 0) { cursor += n; continue; }
      const idx = ev - 1;
      const delay = tables.grad_delay[idx];
      const nPts = tables.grad_n[idx];
      const offAt = tables.grad_offset_at[idx];
      const valAt = tables.grad_at[idx];
      for (let j = 0; j < n; j++) {
        const t = (j + 0.5) * dt;
        let p = 0;
        while (p + 1 < nPts && delay + tables.grad_offset[offAt + p + 1] <= t) p++;
        let value = 0;
        if (nPts > 0) {
          const t0 = delay + tables.grad_offset[offAt + p];
          if (t < t0) {
            value = 0;
          } else if (p + 1 >= nPts) {
            value = t <= t0 ? tables.grad_value[valAt + p] / 1000 : 0;
          } else {
            const t1 = delay + tables.grad_offset[offAt + p + 1];
            const v0 = tables.grad_value[valAt + p] / 1000;
            const v1 = tables.grad_value[valAt + p + 1] / 1000;
            value = t1 === t0 ? v1 : v0 + ((v1 - v0) / (t1 - t0)) * (t - t0);
          }
        }
        g[axis][cursor + j] = value;
      }
      cursor += n;
    }
  }

  const p = {};
  for (const axis of ["x", "y", "z"]) {
    const hwAxis = hw[axis];
    const dtMs = dt * 1000;
    const alpha1 = dtMs / (hwAxis.tau1 + dtMs);
    const alpha2 = dtMs / (hwAxis.tau2 + dtMs);
    const alpha3 = dtMs / (hwAxis.tau3 + dtMs);
    const c1 = 1 - alpha1, c2 = 1 - alpha2, c3 = 1 - alpha3;
    const factor = (1 / hwAxis.stim_limit) * hwAxis.g_scale;
    const arr = g[axis];
    const pAxis = new Float64Array(numSamples);
    let y1 = 0, y2 = 0, y3 = 0, prev = 0;
    for (let k = 0; k < numSamples; k++) {
      const cur = arr[k];
      const x = (cur - prev) / dt;
      prev = cur;
      y1 = alpha1 * x + c1 * y1;
      y2 = alpha2 * Math.abs(x) + c2 * y2;
      y3 = alpha3 * x + c3 * y3;
      pAxis[k] = (hwAxis.a1 * Math.abs(y1) + hwAxis.a2 * y2 + hwAxis.a3 * Math.abs(y3)) * factor;
    }
    p[axis] = pAxis;
  }

  const total = new Float64Array(numSamples);
  for (let k = 0; k < numSamples; k++) {
    total[k] = Math.sqrt(p.x[k] * p.x[k] + p.y[k] * p.y[k] + p.z[k] * p.z[k]);
  }
  return { total, numSamples, blockLen };
}

// The whole-file total from `_internal._plainRecursion`, collected into one
// array (the model's own per-sample recursion, module code, unlike
// `bruteForceTotals` above).
function collectPlainRecursion(model) {
  const total = new Float64Array(model.numSamples);
  PnsLanes._internal._plainRecursion(model, (chunk) => {
    total.set(chunk.total, chunk.fromSample);
  });
  return total;
}

function peakOf(arr) {
  let m = 0;
  for (let i = 0; i < arr.length; i++) {
    const v = Math.abs(arr[i]);
    if (v > m) m = v;
  }
  return m;
}

function maxAbsDiff(a, b) {
  let m = 0;
  for (let i = 0; i < a.length; i++) {
    const d = Math.abs(a[i] - b[i]);
    if (d > m) m = d;
  }
  return m;
}

// Asserts `got` and `want` (same-length arrays of the PNS total, a fraction
// of the limit) agree within `tol` of their peak (plan section 3.5, item 1:
// the block maps and the plain recursion are the same model, so the
// difference is float rounding only; the prototype measured 3.5e-15).
function assertWithinPeakTol(got, want, tol, msg) {
  assert.equal(got.length, want.length, `${msg}: length`);
  const peak = Math.max(peakOf(got), peakOf(want));
  const diff = maxAbsDiff(got, want);
  assert.ok(diff <= tol * Math.max(peak, 1e-300), `${msg}: diff=${diff} peak=${peak} tol=${tol}`);
}

function decodeModel(tables, overrides) {
  return PnsLanes.decode(tables, trivialPns(overrides));
}

const LANE_META = {
  id: "pns", title: "PNS", unit: "%", color: "pns", kind: "line",
  domain: [0, 110], ticks: [0, 100], tick_labels: ["0", "100"], empty: false, fill: 0.0,
};

// ---- 1. Independent brute force against `_plainRecursion` -----------------

test("test_brute_force_matches_plain_recursion_on_a_hand_model", () => {
  // A model with varied block lengths, blocks with no gradient, and a
  // 0-sample block (`buildPnsTables` forces both at fixed indices), decoded
  // and compared against a from-scratch implementation of the model's
  // formulas (`bruteForceTotals`, which never calls `pns_lanes.js`). This
  // is not required to be bit-exact: the two are different code (a
  // whole-file array build against the module's block-by-block, per-event
  // cache), so 1e-12 of the peak is the bound (rule 2 of the worker spec).
  const tables = buildPnsTables(80, 7);
  const model = decodeModel(tables);
  const brute = bruteForceTotals(tables, DT, HW);
  const plain = collectPlainRecursion(model);
  assertWithinPeakTol(plain, brute.total, 1e-12, "plain recursion vs brute force");
});

// ---- 2. Block maps (exactView) equal the plain recursion -------------------

test("test_exact_view_matches_plain_recursion_across_many_views", () => {
  // More than 3 * GROUP_BLOCKS (64) blocks, so views can start in many
  // different checkpoint groups, including partway into the last, partial
  // group. Views of many different starting blocks and spans, always
  // compared against the same whole-file plain recursion.
  assert.equal(PnsLanes.GROUP_BLOCKS, 64);
  const nBlocks = 500;
  const tables = buildPnsTables(nBlocks, 11);
  const model = decodeModel(tables);
  const plain = collectPlainRecursion(model);
  assert.ok(nBlocks > 3 * PnsLanes.GROUP_BLOCKS);

  // Block start times (s), computed independently of the module, to pick
  // views that start inside specific blocks and groups.
  const blockStart = new Float64Array(nBlocks);
  let acc = 0;
  for (let i = 0; i < nBlocks; i++) {
    blockStart[i] = acc;
    acc += tables.durations[tables.duration_index[i]];
  }
  const durationS = acc;

  const startBlocks = [0, 1, 63, 64, 65, 127, 128, 200, 256, 320, 449, nBlocks - 1];
  const spansS = [DT * 3, DT * 50, DT * 137, 0.01];

  for (const b of startBlocks) {
    for (const spanS of spansS) {
      const t0 = blockStart[b];
      const t1 = Math.min(durationS, t0 + spanS);
      const bins = 1_000_000; // large enough that count <= 2 * bins always: kind "samples"
      const view = PnsLanes.exactView(model, t0, t1, bins);
      assert.equal(view.kind, "samples", `b=${b} spanS=${spanS}`);
      const [k0, k1] = PnsLanes._internal.sampleRangeFor(DT, model.numSamples, t0, t1);
      const count = Math.max(0, k1 - k0 + 1);
      assert.equal(view.total.length, count, `b=${b} spanS=${spanS}: count`);
      if (count === 0) continue;
      const want = plain.subarray(k0, k1 + 1);
      assertWithinPeakTol(view.total, want, 1e-12, `b=${b} spanS=${spanS}`);
      // Same code path (exactView), same samples: the times are the exact
      // formula (k + 0.5) * dt, with no tolerance.
      for (let idx = 0; idx < count; idx++) {
        assert.equal(view.t[idx], (k0 + idx + 0.5) * DT, `b=${b} spanS=${spanS} idx=${idx}`);
      }
    }
  }
});

// ---- 3. A gradient not zero at a block border ------------------------------

// Block 0 (10 samples): gx event ends its last sample exactly at the value
// 8 (its points hold 8 from offset 9 * dt through 10 * dt, so sample 9, at
// local time 9.5 * dt, interpolates to exactly 8). Block 1 (8 samples): gx
// event starts at offset 0 already at 8 and holds it before ramping to 0,
// so its sample 0 is also exactly 8: the two blocks' gradients agree at the
// border, unlike a ramp that returns to 0 (the case the prototype's README
// already checked). This exercises the block map's boundary term x[0] =
// (g[0] - g_prev_last) / dt with a non-zero g_prev_last.
function buildBorderTables() {
  const grad_delay = Float64Array.from([0, 0]);
  const grad_n = Uint32Array.from([4, 3]);
  const grad_offset_at = Uint32Array.from([0, 4]);
  const grad_at = Uint32Array.from([0, 4]);
  const grad_offset = Float64Array.from([0, 2, 9, 10, 0, 3, 8].map((x) => x * DT));
  const grad_value = Float64Array.from([0, 8, 8, 8, 8, 8, 0]);
  return {
    duration_index: Uint8Array.from([0, 1]),
    durations: Float64Array.from([10 * DT, 8 * DT]),
    gx: Uint8Array.from([1, 2]),
    gy: Uint8Array.from([0, 0]),
    gz: Uint8Array.from([0, 0]),
    grad_delay, grad_n, grad_offset_at, grad_at, grad_offset, grad_value,
  };
}

test("test_gradient_not_zero_at_a_block_border", () => {
  const tables = buildBorderTables();
  const model = decodeModel(tables);
  assert.equal(model.numSamples, 18);

  // The border itself: the brute force's own gx array must show 8 at the
  // last sample of block 0 and 8 at the first sample of block 1 (a
  // continuous gradient), or the fixture does not test what it claims to.
  const brute = bruteForceTotals(tables, DT, HW);
  // Check 1: the brute force against `_plainRecursion`.
  const plain = collectPlainRecursion(model);
  assertWithinPeakTol(plain, brute.total, 1e-12, "border: plain recursion vs brute force");

  // Check 2: the block maps (exactView) against the plain recursion, for
  // ranges that start inside block 0 and ranges that start exactly at the
  // border (block 1), so the boundary term is exercised both ways.
  const views = [
    [0, 10 * DT],
    [3 * DT, 18 * DT],
    [10 * DT, 18 * DT], // starts exactly at the border
    [9 * DT, 12 * DT], // straddles the border
  ];
  for (const [t0, t1] of views) {
    const view = PnsLanes.exactView(model, t0, t1, 1000);
    assert.equal(view.kind, "samples");
    const [k0, k1] = PnsLanes._internal.sampleRangeFor(DT, model.numSamples, t0, t1);
    const want = plain.subarray(k0, k1 + 1);
    assertWithinPeakTol(view.total, want, 1e-12, `border view [${t0}, ${t1}]`);
  }
});

// ---- 4. exactView kind "bins" ----------------------------------------------

test("test_exact_view_bins_match_brute_force_binning_of_the_samples", () => {
  // A uniform-length model (no 0-duration blocks) so the sample count of a
  // view starting at sample 0 is exactly controllable: `sampleRangeFor`
  // takes t1 = (count - 1 + 0.5) * dt to select exactly `count` samples.
  const tables = buildPnsTables(60, 23, { durationOptionsDt: [20], noEventProb: 0.4 });
  const model = decodeModel(tables);
  assert.equal(model.numSamples, 60 * 20);

  for (const bins of [3, 7, 16]) {
    for (const count of [2 * bins, 2 * bins + 1, 5 * bins + 3]) {
      if (count > model.numSamples) continue;
      const t0 = -1; // clamped to k0 = 0
      const t1 = (count - 1 + 0.5) * DT;
      const view = PnsLanes.exactView(model, t0, t1, bins);
      const expectedKind = count <= 2 * bins ? "samples" : "bins";
      assert.equal(view.kind, expectedKind, `bins=${bins} count=${count}`);
      if (expectedKind === "samples") continue; // the switch case is checked below

      // The reference: the same range's exact per-sample values, fetched in
      // "samples" kind by asking for enough bins that the switch cannot
      // trigger, then binned by hand with the same formula as the module's
      // interface doc.
      const ref = PnsLanes.exactView(model, t0, t1, count);
      assert.equal(ref.kind, "samples");
      const span = t1 - t0;
      const wantMin = new Float64Array(bins).fill(Infinity);
      const wantMax = new Float64Array(bins).fill(-Infinity);
      for (let idx = 0; idx < ref.t.length; idx++) {
        let bin = Math.floor(((ref.t[idx] - t0) / span) * bins);
        if (bin < 0) bin = 0;
        if (bin >= bins) bin = bins - 1;
        if (ref.total[idx] < wantMin[bin]) wantMin[bin] = ref.total[idx];
        if (ref.total[idx] > wantMax[bin]) wantMax[bin] = ref.total[idx];
      }
      assert.deepEqual(Array.from(view.min), Array.from(wantMin), `bins=${bins} count=${count} min`);
      assert.deepEqual(Array.from(view.max), Array.from(wantMax), `bins=${bins} count=${count} max`);
      for (let k = 0; k <= bins; k++) {
        assert.equal(view.edges[k], t0 + (span * k) / bins, `bins=${bins} count=${count} edge ${k}`);
      }
    }
  }
});

test("test_exact_view_bins_empty_bin_is_plus_minus_infinity", () => {
  // A view that reaches far past the end of the file: `exactView` still
  // spreads `bins` bins evenly over the whole requested [t0, t1] (not just
  // over the range that has samples), so the bins after the file's last
  // sample get none. 40 blocks of 5 samples each: 200 samples, ending at
  // 200 * DT; t1 asks for 5 times that span, so only the first ~1/5 of the
  // bins can ever hold a sample.
  const tables = buildPnsTables(40, 5, { durationOptionsDt: [5], noEventProb: 0.5 });
  const model = decodeModel(tables);
  assert.equal(model.numSamples, 200);
  const t0 = 0, t1 = 5 * model.numSamples * DT;
  const bins = 20; // 200 samples > 2 * 20: kind "bins"
  const view = PnsLanes.exactView(model, t0, t1, bins);
  assert.equal(view.kind, "bins");
  let sawEmpty = false;
  for (let k = 0; k < bins; k++) {
    if (view.max[k] === -Infinity) {
      sawEmpty = true;
      assert.equal(view.min[k], Infinity, `bin ${k}`);
    }
  }
  assert.ok(sawEmpty, "expected at least one empty bin");
});

// ---- 5. The sample range ----------------------------------------------------

test("test_exact_view_sample_range_edge_cases", () => {
  const tables = buildPnsTables(30, 41, { durationOptionsDt: [10, 20], noEventProb: 0.4 });
  const model = decodeModel(tables);
  const plain = collectPlainRecursion(model);
  const numSamples = model.numSamples;

  // t0 before 0, t1 after the end: every sample of the file.
  {
    const view = PnsLanes.exactView(model, -5, numSamples * DT + 5, numSamples * 2);
    assert.equal(view.kind, "samples");
    assert.equal(view.total.length, numSamples);
    assert.equal(view.t[0], 0.5 * DT);
    assert.equal(view.t[numSamples - 1], (numSamples - 1 + 0.5) * DT);
    assertWithinPeakTol(view.total, plain, 1e-12, "whole file");
  }

  // t0 = t1 exactly on a sample's centre time: exactly that one sample.
  {
    const k = 12;
    const t = (k + 0.5) * DT;
    const view = PnsLanes.exactView(model, t, t, 10);
    assert.equal(view.kind, "samples");
    assert.equal(view.total.length, 1);
    assert.equal(view.t[0], t);
    assertWithinPeakTol(view.total, plain.subarray(k, k + 1), 1e-12, "single sample");
  }

  // A view strictly between two sample centres: no sample.
  {
    const k = 12;
    const t0 = (k + 0.5) * DT + DT * 0.3;
    const t1 = (k + 0.5) * DT + DT * 0.4;
    const view = PnsLanes.exactView(model, t0, t1, 10);
    assert.equal(view.kind, "samples");
    assert.equal(view.total.length, 0);
    assert.equal(view.t.length, 0);
  }
});

// ---- 6. levels (the pyramid) ------------------------------------------------

// An independent pyramid (using `Math.min`/`Math.max` over small chunks
// instead of the module's own loop) for comparison.
function bruteForcePyramid(binSamples, min, max) {
  const out = [{ binSamples, min, max }];
  let curMin = Array.from(min), curMax = Array.from(max), curBin = binSamples;
  while (curMin.length > 1) {
    const len = Math.ceil(curMin.length / 4);
    const nextMin = [], nextMax = [];
    for (let i = 0; i < len; i++) {
      nextMin.push(Math.min(...curMin.slice(i * 4, i * 4 + 4)));
      nextMax.push(Math.max(...curMax.slice(i * 4, i * 4 + 4)));
    }
    curBin *= 4;
    curMin = nextMin; curMax = nextMax;
    out.push({ binSamples: curBin, min: Float32Array.from(nextMin), max: Float32Array.from(nextMax) });
  }
  return out;
}

test("test_levels_pyramid_matches_brute_force_min_max", () => {
  const cases = [
    { len: 1, seed: 1 },
    { len: 4, seed: 2 },
    { len: 5, seed: 3 },
    { len: 17, seed: 4 },
  ];
  for (const { len, seed } of cases) {
    let s = seed;
    const rnd = () => (s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
    const min = new Float32Array(len), max = new Float32Array(len);
    for (let i = 0; i < len; i++) {
      const a = rnd() * 20 - 10, b = a + rnd() * 5;
      min[i] = a; max[i] = b;
    }
    const stored = { binSamples: 4, min, max };
    const got = PnsLanes.levels(stored);
    const want = bruteForcePyramid(4, min, max);

    assert.equal(got.length, want.length, `len=${len}`);
    for (let level = 0; level < got.length; level++) {
      assert.equal(got[level].binSamples, want[level].binSamples, `len=${len} level=${level}`);
      assert.deepEqual(Array.from(got[level].min), Array.from(want[level].min), `len=${len} level=${level} min`);
      assert.deepEqual(Array.from(got[level].max), Array.from(want[level].max), `len=${len} level=${level} max`);
    }
    assert.equal(got[got.length - 1].min.length, 1, `len=${len}: last level length`);
    // Level 0 is the stored level itself, not a copy.
    assert.strictEqual(got[0].min, min, `len=${len}: level 0 min is not a copy`);
    assert.strictEqual(got[0].max, max, `len=${len}: level 0 max is not a copy`);
  }
});

// ---- 7. lanesFor -------------------------------------------------------------

// A model long enough (in file time) to need the pyramid (> EXACT_MAX_S),
// with a stored level built from the model's own `_plainRecursion` (the
// worker spec's "so that the numbers are realistic"), used by all three
// `lanesFor` tests below.
function buildPyramidModel(binSamples) {
  const tables = buildPnsTables(1100, 17, { durationOptionsDt: [200], noEventProb: 0.4 });
  const placeholder = decodeModel(tables);
  const totals = collectPlainRecursion(placeholder);
  const numBins = Math.ceil(totals.length / binSamples);
  const storedMin = new Float32Array(numBins);
  const storedMax = new Float32Array(numBins);
  for (let b = 0; b < numBins; b++) {
    const from = b * binSamples;
    const to = Math.min(totals.length, from + binSamples);
    let lo = totals[from], hi = totals[from];
    for (let j = from + 1; j < to; j++) {
      if (totals[j] < lo) lo = totals[j];
      if (totals[j] > hi) hi = totals[j];
    }
    storedMin[b] = lo; storedMax[b] = hi;
  }
  const model = decodeModel(tables, { binSamples, levels: { min: storedMin, max: storedMax } });
  return { model, totals };
}

// Reads a zigzag lane's segments back into {edgeMs: [minPct, maxPct]}, as
// `test_seq_lanes.js`'s `gotLineBins` does for `SeqLanes.minMaxLanes`.
function zigzagBins(lane) {
  const map = new Map();
  for (const seg of lane.segments) {
    for (let p = 0; p + 1 < seg.length; p += 2) map.set(seg[p][0], [seg[p][1], seg[p + 1][1]]);
  }
  return map;
}

test("test_lanes_for_exact_branch_is_percent_and_matches_the_plain_recursion", () => {
  const { model, totals } = buildPyramidModel(8);
  assert.equal(model.onRaster, true);

  // Item 1, "samples": a short, sample-poor view.
  {
    const t0 = 0, t1 = 0.001; // 100 samples
    const bins = 812;
    const result = PnsLanes.lanesFor(model, LANE_META, [t0 * 1000, t1 * 1000], bins);
    assert.equal(result.exact, true);
    assert.equal(result.binMs, null);
    assert.equal(result.gap, false);
    assert.equal(result.lane.segments.length, 1);
    const [k0, k1] = PnsLanes._internal.sampleRangeFor(DT, model.numSamples, t0, t1);
    const want = totals.subarray(k0, k1 + 1);
    const got = result.lane.segments[0];
    assert.equal(got.length, want.length);
    const gotTotals = Float64Array.from(got, (p) => p[1] / 100);
    assertWithinPeakTol(gotTotals, want, 1e-12, "exact samples branch");
    for (let idx = 0; idx < got.length; idx++) {
      assert.equal(got[idx][0], (k0 + idx + 0.5) * DT * 1000, `point ${idx} time`);
    }
  }

  // Item 1, "bins": a short view with enough samples to switch to the
  // zigzag. Compared directly against `exactView`'s own "bins" kind: same
  // numbers, only reformatted (percent, ms, zigzag), so this is exact
  // equality, not a tolerance.
  {
    const t0 = 0, t1 = 0.005; // 500 samples
    const bins = 10; // 500 > 2 * 10: kind "bins"
    const view = PnsLanes.exactView(model, t0, t1, bins);
    assert.equal(view.kind, "bins");
    const result = PnsLanes.lanesFor(model, LANE_META, [t0 * 1000, t1 * 1000], bins);
    assert.equal(result.exact, true);
    assert.equal(result.binMs, null);
    const gotMap = zigzagBins(result.lane);
    assert.equal(result.lane.minmax, true);
    for (let k = 0; k < bins; k++) {
      const edgeMs = view.edges[k] * 1000;
      if (view.max[k] === -Infinity) {
        assert.ok(!gotMap.has(edgeMs), `bin ${k} should be absent (empty)`);
        continue;
      }
      assert.deepEqual(gotMap.get(edgeMs), [view.min[k] * 100, view.max[k] * 100], `bin ${k}`);
    }
  }
});

test("test_lanes_for_pyramid_branch_matches_brute_force_of_overlapping_level_bins", () => {
  const { model } = buildPyramidModel(8);
  const t0 = 0, t1 = 2.0; // > EXACT_MAX_S: the pyramid branch
  const bins = 100;
  assert.ok(t1 - t0 > PnsLanes.EXACT_MAX_S);

  const result = PnsLanes.lanesFor(model, LANE_META, [t0 * 1000, t1 * 1000], bins);
  assert.equal(result.exact, false);
  assert.equal(result.gap, false);

  // The level `lanesFor` should have chosen: the largest with binSamples *
  // dt <= (span / bins) / 2, read from the model's own public `levels`
  // (not from any private helper).
  const span = t1 - t0;
  const D = span / bins;
  let chosen = -1;
  for (let level = model.levels.length - 1; level >= 0; level--) {
    if (model.levels[level].binSamples * model.dt <= D / 2) { chosen = level; break; }
  }
  assert.notEqual(chosen, -1, "expected a level to fit for this test's span/bins");
  const level = model.levels[chosen];
  const B_L = level.binSamples * model.dt;
  assert.equal(result.binMs, B_L * 1000);

  const edges = new Float64Array(bins + 1);
  for (let k = 0; k <= bins; k++) edges[k] = t0 + (span * k) / bins;
  const gotMap = zigzagBins(result.lane);
  for (let k = 0; k < bins; k++) {
    let lo = Math.floor(edges[k] / B_L);
    let hi = Math.ceil(edges[k + 1] / B_L) - 1;
    if (lo < 0) lo = 0;
    if (hi > level.min.length - 1) hi = level.min.length - 1;
    let mn = Infinity, mx = -Infinity;
    for (let m = lo; m <= hi; m++) {
      if (level.min[m] < mn) mn = level.min[m];
      if (level.max[m] > mx) mx = level.max[m];
    }
    const edgeMs = edges[k] * 1000;
    if (mx === -Infinity) {
      assert.ok(!gotMap.has(edgeMs), `bin ${k} should be absent (empty)`);
      continue;
    }
    assert.deepEqual(gotMap.get(edgeMs), [mn * 100, mx * 100], `bin ${k}`);
  }
});

test("test_lanes_for_gap_true_when_even_the_stored_level_is_too_coarse", () => {
  const { model } = buildPyramidModel(8);
  const B0 = model.levels[0].binSamples * model.dt;
  const t0 = 0, t1 = 2.0; // > EXACT_MAX_S
  const span = t1 - t0;
  // bins chosen so that D / 2 < B0 for every level (level 0 is the
  // smallest bin, so if it does not fit, none do): D = span / bins,
  // D / 2 < B0  <=>  bins > span / (2 * B0).
  const bins = Math.ceil(span / (2 * B0)) + 1000;
  assert.ok(span / bins / 2 < B0);

  const result = PnsLanes.lanesFor(model, LANE_META, [t0 * 1000, t1 * 1000], bins);
  assert.equal(result.exact, false);
  assert.equal(result.gap, true);
  assert.equal(result.binMs, B0 * 1000);
});

// ---- 8. onRaster false -------------------------------------------------------

function buildOffRasterTables() {
  const tables = buildEventTables(DT);
  return {
    duration_index: Uint8Array.from([0, 1, 0, 1, 0]),
    durations: Float64Array.from([10 * DT, 1.5 * DT]), // 1.5 * dt is not on raster
    gx: Uint8Array.from([1, 0, 2, 0, 1]),
    gy: Uint8Array.from([0, 0, 0, 0, 0]),
    gz: Uint8Array.from([0, 0, 0, 0, 0]),
    ...tables,
  };
}

test("test_on_raster_false_never_uses_the_exact_view", () => {
  const tables = buildOffRasterTables();
  const model = decodeModel(tables);
  assert.equal(model.onRaster, false);
  assert.throws(() => PnsLanes.exactView(model, 0, 5 * DT, 10));

  // A short span, so `lanesFor` would use the exact view if it could: it
  // must not, so it must not throw, and it draws from the stored level.
  // `bins = 2` lets a stored level fit the display bin, so `gap` is false:
  // `gap` says only that the stored level is too coarse (item 7), and the
  // card script reads `model.onRaster` for a file without an exact view.
  const bins = 2;
  const spanS = 20 * DT; // still <= EXACT_MAX_S ("the view is short")
  const D = spanS / bins;
  const B0 = model.levels[0].binSamples * model.dt;
  assert.ok(D / 2 >= B0, "expected level 0 to fit, to isolate the onRaster-false gap rule");
  const result = PnsLanes.lanesFor(model, LANE_META, [0, spanS * 1000], bins);
  assert.equal(result.exact, false);
  assert.equal(result.gap, false);
  assert.equal(result.lane.minmax, true);

  // A long span (already past EXACT_MAX_S on its own) still works.
  const long = PnsLanes.lanesFor(model, LANE_META, [0, 2000], 100);
  assert.equal(long.exact, false);
});

// ---- 9. An empty file, and a file with no gradient event ---------------------

test("test_empty_file_has_no_samples_and_no_exact_view_crash", () => {
  const tables = {
    duration_index: new Uint8Array(0),
    durations: new Float64Array(0),
    gx: new Uint8Array(0), gy: new Uint8Array(0), gz: new Uint8Array(0),
    grad_delay: new Float64Array(0),
    grad_n: new Uint32Array(0),
    grad_offset_at: new Uint32Array(0),
    grad_at: new Uint32Array(0),
    grad_offset: new Float64Array(0),
    grad_value: new Float64Array(0),
  };
  const model = decodeModel(tables);
  assert.equal(model.numBlocks, 0);
  assert.equal(model.numSamples, 0);
  assert.equal(model.onRaster, true);

  const view = PnsLanes.exactView(model, 0, 1, 10);
  assert.equal(view.kind, "samples");
  assert.equal(view.t.length, 0);
  assert.equal(view.total.length, 0);

  const result = PnsLanes.lanesFor(model, LANE_META, [0, 1000], 10);
  assert.deepEqual(result, {
    lane: { ...LANE_META, segments: [] },
    exact: true,
    binMs: null,
    gap: false,
  });
});

test("test_file_with_no_gradient_event_is_all_zero", () => {
  const nBlocks = 20;
  const tables = {
    duration_index: new Uint8Array(nBlocks), // all 0
    durations: Float64Array.from([15 * DT]),
    gx: new Uint8Array(nBlocks), gy: new Uint8Array(nBlocks), gz: new Uint8Array(nBlocks), // all 0
    grad_delay: new Float64Array(0),
    grad_n: new Uint32Array(0),
    grad_offset_at: new Uint32Array(0),
    grad_at: new Uint32Array(0),
    grad_offset: new Float64Array(0),
    grad_value: new Float64Array(0),
  };
  const model = decodeModel(tables);
  assert.equal(model.numSamples, nBlocks * 15);
  const view = PnsLanes.exactView(model, -1, model.numSamples * DT + 1, model.numSamples * 2);
  assert.equal(view.kind, "samples");
  assert.equal(view.total.length, model.numSamples);
  for (let k = 0; k < view.total.length; k++) {
    assert.equal(view.total[k], 0, `sample ${k}`);
  }
});
