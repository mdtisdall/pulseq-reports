// Task 6 of docs/plans/pns-lanes-prototype.md: correctness and timing for
// slew_g.js's `slewMinMax` and `gMagMinMax`. Prototype only, never merged
// (docs/plans/pns-lanes-prototype.md, section 4).
//
// Two subcommands, each merging its own section into one results file:
//
//   node run_slew_g.js correctness TABLES_DIR OUT.json
//     Reads TABLES_DIR/<name>.json (export_grad_tables.py's output) for
//     each of spin_echo, gre, arbitrary, rep_2000trs, worst_2000trs, exvivo.
//     For several views of each (whole file at 812 and 37 bins, a zoomed
//     range that cuts blocks, a range inside one block), compares
//     slew_g.js's `slewMinMax` (each axis) and `gMagMinMax` against a brute
//     force computed independently in this file, straight from the raw
//     tables (never by calling slew_g.js's own internals): every block's
//     polyline segments, expanded, for slew; the same piecewise-quadratic
//     rule as slew_g.js, but applied to every block in a bin instead of
//     only the two a bin's edges cut (so the group tree is never used) for
//     |G|. Writes {"correctness": [...]} into OUT.json.
//
//   node run_slew_g.js timing NAME TABLES_JSON OUT.json
//     Times one exported table file (a large repeating sequence): decode,
//     precompute (the first call to each axis's slew tree and to the |G|
//     triple tree), one whole-file render at 812 bins, and 100 random
//     zoomed views at 812 bins, median and 95th percentile per function.
//     Meant to be run in its own `node` process for each size (a fresh
//     process keeps the peak-RSS reading meaningful), so results are
//     merged under `timing[NAME]` into OUT.json rather than overwritten.
//
// Slew comparisons use exact equality: both `slewMinMax` and the brute
// force compute a segment's slew with the same formula, in the same
// operation order ((v2 - v1) / (t2 - t1)), so there is no floating-point
// reordering between them, and the plan's optional 1e-12 relative
// tolerance is not needed. |G| comparisons use 1e-12 relative tolerance:
// the fast path and the brute force both use the piecewise-quadratic
// closed form (never dense sampling, which the plan says is not exact),
// but a clipped sub-piece computes its own ta/tb from a division that a
// whole, unclipped piece does not, so the two can differ in the last bit.
"use strict";

const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

const SEQ_LANES_PATH =
  "/Users/dylan/dev/pulseq-reports/.worktrees/pns-lanes-prototype/src/pulseq_reports/assets/seq_lanes.js";
const SeqLanes = require(SEQ_LANES_PATH);
const SlewG = require(path.join(__dirname, "slew_g.js"));

const AXES = ["gx", "gy", "gz"];
const MT_PER_T = 1000;

// ---- Loading exported tables (export_grad_tables.py's JSON), independent
// of tests/js/golden_seq_lanes.js (not imported: this prototype does not
// depend on tests/) but the same decoding rule as that script. ----

const TYPED_ARRAY_CTORS = {
  uint8: Uint8Array,
  uint16: Uint16Array,
  uint32: Uint32Array,
  float64: Float64Array,
};

function decodeTable(name, meta) {
  const Ctor = TYPED_ARRAY_CTORS[meta.dtype];
  if (!Ctor) throw new Error(`run_slew_g: table "${name}" has an unknown dtype "${meta.dtype}"`);
  const compressed = Buffer.from(meta.data, "base64");
  const raw = zlib.gunzipSync(compressed);
  const aligned = new ArrayBuffer(raw.length);
  new Uint8Array(aligned).set(raw);
  const arr = new Ctor(aligned);
  if (arr.length !== meta.length) {
    throw new Error(
      `run_slew_g: table "${name}" decoded to length ${arr.length}, declared ${meta.length}`
    );
  }
  return arr;
}

