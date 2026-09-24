// Prototype for docs/plans/pns-lanes-prototype.md, task 3 (see
// prototypes/pns_lanes/README.md for the model, the block-map formulas and
// this module's interface and data layout). NOT library code: this file is
// never merged (see the README).
//
// A pure module, like src/pulseq_reports/assets/seq_lanes.js: one global
// `PnsLanes`, `module.exports = PnsLanes` in Node, no DOM. `decode` builds a
// model from the decoded diagram tables (as SeqLanes.decode takes them) and
// the SAFE hardware/raster options; `exactView` answers the exact PNS
// samples of a time range from that model, using the block maps of README
// section "Block maps" (a scan with a checkpoint every `groupBlocks`
// blocks), not a per-sample recursion over the whole file.
//
// Axes are 0 = x, 1 = y, 2 = z; filters are 0 = tau1 (u = x), 1 = tau2
// (u = |x|), 2 = tau3 (u = x), matching hw.a1/a2/a3 and stim1/stim2/stim3 of
// the README's model table.
const PnsLanes = (() => {
  const AXES = ["x", "y", "z"];
  const AXIS_COLUMN = { x: "gx", y: "gy", z: "gz" };
  const GROUP_BLOCKS_DEFAULT = 64;

  // ---- Per-event data (README "Per-event data (computed one time for each
  // unique event)"): the samples g[j] (T/m) of one gradient event, for a
  // block of `n` samples starting where the event's own delay/offset times
  // are measured from (the block start). Linear interpolation between the
  // event's corner/sample points (delay + offset[p], value[p] mT/m / 1000),
  // 0 before the first point and after the last (README: "0 outside the
  // event"). Sample times and point times are both non-decreasing, so one
  // sequential merge (not a binary search per sample) computes all n
  // samples in O(n + point count).
  function _eventSamples(tables, dt, eventIdx, n) {
    const idx = eventIdx - 1;
    const delay = tables.grad_delay[idx];
    const nPts = tables.grad_n[idx];
    const offAt = tables.grad_offset_at[idx];
    const valAt = tables.grad_at[idx];
    const offset = tables.grad_offset;
    const value = tables.grad_value;
    const g = new Float64Array(n);
    if (nPts === 0) return g; // an event table entry with no point: all zero
    let p = 0;
    for (let j = 0; j < n; j++) {
      const t = (j + 0.5) * dt;
      while (p + 1 < nPts && delay + offset[offAt + p + 1] <= t) p++;
      const t0 = delay + offset[offAt + p];
      if (t < t0) { g[j] = 0; continue; }
      if (p + 1 >= nPts) {
        g[j] = t <= t0 ? value[valAt + p] / 1000 : 0;
        continue;
      }
      const t1 = delay + offset[offAt + p + 1];
      const v0 = value[valAt + p] / 1000;
      const v1 = value[valAt + p + 1] / 1000;
      g[j] = t1 === t0 ? v1 : v0 + (v1 - v0) / (t1 - t0) * (t - t0);
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
  // separately by the caller through B * x0 of the block map).
  function _zeroStateResponse(g, n, dt, alpha, c) {
    let h0 = 0, h1 = 0, h2 = 0;
    const invDt = 1 / dt;
    let prev = g[0];
    for (let j = 1; j < n; j++) {
      const cur = g[j];
      const x = (cur - prev) * invDt;
      prev = cur;
      h0 = c[0] * h0 + alpha[0] * x;
      h1 = c[1] * h1 + alpha[1] * Math.abs(x);
      h2 = c[2] * h2 + alpha[2] * x;
    }
    return [h0, h1, h2];
  }

  // The cached per-event data for one (event, axis, n): {g, h}. `g` is the
  // event's own samples (does not depend on axis, but is kept per axis
  // entry for simplicity: an event is rarely shared between axes). `h` is
  // [h_tau1, h_tau2, h_tau3](n - 1), computed once and reused by every block
  // that plays this event with this length on this axis. A block with no
  // event on the axis never reaches this cache (the caller uses g = 0, h =
  // 0 directly, section "Blocks with no event on an axis").
  function _eventEntry(model, axis, eventIdx, n) {
    const mapKey = eventIdx + "|" + axis + "|" + n;
    const cache = model._eventCache;
    let entry = cache.get(mapKey);
    if (entry !== undefined) return entry;
    const g = _eventSamples(model.tables, model.dt, eventIdx, n);
    const h = _zeroStateResponse(g, n, model.dt, model.filterAlpha[axis], model.filterC[axis]);
    entry = { g, h };
    cache.set(mapKey, entry);
    return entry;
  }

  // c^n and c^(n - 1) for one filter, cached by n: the block map (README
  // "Block maps") needs both powers for every block, and the number of
  // distinct block lengths in a file is normally small (one per distinct
  // block duration), so this turns 2 * 9 Math.pow calls per block into a
  // cache hit for all but the first block of each length.
  function _powPair(cache, c, n) {
    let pair = cache.get(n);
    if (pair !== undefined) return pair;
    const cn = Math.pow(c, n);
    const cn1 = n === 0 ? Math.pow(c, -1) : Math.pow(c, n - 1);
    pair = [cn, cn1];
    cache.set(n, pair);
    return pair;
  }

  // Applies the block map of one block to `state` (9 filter states, axis *
  // 3 + filter) and `lastG` (3 values, the last gradient sample of each
  // axis), in place. `eventIdx[axis]` is the dense event index of the block
  // on that axis (0 = no event). A block of n = 0 samples (a delay-raster
  // block with no gradient raster samples) leaves everything unchanged: it
  // has no boundary sample and contributes no filter input.
  function _applyBlockMap(model, n, eventIdx, state, lastG) {
    if (n === 0) return;
    const dt = model.dt;
    for (let a = 0; a < 3; a++) {
      const axis = AXES[a];
      const ev = eventIdx[a];
      let g0, gLast, h;
      if (ev === 0) {
        g0 = 0; gLast = 0; h = ZERO_H;
      } else {
        const entry = _eventEntry(model, axis, ev, n);
        g0 = entry.g[0];
        gLast = entry.g[n - 1];
        h = entry.h;
      }
      const x0 = (g0 - lastG[a]) / dt;
      const alpha = model.filterAlpha[axis], c = model.filterC[axis];
      const powCache = model.powCache[axis];
      const base = a * 3;
      for (let f = 0; f < 3; f++) {
        const u0 = f === 1 ? Math.abs(x0) : x0;
        const [cn, cn1] = _powPair(powCache[f], c[f], n);
        const s = state[base + f];
        state[base + f] = cn * s + cn1 * alpha[f] * u0 + h[f];
      }
      lastG[a] = gLast;
    }
  }
  const ZERO_H = [0, 0, 0];

  // The per-sample recursion (the plain method, README "Task 3", used both
  // by the tail of `exactView` and by `wholeFileRecursion`, the self-check
  // baseline of run_exact_selfcheck.js) for one block: advances `state` and
  // `lastG` in place, sample by sample, and calls
  // `emit(globalSampleIndex, total, px, py, pz)` for every sample of the
  // block. `sampleCursor` is the global sample index of the block's first
  // sample.
  function _runBlockSamples(model, n, eventIdx, state, lastG, sampleCursor, emit) {
    if (n === 0) return;
    const dt = model.dt;
    const g = [null, null, null];
    for (let a = 0; a < 3; a++) {
      const ev = eventIdx[a];
      g[a] = ev === 0 ? null : _eventEntry(model, AXES[a], ev, n).g;
    }
    const hw = model.hw;
    for (let j = 0; j < n; j++) {
      let px = 0, py = 0, pz = 0;
      for (let a = 0; a < 3; a++) {
        const garr = g[a];
        const cur = garr === null ? 0 : garr[j];
        const x = (cur - lastG[a]) / dt;
        lastG[a] = cur;
        const axis = AXES[a];
        const alpha = model.filterAlpha[axis], c = model.filterC[axis];
        const base = a * 3;
        const y0 = alpha[0] * x + c[0] * state[base];
        const y1 = alpha[1] * Math.abs(x) + c[1] * state[base + 1];
        const y2 = alpha[2] * x + c[2] * state[base + 2];
        state[base] = y0; state[base + 1] = y1; state[base + 2] = y2;
        const hwAxis = hw[axis];
        const p = (hwAxis.a1 * Math.abs(y0) + hwAxis.a2 * y1 + hwAxis.a3 * Math.abs(y2))
          / hwAxis.stim_limit * hwAxis.g_scale;
        if (a === 0) px = p; else if (a === 1) py = p; else pz = p;
      }
      const total = Math.sqrt(px * px + py * py + pz * pz);
      emit(sampleCursor + j, total, px, py, pz);
    }
  }

  // ---- decode ----

  // `tables`: the decoded diagram tables ({name: TypedArray}), as
  // SeqLanes.decode takes them (only the gradient-related columns are
  // read: duration_index, durations, gx, gy, gz, grad_delay, grad_n,
  // grad_offset_at, grad_at, grad_offset, grad_value; PNS does not depend
  // on RF or ADC). `opts`: {gradRasterS, gamma, hw: {x, y, z}, groupBlocks}.
  function decode(tables, opts) {
    const dt = opts.gradRasterS;
    const groupBlocks = opts.groupBlocks || GROUP_BLOCKS_DEFAULT;
    const numBlocks = tables.duration_index.length;

    const filterAlpha = {}, filterC = {}, powCache = {};
    const dtMs = dt * 1000;
    for (const axis of AXES) {
      const hwAxis = opts.hw[axis];
      const taus = [hwAxis.tau1, hwAxis.tau2, hwAxis.tau3];
      const alpha = taus.map(tau => dtMs / (tau + dtMs));
      const c = alpha.map(a => 1 - a);
      filterAlpha[axis] = alpha;
      filterC[axis] = c;
      powCache[axis] = [new Map(), new Map(), new Map()];
    }

    const model = {
      numBlocks,
      dt,
      groupBlocks,
      hw: opts.hw,
      gamma: opts.gamma,
      filterAlpha,
      filterC,
      powCache,
      tables,
      _eventCache: new Map(),
    };

    // blockLen[i] = round(duration / dt), the number of gradient-raster
    // samples of block i (README "Assumption ... each block holds n =
    // round(duration / dt) samples").
    const blockLen = new Uint32Array(numBlocks);
    const numGroups = Math.ceil(numBlocks / groupBlocks) || 1;
    const groupFirstSample = new Float64Array(numGroups);
    const checkpointState = new Float64Array(numGroups * 9);
    const checkpointLastG = new Float64Array(numGroups * 3);

    const state = new Float64Array(9);
    const lastG = new Float64Array(3);
    let sampleCursor = 0;
    const tb = tables;
    const eventIdx = [0, 0, 0];

    for (let i = 0; i < numBlocks; i++) {
      if (i % groupBlocks === 0) {
        const g = i / groupBlocks;
        groupFirstSample[g] = sampleCursor;
        checkpointState.set(state, g * 9);
        checkpointLastG.set(lastG, g * 3);
      }
      const duration = tb.durations[tb.duration_index[i]];
      const n = Math.round(duration / dt);
      blockLen[i] = n;
      eventIdx[0] = tb.gx[i]; eventIdx[1] = tb.gy[i]; eventIdx[2] = tb.gz[i];
      _applyBlockMap(model, n, eventIdx, state, lastG);
      sampleCursor += n;
    }

    model.blockLen = blockLen;
    model.numSamples = sampleCursor;
    model.numGroups = numGroups;
    model.groupFirstSample = groupFirstSample;
    model.checkpointState = checkpointState;
    model.checkpointLastG = checkpointLastG;
    return model;
  }

  // ---- exactView ----

  // The largest group index g with groupFirstSample[g] <= k (binary search:
  // groupFirstSample is non-decreasing, section "Data layout of the
  // model").
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
  // by nudging at most a couple of steps: the same formula and the same
  // correction are used by exactView and by run_exact_selfcheck.js's brute
  // force, so the two always select the same sample range (README/plan:
  // "They are the same model, so the difference is only float rounding
  // from the block maps").
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

  // The exact PNS samples k with t0 <= (k + 0.5) * dt <= t1 (README/plan
  // section 3.3, "exactView"). Starts from the checkpoint of the group
  // before the view, applies block maps (not per-sample recursion) up to
  // the block that holds the first sample in range, then runs the
  // per-sample recursion from there, emitting only the samples in range,
  // and stops as soon as the range is covered (it never processes a block
  // fully after the view).
  function exactView(model, t0, t1) {
    const dt = model.dt;
    const [k0, k1] = sampleRangeFor(dt, model.numSamples, t0, t1);
    const count = k1 - k0 + 1;
    const t = new Float64Array(Math.max(0, count));
    const total = new Float64Array(Math.max(0, count));
    const x = new Float64Array(Math.max(0, count));
    const y = new Float64Array(Math.max(0, count));
    const z = new Float64Array(Math.max(0, count));
    if (count <= 0 || model.numBlocks === 0) return { t, total, x, y, z };

    const g0 = _groupForSample(model, k0);
    const state = model.checkpointState.slice(g0 * 9, g0 * 9 + 9);
    const lastG = model.checkpointLastG.slice(g0 * 3, g0 * 3 + 3);
    const tb = model.tables;
    const eventIdx = [0, 0, 0];

    let sampleCursor = model.groupFirstSample[g0];
    let i = g0 * model.groupBlocks;
    const numBlocks = model.numBlocks;
    let out = 0;

    const emit = (k, tot, px, py, pz) => {
      if (k < k0 || k > k1) return;
      t[out] = (k + 0.5) * dt;
      total[out] = tot; x[out] = px; y[out] = py; z[out] = pz;
      out++;
    };

    for (; i < numBlocks; i++) {
      const n = model.blockLen[i];
      if (sampleCursor + n <= k0) {
        // Entirely before the view: skip forward with the block map only
        // (no samples generated), same as the decode scan.
        eventIdx[0] = tb.gx[i]; eventIdx[1] = tb.gy[i]; eventIdx[2] = tb.gz[i];
        _applyBlockMap(model, n, eventIdx, state, lastG);
        sampleCursor += n;
        continue;
      }
      eventIdx[0] = tb.gx[i]; eventIdx[1] = tb.gy[i]; eventIdx[2] = tb.gz[i];
      _runBlockSamples(model, n, eventIdx, state, lastG, sampleCursor, emit);
      sampleCursor += n;
      if (sampleCursor > k1) break;
    }
    return { t, total, x, y, z };
  }

  // ---- The plain method: the per-sample recursion over the whole file,
  // from a zero initial state (README consequence 1-2: the filter and the
  // boundary sample before the first real sample are both zero, from the
  // zero padding before the file). Used only by the self-check
  // (run_exact_selfcheck.js) as the brute-force baseline that exactView is
  // compared against; never used by exactView itself.
  //
  // Calls `onChunk({fromSample, count, t, total, x, y, z})` once per chunk
  // of up to `chunkSize` samples (default 65536), in play order, so a
  // caller can compare against another source or reduce (max/argmax)
  // without ever holding the whole file's samples in memory at once.
  function wholeFileRecursion(model, onChunk, chunkSize = 65536) {
    const dt = model.dt;
    const state = new Float64Array(9);
    const lastG = new Float64Array(3);
    const tb = model.tables;
    const eventIdx = [0, 0, 0];

    let chunkFrom = 0;
    let chunkT = new Float64Array(chunkSize);
    let chunkTotal = new Float64Array(chunkSize);
    let chunkX = new Float64Array(chunkSize);
    let chunkY = new Float64Array(chunkSize);
    let chunkZ = new Float64Array(chunkSize);
    let chunkLen = 0;

    const flush = () => {
      if (chunkLen === 0) return;
      onChunk({
        fromSample: chunkFrom,
        count: chunkLen,
        t: chunkT.subarray(0, chunkLen),
        total: chunkTotal.subarray(0, chunkLen),
        x: chunkX.subarray(0, chunkLen),
        y: chunkY.subarray(0, chunkLen),
        z: chunkZ.subarray(0, chunkLen),
      });
      chunkFrom += chunkLen;
      chunkLen = 0;
    };

    const emit = (k, tot, px, py, pz) => {
      if (chunkLen === chunkSize) flush();
      chunkT[chunkLen] = (k + 0.5) * dt;
      chunkTotal[chunkLen] = tot; chunkX[chunkLen] = px; chunkY[chunkLen] = py; chunkZ[chunkLen] = pz;
      chunkLen++;
    };

    let sampleCursor = 0;
    for (let i = 0; i < model.numBlocks; i++) {
      const n = model.blockLen ? model.blockLen[i]
        : Math.round(tb.durations[tb.duration_index[i]] / dt);
      eventIdx[0] = tb.gx[i]; eventIdx[1] = tb.gy[i]; eventIdx[2] = tb.gz[i];
      _runBlockSamples(model, n, eventIdx, state, lastG, sampleCursor, emit);
      sampleCursor += n;
    }
    flush();
  }

  return {
    decode, exactView, wholeFileRecursion, sampleRangeFor,
    // For pns_bounds.js (task 5): the block map, the per-sample recursion,
    // the per-event cache and the axis names.
    _internal: {AXES, applyBlockMap: _applyBlockMap, runBlockSamples: _runBlockSamples,
      eventEntry: _eventEntry, groupForSample: _groupForSample},
  };
})();
if (typeof module !== "undefined") module.exports = PnsLanes;
