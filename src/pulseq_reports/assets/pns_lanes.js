// The PNS lane of the sequence diagram (docs/plans/diagram-lanes.md, phase 3),
// computed in the browser from the diagram tables, with no DOM and no
// network. A pure module, like src/pulseq_reports/assets/seq_lanes.js: one
// global `PnsLanes`, `module.exports = PnsLanes` in Node.
//
// `decode` builds a model from the decoded diagram tables (as
// `SeqLanes.decode` takes them) and the file entry's `pns` object (plan
// section 4.4). `exactView` answers the exact PNS of a time range from that
// model, using the block maps of the prototype,
// `prototypes/pns_lanes/pns_lanes.js` and its README in the tag
// `archive/pns-lanes-prototype` (README section "Block maps": a scan with a
// checkpoint every `GROUP_BLOCKS` blocks), not a per-sample recursion over
// the whole file. `levels` builds the coarser pyramid levels (plan section
// 4.5) that `lanesFor` reads for a zoomed-out view. `laneMeta` and
// `statusText` are the two pure helpers the diagram card script
// (assets/cards/diagram.js, phase 4) uses to draw the lane and its part of
// the status line: `laneMeta` builds the lane object without "segments",
// and `statusText` turns one `lanesFor` result into the sentence that says
// which data drew the render.
//
// The model (unchanged from the prototype, `prototypes/pns_lanes/pns_lanes.js`
// and its README in the tag `archive/pns-lanes-prototype`): each block `i`
// holds `n_i = round(duration_i / dt)` gradient-raster samples, at the local
// times `(j + 0.5) * dt` from the block start. The gradient of one axis in a
// block is the event's points at `grad_delay + grad_offset` (s, from the
// block start), with values `grad_value / 1000 * gradScale` (T/m; `gradScale`
// is the file's `pns.gradScale`, 1.0 for a proton sequence, plan section 4.4,
// decision 14), linear between points, 0 before the first point and after
// the last, 0 for a block with no event on the axis. This
// agrees with pypulseq for a sequence that pypulseq accepts: pypulseq's own
// `get_gradients` draws a line across the gap between two events (0 to the
// first point, the last point to 0), and `add_block` makes a gradient
// continuous at a block junction (the checked assumption of the prototype),
// so the two ways of reading "the gradient at a time" never disagree on a
// file that pypulseq itself would write.
//
// Axes are 0 = x, 1 = y, 2 = z. Filters are 0 = tau1 (u = x), 1 = tau2
// (u = |x|), 2 = tau3 (u = x), matching hw.a1/a2/a3 of the SAFE model. Most
// per-axis, per-filter data (the 9 alphas, the 9 c's, the 9 a's) is kept as
// flat Float64Array(9) indexed `axis * 3 + filter`, and the 3 axis factors
// (`1 / stim_limit * g_scale`) as Float64Array(3) indexed by axis, so that
// `exactView`'s inner loop never reads an object property for each sample
// (section 4.3 of the plan; the prototype's loop read `model.hw[axis]` and
// closed over an `emit` callback for each sample, which this module does
// not do).
const PnsLanes = (() => {
  const AXES = ["x", "y", "z"];
  const GROUP_BLOCKS = 64; // blocks between two checkpoints
  const EXACT_MAX_S = 10.0; // the longest exact view (plan section 4.2, decision 13)
  const ZERO_H = [0, 0, 0];

  // ---- Per-event data (the README's section "Data layout of the model" in
  // the tag `archive/pns-lanes-prototype`, the item for each unique gradient
  // event): the samples g[j] (T/m) of one gradient event, for a
  // block of `n` samples starting where the event's own delay/offset times
  // are measured from (the block start). Linear interpolation between the
  // event's points (delay + offset[p], value[p] mT/m / 1000 * scale), 0
  // before the first point and after the last. `scale` is the file's
  // `pns.gradScale` (plan section 4.4, decision 14; 1.0 for a proton
  // sequence), passed in as a plain argument (a local, not an object
  // property read inside the loop). Sample times and point times are both
  // non-decreasing, so one sequential merge (not a binary search per
  // sample) computes all n samples in O(n + point count). Reads only
  // grad_delay, grad_n, grad_offset_at, grad_at, grad_offset, grad_value
  // (the tables this module needs).
  function _eventSamples(tables, dt, eventIdx, n, scale) {
    const idx = eventIdx - 1;
    const delay = tables.grad_delay[idx];
    const nPts = tables.grad_n[idx];
    const offAt = tables.grad_offset_at[idx];
    const valAt = tables.grad_at[idx];
    const offset = tables.grad_offset;
    const value = tables.grad_value;
    const g = new Float64Array(n);
    if (nPts === 0 || n === 0) return g; // no point, or a 0-sample block: all zero
    let p = 0;
    for (let j = 0; j < n; j++) {
      const t = (j + 0.5) * dt;
      while (p + 1 < nPts && delay + offset[offAt + p + 1] <= t) p++;
      const t0 = delay + offset[offAt + p];
      if (t < t0) { g[j] = 0; continue; }
      if (p + 1 >= nPts) {
        g[j] = t <= t0 ? value[valAt + p] / 1000 * scale : 0;
        continue;
      }
      const t1 = delay + offset[offAt + p + 1];
      const v0 = value[valAt + p] / 1000 * scale;
      const v1 = value[valAt + p + 1] / 1000 * scale;
      // The `while` above stops with t0 <= t < t1, so t1 > t0.
      g[j] = v0 + (v1 - v0) / (t1 - t0) * (t - t0);
    }
    return g;
  }

  // The zero-state response h[n - 1] of the three filters of one axis
  // (README "Block maps"), to one event's own samples g[0 .. n - 1]: h[0] =
  // 0, h[j] = c * h[j - 1] + alpha * u[j] for j = 1 .. n - 1, with u = x[j]
  // = (g[j] - g[j - 1]) / dt for filters 0 and 2, u = |x[j]| for filter 1.
  // This is the same recursion as the full filter, run from a zero state
  // over the inputs 1 .. n - 1 only (the boundary input x[0] is not part of
  // it: it depends on the previous block's last sample, so it is applied
  // separately by the caller through the block map's own boundary term).
  function _zeroStateResponse(model, axis, g, n) {
    if (n === 0) return ZERO_H;
    const invDt = 1 / model.dt;
    const base = axis * 3;
    const a0 = model.alpha[base], a1 = model.alpha[base + 1], a2 = model.alpha[base + 2];
    const c0 = model.c[base], c1 = model.c[base + 1], c2 = model.c[base + 2];
    let h0 = 0, h1 = 0, h2 = 0;
    let prev = g[0];
    for (let j = 1; j < n; j++) {
      const cur = g[j];
      const x = (cur - prev) * invDt;
      prev = cur;
      h0 = c0 * h0 + a0 * x;
      h1 = c1 * h1 + a1 * Math.abs(x);
      h2 = c2 * h2 + a2 * x;
    }
    return [h0, h1, h2];
  }

  // The cached per-event data for one (event, axis, n): {g, h}. `g` is the
  // event's own samples; `h` is [h_tau1, h_tau2, h_tau3](n - 1). A block
  // with no event on the axis never reaches this cache (the caller uses
  // g = 0, h = 0 directly). The cache key is a single number, not a string
  // (decode's bound check keeps `(n * 3 + axis) * (numGradEvents + 1) +
  // eventIdx` exact below 2^53).
  function _eventEntry(model, axis, eventIdx, n) {
    const key = (n * 3 + axis) * (model.numGradEvents + 1) + eventIdx;
    const cache = model._eventCache;
    let entry = cache.get(key);
    if (entry !== undefined) return entry;
    const g = _eventSamples(model.tables, model.dt, eventIdx, n, model.gradScale);
    const h = _zeroStateResponse(model, axis, g, n);
    entry = { g, h };
    cache.set(key, entry);
    return entry;
  }

  // c^n and c^(n - 1) for one filter, cached by n: the block map needs both
  // powers for every block, and the number of distinct block lengths in a
  // file is normally small, so this turns 2 Math.pow calls per block into a
  // cache hit for all but the first block of each length.
  function _powPair(cache, c, n) {
    let pair = cache.get(n);
    if (pair !== undefined) return pair;
    const cn = Math.pow(c, n);
    // n >= 1: `_applyBlockMap` returns first for n === 0.
    const cn1 = Math.pow(c, n - 1);
    pair = [cn, cn1];
    cache.set(n, pair);
    return pair;
  }

  // Applies the block map of one block to `state` (9 filter states, axis *
  // 3 + filter) and `lastG` (3 values, the last gradient sample of each
  // axis), in place. `eventIdx[axis]` is the dense event index of the block
  // on that axis (0 = no event). A block of n = 0 samples (a delay-raster
  // block with no gradient-raster samples) leaves everything unchanged: it
  // has no boundary sample and contributes no filter input.
  //
  // For one filter, the block map of a block of n samples takes the start
  // state s to the state after the block (the README's section "Block maps"
  // in the tag `archive/pns-lanes-prototype`):
  //   s_n = c^n * s + c^(n - 1) * alpha * u0 + h[n - 1]
  // with u0 the boundary input (x[0] = (g[0] - lastG) / dt, or its absolute
  // value for the filter of |x|) and h[n - 1] the zero-state response of the
  // event's own samples (`_zeroStateResponse`).
  function _applyBlockMap(model, n, eventIdx, state, lastG) {
    if (n === 0) return;
    const dt = model.dt;
    const alpha = model.alpha, c = model.c, powCache = model.powCache;
    for (let axis = 0; axis < 3; axis++) {
      const ev = eventIdx[axis];
      let g0, gLast, h;
      if (ev === 0) {
        g0 = 0; gLast = 0; h = ZERO_H;
      } else {
        const entry = _eventEntry(model, axis, ev, n);
        g0 = entry.g[0];
        gLast = entry.g[n - 1];
        h = entry.h;
      }
      const x0 = (g0 - lastG[axis]) / dt;
      const base = axis * 3;
      for (let f = 0; f < 3; f++) {
        const u0 = f === 1 ? Math.abs(x0) : x0;
        const idx = base + f;
        const pair = _powPair(powCache[idx], c[idx], n);
        const s = state[idx];
        state[idx] = pair[0] * s + pair[1] * alpha[idx] * u0 + h[f];
      }
      lastG[axis] = gLast;
    }
  }

  // ---- decode ----

  // `tables`: the decoded diagram tables, as `SeqLanes.decode` takes them.
  // Only duration_index, durations, gx, gy, gz, grad_delay, grad_n,
  // grad_offset_at, grad_at, grad_offset and grad_value are read; an unknown
  // or missing table is not refused here (`SeqLanes.decode` owns that
  // rule). `pns`: the file entry's `pns` object (plan section 4.4), with
  // its levels already decoded by the caller: {dtS, binSamples, hw: {x, y,
  // z: {tau1, tau2, tau3, a1, a2, a3, stim_limit, g_scale}}, levels: {min,
  // max}}. `pns.gradScale` (plan section 4.4, decision 14) defaults to 1.0
  // when the key is missing; every gradient sample is multiplied by it
  // (`_eventSamples`) before the SAFE model, so a non-proton sequence's PNS
  // agrees with Python's.
  function decode(tables, pns) {
    const dt = pns.dtS;
    const gradScale = pns.gradScale === undefined ? 1.0 : pns.gradScale;
    const numBlocks = tables.duration_index.length;
    const numGradEvents = tables.grad_n.length;

    // Per-axis, per-filter constants in flat typed arrays (module doc):
    // alpha, c = 1 - alpha, and the SAFE "a" weights, indexed axis * 3 +
    // filter; the axis factor 1 / stim_limit * g_scale, indexed by axis.
    const alpha = new Float64Array(9);
    const c = new Float64Array(9);
    const aCoef = new Float64Array(9);
    const axisFactor = new Float64Array(3);
    const dtMs = dt * 1000;
    for (let axis = 0; axis < 3; axis++) {
      const hwAxis = pns.hw[AXES[axis]];
      const taus = [hwAxis.tau1, hwAxis.tau2, hwAxis.tau3];
      const base = axis * 3;
      for (let f = 0; f < 3; f++) {
        const a = dtMs / (taus[f] + dtMs);
        alpha[base + f] = a;
        c[base + f] = 1 - a;
      }
      aCoef[base] = hwAxis.a1;
      aCoef[base + 1] = hwAxis.a2;
      aCoef[base + 2] = hwAxis.a3;
      axisFactor[axis] = (1 / hwAxis.stim_limit) * hwAxis.g_scale;
    }

    const powCache = [];
    for (let i = 0; i < 9; i++) powCache.push(new Map());

    const model = {
      numBlocks,
      dt,
      gradScale,
      groupBlocks: GROUP_BLOCKS,
      numGradEvents,
      alpha, c, aCoef, axisFactor, powCache,
      tables,
      _eventCache: new Map(),
    };

    // blockLen[i] = round(duration / dt), the number of gradient-raster
    // samples of block i. `onRaster` is false when any block's duration is
    // not within 1e-6 samples of a whole number: then `exactView` throws
    // and `lanesFor` never chooses the exact view.
    const blockLen = new Uint32Array(numBlocks);
    const numGroups = Math.ceil(numBlocks / GROUP_BLOCKS) || 1;
    const groupFirstSample = new Float64Array(numGroups);
    const checkpointState = new Float64Array(numGroups * 9);
    const checkpointLastG = new Float64Array(numGroups * 3);

    const state = new Float64Array(9);
    const lastG = new Float64Array(3);
    let sampleCursor = 0;
    let onRaster = true;
    let maxBlockLen = 0;
    const tb = tables;
    const eventIdx = [0, 0, 0];

    for (let i = 0; i < numBlocks; i++) {
      if (i % GROUP_BLOCKS === 0) {
        const g = i / GROUP_BLOCKS;
        groupFirstSample[g] = sampleCursor;
        checkpointState.set(state, g * 9);
        checkpointLastG.set(lastG, g * 3);
      }
      const duration = tb.durations[tb.duration_index[i]];
      const nExact = duration / dt;
      const n = Math.round(nExact);
      if (Math.abs(nExact - n) > 1e-6) onRaster = false;
      blockLen[i] = n;
      if (n > maxBlockLen) maxBlockLen = n;
      eventIdx[0] = tb.gx[i]; eventIdx[1] = tb.gy[i]; eventIdx[2] = tb.gz[i];
      _applyBlockMap(model, n, eventIdx, state, lastG);
      sampleCursor += n;
    }

    // The per-event cache key `(n * 3 + axis) * (numGradEvents + 1) +
    // eventIdx` must stay an exact integer (below 2^53): check the largest
    // key this file could ever ask for (the longest block, axis 2, the
    // largest dense event index) and refuse the file rather than silently
    // collide two cache entries.
    const maxKey = (maxBlockLen * 3 + 2) * (numGradEvents + 1) + numGradEvents;
    if (maxKey > Number.MAX_SAFE_INTEGER) {
      throw new Error(
        "PnsLanes.decode: the per-event cache key of this file would exceed 2^53");
    }

    model.blockLen = blockLen;
    model.numSamples = sampleCursor;
    model.numGroups = numGroups;
    model.groupFirstSample = groupFirstSample;
    model.checkpointState = checkpointState;
    model.checkpointLastG = checkpointLastG;
    model.onRaster = onRaster;
    model.levels = levels({ binSamples: pns.binSamples, min: pns.levels.min, max: pns.levels.max });
    return model;
  }

  // ---- levels (the pyramid, plan section 4.5) ----

  // Level 0 is the stored level itself (the same Float32Array objects, not
  // copies). Level L + 1 has ceil(len_L / 4) bins, each the minimum
  // (maximum) of up to 4 bins of level L, kept as Float32Array like level
  // 0. Stops after the first level of length 1, or at level 0 when it
  // already has length <= 1 (an empty file, or a file of one bin).
  function levels(stored) {
    const result = [{ binSamples: stored.binSamples, min: stored.min, max: stored.max }];
    let prevMin = stored.min, prevMax = stored.max, prevBinSamples = stored.binSamples;
    while (prevMin.length > 1) {
      const len = Math.ceil(prevMin.length / 4);
      const min = new Float32Array(len);
      const max = new Float32Array(len);
      for (let i = 0; i < len; i++) {
        const from = i * 4;
        const to = Math.min(prevMin.length, from + 4);
        let lo = prevMin[from], hi = prevMax[from];
        for (let j = from + 1; j < to; j++) {
          if (prevMin[j] < lo) lo = prevMin[j];
          if (prevMax[j] > hi) hi = prevMax[j];
        }
        min[i] = lo;
        max[i] = hi;
      }
      prevBinSamples *= 4;
      result.push({ binSamples: prevBinSamples, min, max });
      prevMin = min;
      prevMax = max;
    }
    return result;
  }

  // ---- exactView ----

  // The largest group index g with groupFirstSample[g] <= k (binary search:
  // groupFirstSample is non-decreasing).
  function _groupForSample(model, k) {
    const gfs = model.groupFirstSample;
    let lo = 0, hi = model.numGroups - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (gfs[mid] <= k) lo = mid; else hi = mid - 1;
    }
    return lo;
  }

  // The samples k with t0 <= (k + 0.5) * dt <= t1, as the smallest and
  // largest integer satisfying the inequality, corrected for float rounding
  // by nudging at most a couple of steps. Unchanged from the prototype.
  function sampleRangeFor(dt, numSamples, t0, t1) {
    if (numSamples === 0) return [0, -1];
    let k0 = Math.ceil(t0 / dt - 0.5);
    while (k0 < numSamples && (k0 + 0.5) * dt < t0) k0++;
    while (k0 > 0 && (k0 - 1 + 0.5) * dt >= t0) k0--;
    let k1 = Math.floor(t1 / dt - 0.5);
    while (k1 >= 0 && (k1 + 0.5) * dt > t1) k1--;
    while (k1 + 1 < numSamples && (k1 + 1 + 0.5) * dt <= t1) k1++;
    if (k0 < 0) k0 = 0;
    if (k1 > numSamples - 1) k1 = numSamples - 1;
    return [k0, k1];
  }

  // The exact PNS of the samples k with t0 <= (k + 0.5) * dt <= t1 (as the
  // README's section "Interface of `pns_lanes.js`" in the tag
  // `archive/pns-lanes-prototype` has it). Starts from the checkpoint of the
  // group before the view, applies block maps (not per-sample recursion) up
  // to the block that holds the first sample in range, then runs the
  // per-sample recursion from there by hand (not through a callback),
  // emitting only the samples in range, and stops as soon as the range is
  // covered.
  //
  // All per-axis, per-filter constants are read out of the model's typed
  // arrays into local variables once, before either loop, and the running
  // filter states and last gradient samples are kept in local variables
  // (not array slots) through the per-sample loop: nothing in that loop
  // reads an object property or a Map, and nothing calls a function once
  // for each sample (module doc, plan section 4.3, item 1).
  function exactView(model, t0, t1, bins) {
    if (!model.onRaster) {
      throw new Error("PnsLanes.exactView: the file is not on the gradient raster");
    }
    const dt = model.dt;
    const [k0, k1] = sampleRangeFor(dt, model.numSamples, t0, t1);
    const count = k1 - k0 + 1;
    const kind = count <= 2 * bins ? "samples" : "bins";
    if (count <= 0) {
      return { kind: "samples", t: new Float64Array(0), total: new Float64Array(0) };
    }

    const g0 = _groupForSample(model, k0);
    const state = model.checkpointState.slice(g0 * 9, g0 * 9 + 9);
    const lastG = model.checkpointLastG.slice(g0 * 3, g0 * 3 + 3);
    const tb = model.tables;
    const eventIdx = [0, 0, 0];
    const numBlocks = model.numBlocks;

    let sampleCursor = model.groupFirstSample[g0];
    let i = g0 * model.groupBlocks;

    // Phase 1: blocks entirely before k0 skip forward with the block map
    // only (no samples generated), same as the decode scan.
    for (; i < numBlocks; i++) {
      const n = model.blockLen[i];
      if (sampleCursor + n <= k0) {
        eventIdx[0] = tb.gx[i]; eventIdx[1] = tb.gy[i]; eventIdx[2] = tb.gz[i];
        _applyBlockMap(model, n, eventIdx, state, lastG);
        sampleCursor += n;
        continue;
      }
      break;
    }

    const span = t1 - t0;
    let outT, outTotal, edges, minArr, maxArr;
    if (kind === "samples") {
      outT = new Float64Array(count);
      outTotal = new Float64Array(count);
    } else {
      edges = new Float64Array(bins + 1);
      for (let k = 0; k <= bins; k++) edges[k] = t0 + (span * k) / bins;
      minArr = new Float64Array(bins).fill(Infinity);
      maxArr = new Float64Array(bins).fill(-Infinity);
    }

    // Phase 2: the per-sample recursion, from block g0's checkpoint (moved
    // forward by phase 1) to the block that covers k1. Every per-axis
    // constant is a local variable, and the running state is 9 + 3 local
    // variables, not array or object reads.
    const alpha = model.alpha, c = model.c, aCoef = model.aCoef, axisFactor = model.axisFactor;
    const alphaX1 = alpha[0], alphaX2 = alpha[1], alphaX3 = alpha[2];
    const alphaY1 = alpha[3], alphaY2 = alpha[4], alphaY3 = alpha[5];
    const alphaZ1 = alpha[6], alphaZ2 = alpha[7], alphaZ3 = alpha[8];
    const cX1 = c[0], cX2 = c[1], cX3 = c[2];
    const cY1 = c[3], cY2 = c[4], cY3 = c[5];
    const cZ1 = c[6], cZ2 = c[7], cZ3 = c[8];
    const aX1 = aCoef[0], aX2 = aCoef[1], aX3 = aCoef[2];
    const aY1 = aCoef[3], aY2 = aCoef[4], aY3 = aCoef[5];
    const aZ1 = aCoef[6], aZ2 = aCoef[7], aZ3 = aCoef[8];
    const fX = axisFactor[0], fY = axisFactor[1], fZ = axisFactor[2];
    const invDt = 1 / dt;

    let sX1 = state[0], sX2 = state[1], sX3 = state[2];
    let sY1 = state[3], sY2 = state[4], sY3 = state[5];
    let sZ1 = state[6], sZ2 = state[7], sZ3 = state[8];
    let lastGX = lastG[0], lastGY = lastG[1], lastGZ = lastG[2];

    let out = 0;
    for (; i < numBlocks; i++) {
      const n = model.blockLen[i];
      const evX = tb.gx[i], evY = tb.gy[i], evZ = tb.gz[i];
      const gX = evX === 0 ? null : _eventEntry(model, 0, evX, n).g;
      const gY = evY === 0 ? null : _eventEntry(model, 1, evY, n).g;
      const gZ = evZ === 0 ? null : _eventEntry(model, 2, evZ, n).g;
      for (let j = 0; j < n; j++) {
        const k = sampleCursor + j;
        const curX = gX === null ? 0 : gX[j];
        const curY = gY === null ? 0 : gY[j];
        const curZ = gZ === null ? 0 : gZ[j];

        const xX = (curX - lastGX) * invDt; lastGX = curX;
        const y1X = alphaX1 * xX + cX1 * sX1;
        const y2X = alphaX2 * Math.abs(xX) + cX2 * sX2;
        const y3X = alphaX3 * xX + cX3 * sX3;
        sX1 = y1X; sX2 = y2X; sX3 = y3X;
        const px = (aX1 * Math.abs(y1X) + aX2 * y2X + aX3 * Math.abs(y3X)) * fX;

        const xY = (curY - lastGY) * invDt; lastGY = curY;
        const y1Y = alphaY1 * xY + cY1 * sY1;
        const y2Y = alphaY2 * Math.abs(xY) + cY2 * sY2;
        const y3Y = alphaY3 * xY + cY3 * sY3;
        sY1 = y1Y; sY2 = y2Y; sY3 = y3Y;
        const py = (aY1 * Math.abs(y1Y) + aY2 * y2Y + aY3 * Math.abs(y3Y)) * fY;

        const xZ = (curZ - lastGZ) * invDt; lastGZ = curZ;
        const y1Z = alphaZ1 * xZ + cZ1 * sZ1;
        const y2Z = alphaZ2 * Math.abs(xZ) + cZ2 * sZ2;
        const y3Z = alphaZ3 * xZ + cZ3 * sZ3;
        sZ1 = y1Z; sZ2 = y2Z; sZ3 = y3Z;
        const pz = (aZ1 * Math.abs(y1Z) + aZ2 * y2Z + aZ3 * Math.abs(y3Z)) * fZ;

        if (k < k0 || k > k1) continue;
        const total = Math.sqrt(px * px + py * py + pz * pz);
        if (kind === "samples") {
          outT[out] = (k + 0.5) * dt;
          outTotal[out] = total;
          out++;
        } else {
          const tk = (k + 0.5) * dt;
          let bin = Math.floor(((tk - t0) / span) * bins);
          if (bin < 0) bin = 0;
          if (bin >= bins) bin = bins - 1;
          if (total < minArr[bin]) minArr[bin] = total;
          if (total > maxArr[bin]) maxArr[bin] = total;
        }
      }
      sampleCursor += n;
      if (sampleCursor > k1) break;
    }

    return kind === "samples"
      ? { kind: "samples", t: outT, total: outTotal }
      : { kind: "bins", edges, min: minArr, max: maxArr };
  }

  // ---- lanesFor ----

  // The zigzag segments of a minimum/maximum lane ([edge, min], [centre,
  // max] for each bin that has a value; a bin with no value ends the
  // current segment), reading a bin's [min, max] from `binAt(k)` (null when
  // the bin has no value). Used by both branches of `lanesFor` (the exact
  // "bins" kind and the pyramid). The layout is the one of
  // `SeqLanes.minMaxLanes`, so `laneChart` draws both alike. The points
  // are percent (`* 100`) and milliseconds (`* 1000`), not rounded here.
  function _zigzag(edges, bins, binAt) {
    const segments = [];
    let current = null;
    for (let k = 0; k < bins; k++) {
      const range = binAt(k);
      if (range === null) {
        if (current !== null) { segments.push(current); current = null; }
        continue;
      }
      if (current === null) current = [];
      const centre = edges[k] + (edges[k + 1] - edges[k]) / 2;
      current.push([edges[k] * 1000, range[0] * 100], [centre * 1000, range[1] * 100]);
    }
    if (current !== null) segments.push(current);
    return segments;
  }

  // The PNS lane for the view `viewMs` (ms) with `bins` plot columns
  // (plan section 4.5, item 1). `meta` is the lane object
  // without "segments" (id, title, unit, color, kind, domain, ticks,
  // tick_labels, ...), built by the card script (phase 4). Values in the
  // lane are percent (100 * fraction); times are ms. Each result also holds
  // `onRaster` (`model.onRaster`), which `statusText` reads.
  function lanesFor(model, meta, viewMs, bins) {
    const t0 = viewMs[0] / 1000, t1 = viewMs[1] / 1000;
    const span = t1 - t0;

    if (model.numSamples === 0) {
      // An empty file: no exact data and no stored level either.
      return {
        lane: { ...meta, segments: [] }, exact: true, binMs: null, gap: false,
        onRaster: model.onRaster,
      };
    }

    if (span <= EXACT_MAX_S && model.onRaster) {
      const view = exactView(model, t0, t1, bins);
      if (view.kind === "samples") {
        const segments = view.t.length === 0
          ? []
          : [Array.from(view.t, (tSec, idx) => [tSec * 1000, view.total[idx] * 100])];
        return {
          lane: { ...meta, segments }, exact: true, binMs: null, gap: false,
          onRaster: model.onRaster,
        };
      }
      const segments = _zigzag(view.edges, bins, k => {
        const hi = view.max[k];
        return hi === -Infinity ? null : [view.min[k], hi];
      });
      return {
        lane: { ...meta, segments, minmax: true }, exact: true, binMs: null, gap: false,
        onRaster: model.onRaster,
      };
    }

    // Item 2: the pyramid. The display bin is D = span / bins; take the
    // largest level L with B_L = binSamples_L * dt <= D / 2, so that no
    // peak is lost and a peak can move by at most one display bin.
    const D = span / bins;
    const levelsArr = model.levels;
    let chosen = -1;
    for (let level = levelsArr.length - 1; level >= 0; level--) {
      if (levelsArr[level].binSamples * model.dt <= D / 2) { chosen = level; break; }
    }
    // `gap`: even the stored level (level 0) has bins longer than D / 2 (the
    // gap of plan section 4.2), so each stored bin is wider than half a
    // display bin. It says only that; a file that is not on the raster
    // (`model.onRaster` false) has no exact view at any zoom, and
    // `result.onRaster` carries that to `statusText`.
    const gap = chosen === -1;
    const level = levelsArr[gap ? 0 : chosen];

    const binSamplesL = level.binSamples;
    const B_L = binSamplesL * model.dt;
    const nLevelBins = level.min.length;
    const edges = new Float64Array(bins + 1);
    for (let k = 0; k <= bins; k++) edges[k] = t0 + (span * k) / bins;

    const segments = _zigzag(edges, bins, k => {
      let lo = Math.floor(edges[k] / B_L);
      let hi = Math.ceil(edges[k + 1] / B_L) - 1;
      if (lo < 0) lo = 0;
      if (hi > nLevelBins - 1) hi = nLevelBins - 1;
      if (hi < lo) return null;
      let mn = Infinity, mx = -Infinity;
      for (let m = lo; m <= hi; m++) {
        if (level.min[m] < mn) mn = level.min[m];
        if (level.max[m] > mx) mx = level.max[m];
      }
      return mx === -Infinity ? null : [mn, mx];
    });

    return {
      lane: { ...meta, segments, minmax: true },
      exact: false,
      binMs: B_L * 1000,
      gap,
      onRaster: model.onRaster,
    };
  }

  // ---- laneMeta (the diagram card's lane_chart.js hook, plan section 4.5) ----

  // The PNS lane object without "segments" (the `lane_meta` form of
  // `diagram_data.py`, so `laneChart` draws it like the other lanes):
  // `id`, `title`, `unit`, `color` (a token of `report.css`; "ink-2", as the
  // old PNS card's chart used), `kind`, `domain`, `ticks`, `tick_labels`,
  // `empty` (always false: this lane is built only for a file that has PNS
  // data) and `fill` (the tooltip's fallback value outside every segment, as
  // the gradient lanes have). `summary` is the file entry's `pns.summary`
  // (plan section 4.4): `peak` is a fraction of the limit (1 = 100%), so the
  // domain's `100 * summary.peak` is the peak in percent, and the domain is
  // never narrower than [0, 110] (`Math.max(100, ...)`), as the PNS card's
  // own chart had it.
  function laneMeta(summary) {
    const peakPercent = 100 * summary.peak;
    return {
      id: "pns",
      title: "PNS",
      unit: "%",
      color: "ink-2",
      kind: "line",
      domain: [0, 1.1 * Math.max(100, peakPercent)],
      ticks: [0, 100],
      tick_labels: ["0", "100"],
      empty: false,
      fill: 0.0,
    };
  }

  // A bin width (ms) with a sensible number of digits for the status line:
  // 3 significant figures, printed without a fixed decimal count (so 6.15,
  // 24.6, 393 and 1570 all read naturally, instead of a fixed
  // `toFixed` giving "393.000" or "6.150000").
  function _fmtBinMs(ms) {
    return Number(ms.toPrecision(3)).toString();
  }

  // The PNS part of the diagram's status line (plan section 4.5, item 2),
  // for one render's `lanesFor` result (`result`, the return of `lanesFor`
  // above). It reads `result.exact`, and for a result that is not exact
  // also `result.binMs`, `result.onRaster` and `result.gap`.
  // "Exact" or the bin width, then at most one more sentence: when the file
  // is not on the gradient raster, that there is no exact view at any zoom
  // (this replaces the "zoom in" sentence, which would be misleading: no
  // zoom ever reaches an exact view for such a file); otherwise, when
  // `result.gap` is set (even the stored level is coarser than half a
  // display bin, plan section 4.2), that zooming in to `EXACT_MAX_S` seconds
  // or less reaches the exact values.
  function statusText(result) {
    if (result.exact) return "PNS: exact.";
    let text = `PNS: minimum and maximum in bins of ${_fmtBinMs(result.binMs)} ms.`;
    if (!result.onRaster) {
      text += " The file is not on the gradient raster, so there is no exact view.";
    } else if (result.gap) {
      text += ` Zoom in to ${EXACT_MAX_S} s or less for the exact values.`;
    }
    return text;
  }

  return {
    EXACT_MAX_S,
    GROUP_BLOCKS,
    decode,
    levels,
    exactView,
    lanesFor,
    laneMeta,
    statusText,
    _internal: {
      eventEntry: _eventEntry,
      sampleRangeFor,
    },
  };
})();
if (typeof module !== "undefined") module.exports = PnsLanes;