function loadModel(tablesJsonPath) {
  const input = JSON.parse(fs.readFileSync(tablesJsonPath, "utf8"));
  const tables = {};
  for (const [name, meta] of Object.entries(input.tables)) tables[name] = decodeTable(name, meta);
  return SeqLanes.decode(input.format, tables, input.lanes);
}

// ---- Brute force, independent of slew_g.js's own code -------------------

// Every block's slew segments on `axis`, expanded straight from the raw
// tables (not `_eventGeometry`/`_eventSlewStats` of slew_g.js): a block
// with no event is one segment (the whole block, slew 0); a block with an
// event has one segment for each pair of consecutive breakpoints, slew
// `(v2 - v1) / (t2 - t1)`, T/m/s. Returns parallel arrays `segStart`,
// `segEnd` (s, absolute) and `segSlew` (T/m/s), in play order (so already
// sorted by start time).
function bruteSlewSegments(model, axis) {
  const tb = model.tables;
  const axisCol = tb[axis];
  const N = model.numBlocks;
  const segStart = [];
  const segEnd = [];
  const segSlew = [];
  let start = 0;
  for (let i = 0; i < N; i++) {
    const dur = tb.durations[tb.duration_index[i]];
    const bStart = start;
    start += dur;
    const k = axisCol[i];
    if (k === 0) {
      segStart.push(bStart);
      segEnd.push(bStart + dur);
      segSlew.push(0);
      continue;
    }
    const idx = k - 1;
    const n = tb.grad_n[idx];
    const offAt = tb.grad_offset_at[idx];
    const valAt = tb.grad_at[idx];
    const delay = tb.grad_delay[idx];
    if (n < 2) {
      segStart.push(bStart);
      segEnd.push(bStart + dur);
      segSlew.push(0);
      continue;
    }
    for (let p = 1; p < n; p++) {
      const t1 = delay + tb.grad_offset[offAt + p - 1];
      const t2 = delay + tb.grad_offset[offAt + p];
      const v1 = tb.grad_value[valAt + p - 1] / MT_PER_T;
      const v2 = tb.grad_value[valAt + p] / MT_PER_T;
      const dt = t2 - t1;
      segStart.push(bStart + t1);
      segEnd.push(bStart + t2);
      segSlew.push(dt > 0 ? (v2 - v1) / dt : 0);
    }
  }
  return {segStart, segEnd, segSlew};
}

// The exact min/max slew of `axis` in each of `bins` equal bins of
// `[t0, t1]`, by clipping every segment of `bruteSlewSegments` against
// every bin it can reach (narrowed by the segment's own absolute time
// range, not by walking every bin for every segment, so this stays well
// under O(segments * bins) even for the largest sequence measured here,
// exvivo at about 118,000 segments).
function bruteSlewMinMax(model, axis, t0, t1, bins) {
  const edges = new Float64Array(bins + 1);
  const span = t1 - t0;
  for (let k = 0; k <= bins; k++) edges[k] = t0 + span * k / bins;
  const outMin = new Float64Array(bins).fill(Infinity);
  const outMax = new Float64Array(bins).fill(-Infinity);
  const {segStart, segEnd, segSlew} = bruteSlewSegments(model, axis);
  const binWidth = span / bins;
  for (let s = 0; s < segStart.length; s++) {
    const a = segStart[s], b = segEnd[s];
    if (b <= t0 || a >= t1) continue;
    const v = segSlew[s];
    let kLo = binWidth > 0 ? Math.floor((a - t0) / binWidth) - 1 : 0;
    let kHi = binWidth > 0 ? Math.floor((b - t0) / binWidth) + 1 : bins - 1;
    kLo = Math.max(0, kLo);
    kHi = Math.min(bins - 1, kHi);
    for (let k = kLo; k <= kHi; k++) {
      const lo = Math.max(a, edges[k]), hi = Math.min(b, edges[k + 1]);
      if (hi > lo) {
        if (v < outMin[k]) outMin[k] = v;
        if (v > outMax[k]) outMax[k] = v;
      }
    }
  }
  for (let k = 0; k < bins; k++) {
    if (outMin[k] === Infinity) outMin[k] = 0;
    if (outMax[k] === -Infinity) outMax[k] = 0;
  }
  return {edges, min: outMin, max: outMax};
}

