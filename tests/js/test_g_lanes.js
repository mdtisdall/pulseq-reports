const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const SeqLanes = require(
  path.join(__dirname, "..", "..", "src", "pulseq_reports", "assets", "seq_lanes.js")
);
const GLanes = require(
  path.join(__dirname, "..", "..", "src", "pulseq_reports", "assets", "g_lanes.js")
);

// ---- Model builders ---------------------------------------------------------
//
// `g_lanes.js` reads only duration_index, durations, gx, gy, gz and the grad_*
// event tables of a `SeqLanes.decode` model (the tables `docs/plans/diagram-lanes.md`
// phase 5 names), but `SeqLanes.decode` itself requires every known table (section
// 4.2 of docs/plans/diagram-event-table.md) to be present, so the RF and ADC tables
// below are empty (no RF, no ADC), not omitted.

function seqLaneMeta(id, kind) {
  return {
    id, title: id, unit: "", color: id, kind: kind || "line",
    domain: [0, 1], ticks: [0], tick_labels: ["0"], empty: false, fill: 0.0,
  };
}

const SEQ_LANES_META = [
  seqLaneMeta("rf_mag"),
  { ...seqLaneMeta("rf_phase"), fill: null },
  seqLaneMeta("adc", "gate"),
  seqLaneMeta("gx"),
  seqLaneMeta("gy"),
  seqLaneMeta("gz"),
];

// Four gradient event shapes (delay, offsets and values, s and mT/m), reused by many
// blocks: template 2 has a zero-length segment (two offsets at the same time, offset
// 3 == offset 2), and template 3 has only two points (a single piece) and is not zero
// at either end. A template carries no block duration: `buildGModel` draws each
// block's duration from `durationOptions`, independently of the events the block plays
// (see its comment), so that a block that draws one of these templates commonly has
// real padding on at least one side (`GLanes` pads each block to its whole duration,
// with 0 outside the event, so the tables need not avoid this case).
const EVENT_TEMPLATES = [
  { delay: 2e-5, offsets: [0, 1e-4, 4e-4, 5e-4], values: [0, 8, 8, 0] },
  { delay: 1e-5, offsets: [0, 5e-5, 1.5e-4, 2e-4], values: [0, -6, -9, 0] },
  { delay: 0, offsets: [0, 3e-5, 3e-5, 1.2e-4], values: [0, 4, 4, 0] },
  { delay: 4e-5, offsets: [0, 6e-5], values: [5, -5] },
];

