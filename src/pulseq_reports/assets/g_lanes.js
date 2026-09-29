// The |G| lane of the sequence diagram (docs/plans/diagram-lanes.md, phase 5):
// |G| = sqrt(gx^2 + gy^2 + gz^2) (mT/m, the table units), computed in the browser from
// the diagram tables, with no DOM and no network. A pure module, like
// src/pulseq_reports/assets/seq_lanes.js and pns_lanes.js: one global `GLanes`,
// `module.exports = GLanes` in Node.
//
// This is the prototype's `gMagMinMax` (prototypes/pns_lanes/slew_g.js in the tag
// `archive/pns-lanes-prototype`, its "|G|" section only; the slew half of that file
// is not part of this plan) made into library code: `decode` builds the per-block and
// per-group extrema and the trees, one time, from a `SeqLanes.decode` model; `minMax`
// gives the exact minimum and maximum of |G| in each of a view's time bins, and
// `lanesFor` turns that into the chart's minimum/maximum zigzag form (the only form this
// lane ever uses, at every zoom: unlike a value lane's corner points, |G| is not linear
// between two axes' corner points, so a polyline through the corner values would be
// wrong -- see the module doc of `_tripleGeometry` below). `laneMeta` builds the lane
// object without "segments", for the card script (assets/cards/diagram.js) to draw the
// lane like the other lanes.
//
// Between two consecutive breakpoints of any of the three axes, all three are linear in
// time, so |G|^2 is a quadratic there; its exact minimum and maximum on any sub-range (a
// whole piece, for a block's own extrema, or a clipped piece, for a bin edge) is one
// closed-form evaluation (`_quadRangeExtrema`). The quadratic is a sum of three squares
// of affine functions, so it is convex: never negative, and its vertex (when inside the
// range) is always the minimum, never the maximum, which is always at a range end.
//
// A block with no event on an axis reads as the constant 0 on that axis there (the
// model of pns_lanes.js's module doc: the event's own polyline, 0 outside it, 0 for no
// event), so every block always has a |G| range, never "no value".
//
// `decode`, `minMax` and `lanesFor` build (and cache, on the model `decode` returns) an
// event-triple-level cache and a tree over groups of `GROUP_BLOCKS` blocks, the same
// grouping technique as `seq_lanes.js`'s own (private) group tree, so that a whole-file
// render touches only the O(bins) groups a bin's edges cut, never all N blocks.
"use strict";

// In Node, `require` this file's sibling `seq_lanes.js` (`minMax`'s `_binEdges` needs
// its public `blockAt`/`blockStart`) and make it available as the bare global
// `SeqLanes`, exactly as the browser already has it: page.py loads seq_lanes.js in its
// own <script> element before this one, and top-level `const` declarations of one
// classic <script> are visible as bare identifiers to a later one on the same page, so
// `SeqLanes` is already in scope there with no import. `typeof require` (not `typeof
// module`) is the guard, so that a mistaken load order in the browser fails loudly on
// the first use of `SeqLanes` instead of silently reading `undefined`.
if (typeof require === "function") {
  global.SeqLanes = require("./seq_lanes.js");
}

