// Task 5 of docs/plans/pns-lanes-prototype.md: bounds, refinement and the
// whole-file peak for the PNS lanes, on top of pns_lanes.js (tasks 3).
//
// Lanes: "total" (root-sum-of-squares), "x", "y", "z" (axis values), in units
// of the stimulation limit (1 = the limit), as pns_lanes.js computes them.
//
// Bounds of one block (plan section 3.4). For one filter with c = 1 - alpha,
// start state s and boundary input u0, the samples of the block are
// y[j] = c^j * v + h[j], with v = alpha * u0 + c * s (= y[0]) and h the
// zero-state response to the block's own inputs (h[0] = 0). So:
//   |y[j]| <= |v| + H,          H = max_j |h[j]|        (upper bound)
//   |y[j]| >= c^(n-1) * |v| - H (lower bound, 0 if negative)
// For the filter of |x| (tau2), v >= 0 and h >= 0, so y[j] >= c^(n-1) * v.
// The axis value a1*|y1| + a2*y2 + a3*|y3| (times g_scale / stim_limit) and the
// total sqrt(px^2 + py^2 + pz^2) only grow when the |y| grow, so the filter
// bounds give bounds of each lane in the block. The first and the last sample
// of the block are computed exactly from v and from the block map, and they
// are attained values.
//
// Groups of blocks (the checkpoint groups of pns_lanes.js) keep, for each
// lane, the largest upper bound and the largest attained value of their
// blocks (for maxima), and the smallest lower bound and the smallest attained
// value (for minima). Segment trees over the groups answer ranges.
//
// Refinement (plan section 3.4, item 3): for the maximum of one lane over a
// sample range, the best attained value found so far prunes every group and
// every block whose upper bound is at most best + eps. The other blocks are
// evaluated exactly on their samples. The result is within eps of the exact
// maximum (eps = 0 gives the exact value). The minimum is the same with the
// bounds exchanged.