// The axis value (T/m) at relative time `t` (s, from the block start),
// from a raw (times, values) pair (Float64Array, already delay-shifted, T/m):
// 0 with no event; flat at the first/last value outside the event's own
// span; linear between its breakpoints otherwise. A fresh, independent
// implementation of the same rule as slew_g.js's `_axisValueAt` (not a
// call into it): the piece-quadratic brute force below needs it to build
// each block's own breakpoint values, exactly as the fast path does, but
// without sharing code with it.
function bruteAxisValueAt(times, values, t) {
  if (times === null) return 0;
  const n = times.length;
  if (n === 0) return 0;
  if (t <= times[0]) return values[0];
  if (t >= times[n - 1]) return values[n - 1];
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
  if (k === 0) return {times: null, values: null};
  const idx = k - 1;
  const n = tb.grad_n[idx];
  const offAt = tb.grad_offset_at[idx];
  const valAt = tb.grad_at[idx];
  const delay = tb.grad_delay[idx];
  const times = new Float64Array(n);
  const values = new Float64Array(n);
  for (let p = 0; p < n; p++) {
    times[p] = delay + tb.grad_offset[offAt + p];
    values[p] = tb.grad_value[valAt + p] / MT_PER_T;
  }
  return {times, values};
}

// The extrema of the convex quadratic A*tau^2 + B*tau + C over
// tau in [ta, tb], the same closed form as slew_g.js's
// `_quadRangeExtrema` (a short, simple formula; written again here, not
// called from slew_g.js, to keep this brute force independent).
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

// The exact min/max |G| of one block, restricted to `[loAbs, hiAbs)`
// clipped to the block's own extent, by the union-of-breakpoints
// piecewise-quadratic rule (plan section 3.6, item 2), applied here to a
// single block on demand (never a per-triple cache, never a tree): the
// point of the brute force is to compute every block this way, so the fast
// path's grouping is the only thing being checked, not this formula.
// Returns null when there is no positive-length overlap.
function bruteBlockGRange(tb, i, bStart, dur, loAbs, hiAbs) {
  const overlapLo = Math.max(bStart, loAbs);
  const overlapHi = Math.min(bStart + dur, hiAbs);
  if (overlapHi <= overlapLo) return null;

  const kx = tb.gx[i], ky = tb.gy[i], kz = tb.gz[i];
  const ex = bruteEventTimesValues(tb, kx);
  const ey = bruteEventTimesValues(tb, ky);
  const ez = bruteEventTimesValues(tb, kz);
  const merged = new Set([0]);
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
    for (const [v0, v1] of [[vx0, vx1], [vy0, vy1], [vz0, vz1]]) {
      const d = v1 - v0;
      A += d * d;
      B += 2 * v0 * d;
      C += v0 * v0;
    }
    const ta = (clipLo - t0v) / (t1v - t0v), tbb = (clipHi - t0v) / (t1v - t0v);
    const [g2lo, g2hi] = bruteQuadExtrema(A, B, C, ta, tbb);
    const a = Math.sqrt(Math.max(0, g2lo)), b = Math.sqrt(Math.max(0, g2hi));
    if (a < lo) lo = a;
    if (b > hi) hi = b;
  }
  if (times.length < 2) return [0, 0];
  return hi === -Infinity ? null : [lo, hi];
}