const GLanes = (() => {
  // 64 blocks in each group: the same order of magnitude as seq_lanes.js's own
  // (private) grouping, so that a render at 10^7 blocks and 812 bins touches only a
  // couple of hundred groups for each bin, far fewer than the blocks in it.
  const GROUP_BLOCKS = 64;
  // Two times closer than this (s) are one breakpoint at a block edge (`_tripleTimes`).
  const EDGE_EPS = 1e-9;

  // ---- Small shared helpers --------------------------------------------------

  // First index `p` in `arr[0, n)` with `arr[p] >= x`. Used on the strictly ascending
  // breakpoint times of one event or one triple, as in seq_lanes.js's
  // `_lowerBound`/`_upperBound`.
  function _lowerBound(arr, x, n) {
    let lo = 0, hi = n;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (arr[mid] < x) lo = mid + 1; else hi = mid;
    }
    return lo;
  }

  // First index `p` in `arr[0, n)` with `arr[p] > x`.
  function _upperBound(arr, x, n) {
    let lo = 0, hi = n;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (arr[mid] <= x) lo = mid + 1; else hi = mid;
    }
    return lo;
  }

  // An iterative segment tree over group minima or maxima, the same layout as
  // seq_lanes.js's (private) `_segTree`: leaves at [n, 2n), node j the extreme of its
  // two children, `query(lo, hi)` in O(log n). Not imported (that function is private
  // to seq_lanes.js): a small, deliberate duplicate of the same well-understood
  // layout, not a divergent copy of its logic (the same choice the prototype made).
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

  // The bin edges e_k = t0 + (t1 - t0) * k / bins (k = 0 ... bins), and the block that
  // holds each edge (`SeqLanes.blockAt`), exactly as `seq_lanes.js`'s `minMaxLanes`
  // finds them, so a |G| render and a value-lane render of the same view cut the file
  // into the same bins.
  function _binEdges(seqModel, t0, t1, bins) {
    const N = seqModel.numBlocks;
    const span = t1 - t0;
    const edges = new Float64Array(bins + 1);
    const edgeBlock = new Int32Array(bins + 1);
    for (let k = 0; k <= bins; k++) {
      edges[k] = t0 + span * k / bins;
      if (N === 0) continue;
      edgeBlock[k] = SeqLanes.blockAt(seqModel, edges[k]);
    }
    return { edges, edgeBlock };
  }

  // ---- Event geometry ---------------------------------------------------------

  // The breakpoint times (s, relative to the block start) and values (mT/m) of one
  // dense gradient event id `k` (1-based; the caller never passes 0). The event's own
  // delay is folded into the times (`start + delay + offset`, section 4.3 of
  // docs/plans/diagram-event-table.md; `minMax`/`_exactBlockGRange` add the block
  // start separately). Computed once for each event and cached (`cache`, keyed by the
  // event id, a plain integer: a numeric cache key, as pns_lanes.js's own per-event
  // cache is).
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
      values[p] = tb.grad_value[valAt + p];
    }
    g = { times, values };
    cache.set(k, g);
    return g;
  }

  // The value (mT/m) of axis event `k` (0 = no event on this axis) at time `t` (s,
  // relative to the block start): 0 when `k === 0`, the event has no point, or `t` is
  // strictly before the event's first point or strictly after its last (the model of
  // the module doc: "0 outside the event", not flat at the boundary value -- a real
  // gradient event usually starts and ends at 0 anyway, but this must hold even when
  // it does not, for example a block whose duration outlasts every one of its
  // events). At exactly the first or last point, the event's own recorded value
  // there (which need not be 0: `_tripleTimes` below relies on this for a "not zero
  // at a block border" event). Interior points interpolate linearly between the
  // event's own breakpoints, as before.
  function _axisValueAt(tb, k, cache, t) {
    if (k === 0) return 0;
    const { times, values } = _eventGeometry(tb, k, cache);
    const n = times.length;
    if (n === 0) return 0;
    if (t <= times[0]) return t === times[0] ? values[0] : 0;
    if (t >= times[n - 1]) return t === times[n - 1] ? values[n - 1] : 0;
    const p = _lowerBound(times, t, n);
    if (times[p] === t) return values[p];
    const t1 = times[p - 1], t2 = times[p];
    const v1 = values[p - 1], v2 = values[p];
    return v1 + (v2 - v1) / (t2 - t1) * (t - t1);
  }

  // ---- |G| geometry -------------------------------------------------------------

  // The extrema of a convex quadratic f(tau) = A*tau^2 + B*tau + C (A >= 0) over
  // tau in [ta, tb] (0 <= ta <= tb <= 1): the maximum is always at one of the two
  // ends (a convex function's maximum on an interval is at an endpoint); the minimum
  // is at the vertex tau* = -B / (2A) when A > 0 and tau* falls inside [ta, tb], else
  // also at an endpoint. Returns [min, max] of f itself (not yet square-rooted).
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

  // The breakpoint times (s, relative to the block start) of a distinct (kx, ky, kz)
  // triple of dense gradient event ids (0 = no event on that axis) played by a block
  // of duration `dur`: the sorted, de-duplicated union of the up to three events' own
  // times, i.e. the times at which any axis has a corner, plus the block's own start
  // (0) and end (`dur`). The block's own start and end are always included, whether
  // or not any axis's own event reaches them (a block can be longer than its events:
  // a short trapezoid with a longer `pp.make_delay`, ADC or RF ringdown in the same
  // block; a gradient event that starts only after a delay), so that the padding
  // before the first event and after the last is a piece of its own, at the value 0
  // (`_axisValueAt`'s "0 outside the event"), not a range `_exactBlockGRange` never
  // visits. All three axes are linear between two consecutive union times, so |G|^2
  // is a quadratic there (`_quadRangeExtrema`).
  //
  // The block's start or end is added only when no event point is within `EDGE_EPS`
  // (pypulseq's own `eps`, 1e-9 s) of it. A gradient that continues into the next block
  // ends there at a value that is not 0; if float rounding put its last point a hair
  // before `dur`, a separate end point would make a piece of almost no width that falls
  // from that value to 0, and every such border would show a false minimum of 0.
  function _tripleTimes(tb, kx, ky, kz, dur, geomCache) {
    const merged = new Set();
    for (const k of [kx, ky, kz]) {
      if (k === 0) continue;
      const t = _eventGeometry(tb, k, geomCache).times;
      for (let i = 0; i < t.length; i++) merged.add(t[i]);
    }
    const sorted = Array.from(merged).sort((a, b) => a - b);
    if (sorted.length === 0 || sorted[0] > EDGE_EPS) sorted.unshift(0);
    if (sorted[sorted.length - 1] < dur - EDGE_EPS) sorted.push(dur);
    return Float64Array.from(sorted);
  }

  // The per-(triple, block duration) cached geometry: the union breakpoint times
  // (`_tripleTimes`, padded to the whole block), the quadratic coefficients (A, B, C,
  // in tau in [0, 1] of each piece) of |G|^2 on each of the `times.length - 1`
  // pieces, and the whole block's own minimum and maximum |G| (mT/m; the minimum and
  // the maximum over every piece's own [0, 1] range, which -- because the pieces now
  // cover [0, dur] whole, not just the union of the events' own spans -- always
  // includes any stretch of the block where every axis reads 0).
  //
  // Computed once for each distinct (triple, duration) and memoized in
  // `evCache.triple`, a `Map` of `Map`s: the outer key `kx * M + ky`
  // (`M = numGradEvents + 1`) selects an inner `Map`, and the inner key
  // `kz * D + durIdx` (`D` the number of distinct block durations) selects the entry
  // in it. Two levels, not the one flat key `((kx * M + ky) * M + kz) * D + durIdx`
  // the prototype's own `slew_g.js` style would give, because that single key stops
  // being an exact integer past 2^53 at about 1.2 * 10^5 gradient events; the two
  // keys above need only `M * M` and `M * D` to stay exact integers (`decode`'s
  // check), which raises the limit to about 9.5 * 10^7 events. The caller
  // (`_tripleKeyOf`) computes both keys once and passes them in as
  // `outerKey`/`innerKey`, so a block makes no extra object on the hot path. Keyed by
  // duration as well as triple (not by triple alone, as the prototype's own
  // `slew_g.js` is) because the padding this function adds depends on the block's own
  // duration, which the same triple can play at more than one length (for example a
  // spoiler gradient shared by blocks with different trailing delays); a file's own
  // durations are pooled to a small number of distinct values
  // (`diagram_data.diagram_tables`), so this does not multiply the number of distinct
  // cache entries by the number of blocks.
  function _tripleGeometry(tb, kx, ky, kz, dur, evCache, outerKey, innerKey) {
    let inner = evCache.triple.get(outerKey);
    if (inner === undefined) {
      inner = new Map();
      evCache.triple.set(outerKey, inner);
    }
    let g = inner.get(innerKey);
    if (g !== undefined) return g;

    const times = _tripleTimes(tb, kx, ky, kz, dur, evCache.geom);
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
      for (const pair of [[vx[i - 1], vx[i]], [vy[i - 1], vy[i]], [vz[i - 1], vz[i]]]) {
        const v0 = pair[0], d = pair[1] - v0;
        A += d * d;
        B += 2 * v0 * d;
        C += v0 * v0;
      }
      pieceA[i - 1] = A;
      pieceB[i - 1] = B;
      pieceC[i - 1] = C;
      const extrema = _quadRangeExtrema(A, B, C, 0, 1);
      const lo = Math.sqrt(Math.max(0, extrema[0])), hi = Math.sqrt(Math.max(0, extrema[1]));
      if (lo < blockMin) blockMin = lo;
      if (hi > blockMax) blockMax = hi;
    }
    if (n < 2) {
      // Only a 0-duration block reaches this (`{0, dur}` collapses to the one point
      // `{0}`): |G| = 0 for its whole (zero-length) extent, whatever the triple.
      blockMin = 0;
      blockMax = 0;
    }
    g = { times, pieceA, pieceB, pieceC, blockMin, blockMax };
    inner.set(innerKey, g);
    return g;
  }

  // The dense triple id of block `i`, its duration, and its two-level numeric cache
  // key (`M`, `D` from `decode`): the outer key `kx * M + ky` and the inner key
  // `kz * D + durIdx` (the comment of `_tripleGeometry` above).
  function _tripleKeyOf(tb, i, M, D) {
    const kx = tb.gx[i], ky = tb.gy[i], kz = tb.gz[i];
    const durIdx = tb.duration_index[i];
    const dur = tb.durations[durIdx];
    return { kx, ky, kz, dur, outerKey: kx * M + ky, innerKey: kz * D + durIdx };
  }

  // The minimum/maximum |G| range of block `i`: the whole-block extrema of its
  // (gx, gy, gz) triple, padded to the block's own duration (`_tripleGeometry`).
  // Never null: a block always has a |G| range (0 where it has no event on any axis,
  // or before/after every one of its events, whatever the block's duration), unlike
  // a value lane's own minimum/maximum in seq_lanes.js, which a block with no event
  // contributes nothing to.
  function _blockGRange(tb, i, evCache, M, D) {
    const t = _tripleKeyOf(tb, i, M, D);
    const g = _tripleGeometry(tb, t.kx, t.ky, t.kz, t.dur, evCache, t.outerKey, t.innerKey);
    return [g.blockMin, g.blockMax];
  }

  // The exact minimum/maximum |G| of block `i`, restricted to `[loAbs, hiAbs)`
  // (s, absolute time) clipped to the block's own extent. Returns null when there is
  // no positive-length overlap. Walks only the pieces the clip range can touch
  // (binary search on the triple's own union times, now padded to the block's own
  // start and end, so a clip range entirely before the first event or after the last
  // still finds the padding piece there, at the value 0).
  function _exactBlockGRange(seqModel, tb, i, evCache, M, D, loAbs, hiAbs) {
    const bStart = SeqLanes.blockStart(seqModel, i);
    const bDur = tb.durations[tb.duration_index[i]];
    const overlapLo = Math.max(bStart, loAbs);
    const overlapHi = Math.min(bStart + bDur, hiAbs);
    if (overlapHi <= overlapLo) return null;

    const t = _tripleKeyOf(tb, i, M, D);
    const g = _tripleGeometry(tb, t.kx, t.ky, t.kz, t.dur, evCache, t.outerKey, t.innerKey);
    const n = g.times.length;
    // Defensive, not reached in practice: `n < 2` only when `dur === 0` (the times
    // are `{0, dur}`, collapsed), and a 0-duration block's `[bStart, bStart]` can
    // never have the positive-length overlap the guard above already requires.
    if (n < 2) return [0, 0];
    const relLo = overlapLo - bStart, relHi = overlapHi - bStart;
    const pFrom = Math.max(1, _upperBound(g.times, relLo, n));
    const pTo = Math.min(n - 1, _lowerBound(g.times, relHi, n));
    let lo = Infinity, hi = -Infinity;
    for (let p = pFrom; p <= pTo; p++) {
      const t0v = g.times[p - 1], t1v = g.times[p];
      if (t0v >= relHi || t1v <= relLo) continue;
      const clipLo = Math.max(t0v, relLo), clipHi = Math.min(t1v, relHi);
      const ta = (clipLo - t0v) / (t1v - t0v), tbEnd = (clipHi - t0v) / (t1v - t0v);
      const extrema = _quadRangeExtrema(g.pieceA[p - 1], g.pieceB[p - 1], g.pieceC[p - 1], ta, tbEnd);
      const a = Math.sqrt(Math.max(0, extrema[0])), b = Math.sqrt(Math.max(0, extrema[1]));
      if (a < lo) lo = a;
      if (b > hi) hi = b;
    }
    return hi === -Infinity ? null : [lo, hi];
  }

  // The minimum/maximum |G| range over blocks [from, to] (both inclusive), from
  // whole-block ranges: the boundary blocks of the two partial groups are scanned one
  // at a time, and the groups strictly between come from the tree, exactly like
  // seq_lanes.js's (private) `_rangeMinMax`. Every block has a range (never null, see
  // `_blockGRange`), so this always returns a pair, or null for an empty range.
  function _rangeGMinMax(tb, evCache, M, D, tree, from, to, N) {
    from = Math.max(0, from);
    to = Math.min(N - 1, to);
    if (to < from) return null;
    let lo = Infinity, hi = -Infinity;
    const scan = (a, b) => {
      for (let i = a; i <= b; i++) {
        const range = _blockGRange(tb, i, evCache, M, D);
        if (range[0] < lo) lo = range[0];
        if (range[1] > hi) hi = range[1];
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

  // The group tree of the file's |G| range (one pass over the N blocks; each distinct
  // triple's own geometry is computed at most once, memoized in `evCache.triple`).
  // `Math.ceil(N / GROUP_BLOCKS) || 1` keeps a well-formed (length >= 1) tree for an
  // empty file too, with both its entries at their identity value (Infinity,
  // -Infinity): an empty range, not a zero range.
  function _buildGGroups(seqModel, tb, evCache, M, D) {
    const N = seqModel.numBlocks;
    const G = Math.ceil(N / GROUP_BLOCKS) || 1;
    const gMin = new Float64Array(G).fill(Infinity);
    const gMax = new Float64Array(G).fill(-Infinity);
    for (let g = 0; g < G; g++) {
      const from = g * GROUP_BLOCKS, to = Math.min(N, from + GROUP_BLOCKS);
      let lo = Infinity, hi = -Infinity;
      for (let i = from; i < to; i++) {
        const range = _blockGRange(tb, i, evCache, M, D);
        if (range[0] < lo) lo = range[0];
        if (range[1] > hi) hi = range[1];
      }
      gMin[g] = lo;
      gMax[g] = hi;
    }
    return { min: _segTree(gMin, G, true), max: _segTree(gMax, G, false) };
  }

  // ---- decode -------------------------------------------------------------------

  // `seqModel`: a model from `SeqLanes.decode` (its tables, `numBlocks`, and
  // `blockStart`/`blockAt` through the `SeqLanes` global/require above). Builds the
  // per-(triple, duration) geometry cache and the group tree one time, and the
  // whole-file peak |G| that `laneMeta` needs (the tree's own root range, so no extra
  // pass over the blocks). Returns a model for `minMax`/`lanesFor`/`laneMeta`.
  //
  // `D`, the number of distinct block durations (`tb.durations.length`, at least 1 so
  // an empty file's unused key space is still well-formed), is part of the two-level
  // cache key `_tripleKeyOf` computes (the comment of `_tripleGeometry`). Throws when
  // either of the two keys' own bound, `M * M - 1` (the outer key) or `M * D - 1`
  // (the inner key), would not stay an exact integer below 2^53, the same defensive
  // check pns_lanes.js's `decode` makes for its own per-event cache key.
  function decode(seqModel) {
    const tb = seqModel.tables;
    const numGradEvents = tb.grad_n.length;
    const M = numGradEvents + 1;
    const D = Math.max(1, tb.durations.length);
    if (M * M - 1 > Number.MAX_SAFE_INTEGER || M * D - 1 > Number.MAX_SAFE_INTEGER) {
      throw new Error(
        "GLanes.decode: the per-(triple, duration) cache key of this file would exceed 2^53");
    }
    const N = seqModel.numBlocks;
    const evCache = { geom: new Map(), triple: new Map() };
    const gTree = _buildGGroups(seqModel, tb, evCache, M, D);
    const whole = N > 0 ? _rangeGMinMax(tb, evCache, M, D, gTree, 0, N - 1, N) : null;
    const wholeFileMax = whole === null ? 0 : whole[1];
    return { seqModel, tables: tb, evCache, gTree, M, D, numBlocks: N, wholeFileMax };
  }

  // ---- minMax ---------------------------------------------------------------------

  // The exact minimum and the exact maximum |G| (mT/m) in each of `bins` equal bins
  // of `[t0, t1]` (s), with the same bin edges `seq_lanes.js`'s `minMaxLanes` uses for
  // the same view. A bin with no block overlapping it at all (only possible when the
  // view reaches outside `[0, seqModel.durationS)`: blocks tile the whole file with
  // no gaps) keeps the identity values (Infinity, -Infinity), the same "no value"
  // convention `PnsLanes.exactView`'s "bins" kind uses, so `lanesFor` can tell a
  // genuinely empty bin from a bin whose |G| is 0.
  //
  // Returns `{edges (Float64Array, bins + 1, s), min, max (Float64Array, bins)}`.
  function minMax(model, t0, t1, bins) {
    const seqModel = model.seqModel;
    const tb = model.tables;
    const evCache = model.evCache;
    const tree = model.gTree;
    const M = model.M;
    const D = model.D;
    const N = model.numBlocks;
    const { edges, edgeBlock } = _binEdges(seqModel, t0, t1, bins);
    const outMin = new Float64Array(bins).fill(Infinity);
    const outMax = new Float64Array(bins).fill(-Infinity);
    if (N === 0) {
      return { edges, min: outMin, max: outMax };
    }

    for (let k = 0; k < bins; k++) {
      let lo = Infinity, hi = -Infinity;
      const take = pair => {
        if (pair === null) return;
        if (pair[0] < lo) lo = pair[0];
        if (pair[1] > hi) hi = pair[1];
      };
      const loAbs = edges[k], hiAbs = edges[k + 1];
      take(_exactBlockGRange(seqModel, tb, edgeBlock[k], evCache, M, D, loAbs, hiAbs));
      if (edgeBlock[k + 1] !== edgeBlock[k]) {
        take(_exactBlockGRange(seqModel, tb, edgeBlock[k + 1], evCache, M, D, loAbs, hiAbs));
      }
      if (edgeBlock[k + 1] - edgeBlock[k] > 1) {
        take(_rangeGMinMax(tb, evCache, M, D, tree, edgeBlock[k] + 1, edgeBlock[k + 1] - 1, N));
      }
      outMin[k] = lo;
      outMax[k] = hi;
    }
    return { edges, min: outMin, max: outMax };
  }

  // ---- lanesFor ---------------------------------------------------------------------

  // The |G| lane for the view `viewMs` (ms) with `bins` plot columns, always the
  // minimum/maximum zigzag of `minMax` (points [edge ms, min], [centre ms, max] for
  // each bin that has a value; a bin with no value, `max[k] === -Infinity`, ends the
  // current segment, the same layout `SeqLanes.minMaxLanes` and `PnsLanes.lanesFor`
  // use), at every zoom: between two corner points of gx, gy and gz, |G| is a
  // (generally non-linear) square root of a quadratic, so a polyline through the
  // three axes' own corner values would not be |G|'s true shape there, unlike a
  // single value lane's own polyline. The bins are always exact (`minMax`): there is
  // no separate "few enough points" branch, and no stored/pyramid level either --
  // |G| is computed on demand from the diagram tables already in the page, not from
  // an extra server-computed level (unlike the PNS lane, which needs one because its
  // filters are not local to one block).
  //
  // `meta` is the lane object without "segments" (`laneMeta`, built once by the card
  // script). Values in the lane are mT/m (the table units); times are ms.
  function lanesFor(model, meta, viewMs, bins) {
    const t0 = viewMs[0] / 1000, t1 = viewMs[1] / 1000;
    const view = minMax(model, t0, t1, bins);
    const segments = [];
    let current = null;
    for (let k = 0; k < bins; k++) {
      if (view.max[k] === -Infinity) {
        if (current !== null) { segments.push(current); current = null; }
        continue;
      }
      if (current === null) current = [];
      const centre = view.edges[k] + (view.edges[k + 1] - view.edges[k]) / 2;
      current.push([view.edges[k] * 1000, view.min[k]], [centre * 1000, view.max[k]]);
    }
    if (current !== null) segments.push(current);
    return { ...meta, segments, minmax: true };
  }

  // ---- laneMeta ---------------------------------------------------------------------

  // 3 significant figures, without a fixed decimal count (so 6.15, 24.6 and 393 all
  // read naturally), the same convention `assets/chart_math.js`'s `fmt` and
  // `pns_lanes.js`'s own `_fmtBinMs` use for a lane's own numbers. |G| is never
  // negative, so there is no sign to turn into "−".
  function _fmt(v) {
    return Number(v.toPrecision(3)).toString();
  }

  // The |G| lane object without "segments" (the `lane_meta` form of
  // `diagram_data.py`, so `laneChart` draws it like the other lanes): "gmag", "|G|",
  // "mT/m", a color token of report.css that is not one of gx/gy/gz ("ink": a solid,
  // neutral color for a combined trace, distinct from the PNS lane's own "ink-2" so
  // the two are never the same color when both are visible at once), "line", the
  // domain/ticks/tick_labels of the whole-file peak (`model.wholeFileMax`, the same
  // style `diagram_data.lane_meta` gives the gx/gy/gz lanes for a peak that is not
  // symmetric about 0: `[0, 1.1 * peak]`, ticks at 0 and the peak -- except that,
  // unlike those lanes, a file with no gradient at all (`peak === 0`) still gets the
  // one-sided domain `[0, 1]`, never `[-1, 1]`: |G| can never be negative), `empty`
  // (true only when the file has no gradient event on any axis, as `gx`/`gy`/`gz`'s
  // own `empty` is) and `fill` (the tooltip's fallback value outside every segment).
  function laneMeta(model) {
    const peak = model.wholeFileMax;
    const hasGradient = peak > 0;
    const domain = hasGradient ? [0, 1.1 * peak] : [0, 1];
    const ticks = hasGradient ? [0, peak] : [0];
    const tickLabels = hasGradient ? ["0", _fmt(peak)] : ["0"];
    return {
      id: "gmag",
      title: "|G|",
      unit: "mT/m",
      color: "ink",
      kind: "line",
      domain,
      ticks,
      tick_labels: tickLabels,
      empty: !hasGradient,
      fill: 0.0,
    };
  }

  return { GROUP_BLOCKS, decode, minMax, lanesFor, laneMeta };
})();
if (typeof module !== "undefined") module.exports = GLanes;
