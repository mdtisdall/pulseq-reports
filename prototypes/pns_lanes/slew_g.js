// Task 6 of docs/plans/pns-lanes-prototype.md (section 3.6): does the
// sequence diagram's compact block and event tables give the exact minimum
// and maximum, in each time bin, of the gradient slew rate dG/dt (per axis,
// T/m/s) and of |G| = sqrt(gx^2 + gy^2 + gz^2) (T/m), fast enough at 10^7
// blocks? Prototype only (docs/plans/pns-lanes-prototype.md, section 4);
// never merged.
//
// A pure module, no DOM, in the style of
// src/pulseq_reports/assets/seq_lanes.js: it `require`s that file by an
// absolute path and reuses `decode`, `blockStart` and `blockAt` rather than
// copying them. `SlewG.slewMinMax` and `SlewG.gMagMinMax` take the same
// `model` that `SeqLanes.decode` returns (built from the diagram's `gx`,
// `gy`, `gz` dense gradient index columns and the `grad_*` event tables,
// section 4.2 of docs/plans/diagram-event-table.md). `grad_value` is in
// mT/m; this module works in T/m throughout, so every event value is
// divided by 1000 once, where it is first read.
//
// Both functions build (and cache, on the model) an event-level cache and a
// tree over groups of GROUP_BLOCKS blocks, the same grouping seq_lanes.js
// uses, so that a whole-file render touches only the O(bins) groups a bin's
// edges cut, never all N blocks:
//
// - Slew: each unique gradient event's own segments give its min/max slew,
//   computed once (`_eventSlewStats`). A block with no event on an axis is
//   the constant 0 (the plan: "the gradient is 0 there"), so its range is
//   [0, 0], not "no value" -- every bin's range includes 0 wherever the
//   axis has any gap in it. Whole blocks inside a bin come from the group
//   tree; only the (at most two) blocks a bin's edges cut are walked
//   segment by segment, clipped to the bin.
// - |G|: each distinct triple of (gx, gy, gz) event ids gives one set of
//   piecewise-linear pieces (the union of the three events' own
//   breakpoints); on each piece, all three axes are linear in t, so |G|^2
//   is a quadratic, and its exact min/max on any sub-range (a whole piece,
//   for a block's own extrema, or a clipped piece, for a bin edge) is one
//   closed-form evaluation (`_quadRangeExtrema`). The quadratic is a sum of
//   three squares of affine functions, so it is convex: never negative, and
//   its vertex (if inside the range) is always the minimum, never the
//   maximum, which is always at a range end.
"use strict";

const SeqLanes = require(
  "/Users/dylan/dev/pulseq-reports/.worktrees/pns-lanes-prototype/src/pulseq_reports/assets/seq_lanes.js"
);

// 64 blocks in each group, the same grouping as seq_lanes.js's GROUP_BLOCKS:
// a render at 10^7 blocks and 812 bins must not walk more than a couple of
// groups per bin, so the group size has to match the bin count's order of
// magic (10^7 / 812 ~ 12,300 blocks per bin, so about 192 groups per bin --
// still far fewer than the blocks in the bin).
const GROUP_BLOCKS = 64;

const AXES = ["gx", "gy", "gz"];
const MT_PER_T = 1000; // grad_value is stored in mT/m; this module uses T/m.

// ---- Small shared helpers --------------------------------------------------

// First index `p` in `arr[0, n)` with `arr[p] >= x` (n = arr.length when
// omitted). Used on the strictly ascending breakpoint times of one event, as
// in seq_lanes.js's `_lowerBound`/`_upperBound`.
function _lowerBound(arr, x, n) {
  let lo = 0, hi = n === undefined ? arr.length : n;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (arr[mid] < x) lo = mid + 1; else hi = mid;
  }
  return lo;
}

// First index `p` in `arr[0, n)` with `arr[p] > x`.
function _upperBound(arr, x, n) {
  let lo = 0, hi = n === undefined ? arr.length : n;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (arr[mid] <= x) lo = mid + 1; else hi = mid;
  }
  return lo;
}