// The exact min/max |G| in each of `bins` equal bins of `[t0, t1]`, from
// `bruteBlockGRange` applied to every block that overlaps the view (never
// slew_g.js's group tree or its per-triple cache).
function bruteGMagMinMax(model, t0, t1, bins) {
  const tb = model.tables;
  const N = model.numBlocks;
  const edges = new Float64Array(bins + 1);
  const span = t1 - t0;
  for (let k = 0; k <= bins; k++) edges[k] = t0 + span * k / bins;
  const outMin = new Float64Array(bins).fill(Infinity);
  const outMax = new Float64Array(bins).fill(-Infinity);

  let start = 0;
  for (let i = 0; i < N; i++) {
    const dur = tb.durations[tb.duration_index[i]];
    const bStart = start;
    start += dur;
    if (bStart + dur <= t0 || bStart >= t1) continue;
    for (let k = 0; k < bins; k++) {
      const range = bruteBlockGRange(tb, i, bStart, dur, edges[k], edges[k + 1]);
      if (range === null) continue;
      if (range[0] < outMin[k]) outMin[k] = range[0];
      if (range[1] > outMax[k]) outMax[k] = range[1];
    }
  }
  for (let k = 0; k < bins; k++) {
    if (outMin[k] === Infinity) outMin[k] = 0;
    if (outMax[k] === -Infinity) outMax[k] = 0;
  }
  return {edges, min: outMin, max: outMax};
}

// ---- Views (whole file at 812 and 37 bins; a zoomed range that cuts
// blocks; a range inside one block) -----------------------------------------

function _blockDuration(model, i) {
  return model.tables.durations[model.tables.duration_index[i]];
}

function _firstNonZeroDurationBlock(model) {
  const N = model.numBlocks;
  for (let i = 0; i < N; i++) if (_blockDuration(model, i) > 0) return i;
  return -1;
}

function viewsFor(model) {
  const N = model.numBlocks;
  const durationS = model.durationS;
  const views = [
    {name: "whole_812", t0: 0, t1: durationS, bins: 812},
    {name: "whole_37", t0: 0, t1: durationS, bins: 37},
  ];
  if (N >= 2) {
    const iA = Math.floor(N / 4);
    const iB = Math.min(N - 1, Math.max(iA + 1, Math.floor((3 * N) / 4)));
    if (iB > iA) {
      const sA = SeqLanes.blockStart(model, iA), dA = _blockDuration(model, iA);
      const sB = SeqLanes.blockStart(model, iB), dB = _blockDuration(model, iB);
      const t0z = sA + dA * 0.3;
      const t1z = sB + dB * 0.7;
      if (t1z > t0z) {
        views.push({name: "zoomed_cut", t0: t0z, t1: t1z, bins: Math.min(37, Math.max(4, iB - iA))});
      }
    }
  }
  let iMid = Math.floor(N / 2);
  if (_blockDuration(model, iMid) <= 0) iMid = _firstNonZeroDurationBlock(model);
  if (iMid >= 0) {
    const sMid = SeqLanes.blockStart(model, iMid), dMid = _blockDuration(model, iMid);
    if (dMid > 0) {
      views.push({name: "inside_block", t0: sMid + dMid * 0.2, t1: sMid + dMid * 0.8, bins: 8});
    }
  }
  return views;
}

// ---- Comparison -----------------------------------------------------------

function compareArrays(fastArr, bruteArr, tol, exact) {
  let maxAbsDiff = 0, maxRelDiff = 0, worst = null;
  for (let i = 0; i < fastArr.length; i++) {
    const a = fastArr[i], b = bruteArr[i];
    const diff = Math.abs(a - b);
    const scale = Math.max(Math.abs(a), Math.abs(b), 1e-300);
    const rel = diff / scale;
    if (diff > maxAbsDiff) maxAbsDiff = diff;
    if (rel > maxRelDiff) { maxRelDiff = rel; worst = {i, fast: a, brute: b}; }
  }
  const ok = exact ? maxAbsDiff === 0 : maxRelDiff <= tol;
  return {ok, maxAbsDiff, maxRelDiff, worst};
}