function buildEventTables() {
  const grad_delay = [], grad_n = [], grad_offset_at = [], grad_at = [];
  const grad_offset = [], grad_value = [];
  for (const tmpl of EVENT_TEMPLATES) {
    grad_delay.push(tmpl.delay);
    grad_n.push(tmpl.offsets.length);
    grad_offset_at.push(grad_offset.length);
    grad_at.push(grad_value.length);
    for (const o of tmpl.offsets) grad_offset.push(o);
    for (const v of tmpl.values) grad_value.push(v);
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

// A pseudo-random block table of `nBlocks` blocks, decoded through
// `SeqLanes.decode` (as `test_seq_lanes.js`'s `buildRandomModel` is). Each axis
// independently has no event (probability `noEventProb`) or one of
// `EVENT_TEMPLATES`. A block that has an event draws its own duration independently
// of which events it plays (`durationOptions`, deliberately not tied to any event's
// own span or delay), so it commonly has real padding before its first event's own
// delay and after its last event's own end, or is longer than every one of its
// events put together: exactly the case `_tripleGeometry`'s padding (`_tripleTimes`)
// is for. A block with no event may still draw the 0 duration option (a delay-only
// marker block); a block that has an event never does (real `diagram_tables` output
// never has one either: `add_block` sets a block's duration to the longest of its
// own events, so an event of positive duration always makes its own block's
// duration positive too) -- picking 0 for such a block would ask `GLanes` a question
// its own tables can never pose (an event whose own breakpoints reach past its
// block's zero-length span), not exercise the padding this test targets. Seeded, so
// a call with the same arguments always builds the same tables. Forces (regardless
// of the seed, when `nBlocks` is large enough): a 0-duration block (with no event) at
// index 5, a block with no event on any axis at index 10, and a block with an event
// on only one axis (gx) at index 11 (`opts.forceSpecialBlocks: false` turns this off,
// for a caller that wants every block to have no event: the forced block 11 always
// has one on gx, which would defeat that).
function buildGModel(nBlocks, seed, opts = {}) {
  let s = seed;
  const rnd = () => (s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
  const durationOptions = opts.durationOptions || [0, 2e-4, 3.5e-4, 6e-4, 9e-4];
  const noEventProb = opts.noEventProb ?? 0.35;
  const forceSpecialBlocks = opts.forceSpecialBlocks ?? true;
  const allDurationIdxs = durationOptions.map((_, idx) => idx);
  const nonZeroDurationIdxs = allDurationIdxs.filter(idx => durationOptions[idx] > 0);

  const duration_index = new Uint8Array(nBlocks);
  const durations = Float64Array.from(durationOptions);
  const gx = new Uint8Array(nBlocks), gy = new Uint8Array(nBlocks), gz = new Uint8Array(nBlocks);
  for (let i = 0; i < nBlocks; i++) {
    gx[i] = rnd() < noEventProb ? 0 : 1 + Math.floor(rnd() * EVENT_TEMPLATES.length);
    gy[i] = rnd() < noEventProb ? 0 : 1 + Math.floor(rnd() * EVENT_TEMPLATES.length);
    gz[i] = rnd() < noEventProb ? 0 : 1 + Math.floor(rnd() * EVENT_TEMPLATES.length);
    const hasEvent = gx[i] !== 0 || gy[i] !== 0 || gz[i] !== 0;
    const idxs = hasEvent && nonZeroDurationIdxs.length > 0 ? nonZeroDurationIdxs : allDurationIdxs;
    duration_index[i] = idxs[Math.floor(rnd() * idxs.length)];
  }
  if (nBlocks > 12 && forceSpecialBlocks) {
    const zeroIdx = durationOptions.indexOf(0);
    // A 0-duration block never has an event either (the same reason a block with an
    // event never draws the 0 duration option, above): clear whatever the main loop
    // assigned it, so this forced block stays consistent with real `diagram_tables`
    // output.
    if (zeroIdx >= 0) duration_index[5] = zeroIdx;
    gx[5] = 0; gy[5] = 0; gz[5] = 0;
    gx[10] = 0; gy[10] = 0; gz[10] = 0;
    gx[11] = 1; gy[11] = 0; gz[11] = 0;
  }

  const nCp = Math.ceil(nBlocks / 1024) || 1;
  const checkpoints = new Float64Array(nCp);
  let t = 0.0;
  for (let i = 0; i < nBlocks; i++) {
    if (i % 1024 === 0) checkpoints[i / 1024] = t;
    t += durations[duration_index[i]];
  }

  const tables = {
    duration_index, durations, checkpoints,
    rf: new Uint8Array(nBlocks),
    adc: new Uint8Array(nBlocks),
    gx, gy, gz,
    rf_delay: new Float64Array(0),
    rf_mag_n: new Uint32Array(0),
    rf_mag_offset_at: new Uint32Array(0),
    rf_mag_at: new Uint32Array(0),
    rf_mag_offset: new Float64Array(0),
    rf_mag: new Float64Array(0),
    rf_phase_n: new Uint32Array(0),
    rf_phase_offset_at: new Uint32Array(0),
    rf_phase_at: new Uint32Array(0),
    rf_phase_offset: new Float64Array(0),
    rf_phase: new Float64Array(0),
    adc_delay: new Float64Array(0),
    adc_length: new Float64Array(0),
    ...buildEventTables(),
  };
  const seqModel = SeqLanes.decode(1, tables, SEQ_LANES_META);
  return { tables, seqModel };
}

// The block starts (s), computed independently of both modules by a running sum, for
// picking views that start inside a particular block.
function blockStarts(tables) {
  const N = tables.duration_index.length;
  const starts = new Float64Array(N);
  let t = 0;
  for (let i = 0; i < N; i++) {
    starts[i] = t;
    t += tables.durations[tables.duration_index[i]];
  }
  return { starts, durationS: t };
}

// ---- An independent brute force, straight from the raw tables (never calling any
// function of g_lanes.js): the union-of-breakpoints piecewise-quadratic rule of
// g_lanes.js's own module doc, applied to every block of a bin (not the module's
// group tree), clipped bin by bin, with the whole block padded to 0 outside every
// event (not just the union of the events' own spans). A bin with no block
// overlapping it at all keeps [Infinity, -Infinity] ("no value"), the same
// convention `GLanes.minMax` uses; a bin (or part of one) that lies in the padding
// gets the real value 0, never "no value". -----

// 0 strictly before the event's first point or strictly after its last (a gradient
// is 0 outside the event it belongs to, whatever the block's own duration or the
// event's own delay -- g_lanes.js's `_axisValueAt`, independently reimplemented
// here); the event's own recorded value at exactly its first or last point (which
// need not be 0); linear interpolation between its own breakpoints otherwise.
function bruteAxisValueAt(times, values, t) {
  if (times === null) return 0;
  const n = times.length;
  if (n === 0) return 0;
  if (t <= times[0]) return t === times[0] ? values[0] : 0;
  if (t >= times[n - 1]) return t === times[n - 1] ? values[n - 1] : 0;
  let lo = 0, hi = n;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (times[mid] < t) lo = mid + 1; else hi = mid;
  }
  if (times[lo] === t) return values[lo];
  const t1 = times[lo - 1], t2 = times[lo];
  const v1 = values[lo - 1], v2 = values[lo];
  return v1 + (v2 - v1) / (t2 - t1) * (t - t1);
}

function bruteEventTimesValues(tb, k) {
  if (k === 0) return { times: null, values: null };
  const idx = k - 1;
  const n = tb.grad_n[idx];
  const offAt = tb.grad_offset_at[idx];
  const valAt = tb.grad_at[idx];
  const delay = tb.grad_delay[idx];
  const times = new Float64Array(n);
  const values = new Float64Array(n);
  for (let p = 0; p < n; p++) {
    times[p] = delay + tb.grad_offset[offAt + p];
    values[p] = tb.grad_value[valAt + p];
  }
  return { times, values };
}

function bruteQuadExtrema(A, B, C, ta, tb) {
  const fa = (A * ta + B) * ta + C;
  const fb = (A * tb + B) * tb + C;
  let lo = fa < fb ? fa : fb;
  const hi = fa > fb ? fa : fb;
  if (A > 0) {
    const tv = -B / (2 * A);
    if (tv > ta && tv < tb) {
      const fv = C - (B * B) / (4 * A);
      if (fv < lo) lo = fv;
    }
  }
  return [lo, hi];
}

// The exact min/max |G| of block `i` (starting at `bStart`, duration `dur`),
// restricted to `[loAbs, hiAbs)` clipped to the block's own extent, or null when
// there is no positive-length overlap.
function bruteBlockGRange(tb, i, bStart, dur, loAbs, hiAbs) {
  const overlapLo = Math.max(bStart, loAbs);
  const overlapHi = Math.min(bStart + dur, hiAbs);
  if (overlapHi <= overlapLo) return null;

  const kx = tb.gx[i], ky = tb.gy[i], kz = tb.gz[i];
  const ex = bruteEventTimesValues(tb, kx);
  const ey = bruteEventTimesValues(tb, ky);
  const ez = bruteEventTimesValues(tb, kz);
  // The block's own start and end are always in the piece list, whether or not any
  // axis's own event reaches them (g_lanes.js's `_tripleTimes`, independently
  // reimplemented here): a block can be longer than its events (a short trapezoid
  // with a longer delay, ADC or RF ringdown in the same block), and its events can
  // all start after a delay, and in those stretches |G| is 0, not "no value".
  const merged = new Set([0, dur]);
  for (const e of [ex, ey, ez]) {
    if (e.times !== null) for (let p = 0; p < e.times.length; p++) merged.add(e.times[p]);
  }
  const times = Array.from(merged).sort((a, b) => a - b);
  const relLo = overlapLo - bStart, relHi = overlapHi - bStart;

  let lo = Infinity, hi = -Infinity;
  for (let p = 1; p < times.length; p++) {
    const t0v = times[p - 1], t1v = times[p];
    if (t1v <= relLo || t0v >= relHi) continue;
    const clipLo = Math.max(t0v, relLo), clipHi = Math.min(t1v, relHi);
    if (clipHi <= clipLo) continue;
    const vx0 = bruteAxisValueAt(ex.times, ex.values, t0v), vx1 = bruteAxisValueAt(ex.times, ex.values, t1v);
    const vy0 = bruteAxisValueAt(ey.times, ey.values, t0v), vy1 = bruteAxisValueAt(ey.times, ey.values, t1v);
    const vz0 = bruteAxisValueAt(ez.times, ez.values, t0v), vz1 = bruteAxisValueAt(ez.times, ez.values, t1v);
    let A = 0, B = 0, C = 0;
    for (const pair of [[vx0, vx1], [vy0, vy1], [vz0, vz1]]) {
      const d = pair[1] - pair[0];
      A += d * d;
      B += 2 * pair[0] * d;
      C += pair[0] * pair[0];
    }
    const ta = (clipLo - t0v) / (t1v - t0v), tbEnd = (clipHi - t0v) / (t1v - t0v);
    const extrema = bruteQuadExtrema(A, B, C, ta, tbEnd);
    const a = Math.sqrt(Math.max(0, extrema[0])), b = Math.sqrt(Math.max(0, extrema[1]));
    if (a < lo) lo = a;
    if (b > hi) hi = b;
  }
  if (times.length < 2) return [0, 0];
  return hi === -Infinity ? null : [lo, hi];
}

// The exact minimum/maximum |G| in each of `bins` equal bins of `[t0, t1]`, from
// `bruteBlockGRange` applied to every block that could overlap the view (never
// `g_lanes.js`'s group tree or its per-triple cache).
function bruteMinMax(tables, t0, t1, bins) {
  const N = tables.duration_index.length;
  const edges = new Float64Array(bins + 1);
  const span = t1 - t0;
  for (let k = 0; k <= bins; k++) edges[k] = t0 + span * k / bins;
  const outMin = new Float64Array(bins).fill(Infinity);
  const outMax = new Float64Array(bins).fill(-Infinity);

  let start = 0;
  for (let i = 0; i < N; i++) {
    const dur = tables.durations[tables.duration_index[i]];
    const bStart = start;
    start += dur;
    if (bStart + dur < t0 || bStart > t1) continue;
    for (let k = 0; k < bins; k++) {
      const range = bruteBlockGRange(tables, i, bStart, dur, edges[k], edges[k + 1]);
      if (range === null) continue;
      if (range[0] < outMin[k]) outMin[k] = range[0];
      if (range[1] > outMax[k]) outMax[k] = range[1];
    }
  }
  return { edges, min: outMin, max: outMax };
}

// Asserts `got` (a `GLanes.minMax` result) and `want` (a `bruteMinMax` result) agree:
// exactly on which bins are empty (both `max[k] === -Infinity`, or neither), and
// within `tol` of the overall peak on every other bin's min and max (the fast path
// and the brute force both use the piecewise-quadratic closed form, but a clipped
// sub-piece computes its own ta/tb from a division that a whole, unclipped piece does
// not, so the two can differ in the last bit -- the same reasoning the prototype's
// own brute force comparison used, 1e-12 relative to the peak).
function assertMinMaxMatches(got, want, tol, msg) {
  assert.equal(got.min.length, want.min.length, `${msg}: length`);
  const bins = got.min.length;
  let peak = 0;
  for (let k = 0; k < bins; k++) {
    if (Number.isFinite(want.max[k])) peak = Math.max(peak, Math.abs(want.max[k]));
  }
  let maxDiff = 0;
  for (let k = 0; k < bins; k++) {
    const gotEmpty = got.max[k] === -Infinity;
    const wantEmpty = want.max[k] === -Infinity;
    assert.equal(gotEmpty, wantEmpty, `${msg}: bin ${k} emptiness (got=${got.max[k]} want=${want.max[k]})`);
    if (gotEmpty) {
      assert.equal(got.min[k], Infinity, `${msg}: bin ${k} min should be Infinity when empty`);
      continue;
    }
    maxDiff = Math.max(maxDiff, Math.abs(got.min[k] - want.min[k]), Math.abs(got.max[k] - want.max[k]));
  }
  assert.ok(maxDiff <= tol * Math.max(peak, 1e-300), `${msg}: maxDiff=${maxDiff} peak=${peak} tol=${tol}`);
}

// ---- 1. minMax against the brute force, many views --------------------------------

test("test_min_max_matches_brute_force_across_many_views", () => {
  assert.equal(GLanes.GROUP_BLOCKS, 64);
  const nBlocks = 300; // > 4 * GROUP_BLOCKS: crosses more than one checkpoint group
  assert.ok(nBlocks > 4 * GLanes.GROUP_BLOCKS);
  const { tables, seqModel } = buildGModel(nBlocks, 13);
  const model = GLanes.decode(seqModel);
  const { starts, durationS } = blockStarts(tables);

  const views = [
    // Whole file.
    [0, durationS, 37],
    // Whole file, more bins than blocks in many groups (cuts blocks finely).
    [0, durationS, 211],
    // Zoomed, cutting blocks, starting and ending mid-block.
    [starts[20] + 0.3 * (starts[21] - starts[20]), starts[90] + 0.6 * (starts[91] - starts[90]), 23],
    // A range inside a single block (no bin ever spans more than one block).
    [starts[50], starts[51], 5],
    // A range that crosses many checkpoint groups (> GROUP_BLOCKS blocks between the
    // two edges' own blocks), so `_rangeGMinMax`'s tree branch is exercised.
    [starts[10], starts[280], 17],
    // A range that starts exactly at the forced 0-duration block (index 5) and the
    // forced no-event/one-axis blocks (10, 11).
    [starts[4], starts[13], 9],
  ];
  for (const [t0, t1, bins] of views) {
    const got = GLanes.minMax(model, t0, t1, bins);
    const want = bruteMinMax(tables, t0, t1, bins);
    assertMinMaxMatches(got, want, 1e-12, `[${t0}, ${t1}] bins=${bins}`);
  }
});

// ---- 2. A gradient not zero at a block border; blocks with an event on only one
// axis -----------------------------------------------------------------------------

// Block 0 (duration exactly its gx event's own span): the event ramps up and holds
// at 8 mT/m through the block's end (its last two points are both 8, at offsets 9 and
// 10 raster steps, so the polyline is flat, not zero, at the border). Block 1: its gx
// event starts already at 8 (offset 0), the same value, so the two blocks' gradients
// agree at the border (a continuous gradient, unlike a ramp that returns to 0). Both
// blocks have gy = gz = 0 (an event on only the gx axis). Block 2: gy only. Block 3:
// gz only.
function buildBorderTables() {
  const DT = 1e-5;
  const grad_delay = Float64Array.from([0, 0, 0, 0]);
  const grad_n = Uint32Array.from([4, 3, 2, 2]);
  const grad_offset_at = Uint32Array.from([0, 4, 7, 9]);
  const grad_at = Uint32Array.from([0, 4, 7, 9]);
  const grad_offset = Float64Array.from(
    [0, 2, 9, 10, 0, 3, 8, 0, 5, 0, 4].map(x => x * DT)
  );
  const grad_value = Float64Array.from([0, 8, 8, 8, 8, 8, 0, 0, 6, 0, -3]);
  return {
    duration_index: Uint8Array.from([0, 1, 2, 3]),
    durations: Float64Array.from([10 * DT, 8 * DT, 5 * DT, 4 * DT]),
    checkpoints: Float64Array.from([0.0]),
    rf: new Uint8Array(4),
    adc: new Uint8Array(4),
    gx: Uint8Array.from([1, 2, 0, 0]),
    gy: Uint8Array.from([0, 0, 3, 0]),
    gz: Uint8Array.from([0, 0, 0, 4]),
    rf_delay: new Float64Array(0),
    rf_mag_n: new Uint32Array(0),
    rf_mag_offset_at: new Uint32Array(0),
    rf_mag_at: new Uint32Array(0),
    rf_mag_offset: new Float64Array(0),
    rf_mag: new Float64Array(0),
    rf_phase_n: new Uint32Array(0),
    rf_phase_offset_at: new Uint32Array(0),
    rf_phase_at: new Uint32Array(0),
    rf_phase_offset: new Float64Array(0),
    rf_phase: new Float64Array(0),
    adc_delay: new Float64Array(0),
    adc_length: new Float64Array(0),
    grad_delay, grad_n, grad_offset_at, grad_at, grad_offset, grad_value,
  };
}

test("test_gradient_not_zero_at_a_block_border_and_single_axis_blocks", () => {
  const tables = buildBorderTables();
  const seqModel = SeqLanes.decode(1, tables, SEQ_LANES_META);
  const model = GLanes.decode(seqModel);
  const { durationS } = blockStarts(tables);

  // The border itself: the brute force's own gx values must show 8 at the end of
  // block 0 and 8 at the start of block 1, or the fixture does not test what it
  // claims to.
  const DT = 1e-5;
  const nearBorder = bruteBlockGRange(tables, 0, 0, 10 * DT, 10 * DT - 1e-9, 10 * DT);
  assert.ok(Math.abs(nearBorder[1] - 8) < 1e-9, "expected the fixture's gx to reach 8 at the border");

  const views = [
    [0, durationS, 1],
    [0, durationS, 4], // one bin per block, roughly
    [0, 10 * DT, 3], // block 0 alone
    [10 * DT, 18 * DT, 3], // block 1 alone, starting exactly at the border
    [9 * DT, 12 * DT, 5], // straddles the border
    [0, durationS, 27], // many bins, cutting every block finely
  ];
  for (const [t0, t1, bins] of views) {
    const got = GLanes.minMax(model, t0, t1, bins);
    const want = bruteMinMax(tables, t0, t1, bins);
    assertMinMaxMatches(got, want, 1e-12, `border view [${t0}, ${t1}] bins=${bins}`);
  }
});

// ---- 2b. Padding: a block longer than its own gradient, and a block whose
// gradients all start after a delay -------------------------------------------------

// One block, duration 20 * DT. gx: delay 0, offsets [0, 4, 6, 10] * DT (ends at
// 10 * DT, well before the block's own end at 20 * DT), values [0, 8, 8, 0]. gy =
// gz = 0 (no event at all). So |G| = gx for t in [0, 10 * DT], and must be exactly 0
// (padding, not "no value") for t in [10 * DT, 20 * DT] -- a block longer than its
// own gradient event.
function buildTailPaddingTables(offsetsDt = [0, 4, 6, 10], values = [0, 8, 8, 0]) {
  const DT = 1e-5;
  const grad_delay = Float64Array.from([0]);
  const grad_n = Uint32Array.from([offsetsDt.length]);
  const grad_offset_at = Uint32Array.from([0]);
  const grad_at = Uint32Array.from([0]);
  const grad_offset = Float64Array.from(offsetsDt.map(x => x * DT));
  const grad_value = Float64Array.from(values);
  return {
    duration_index: Uint8Array.from([0]),
    durations: Float64Array.from([20 * DT]),
    checkpoints: Float64Array.from([0.0]),
    rf: new Uint8Array(1),
    adc: new Uint8Array(1),
    gx: Uint8Array.from([1]),
    gy: Uint8Array.from([0]),
    gz: Uint8Array.from([0]),
    rf_delay: new Float64Array(0),
    rf_mag_n: new Uint32Array(0),
    rf_mag_offset_at: new Uint32Array(0),
    rf_mag_at: new Uint32Array(0),
    rf_mag_offset: new Float64Array(0),
    rf_mag: new Float64Array(0),
    rf_phase_n: new Uint32Array(0),
    rf_phase_offset_at: new Uint32Array(0),
    rf_phase_at: new Uint32Array(0),
    rf_phase_offset: new Float64Array(0),
    rf_phase: new Float64Array(0),
    adc_delay: new Float64Array(0),
    adc_length: new Float64Array(0),
    grad_delay, grad_n, grad_offset_at, grad_at, grad_offset, grad_value,
  };
}

test("test_bins_in_the_tail_padding_after_a_shorter_gradient_are_zero_not_empty", () => {
  const tables = buildTailPaddingTables();
  const seqModel = SeqLanes.decode(1, tables, SEQ_LANES_META);
  const model = GLanes.decode(seqModel);
  const DT = 1e-5;

  // A bin entirely inside the padding tail [10 * DT, 20 * DT]: exactly [0, 0] (a
  // real value, never "no value" -- SeqLanes.blockAt still resolves every edge to
  // this one block, so `_exactBlockGRange` is asked about a range fully inside it).
  let view = GLanes.minMax(model, 12 * DT, 18 * DT, 1);
  assert.deepEqual([view.min[0], view.max[0]], [0, 0]);

  // A bin that straddles the transition from the ramp's flat-top value (8, held
  // until 6 * DT) through the fall to 0 (10 * DT) and into the padding: the minimum
  // must be 0 (the padding is part of the bin), and the maximum must still be the
  // event's own peak (8), which the bin also covers.
  view = GLanes.minMax(model, 6 * DT, 14 * DT, 1);
  assert.equal(view.min[0], 0, "minimum must include the padding's 0");
  assert.equal(view.max[0], 8);

  // Cross-check every view above against the (now also padding-aware) brute force.
  for (const [t0, t1, bins] of [[12 * DT, 18 * DT, 1], [6 * DT, 14 * DT, 1], [0, 20 * DT, 6]]) {
    const got = GLanes.minMax(model, t0, t1, bins);
    const want = bruteMinMax(tables, t0, t1, bins);
    assertMinMaxMatches(got, want, 1e-12, `tail padding view [${t0}, ${t1}] bins=${bins}`);
  }
});

// A gradient that ends at a value that is not 0 at the block end (it continues into the
// next block), with its last point a rounding error before the block duration: the
// block end must not become a separate breakpoint, or a piece of almost no width would
// fall from 8 to 0 and give the last bin a false minimum of 0.
test("test_a_gradient_ending_non_zero_a_hair_before_the_block_end_has_no_false_zero", () => {
  const DT = 1e-5;
  const lastDt = 20 - 1e-12; // 1e-17 s before the block end, as float rounding can put it
  const tables = buildTailPaddingTables([0, 4, lastDt], [0, 8, 8]);
  const model = GLanes.decode(SeqLanes.decode(1, tables, SEQ_LANES_META));
  const view = GLanes.minMax(model, 15 * DT, 20 * DT, 1);
  assert.deepEqual([view.min[0], view.max[0]], [8, 8]);
});

// One block, duration 20 * DT. gx: delay 8 * DT, offsets [0, 2, 6, 8] * DT (absolute
// [8, 10, 14, 16] * DT), values [0, -5, -5, 0]. gy: delay 5 * DT, offsets
// [0, 3, 3, 9] * DT (absolute [5, 8, 8, 14] * DT), values [0, 6, 6, 0]. gz = 0. Every
// active axis starts only after a delay (8 * DT and 5 * DT, both > 0), so |G| must be
// exactly 0 (padding) for t in [0, 5 * DT) -- before either axis has started.
function buildHeadPaddingTables() {
  const DT = 1e-5;
  const grad_delay = Float64Array.from([8 * DT, 5 * DT]);
  const grad_n = Uint32Array.from([4, 4]);
  const grad_offset_at = Uint32Array.from([0, 4]);
  const grad_at = Uint32Array.from([0, 4]);
  const grad_offset = Float64Array.from([0, 2, 6, 8, 0, 3, 3, 9].map(x => x * DT));
  const grad_value = Float64Array.from([0, -5, -5, 0, 0, 6, 6, 0]);
  return {
    duration_index: Uint8Array.from([0]),
    durations: Float64Array.from([20 * DT]),
    checkpoints: Float64Array.from([0.0]),
    rf: new Uint8Array(1),
    adc: new Uint8Array(1),
    gx: Uint8Array.from([1]),
    gy: Uint8Array.from([2]),
    gz: Uint8Array.from([0]),
    rf_delay: new Float64Array(0),
    rf_mag_n: new Uint32Array(0),
    rf_mag_offset_at: new Uint32Array(0),
    rf_mag_at: new Uint32Array(0),
    rf_mag_offset: new Float64Array(0),
    rf_mag: new Float64Array(0),
    rf_phase_n: new Uint32Array(0),
    rf_phase_offset_at: new Uint32Array(0),
    rf_phase_at: new Uint32Array(0),
    rf_phase_offset: new Float64Array(0),
    rf_phase: new Float64Array(0),
    adc_delay: new Float64Array(0),
    adc_length: new Float64Array(0),
    grad_delay, grad_n, grad_offset_at, grad_at, grad_offset, grad_value,
  };
}

test("test_bins_in_the_head_padding_before_every_delayed_gradient_are_zero_not_empty", () => {
  const tables = buildHeadPaddingTables();
  const seqModel = SeqLanes.decode(1, tables, SEQ_LANES_META);
  const model = GLanes.decode(seqModel);
  const DT = 1e-5;

  // A bin entirely inside the head padding [0, 5 * DT): exactly [0, 0].
  let view = GLanes.minMax(model, 0, 4 * DT, 1);
  assert.deepEqual([view.min[0], view.max[0]], [0, 0]);

  // A bin that straddles the start of gy's own event (5 * DT, the earlier of the
  // two delays): the minimum must be 0 (the padding before 5 * DT is part of the
  // bin).
  view = GLanes.minMax(model, 2 * DT, 7 * DT, 1);
  assert.equal(view.min[0], 0, "minimum must include the padding's 0");

  for (const [t0, t1, bins] of [[0, 4 * DT, 1], [2 * DT, 7 * DT, 1], [0, 20 * DT, 6]]) {
    const got = GLanes.minMax(model, t0, t1, bins);
    const want = bruteMinMax(tables, t0, t1, bins);
    assertMinMaxMatches(got, want, 1e-12, `head padding view [${t0}, ${t1}] bins=${bins}`);
  }
});

// ---- 3. laneMeta domain; lanesFor zigzag form --------------------------------------

test("test_lane_meta_domain_ticks_and_the_other_fixed_fields", () => {
  const { seqModel } = buildGModel(60, 29);
  const model = GLanes.decode(seqModel);
  assert.ok(model.wholeFileMax > 0, "expected this model to have a nonzero peak |G|");

  const meta = GLanes.laneMeta(model);
  assert.equal(meta.id, "gmag");
  assert.equal(meta.title, "|G|");
  assert.equal(meta.unit, "mT/m");
  // Not one of gx/gy/gz's own tokens (report.css).
  assert.ok(!["gx", "gy", "gz"].includes(meta.color));
  assert.equal(meta.kind, "line");
  assert.equal(meta.empty, false);
  assert.equal(meta.fill, 0.0);

  const peak = model.wholeFileMax;
  assert.deepEqual(meta.domain, [0, 1.1 * peak]);
  assert.deepEqual(meta.ticks, [0, peak]);
  // 3 significant figures, the same convention as assets/chart_math.js's `fmt`,
  // pns_lanes.js's `_fmtBinMs` and diagram_data.lane_meta's own peak-dependent tick
  // label.
  assert.deepEqual(meta.tick_labels, ["0", Number(peak.toPrecision(3)).toString()]);
});

test("test_lane_meta_domain_is_zero_to_one_with_no_gradient", () => {
  // A file with blocks but no event on any axis: `wholeFileMax` is 0, and the domain
  // is [0, 1], never [-1, 1] (unlike diagram_data.lane_meta's own gx/gy/gz lanes for a
  // 0 peak): |G| can never be negative.
  const { seqModel } = buildGModel(20, 3, { noEventProb: 1.0, forceSpecialBlocks: false });
  const model = GLanes.decode(seqModel);
  assert.equal(model.wholeFileMax, 0);

  const meta = GLanes.laneMeta(model);
  assert.deepEqual(meta.domain, [0, 1]);
  assert.deepEqual(meta.ticks, [0]);
  assert.deepEqual(meta.tick_labels, ["0"]);
  assert.equal(meta.empty, true);
});

// Reads a zigzag lane's segments back into {edgeMs: [minVal, maxVal]}, as
// tests/js/test_pns_lanes.js's `zigzagBins` does.
function zigzagBins(lane) {
  const map = new Map();
  for (const seg of lane.segments) {
    for (let p = 0; p + 1 < seg.length; p += 2) map.set(seg[p][0], [seg[p][1], seg[p + 1][1]]);
  }
  return map;
}

test("test_lanes_for_zigzag_form_matches_min_max_exactly", () => {
  const { seqModel } = buildGModel(120, 41);
  const model = GLanes.decode(seqModel);
  const meta = GLanes.laneMeta(model);
  const bins = 30;
  // `lanesFor` divides `viewMs` by 1000 to get `[t0, t1]` for `minMax`; this call
  // does the same division, in the same order, so `view` and `lane` are built from
  // bit-for-bit the same `t0`/`t1` (not `seqModel.durationS` directly, which
  // `durationS * 1000 / 1000` does not always equal exactly).
  const viewMs = [0, seqModel.durationS * 1000];
  const view = GLanes.minMax(model, viewMs[0] / 1000, viewMs[1] / 1000, bins);
  const lane = GLanes.lanesFor(model, meta, viewMs, bins);
  assert.equal(lane.id, "gmag");
  assert.equal(lane.minmax, true);
  assert.ok(!("id" in lane) || lane.id === meta.id); // meta's own fields are kept

  const gotMap = zigzagBins(lane);
  for (let k = 0; k < bins; k++) {
    const edgeMs = view.edges[k] * 1000;
    if (view.max[k] === -Infinity) {
      assert.ok(!gotMap.has(edgeMs), `bin ${k} should be absent (empty)`);
      continue;
    }
    assert.deepEqual(gotMap.get(edgeMs), [view.min[k], view.max[k]], `bin ${k}`);
  }
});

test("test_lanes_for_empty_bins_end_a_segment", () => {
  // A view that reaches far past the end of the file: bins beyond the last block get
  // no value (`SeqLanes.blockAt` clamps every edge past `durationS` to the last
  // block, so a bin whose own range does not reach that block's tail overlaps
  // nothing), which must end the current segment rather than draw a value there.
  const { seqModel } = buildGModel(40, 5, { noEventProb: 0.5 });
  const model = GLanes.decode(seqModel);
  const meta = GLanes.laneMeta(model);
  const durationS = seqModel.durationS;
  assert.ok(durationS > 0);

  const t0 = 0, t1 = 5 * durationS;
  const bins = 25; // only the first ~1/5 of the bins can ever hold a value
  const view = GLanes.minMax(model, t0, t1, bins);
  let sawEmpty = false;
  for (let k = 0; k < bins; k++) {
    if (view.max[k] === -Infinity) sawEmpty = true;
  }
  assert.ok(sawEmpty, "expected at least one empty bin in this view");

  const lane = GLanes.lanesFor(model, meta, [t0 * 1000, t1 * 1000], bins);
  const gotMap = zigzagBins(lane);
  for (let k = 0; k < bins; k++) {
    const edgeMs = view.edges[k] * 1000;
    if (view.max[k] === -Infinity) {
      assert.ok(!gotMap.has(edgeMs), `bin ${k} should be absent (empty)`);
    } else {
      assert.ok(gotMap.has(edgeMs), `bin ${k} should be present`);
    }
  }
  // At least one segment, and no segment spans the whole `bins` range (the empty
  // bins at the end split it off), so there must be more than one bin represented
  // in the first (only) segment, and at least one bin missing overall.
  assert.ok(lane.segments.length >= 1);
  const presentEdges = new Set(gotMap.keys());
  assert.ok(presentEdges.size < bins, "expected some bins to be empty");
});

// ---- 4. An empty file, and a file without gradients --------------------------------

test("test_empty_file_has_zero_peak_and_no_lane_segments", () => {
  const tables = {
    duration_index: new Uint8Array(0),
    durations: new Float64Array(0),
    checkpoints: new Float64Array([0.0]),
    rf: new Uint8Array(0),
    adc: new Uint8Array(0),
    gx: new Uint8Array(0), gy: new Uint8Array(0), gz: new Uint8Array(0),
    rf_delay: new Float64Array(0),
    rf_mag_n: new Uint32Array(0),
    rf_mag_offset_at: new Uint32Array(0),
    rf_mag_at: new Uint32Array(0),
    rf_mag_offset: new Float64Array(0),
    rf_mag: new Float64Array(0),
    rf_phase_n: new Uint32Array(0),
    rf_phase_offset_at: new Uint32Array(0),
    rf_phase_at: new Uint32Array(0),
    rf_phase_offset: new Float64Array(0),
    rf_phase: new Float64Array(0),
    adc_delay: new Float64Array(0),
    adc_length: new Float64Array(0),
    grad_delay: new Float64Array(0),
    grad_n: new Uint32Array(0),
    grad_offset_at: new Uint32Array(0),
    grad_at: new Uint32Array(0),
    grad_offset: new Float64Array(0),
    grad_value: new Float64Array(0),
  };
  const seqModel = SeqLanes.decode(1, tables, SEQ_LANES_META);
  assert.equal(seqModel.numBlocks, 0);
  const model = GLanes.decode(seqModel);
  assert.equal(model.wholeFileMax, 0);
  assert.equal(model.numBlocks, 0);

  const view = GLanes.minMax(model, 0, 1, 10);
  for (let k = 0; k < 10; k++) {
    assert.equal(view.max[k], -Infinity, `bin ${k}`);
    assert.equal(view.min[k], Infinity, `bin ${k}`);
  }

  const meta = GLanes.laneMeta(model);
  assert.deepEqual(meta.domain, [0, 1]);
  assert.equal(meta.empty, true);

  const lane = GLanes.lanesFor(model, meta, [0, 1000], 10);
  assert.deepEqual(lane.segments, []);
  assert.equal(lane.minmax, true);
});

test("test_file_without_gradients_is_all_zero_not_empty", () => {
  // Blocks exist and tile the whole file, but no block has an event on any axis:
  // every bin's |G| is exactly 0 (a real value, not "no value" -- see the module
  // doc's "a block with no event on an axis reads as the constant 0").
  const { seqModel } = buildGModel(30, 17, { noEventProb: 1.0, forceSpecialBlocks: false });
  const model = GLanes.decode(seqModel);
  assert.equal(model.wholeFileMax, 0);
  assert.ok(seqModel.numBlocks > 0);
  assert.ok(seqModel.durationS > 0);

  const view = GLanes.minMax(model, 0, seqModel.durationS, 12);
  for (let k = 0; k < 12; k++) {
    assert.equal(view.min[k], 0, `bin ${k}`);
    assert.equal(view.max[k], 0, `bin ${k}`);
  }

  const meta = GLanes.laneMeta(model);
  const lane = GLanes.lanesFor(model, meta, [0, seqModel.durationS * 1000], 12);
  assert.equal(lane.segments.length, 1, "expected one unbroken segment of zeros");
  for (const [, v] of lane.segments[0]) assert.equal(v, 0);
});

// ---- 5. More gradient events than one flat numeric key allows (B3) -----------------

// A block table with `numEvents` distinct gradient events (each a 4-point trapezoid
// from the block start, offsets shared across every event: `grad_offset_at` is all
// 0, so every event reuses the same 4-entry `grad_offset` and differs only in
// `grad_value`) and `nBlocks` blocks, most of which reference event indexes within 50
// of `numEvents` on each axis (`docs/plans/review-bugs.md` section 9.3's repro,
// restated here as a reusable builder), so `M = numEvents + 1` is exercised at its
// own top end, not only near 0. 5 distinct block durations (`D = 5`). Event columns
// are `Uint32Array` (as real `diagram_tables` output uses once a file has this many
// distinct events), unlike `buildGModel`'s `Uint8Array`. Seeded, so a call with the
// same arguments always builds the same tables.
function buildManyEventsTables(numEvents, nBlocks) {
  const grad_at = new Uint32Array(numEvents);
  const grad_value = new Float64Array(4 * numEvents);
  for (let e = 0; e < numEvents; e++) {
    grad_at[e] = 4 * e;
    const a = ((e * 7919) % 2001 - 1000) / 40; // -25 to 25 mT/m
    grad_value.set([0, a, a, 0], 4 * e);
  }
  let s = 12345;
  const rnd = () => (s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
  const duration_index = new Uint8Array(nBlocks);
  const durations = Float64Array.from([2e-4, 3.5e-4, 6e-4, 9e-4, 1.2e-3]);
  const gx = new Uint32Array(nBlocks), gy = new Uint32Array(nBlocks), gz = new Uint32Array(nBlocks);
  for (let i = 0; i < nBlocks; i++) {
    duration_index[i] = Math.floor(rnd() * 5);
    gx[i] = rnd() < 0.3 ? 0 : numEvents - Math.floor(rnd() * 50);
    gy[i] = rnd() < 0.3 ? 0 : numEvents - Math.floor(rnd() * 50);
    gz[i] = rnd() < 0.3 ? 0 : numEvents - Math.floor(rnd() * 50);
  }
  const nCp = Math.ceil(nBlocks / 1024) || 1;
  const checkpoints = new Float64Array(nCp);
  let t = 0;
  for (let i = 0; i < nBlocks; i++) {
    if (i % 1024 === 0) checkpoints[i / 1024] = t;
    t += durations[duration_index[i]];
  }
  const tables = {
    duration_index, durations, checkpoints,
    rf: new Uint8Array(nBlocks),
    adc: new Uint8Array(nBlocks),
    gx, gy, gz,
    rf_delay: new Float64Array(0),
    rf_mag_n: new Uint32Array(0),
    rf_mag_offset_at: new Uint32Array(0),
    rf_mag_at: new Uint32Array(0),
    rf_mag_offset: new Float64Array(0),
    rf_mag: new Float64Array(0),
    rf_phase_n: new Uint32Array(0),
    rf_phase_offset_at: new Uint32Array(0),
    rf_phase_at: new Uint32Array(0),
    rf_phase_offset: new Float64Array(0),
    rf_phase: new Float64Array(0),
    adc_delay: new Float64Array(0),
    adc_length: new Float64Array(0),
    grad_delay: new Float64Array(numEvents),
    grad_n: new Uint32Array(numEvents).fill(4),
    grad_offset_at: new Uint32Array(numEvents),
    grad_at,
    grad_offset: Float64Array.from([0, 5e-5, 1.5e-4, 2e-4]),
    grad_value,
  };
  const seqModel = SeqLanes.decode(1, tables, SEQ_LANES_META);
  return { tables, seqModel };
}

// Before the fix, `GLanes.decode`'s single flat cache key
// `((kx * M + ky) * M + kz) * D + durIdx` stops being an exact integer below 2^53 at
// about 1.2 * 10^5 gradient events (`M = numGradEvents + 1`); with the two-level key
// (the comment of `_tripleKeyOf` in g_lanes.js), the limit is about 9.5 * 10^7 events. 150,000 events
// is past the old limit and far below the new one.
test("test_decode_accepts_more_gradient_events_than_one_numeric_key_allows", () => {
  const numEvents = 150000, nBlocks = 300;
  const { tables, seqModel } = buildManyEventsTables(numEvents, nBlocks);
  const model = GLanes.decode(seqModel); // must not throw
  const { starts, durationS } = blockStarts(tables);

  const views = [
    [0, durationS, 37],
    [0, durationS, 211],
    [starts[10], starts[280], 17],
  ];
  for (const [t0, t1, bins] of views) {
    const got = GLanes.minMax(model, t0, t1, bins);
    const want = bruteMinMax(tables, t0, t1, bins);
    assertMinMaxMatches(got, want, 1e-12, `[${t0}, ${t1}] bins=${bins}`);
  }
});