// An iterative segment tree over group minima or maxima, identical in shape
// to seq_lanes.js's `_segTree` (not imported: that function is private to
// seq_lanes.js, so this is a small, deliberate duplicate of the same
// well-understood layout, not a divergent copy of its logic).
function _segTree(values, n, isMin) {
  const id = isMin ? Infinity : -Infinity;
  const tree = new Float64Array(2 * n).fill(id);
  for (let j = 0; j < n; j++) tree[n + j] = values[j];
  for (let j = n - 1; j >= 1; j--) {
    const a = tree[2 * j], b = tree[2 * j + 1];
    tree[j] = isMin ? (a < b ? a : b) : (a > b ? a : b);
  }
  return {
    tree, n, isMin,
    query(lo, hi) {
      let acc = id;
      if (isMin) {
        for (let l = lo + n, r = hi + n; l < r; l >>= 1, r >>= 1) {
          if (l & 1) { const v = tree[l++]; if (v < acc) acc = v; }
          if (r & 1) { const v = tree[--r]; if (v < acc) acc = v; }
        }
      } else {
        for (let l = lo + n, r = hi + n; l < r; l >>= 1, r >>= 1) {
          if (l & 1) { const v = tree[l++]; if (v > acc) acc = v; }
          if (r & 1) { const v = tree[--r]; if (v > acc) acc = v; }
        }
      }
      return acc;
    },
  };
}

// The bin edges e_k = t0 + (t1 - t0) * k / bins (k = 0 ... bins), and the
// block that holds each edge (via SeqLanes.blockAt/blockStart), exactly as
// seq_lanes.js's minMaxLanes finds them, so both modules cut the file into
// the same bins.
function _binEdges(model, t0, t1, bins) {
  const N = model.numBlocks;
  const span = t1 - t0;
  const edges = new Float64Array(bins + 1);
  const edgeBlock = new Int32Array(bins + 1);
  const edgeStart = new Float64Array(bins + 1);
  for (let k = 0; k <= bins; k++) {
    edges[k] = t0 + span * k / bins;
    if (N === 0) continue;
    const b = SeqLanes.blockAt(model, edges[k]);
    edgeBlock[k] = b;
    edgeStart[k] = SeqLanes.blockStart(model, b);
  }
  return {edges, edgeBlock, edgeStart};
}

// ---- Event geometry (shared by slew and |G|) -------------------------------

// The breakpoint times (s, relative to the block start) and values (T/m) of
// one dense gradient event id `k` (1-based; the caller never passes 0). The
// event's own delay is folded into the times, as everywhere else in this
// project (`start + delay + offset`, section 4.3 of
// docs/plans/diagram-event-table.md): `times[0] = delay`, not 0, when the
// event has a delay. Every test sequence measured here has `delay === 0`
// and starts/ends its events at value 0 (README.md, task 1's assumption
// check), so the times below span exactly the block's own duration in
// practice; a nonzero delay is still handled correctly by `_axisValueAt`
// (flat at the first/last value outside the event's own span), which is the
// only place that reads a raw time outside `[times[0], times[n-1]]`.
function _eventGeometry(tb, k, cache) {
  let g = cache.get(k);
  if (g !== undefined) return g;
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
  g = {times, values};
  cache.set(k, g);
  return g;
}

// The value (T/m) of axis event `k` (0 = no event on this axis) at time `t`
// (s, relative to the block start): 0 when `k === 0`; else linear
// interpolation between the event's own breakpoints, flat at the first or
// last value outside its own span (the flat extension the plan's "the
// gradient is 0 there" applies to a whole missing-event block; here it
// applies to a fringe of one present event's own block, which is 0 in every
// sequence measured, README.md task 1).
function _axisValueAt(tb, k, cache, t) {
  if (k === 0) return 0;
  const {times, values} = _eventGeometry(tb, k, cache);
  const n = times.length;
  if (n === 0) return 0;
  if (t <= times[0]) return values[0];
  if (t >= times[n - 1]) return values[n - 1];
  const p = _lowerBound(times, t, n);
  if (times[p] === t) return values[p];
  const t1 = times[p - 1], t2 = times[p];
  const v1 = values[p - 1], v2 = values[p];
  return v1 + (v2 - v1) / (t2 - t1) * (t - t1);
}