function runCorrectness(tablesDir, names) {
  const results = [];
  for (const name of names) {
    const p = path.join(tablesDir, `${name}.json`);
    if (!fs.existsSync(p)) {
      results.push({name, error: `missing exported tables at ${p}`});
      continue;
    }
    const model = loadModel(p);
    const views = viewsFor(model);
    for (const view of views) {
      for (const axis of AXES) {
        const fast = SlewG.slewMinMax(model, axis, view.t0, view.t1, view.bins);
        const brute = bruteSlewMinMax(model, axis, view.t0, view.t1, view.bins);
        const cmpMin = compareArrays(fast.min, brute.min, 0, true);
        const cmpMax = compareArrays(fast.max, brute.max, 0, true);
        results.push({
          name, view: view.name, bins: view.bins, kind: "slew", axis,
          tolerance: "exact",
          minOk: cmpMin.ok, maxOk: cmpMax.ok,
          minMaxAbsDiff: cmpMin.maxAbsDiff, maxMaxAbsDiff: cmpMax.maxAbsDiff,
          minWorst: cmpMin.worst, maxWorst: cmpMax.worst,
        });
      }
      const fastG = SlewG.gMagMinMax(model, view.t0, view.t1, view.bins);
      const bruteG = bruteGMagMinMax(model, view.t0, view.t1, view.bins);
      const cmpMinG = compareArrays(fastG.min, bruteG.min, 1e-12, false);
      const cmpMaxG = compareArrays(fastG.max, bruteG.max, 1e-12, false);
      results.push({
        name, view: view.name, bins: view.bins, kind: "gmag",
        tolerance: "1e-12 relative",
        minOk: cmpMinG.ok, maxOk: cmpMaxG.ok,
        minMaxRelDiff: cmpMinG.maxRelDiff, maxMaxRelDiff: cmpMaxG.maxRelDiff,
        minWorst: cmpMinG.worst, maxWorst: cmpMaxG.worst,
      });
    }
  }
  return results;
}

// ---- Timing -----------------------------------------------------------