const PnsBounds = (() => {
  const PnsLanes = require(require("path").join(__dirname, "pns_lanes.js"));
  const {AXES, applyBlockMap, runBlockSamples, eventEntry} = PnsLanes._internal;
  const LANES = ["total", "x", "y", "z"];

  // ---- per-event maxima of |h| (cached by event, axis, n) ----

  // max_j |h[j]| of the three filters of one axis, for one event played in a
  // block of n samples: the same recursion as pns_lanes' zero-state response,
  // with the maximum kept.
  function _hMax(model, cache, axis, ev, n) {
    const key = ev * 4 + AXES.indexOf(axis) + n * 1e7;  // ev < 2^31, n < 2^20: no collision in practice
    let m = cache.get(key);
    if (m !== undefined) return m;
    const g = eventEntry(model, axis, ev, n).g;
    const alpha = model.filterAlpha[axis], c = model.filterC[axis];
    const invDt = 1 / model.dt;
    let h0 = 0, h1 = 0, h2 = 0, m0 = 0, m1 = 0, m2 = 0;
    for (let j = 1; j < n; j++) {
      const x = (g[j] - g[j - 1]) * invDt;
      h0 = c[0] * h0 + alpha[0] * x;
      h1 = c[1] * h1 + alpha[1] * Math.abs(x);
      h2 = c[2] * h2 + alpha[2] * x;
      const a0 = Math.abs(h0), a2 = Math.abs(h2);
      if (a0 > m0) m0 = a0;
      if (h1 > m1) m1 = h1;
      if (a2 > m2) m2 = a2;
    }
    m = [m0, m1, m2];
    cache.set(key, m);
    return m;
  }

  // ---- segment trees over groups ----

  function _tree(values, isMax) {
    let size = 1;
    while (size < values.length) size *= 2;
    const fill = isMax ? -Infinity : Infinity;
    const t = new Float64Array(2 * size).fill(fill);
    t.set(values, size);
    for (let i = size - 1; i >= 1; i--) {
      const a = t[2 * i], b = t[2 * i + 1];
      t[i] = isMax ? (a > b ? a : b) : (a < b ? a : b);
    }
    return {t, size, isMax, fill};
  }

  // The max (or min) over leaves [lo, hi) (lo < hi).
  function _query(tr, lo, hi) {
    let acc = tr.fill;
    const t = tr.t;
    for (let l = lo + tr.size, r = hi + tr.size; l < r; l >>= 1, r >>= 1) {
      if (l & 1) { const v = t[l++]; if (tr.isMax ? v > acc : v < acc) acc = v; }
      if (r & 1) { const v = t[--r]; if (tr.isMax ? v > acc : v < acc) acc = v; }
    }
    return acc;
  }

  // The leaves in [lo, hi) whose value passes `test` (the value is above a
  // threshold for a max tree, below it for a min tree), found by descending
  // only into nodes that pass.
  function _collect(tr, lo, hi, test, out) {
    const rec = (node, nlo, nhi) => {
      if (nhi <= lo || nlo >= hi || !test(tr.t[node])) return;
      if (node >= tr.size) { out.push(node - tr.size); return; }
      const mid = (nlo + nhi) >> 1;
      rec(2 * node, nlo, mid);
      rec(2 * node + 1, mid, nhi);
    };
    rec(1, 0, tr.size);
    return out;
  }

  // ---- precompute (one scan over all blocks) ----

  // Bounds of one block (4 lanes): upper and lower bounds, and the exact
  // values at its first and last samples. `state` and `lastG` are the start
  // state and the last gradient samples of the block before; they are not
  // changed here. `out`: {ub, lb, first, last} Float64Array(4) each.
  function _blockBounds(bm, n, eventIdx, state, lastG, out) {
    const model = bm.model;
    const dt = model.dt;
    let ubT2 = 0, lbT2 = 0, fT2 = 0;
    for (let a = 0; a < 3; a++) {
      const axis = AXES[a];
      const ev = eventIdx[a];
      let g0 = 0, H = ZERO3;
      if (ev !== 0) {
        g0 = eventEntry(model, axis, ev, n).g[0];
        H = _hMax(model, bm.hCache, axis, ev, n);
      }
      const x0 = (g0 - lastG[a]) / dt;
      const alpha = model.filterAlpha[axis], c = model.filterC[axis];
      const hw = model.hw[axis];
      const k = hw.g_scale / hw.stim_limit;
      const coef = [hw.a1, hw.a2, hw.a3];
      let ub = 0, lb = 0, first = 0;
      for (let f = 0; f < 3; f++) {
        const u0 = f === 1 ? Math.abs(x0) : x0;
        const v = alpha[f] * u0 + c[f] * state[a * 3 + f];
        const av = Math.abs(v);
        const cEnd = Math.pow(c[f], n - 1);
        ub += coef[f] * (av + H[f]);
        const lo = f === 1 ? cEnd * v : cEnd * av - H[f];
        lb += coef[f] * (lo > 0 ? lo : 0);
        first += coef[f] * av;
      }
      ub *= k; lb *= k; first *= k;
      out.ub[a + 1] = ub; out.lb[a + 1] = lb; out.first[a + 1] = first;
      ubT2 += ub * ub; lbT2 += lb * lb; fT2 += first * first;
    }
    out.ub[0] = Math.sqrt(ubT2);
    out.lb[0] = Math.sqrt(lbT2);
    out.first[0] = Math.sqrt(fT2);
  }
  const ZERO3 = [0, 0, 0];

  // The 4 lane values of the filter states `state` (the value of a sample
  // whose filter outputs are `state`).
  function _lanesOfState(model, state, out) {
    let t2 = 0;
    for (let a = 0; a < 3; a++) {
      const hw = model.hw[AXES[a]];
      const p = (hw.a1 * Math.abs(state[a * 3]) + hw.a2 * state[a * 3 + 1]
        + hw.a3 * Math.abs(state[a * 3 + 2])) / hw.stim_limit * hw.g_scale;
      out[a + 1] = p;
      t2 += p * p;
    }
    out[0] = Math.sqrt(t2);
  }

  // Builds the group summaries and the trees. Cost: one pass over the blocks
  // (block maps only, no sample), like pns_lanes.decode.
  function build(model) {
    const G = model.numGroups, GB = model.groupBlocks, N = model.numBlocks;
    const tb = model.tables;
    const bm = {model, hCache: new Map()};
    const gMaxUb = LANES.map(() => new Float64Array(G).fill(-Infinity));
    const gMaxAtt = LANES.map(() => new Float64Array(G).fill(-Infinity));
    const gMinLb = LANES.map(() => new Float64Array(G).fill(Infinity));
    const gMinAtt = LANES.map(() => new Float64Array(G).fill(Infinity));
    const state = new Float64Array(9), lastG = new Float64Array(3);
    const out = {ub: new Float64Array(4), lb: new Float64Array(4), first: new Float64Array(4)};
    const endVals = new Float64Array(4);
    const eventIdx = [0, 0, 0];
    for (let i = 0; i < N; i++) {
      const g = Math.floor(i / GB);
      const n = model.blockLen[i];
      eventIdx[0] = tb.gx[i]; eventIdx[1] = tb.gy[i]; eventIdx[2] = tb.gz[i];
      if (n > 0) {
        _blockBounds(bm, n, eventIdx, state, lastG, out);
        applyBlockMap(model, n, eventIdx, state, lastG);
        _lanesOfState(model, state, endVals);
        for (let L = 0; L < 4; L++) {
          if (out.ub[L] > gMaxUb[L][g]) gMaxUb[L][g] = out.ub[L];
          if (out.lb[L] < gMinLb[L][g]) gMinLb[L][g] = out.lb[L];
          const hi = out.first[L] > endVals[L] ? out.first[L] : endVals[L];
          const lo = out.first[L] < endVals[L] ? out.first[L] : endVals[L];
          if (hi > gMaxAtt[L][g]) gMaxAtt[L][g] = hi;
          if (lo < gMinAtt[L][g]) gMinAtt[L][g] = lo;
        }
      }
    }
    bm.trees = LANES.map((_, L) => ({
      maxUb: _tree(gMaxUb[L], true), maxAtt: _tree(gMaxAtt[L], true),
      minLb: _tree(gMinLb[L], false), minAtt: _tree(gMinAtt[L], false),
    }));
    return bm;
  }

  // ---- positions ----

  // Start sample, start state and lastG of block i, from its group's
  // checkpoint (block maps over at most GB - 1 blocks).
  function _blockStart(model, i, state, lastG) {
    const GB = model.groupBlocks, g = Math.floor(i / GB), tb = model.tables;
    state.set(model.checkpointState.subarray(g * 9, g * 9 + 9));
    lastG.set(model.checkpointLastG.subarray(g * 3, g * 3 + 3));
    let k = model.groupFirstSample[g];
    const eventIdx = [0, 0, 0];
    for (let b = g * GB; b < i; b++) {
      const n = model.blockLen[b];
      eventIdx[0] = tb.gx[b]; eventIdx[1] = tb.gy[b]; eventIdx[2] = tb.gz[b];
      applyBlockMap(model, n, eventIdx, state, lastG);
      k += n;
    }
    return k;
  }

  // The block that holds sample k (binary search on groups, then a scan).
  function _blockOfSample(model, k) {
    const gfs = model.groupFirstSample;
    let lo = 0, hi = model.numGroups - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (gfs[mid] <= k) lo = mid; else hi = mid - 1;
    }
    let i = lo * model.groupBlocks, s = gfs[lo];
    while (i < model.numBlocks - 1 && s + model.blockLen[i] <= k) { s += model.blockLen[i]; i++; }
    return i;
  }

  // ---- exact evaluation of a block (all 4 lanes, max and min) ----

  // Exact max and min of each lane over the samples [ka, kb] of block i
  // (whole block when ka/kb cover it). Memoized per query context for whole
  // blocks. With the cache option, whole-block results are also kept across
  // queries, keyed by the events, n, lastG and the start state rounded to q.
  function _evalBlock(ctx, i, ka, kb) {
    const model = ctx.model;
    const st = new Float64Array(9), lg = new Float64Array(3);
    const k0 = _blockStart(model, i, st, lg);
    const n = model.blockLen[i];
    const whole = ka <= k0 && kb >= k0 + n - 1;
    if (whole && ctx.memo.has(i)) return ctx.memo.get(i);
    const tb = model.tables;
    let key = null;
    if (whole && ctx.stateCache) {
      const q = ctx.stateQuantum;
      key = tb.gx[i] + "," + tb.gy[i] + "," + tb.gz[i] + "," + n + "," + lg[0] + "," + lg[1] + ","
        + lg[2];
      for (let f = 0; f < 9; f++) key += "," + Math.round(st[f] / q);
      const hit = ctx.stateCache.get(key);
      if (hit !== undefined) { ctx.stats.cacheHits++; ctx.memo.set(i, hit); return hit; }
    }
    const mx = new Float64Array(4).fill(-Infinity), mn = new Float64Array(4).fill(Infinity);
    const lo = Math.max(ka, k0), hi = Math.min(kb, k0 + n - 1);
    runBlockSamples(model, n, [tb.gx[i], tb.gy[i], tb.gz[i]], st, lg, k0, (k, tot, px, py, pz) => {
      if (k < lo || k > hi) return;
      const v = [tot, px, py, pz];
      for (let L = 0; L < 4; L++) {
        if (v[L] > mx[L]) mx[L] = v[L];
        if (v[L] < mn[L]) mn[L] = v[L];
      }
    });
    ctx.stats.blocksEvaluated++;
    ctx.stats.samplesEvaluated += n;
    const res = {max: mx, min: mn};
    if (whole) {
      ctx.memo.set(i, res);
      if (key !== null) ctx.stateCache.set(key, res);
    }
    return res;
  }

  // ---- refinement over a sample range ----

  // The max (isMax) or min of lane L over the samples [ka, kb], within eps.
  function _extreme(ctx, L, ka, kb, isMax, eps) {
    const model = ctx.model, bm = ctx.bm, GB = model.groupBlocks;
    const trees = bm.trees[L];
    const better = isMax ? (a, b) => a > b : (a, b) => a < b;
    let best = isMax ? -Infinity : Infinity;
    const take = v => { if (better(v, best)) best = v; };
    // A block or a group can hold a better value only if its bound passes this.
    const open = bound => (isMax ? bound > best + eps : bound < best - eps);

    const iA = _blockOfSample(model, ka), iB = _blockOfSample(model, kb);
    const gA = Math.floor(iA / GB), gB = Math.floor(iB / GB);

    // The two cut blocks: exact on the samples in range.
    const edgeBlocks = iA === iB ? [iA] : [iA, iB];
    for (const i of edgeBlocks) {
      const r = _evalBlock(ctx, i, ka, kb);
      take(isMax ? r.max[L] : r.min[L]);
    }

    // Whole blocks of a group range [b0, b1] (block indexes), with bounds.
    const blockPass = (b0, b1) => {
      if (b1 < b0) return;
      const st = new Float64Array(9), lg = new Float64Array(3);
      _blockStart(model, b0, st, lg);
      const tb = model.tables;
      const out = {ub: new Float64Array(4), lb: new Float64Array(4), first: new Float64Array(4)};
      const endVals = new Float64Array(4);
      const cands = [];
      const eventIdx = [0, 0, 0];
      for (let i = b0; i <= b1; i++) {
        const n = model.blockLen[i];
        eventIdx[0] = tb.gx[i]; eventIdx[1] = tb.gy[i]; eventIdx[2] = tb.gz[i];
        if (n === 0) continue;
        _blockBounds(bm, n, eventIdx, st, lg, out);
        applyBlockMap(model, n, eventIdx, st, lg);
        _lanesOfState(model, st, endVals);
        take(out.first[L]); take(endVals[L]);
        cands.push([i, isMax ? out.ub[L] : out.lb[L]]);
        ctx.stats.blocksBounded++;
      }
      cands.sort((p, q) => (isMax ? q[1] - p[1] : p[1] - q[1]));
      for (const [i, bound] of cands) {
        if (!open(bound)) break;
        const r = _evalBlock(ctx, i, -Infinity, Infinity);
        take(isMax ? r.max[L] : r.min[L]);
      }
    };

    if (iB - iA >= 1) {
      if (gA === gB) {
        blockPass(iA + 1, iB - 1);
      } else {
        blockPass(iA + 1, Math.min((gA + 1) * GB - 1, iB - 1));
        blockPass(Math.max(gB * GB, iA + 1), iB - 1);
        if (gB - gA > 1) {
          // Whole groups: attained values first, then branch and bound.
          take(_query(isMax ? trees.maxAtt : trees.minAtt, gA + 1, gB));
          const boundTree = isMax ? trees.maxUb : trees.minLb;
          const groups = _collect(boundTree, gA + 1, gB, open, []);
          ctx.stats.groupsOpened += groups.length;
          groups.sort((p, q) => (isMax ? boundTree.t[boundTree.size + q] - boundTree.t[boundTree.size + p]
            : boundTree.t[boundTree.size + p] - boundTree.t[boundTree.size + q]));
          for (const g of groups) {
            if (!open(boundTree.t[boundTree.size + g])) break;
            blockPass(g * GB, Math.min((g + 1) * GB, model.numBlocks) - 1);
          }
        }
      }
    }
    return best;
  }

  function _context(model, bm, options) {
    const opts = options || {};
    const q = opts.cache ? opts.stateQuantum : 0;
    return {
      model, bm, memo: new Map(),
      stateCache: opts.cache ? (opts.stateCacheMap || new Map()) : null,
      stateQuantum: q,
      stats: {blocksBounded: 0, blocksEvaluated: 0, samplesEvaluated: 0, groupsOpened: 0,
        cacheHits: 0},
    };
  }

  // The state quantum for the cache: an error of at most eps / 2 in any lane.
  // |Δ lane| <= sum over axes and filters of coef * k * |Δ s| (the total is
  // at most the sum of the axis changes), so q = eps / (2 * that sum).
  function stateQuantumFor(model, eps) {
    let s = 0;
    for (const axis of AXES) {
      const hw = model.hw[axis];
      s += (hw.a1 + hw.a2 + hw.a3) * hw.g_scale / hw.stim_limit;
    }
    return eps / (2 * s);
  }

  // ---- public ----

  // The min and max of each lane in each of `bins` equal bins of [t0, t1] (s),
  // within eps. A bin with no sample gives NaN.
  function minMaxView(model, bm, t0, t1, bins, eps, options) {
    const ctx = _context(model, bm, options);
    const edges = new Float64Array(bins + 1);
    for (let k = 0; k <= bins; k++) edges[k] = t0 + (t1 - t0) * k / bins;
    const lanes = {};
    for (const name of LANES) lanes[name] = {min: new Float64Array(bins), max: new Float64Array(bins)};
    const dt = model.dt;
    for (let b = 0; b < bins; b++) {
      const last = b === bins - 1;
      // Samples with e_b <= (k + 0.5) dt < e_(b+1) (<= in the last bin).
      let ka = Math.ceil(edges[b] / dt - 0.5);
      while ((ka + 0.5) * dt < edges[b]) ka++;
      while (ka > 0 && (ka - 0.5) * dt >= edges[b]) ka--;
      let kb = Math.ceil(edges[b + 1] / dt - 0.5) - 1;
      while (kb + 1 < model.numSamples && (kb + 1.5) * dt < edges[b + 1]) kb++;
      while (kb >= 0 && (kb + 0.5) * dt >= edges[b + 1]) kb--;
      if (last) while (kb + 1 < model.numSamples && (kb + 1.5) * dt <= edges[b + 1]) kb++;
      if (ka < 0) ka = 0;
      if (kb > model.numSamples - 1) kb = model.numSamples - 1;
      for (let L = 0; L < 4; L++) {
        const name = LANES[L];
        if (kb < ka) { lanes[name].max[b] = NaN; lanes[name].min[b] = NaN; continue; }
        lanes[name].max[b] = _extreme(ctx, L, ka, kb, true, eps);
        lanes[name].min[b] = _extreme(ctx, L, ka, kb, false, eps);
      }
    }
    return {edges, lanes, stats: ctx.stats};
  }

  // The exact whole-file peak of each lane, and the time of the first sample
  // of the total at or above peak * (1 - 1e-6).
  function peak(model, bm, options) {
    const ctx = _context(model, bm, options);
    const N = model.numSamples;
    if (N === 0) return {peak: 0, peakTimeS: null, axisPeaks: {x: 0, y: 0, z: 0}, stats: ctx.stats};
    const vals = LANES.map((_, L) => _extreme(ctx, L, 0, N - 1, true, 0));
    const pk = vals[0];
    const thr = pk * (1 - 1e-6);
    // The first sample at or above thr: groups in play order whose upper
    // bound reaches thr, then blocks in order, then samples.
    const tree = bm.trees[0].maxUb;
    const groups = _collect(tree, 0, model.numGroups, v => v >= thr, []);
    groups.sort((a, b) => a - b);
    let peakK = null;
    const GB = model.groupBlocks, tb = model.tables;
    const out = {ub: new Float64Array(4), lb: new Float64Array(4), first: new Float64Array(4)};
    for (const g of groups) {
      const st = new Float64Array(9), lg = new Float64Array(3);
      let k = _blockStart(model, g * GB, st, lg);
      for (let i = g * GB; i < Math.min((g + 1) * GB, model.numBlocks) && peakK === null; i++) {
        const n = model.blockLen[i];
        const ev = [tb.gx[i], tb.gy[i], tb.gz[i]];
        if (n > 0) {
          _blockBounds(bm, n, ev, st, lg, out);
          if (out.ub[0] >= thr) {
            const s2 = st.slice(), l2 = lg.slice();
            runBlockSamples(model, n, ev, s2, l2, k, (kk, tot) => {
              if (peakK === null && tot >= thr) peakK = kk;
            });
            ctx.stats.samplesEvaluated += n;
          }
          applyBlockMap(model, n, ev, st, lg);
        }
        k += n;
      }
      if (peakK !== null) break;
    }
    return {
      peak: pk, peakTimeS: peakK === null ? null : (peakK + 0.5) * model.dt,
      axisPeaks: {x: vals[1], y: vals[2], z: vals[3]}, stats: ctx.stats,
    };
  }

  // The plain method: the sample recursion over the whole file (two passes:
  // the peak, then the first sample at or above peak * (1 - 1e-6)).
  function plainPeak(model) {
    const mx = [0, 0, 0, 0];
    PnsLanes.wholeFileRecursion(model, chunk => {
      const arrs = [chunk.total, chunk.x, chunk.y, chunk.z];
      for (let L = 0; L < 4; L++) {
        const a = arrs[L];
        for (let j = 0; j < a.length; j++) if (a[j] > mx[L]) mx[L] = a[j];
      }
    });
    const thr = mx[0] * (1 - 1e-6);
    let peakK = null;
    try {
      PnsLanes.wholeFileRecursion(model, chunk => {
        const tot = chunk.total;
        for (let j = 0; j < tot.length; j++) {
          if (tot[j] >= thr) { peakK = chunk.fromSample + j; throw STOP; }
        }
      });
    } catch (e) { if (e !== STOP) throw e; }
    return {peak: mx[0], peakTimeS: peakK === null ? null : (peakK + 0.5) * model.dt,
      axisPeaks: {x: mx[1], y: mx[2], z: mx[3]}};
  }
  const STOP = {};

  return {build, minMaxView, peak, plainPeak, stateQuantumFor, LANES,
    _blockOfSample, _evalBlock, _context};
})();
if (typeof module !== "undefined") module.exports = PnsBounds;