// ---- Slew (plan section 3.6, item 1) ---------------------------------------

// The min and the max slew (T/m/s) of each segment of event `k`'s own
// polyline, computed once and cached: `slew[p] = (values[p] - values[p-1])
// / (times[p] - times[p-1])` for p = 1 ... n-1. A segment of zero duration
// (two breakpoints at the same time, for example a trapezoid with no flat
// top) gets slew 0 by convention; it can never be selected by a bin's
// positive-length-overlap test (`_clipSlewSegments`) regardless, because its
// own overlap with any bin is always zero length.
function _eventSlewStats(tb, k, cache) {
  let s = cache.get(k);
  if (s !== undefined) return s;
  const {times, values} = _eventGeometry(tb, k, cache);
  const n = times.length;
  const slew = new Float64Array(Math.max(0, n - 1));
  let min = Infinity, max = -Infinity;
  for (let p = 1; p < n; p++) {
    const dt = times[p] - times[p - 1];
    const v = dt > 0 ? (values[p] - values[p - 1]) / dt : 0;
    slew[p - 1] = v;
    if (v < min) min = v;
    if (v > max) max = v;
  }
  if (n < 2) { min = 0; max = 0; }
  s = {times, slew, min, max};
  cache.set(k, s);
  return s;
}

// The min/max slew range of block `i` on one axis: [0, 0] when the block has
// no event on the axis (the plan's "the gradient is 0 there"), else the
// event's own min/max (`_eventSlewStats`), also [0, 0] for a one-point event
// (no segment). Never null: a block always has a slew range, because "no
// event" is itself a value (0), not an absence of one -- unlike a value
// lane's own min/max in seq_lanes.js, which a block with no event
// contributes nothing to.
function _blockSlewRange(tb, i, axisCol, evCache) {
  const k = axisCol[i];
  if (k === 0) return [0, 0];
  const s = _eventSlewStats(tb, k, evCache.slew);
  return [s.min, s.max];
}