// A small seeded PRNG (mulberry32), so the 100 random views are the same
// from one run to the next.
function mulberry32(seed) {
  let t = seed >>> 0;
  return function () {
    t |= 0;
    t = (t + 0x6d2b79f5) | 0;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r = (r + Math.imul(r ^ (r >>> 7), 61 | r)) ^ r;
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

function stats(arrMs) {
  const sorted = [...arrMs].sort((a, b) => a - b);
  const n = sorted.length;
  const median = sorted[Math.floor(0.5 * (n - 1))];
  const p95 = sorted[Math.floor(0.95 * (n - 1))];
  return {median_ms: median, p95_ms: p95, min_ms: sorted[0], max_ms: sorted[n - 1], n};
}

function nowMs() {
  return Number(process.hrtime.bigint()) / 1e6;
}

function runTiming(name, tablesJsonPath) {
  const t0 = nowMs();
  const raw = JSON.parse(fs.readFileSync(tablesJsonPath, "utf8"));
  const tables = {};
  for (const [n, meta] of Object.entries(raw.tables)) tables[n] = decodeTable(n, meta);
  const decodeTablesMs = nowMs() - t0;

  const t1 = nowMs();
  const model = SeqLanes.decode(raw.format, tables, raw.lanes);
  const seqLanesDecodeMs = nowMs() - t1;

  const durationS = model.durationS;

  // Force the first-call precompute (event caches, per-axis slew group
  // trees, the |G| triple cache and its group tree) once, timed separately
  // from every later render.
  const t2 = nowMs();
  for (const axis of AXES) SlewG.slewMinMax(model, axis, 0, durationS, 2);
  SlewG.gMagMinMax(model, 0, durationS, 2);
  const precomputeMs = nowMs() - t2;

  const peakRssKb = process.resourceUsage().maxRSS;

  const wholeFileMs = {};
  for (const axis of AXES) {
    const a = nowMs();
    SlewG.slewMinMax(model, axis, 0, durationS, 812);
    wholeFileMs[`slew_${axis}`] = nowMs() - a;
  }
  {
    const a = nowMs();
    SlewG.gMagMinMax(model, 0, durationS, 812);
    wholeFileMs.gmag = nowMs() - a;
  }

  const rng = mulberry32(20260924);
  const views = [];
  for (let i = 0; i < 100; i++) {
    const widthFrac = Math.pow(10, -4 + rng() * 4); // 1e-4 .. 1 of the file
    const width = Math.max(durationS * widthFrac, 1e-6);
    const vt0 = rng() * Math.max(0, durationS - width);
    views.push([vt0, vt0 + width]);
  }
  const samples = {slew_gx: [], slew_gy: [], slew_gz: [], gmag: []};
  for (const [vt0, vt1] of views) {
    for (const axis of AXES) {
      const a = nowMs();
      SlewG.slewMinMax(model, axis, vt0, vt1, 812);
      samples[`slew_${axis}`].push(nowMs() - a);
    }
    const a = nowMs();
    SlewG.gMagMinMax(model, vt0, vt1, 812);
    samples.gmag.push(nowMs() - a);
  }

  const peakRssKbAfter = process.resourceUsage().maxRSS;

  return {
    name,
    numBlocks: model.numBlocks,
    durationS,
    decode_tables_ms: decodeTablesMs,
    seq_lanes_decode_ms: seqLanesDecodeMs,
    precompute_ms: precomputeMs,
    peak_rss_kb_after_precompute: peakRssKb,
    peak_rss_kb_after_all: peakRssKbAfter,
    whole_file_812_bins_ms: wholeFileMs,
    zoomed_100_views_812_bins: {
      slew_gx: stats(samples.slew_gx),
      slew_gy: stats(samples.slew_gy),
      slew_gz: stats(samples.slew_gz),
      gmag: stats(samples.gmag),
    },
  };
}

// ---- CLI --------------------------------------------------------------

function loadResults(outPath) {
  if (fs.existsSync(outPath)) return JSON.parse(fs.readFileSync(outPath, "utf8"));
  return {};
}

function saveResults(outPath, data) {
  fs.mkdirSync(path.dirname(outPath), {recursive: true});
  fs.writeFileSync(outPath, JSON.stringify(data, null, 2));
}

function main() {
  const [, , mode, ...rest] = process.argv;
  if (mode === "correctness") {
    const [tablesDir, outPath] = rest;
    if (!tablesDir || !outPath) {
      console.error("usage: node run_slew_g.js correctness TABLES_DIR OUT.json");
      process.exit(2);
    }
    const names = ["spin_echo", "gre", "arbitrary", "rep_2000trs", "worst_2000trs", "exvivo"];
    const results = runCorrectness(tablesDir, names);
    const out = loadResults(outPath);
    out.correctness = results;
    saveResults(outPath, out);
    const failed = results.filter((r) => r.error || r.minOk === false || r.maxOk === false);
    console.log(`correctness: ${results.length} checks, ${failed.length} failed`);
    if (failed.length) console.log(JSON.stringify(failed, null, 2));
    process.exitCode = failed.length ? 1 : 0;
  } else if (mode === "timing") {
    const [name, tablesJsonPath, outPath] = rest;
    if (!name || !tablesJsonPath || !outPath) {
      console.error("usage: node run_slew_g.js timing NAME TABLES_JSON OUT.json");
      process.exit(2);
    }
    const result = runTiming(name, tablesJsonPath);
    const out = loadResults(outPath);
    out.timing = out.timing || {};
    out.timing[name] = result;
    saveResults(outPath, out);
    console.log(JSON.stringify(result, null, 2));
  } else {
    console.error("usage: node run_slew_g.js correctness TABLES_DIR OUT.json");
    console.error("       node run_slew_g.js timing NAME TABLES_JSON OUT.json");
    process.exit(2);
  }
}

main();