// The exact min/max slew of block `i`'s segments that overlap
// `[loAbs, hiAbs)` with positive length (s, absolute time), clipped to the
// block's own extent. Returns null when there is no positive-length
// overlap. Binary search narrows the segment range to the ones that can
// possibly overlap, so the cost is the number of overlapping segments, not
// the event's whole length (`_lowerBound`/`_upperBound` on the event's own
// ascending breakpoint times).
function _exactBlockSlewRange(model, tb, i, axisCol, evCache, loAbs, hiAbs) {
  const bStart = SeqLanes.blockStart(model, i);
  const bDur = tb.durations[tb.duration_index[i]];
  const overlapLo = Math.max(bStart, loAbs);
  const overlapHi = Math.min(bStart + bDur, hiAbs);
  if (overlapHi <= overlapLo) return null;

  const k = axisCol[i];
  if (k === 0) return [0, 0];
  const s = _eventSlewStats(tb, k, evCache.slew);
  const n = s.times.length;
  if (n < 2) return [0, 0];
  const relLo = overlapLo - bStart, relHi = overlapHi - bStart;
  // Segment p (times[p-1] .. times[p], value slew[p-1]) overlaps
  // (relLo, relHi) with positive length iff times[p-1] < relHi and
  // times[p] > relLo.
  const pFrom = Math.max(1, _upperBound(s.times, relLo, n));
  const pTo = Math.min(n - 1, _lowerBound(s.times, relHi, n));
  let lo = Infinity, hi = -Infinity;
  for (let p = pFrom; p <= pTo; p++) {
    if (s.times[p - 1] >= relHi || s.times[p] <= relLo) continue;
    const v = s.slew[p - 1];
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  return hi === -Infinity ? null : [lo, hi];
}

// The min/max slew range over blocks `[from, to]` (both inclusive), from
// whole-block ranges: the boundary blocks of the two partial groups are
// scanned one at a time, and the groups strictly between come from the
// tree, exactly like seq_lanes.js's `_rangeMinMax`. Every block has a range
// (never null, see `_blockSlewRange`), so this always returns a pair.
function _rangeSlewMinMax(model, tb, axisCol, evCache, tree, from, to) {
  const N = model.numBlocks;
  from = Math.max(0, from);
  to = Math.min(N - 1, to);
  if (to < from) return null;
  let lo = Infinity, hi = -Infinity;
  const scan = (a, b) => {
    for (let i = a; i <= b; i++) {
      const [x, y] = _blockSlewRange(tb, i, axisCol, evCache);
      if (x < lo) lo = x;
      if (y > hi) hi = y;
    }
  };
  const gFrom = Math.floor(from / GROUP_BLOCKS), gTo = Math.floor(to / GROUP_BLOCKS);
  if (gFrom === gTo) {
    scan(from, to);
    return [lo, hi];
  }
  scan(from, (gFrom + 1) * GROUP_BLOCKS - 1);
  scan(gTo * GROUP_BLOCKS, to);
  if (gTo - gFrom > 1) {
    const tLo = tree.min.query(gFrom + 1, gTo);
    const tHi = tree.max.query(gFrom + 1, gTo);
    if (tLo < lo) lo = tLo;
    if (tHi > hi) hi = tHi;
  }
  return [lo, hi];
}

// The group trees of one axis's slew range, built once per model (cached in
// `model._slewG.slewTrees`). One pass over the N blocks; the event stats
// themselves are computed at most once per unique event, memoized in
// `evCache.slew`.
function _buildSlewGroups(model, tb, axisCol, evCache) {
  const N = model.numBlocks;
  const G = Math.ceil(N / GROUP_BLOCKS) || 1;
  const gMin = new Float64Array(G).fill(Infinity);
  const gMax = new Float64Array(G).fill(-Infinity);
  for (let g = 0; g < G; g++) {
    const from = g * GROUP_BLOCKS, to = Math.min(N, from + GROUP_BLOCKS);
    let lo = Infinity, hi = -Infinity;
    for (let i = from; i < to; i++) {
      const [a, b] = _blockSlewRange(tb, i, axisCol, evCache);
      if (a < lo) lo = a;
      if (b > hi) hi = b;
    }
    gMin[g] = lo;
    gMax[g] = hi;
  }
  return {min: _segTree(gMin, G, true), max: _segTree(gMax, G, false)};
}

function _prep(model) {
  let p = model._slewG;
  if (p === undefined) {
    p = {evCache: {slew: new Map(), geom: new Map(), triple: new Map()}, slewTrees: {}, gTree: null};
    model._slewG = p;
  }
  return p;
}

// The exact min and the exact max slew rate (T/m/s) of `axis` ("gx", "gy" or
// "gz") in each of `bins` equal bins of `[t0, t1]` (s), edges e_k = t0 +
// (t1 - t0) * k / bins as seq_lanes.js's minMaxLanes computes them. Builds
// (and caches on `model`) the per-event stats and the group tree for this
// axis on first use.
//
// Returns `{edges (Float64Array, bins + 1, s), min, max (Float64Array,
// bins)}`.
function slewMinMax(model, axis, t0, t1, bins) {
  if (AXES.indexOf(axis) < 0) {
    throw new Error(`slewMinMax: unknown axis ${JSON.stringify(axis)} (expected gx, gy or gz)`);
  }
  const tb = model.tables;
  const axisCol = tb[axis];
  const prep = _prep(model);
  const evCache = prep.evCache;
  let tree = prep.slewTrees[axis];
  if (tree === undefined) {
    tree = _buildSlewGroups(model, tb, axisCol, evCache);
    prep.slewTrees[axis] = tree;
  }

  const N = model.numBlocks;
  const {edges, edgeBlock} = _binEdges(model, t0, t1, bins);
  const outMin = new Float64Array(bins);
  const outMax = new Float64Array(bins);
  if (N === 0) {
    outMin.fill(0);
    outMax.fill(0);
    return {edges, min: outMin, max: outMax};
  }

  for (let k = 0; k < bins; k++) {
    let lo = Infinity, hi = -Infinity;
    const take = (pair) => {
      if (pair === null) return;
      if (pair[0] < lo) lo = pair[0];
      if (pair[1] > hi) hi = pair[1];
    };
    const loAbs = edges[k], hiAbs = edges[k + 1];
    take(_exactBlockSlewRange(model, tb, edgeBlock[k], axisCol, evCache, loAbs, hiAbs));
    if (edgeBlock[k + 1] !== edgeBlock[k]) {
      take(_exactBlockSlewRange(model, tb, edgeBlock[k + 1], axisCol, evCache, loAbs, hiAbs));
    }
    if (edgeBlock[k + 1] - edgeBlock[k] > 1) {
      take(_rangeSlewMinMax(model, tb, axisCol, evCache, tree, edgeBlock[k] + 1, edgeBlock[k + 1] - 1));
    }
    // A bin with no positive-length overlap found (a degenerate bin, at
    // most a floating point sliver at the very end of the file) still has
    // the gradient at 0: every block's range already includes 0 whenever it
    // has no event, so this only triggers when a bin is empty of blocks
    // altogether.
    outMin[k] = lo === Infinity ? 0 : lo;
    outMax[k] = hi === -Infinity ? 0 : hi;
  }
  return {edges, min: outMin, max: outMax};
}

// ---- |G| (plan section 3.6, item 2) ----------------------------------------

// The extrema of a convex quadratic `f(tau) = A*tau^2 + B*tau + C` (A >= 0)
// over `tau in [ta, tb]` (0 <= ta <= tb <= 1): the max is always at one of
// the two ends (a convex function's maximum on an interval is at an
// endpoint); the min is at the vertex `tau* = -B / (2A)` when `A > 0` and
// `tau*` falls inside `[ta, tb]`, else also at an endpoint. Returns
// `[min, max]` of `f` itself (not yet square-rooted).
function _quadRangeExtrema(A, B, C, ta, tb) {
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

// The breakpoint times (s, relative to the block start) of a distinct
// (kx, ky, kz) triple of dense gradient event ids (0 = no event on that
// axis): the sorted, de-duplicated union of the up to three events' own
// times, i.e. the times at which any axis has a corner. All three axes are
// linear between two consecutive union times, so |G|^2 is a quadratic
// there (`_quadRangeExtrema`). The values of each axis at each union time
// come from `_axisValueAt` (0 for an absent axis).
function _tripleTimes(tb, kx, ky, kz, evCache) {
  const parts = [];
  if (kx !== 0) parts.push(_eventGeometry(tb, kx, evCache.geom).times);
  if (ky !== 0) parts.push(_eventGeometry(tb, ky, evCache.geom).times);
  if (kz !== 0) parts.push(_eventGeometry(tb, kz, evCache.geom).times);
  if (parts.length === 0) return new Float64Array([0]);
  const merged = new Set();
  for (const arr of parts) for (let i = 0; i < arr.length; i++) merged.add(arr[i]);
  return Float64Array.from(Array.from(merged).sort((a, b) => a - b));
}

// The per-triple cached geometry: the union breakpoint times, the three
// axes' values at each of those times (T/m), and the quadratic
// coefficients (A, B, C, in tau in [0, 1] of each piece) of |G|^2 on each
// of the `times.length - 1` pieces, plus the triple's own whole-block min
// and max |G| (T/m; the min and max over every piece's own [0, 1] range).
// Computed once per distinct triple and memoized in `evCache.triple`, keyed
// by a string of the three dense ids: simple and exact regardless of how
// large a dense id gets, unlike packing them into one Number (whose exact
// integers run out at 2^53).
function _tripleGeometry(tb, kx, ky, kz, evCache) {
  const key = kx + "," + ky + "," + kz;
  let g = evCache.triple.get(key);
  if (g !== undefined) return g;

  const times = _tripleTimes(tb, kx, ky, kz, evCache);
  const n = times.length;
  const vx = new Float64Array(n), vy = new Float64Array(n), vz = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    vx[i] = _axisValueAt(tb, kx, evCache.geom, times[i]);
    vy[i] = _axisValueAt(tb, ky, evCache.geom, times[i]);
    vz[i] = _axisValueAt(tb, kz, evCache.geom, times[i]);
  }
  const pieceA = new Float64Array(Math.max(0, n - 1));
  const pieceB = new Float64Array(Math.max(0, n - 1));
  const pieceC = new Float64Array(Math.max(0, n - 1));
  let blockMin = Infinity, blockMax = -Infinity;
  for (let i = 1; i < n; i++) {
    let A = 0, B = 0, C = 0;
    for (const v of [[vx[i - 1], vx[i]], [vy[i - 1], vy[i]], [vz[i - 1], vz[i]]]) {
      const v0 = v[0], d = v[1] - v[0];
      A += d * d;
      B += 2 * v0 * d;
      C += v0 * v0;
    }
    pieceA[i - 1] = A;
    pieceB[i - 1] = B;
    pieceC[i - 1] = C;
    const [g2lo, g2hi] = _quadRangeExtrema(A, B, C, 0, 1);
    const lo = Math.sqrt(Math.max(0, g2lo)), hi = Math.sqrt(Math.max(0, g2hi));
    if (lo < blockMin) blockMin = lo;
    if (hi > blockMax) blockMax = hi;
  }
  if (n < 2) {
    // A triple with no event at all (kx === ky === kz === 0): |G| = 0
    // everywhere the triple is used.
    blockMin = 0;
    blockMax = 0;
  }
  g = {times, pieceA, pieceB, pieceC, blockMin, blockMax};
  evCache.triple.set(key, g);
  return g;
}

// The min/max |G| range of block `i`: the whole-block extrema of its
// (gx, gy, gz) triple (`_tripleGeometry`), independent of the block's own
// duration (section 3.6's comment above: every event measured here starts
// and ends at value 0 and has zero delay, so extending a block past an
// event's own span never changes |G|'s extrema, which are already 0 at that
// boundary; docs in `_eventGeometry`).
function _blockGRange(tb, i, evCache) {
  const kx = tb.gx[i], ky = tb.gy[i], kz = tb.gz[i];
  const g = _tripleGeometry(tb, kx, ky, kz, evCache);
  return [g.blockMin, g.blockMax];
}

// The exact min/max |G| of block `i`, restricted to `[loAbs, hiAbs)`
// (s, absolute time) clipped to the block's own extent. Returns null when
// there is no positive-length overlap. Walks only the pieces the clip
// range can touch (binary search on the triple's own union times, as
// `_exactBlockSlewRange` does for one axis's segments).
function _exactBlockGRange(model, tb, i, evCache, loAbs, hiAbs) {
  const bStart = SeqLanes.blockStart(model, i);
  const bDur = tb.durations[tb.duration_index[i]];
  const overlapLo = Math.max(bStart, loAbs);
  const overlapHi = Math.min(bStart + bDur, hiAbs);
  if (overlapHi <= overlapLo) return null;

  const kx = tb.gx[i], ky = tb.gy[i], kz = tb.gz[i];
  const g = _tripleGeometry(tb, kx, ky, kz, evCache);
  const n = g.times.length;
  if (n < 2) return [0, 0]; // overlapHi > overlapLo already established above
  const relLo = overlapLo - bStart, relHi = overlapHi - bStart;
  const pFrom = Math.max(1, _upperBound(g.times, relLo, n));
  const pTo = Math.min(n - 1, _lowerBound(g.times, relHi, n));
  let lo = Infinity, hi = -Infinity;
  for (let p = pFrom; p <= pTo; p++) {
    const t0v = g.times[p - 1], t1v = g.times[p];
    if (t0v >= relHi || t1v <= relLo) continue;
    const clipLo = Math.max(t0v, relLo), clipHi = Math.min(t1v, relHi);
    const ta = (clipLo - t0v) / (t1v - t0v), tb2 = (clipHi - t0v) / (t1v - t0v);
    const [g2lo, g2hi] = _quadRangeExtrema(g.pieceA[p - 1], g.pieceB[p - 1], g.pieceC[p - 1], ta, tb2);
    const a = Math.sqrt(Math.max(0, g2lo)), b = Math.sqrt(Math.max(0, g2hi));
    if (a < lo) lo = a;
    if (b > hi) hi = b;
  }
  return hi === -Infinity ? null : [lo, hi];
}

function _rangeGMinMax(model, tb, evCache, tree, from, to) {
  const N = model.numBlocks;
  from = Math.max(0, from);
  to = Math.min(N - 1, to);
  if (to < from) return null;
  let lo = Infinity, hi = -Infinity;
  const scan = (a, b) => {
    for (let i = a; i <= b; i++) {
      const [x, y] = _blockGRange(tb, i, evCache);
      if (x < lo) lo = x;
      if (y > hi) hi = y;
    }
  };
  const gFrom = Math.floor(from / GROUP_BLOCKS), gTo = Math.floor(to / GROUP_BLOCKS);
  if (gFrom === gTo) {
    scan(from, to);
    return [lo, hi];
  }
  scan(from, (gFrom + 1) * GROUP_BLOCKS - 1);
  scan(gTo * GROUP_BLOCKS, to);
  if (gTo - gFrom > 1) {
    const tLo = tree.min.query(gFrom + 1, gTo);
    const tHi = tree.max.query(gFrom + 1, gTo);
    if (tLo < lo) lo = tLo;
    if (tHi > hi) hi = tHi;
  }
  return [lo, hi];
}

function _buildGGroups(model, tb, evCache) {
  const N = model.numBlocks;
  const G = Math.ceil(N / GROUP_BLOCKS) || 1;
  const gMin = new Float64Array(G).fill(Infinity);
  const gMax = new Float64Array(G).fill(-Infinity);
  for (let g = 0; g < G; g++) {
    const from = g * GROUP_BLOCKS, to = Math.min(N, from + GROUP_BLOCKS);
    let lo = Infinity, hi = -Infinity;
    for (let i = from; i < to; i++) {
      const [a, b] = _blockGRange(tb, i, evCache);
      if (a < lo) lo = a;
      if (b > hi) hi = b;
    }
    gMin[g] = lo;
    gMax[g] = hi;
  }
  return {min: _segTree(gMin, G, true), max: _segTree(gMax, G, false)};
}

// The exact min and the exact max |G| (T/m) in each of `bins` equal bins of
// `[t0, t1]` (s), with the same bin edges as `slewMinMax`/seq_lanes.js.
// Builds (and caches on `model`) the per-triple geometry and the group tree
// on first use.
//
// Returns `{edges (Float64Array, bins + 1, s), min, max (Float64Array,
// bins)}`.
function gMagMinMax(model, t0, t1, bins) {
  const tb = model.tables;
  const prep = _prep(model);
  const evCache = prep.evCache;
  if (prep.gTree === null) {
    prep.gTree = _buildGGroups(model, tb, evCache);
  }
  const tree = prep.gTree;

  const N = model.numBlocks;
  const {edges, edgeBlock} = _binEdges(model, t0, t1, bins);
  const outMin = new Float64Array(bins);
  const outMax = new Float64Array(bins);
  if (N === 0) {
    outMin.fill(0);
    outMax.fill(0);
    return {edges, min: outMin, max: outMax};
  }

  for (let k = 0; k < bins; k++) {
    let lo = Infinity, hi = -Infinity;
    const take = (pair) => {
      if (pair === null) return;
      if (pair[0] < lo) lo = pair[0];
      if (pair[1] > hi) hi = pair[1];
    };
    const loAbs = edges[k], hiAbs = edges[k + 1];
    take(_exactBlockGRange(model, tb, edgeBlock[k], evCache, loAbs, hiAbs));
    if (edgeBlock[k + 1] !== edgeBlock[k]) {
      take(_exactBlockGRange(model, tb, edgeBlock[k + 1], evCache, loAbs, hiAbs));
    }
    if (edgeBlock[k + 1] - edgeBlock[k] > 1) {
      take(_rangeGMinMax(model, tb, evCache, tree, edgeBlock[k] + 1, edgeBlock[k + 1] - 1));
    }
    outMin[k] = lo === Infinity ? 0 : lo;
    outMax[k] = hi === -Infinity ? 0 : hi;
  }
  return {edges, min: outMin, max: outMax};
}

module.exports = {slewMinMax, gMagMinMax, GROUP_BLOCKS};
