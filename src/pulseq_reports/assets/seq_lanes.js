// Turns the compressed block and event tables of one .seq file (section 4.2
// of docs/plans/diagram-event-table.md) into chart lanes, in the browser,
// with no DOM and no network. Pure functions, loaded after lane_chart.js in
// the page (page.py) and by `require` in tests/js, as in chart_math.js.
//
// `SeqLanes.decode` builds a model from the already-decompressed tables
// (typed arrays) and the lane metadata (`file_lanes` without `segments` and
// `windows`, section 4.1). `blockStart` and `blockAt` give block times
// without ever building a start-time array of length N (section 4.5).
// `exactLanes` and `pointsIn` give the exact view (section 4.4, item 1) and
// its point count. `minMaxLanes` gives the minimum/maximum view (section
// 4.4, item 2), from the group tree of section 4.5 that `decode` builds, and
// `lanesFor` chooses between the two views for each render (item 3).
const SeqLanes = (() => {
  const EXACT_POINT_LIMIT = 20000;
  const CHECKPOINT_BLOCKS = 1024; // section 4.2: one checkpoint for each 1024 blocks

  // The table names of section 4.2. `decode` accepts only these (and
  // requires all of them), so that a page with data for a later format
  // (section 4.6, for example a `rotation` table) fails loudly instead of
  // drawing wrong waveforms with an old script.
  const KNOWN_TABLES = [
    "duration_index", "durations", "checkpoints",
    "rf", "gx", "gy", "gz", "adc",
    "rf_delay", "rf_mag_n", "rf_mag_offset_at", "rf_mag_at", "rf_mag_offset", "rf_mag",
    "rf_phase_n", "rf_phase_offset_at", "rf_phase_at", "rf_phase_offset", "rf_phase",
    "grad_delay", "grad_n", "grad_offset_at", "grad_at", "grad_offset", "grad_value",
    "adc_delay", "adc_length",
  ];
  const KNOWN_TABLE_SET = new Set(KNOWN_TABLES);

  // The minimum, the maximum and (via `nArr`, unchanged) the point count of
  // each of `count` events, over the values at `valueArr[atArr[k] ..
  // atArr[k] + nArr[k] - 1]` (section 4.5). An event with no point (n === 0)
  // gets [Infinity, -Infinity], so that a plain Math.min/Math.max reduction
  // over several events ignores it on its own.
  function _eventStats(nArr, atArr, valueArr, count) {
    const min = new Float64Array(count);
    const max = new Float64Array(count);
    for (let k = 0; k < count; k++) {
      const n = nArr[k];
      if (n === 0) {
        min[k] = Infinity;
        max[k] = -Infinity;
        continue;
      }
      const at = atArr[k];
      let lo = valueArr[at], hi = valueArr[at];
      for (let p = 1; p < n; p++) {
        const v = valueArr[at + p];
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
      min[k] = lo;
      max[k] = hi;
    }
    return {min, max};
  }

  // Throws when the offsets of an event are not in time order. The
  // minimum/maximum view finds points inside an event by binary search on
  // its point times, which is correct only for offsets that never go down
  // (pypulseq gives them so: RF sample times, and the corner or sample
  // times of a gradient). An offset array that several events share is
  // checked one time.
  function _checkOffsetOrder(kind, nArr, offsetAtArr, offsetArr, count) {
    const checked = new Set();
    for (let k = 0; k < count; k++) {
      const n = nArr[k], at = offsetAtArr[k];
      const key = at * 4294967296 + n;
      if (checked.has(key)) continue;
      checked.add(key);
      for (let p = 1; p < n; p++) {
        if (!(offsetArr[at + p] >= offsetArr[at + p - 1])) {
          throw new Error(
            `SeqLanes.decode: the offsets of ${kind} event ${k + 1} are not in time order`);
        }
      }
    }
  }

  // `tables`: {name: TypedArray}, already decompressed (section 4.1's
  // "dtype"/"data" are decoded by the caller). `lanesMeta`: the six lane
  // objects of section 4.1 ("lanes"), without "segments" and "windows".
  // Returns a model: the block-table columns kept as the given typed arrays
  // (never expanded to a start-time array of length N), plus the values
  // this module computes once at decode time (the end of the file, the
  // last block with a duration above zero, and the per-event minimum,
  // maximum and point count of section 4.5).
  function decode(format, tables, lanesMeta) {
    if (format !== 1) {
      throw new Error(`SeqLanes.decode: unsupported format ${format} (only format 1 is known)`);
    }
    for (const name of Object.keys(tables)) {
      if (!KNOWN_TABLE_SET.has(name)) {
        throw new Error(`SeqLanes.decode: unknown table "${name}"`);
      }
    }
    for (const name of KNOWN_TABLES) {
      if (!(name in tables)) {
        throw new Error(`SeqLanes.decode: missing table "${name}"`);
      }
    }

    const tb = tables;
    const numBlocks = tb.duration_index.length;

    // The end of the file, the last block with a duration above zero, and
    // the start of each group of GROUP_BLOCKS blocks: the same sequential
    // sum as `waveforms._timed_blocks`/`duration_s`, one duration at a time,
    // from 0.0 (section 4.3). The Python checkpoints are that same sum, so
    // the running sum must equal each of them exactly; a difference means
    // that the tables are not consistent, and `decode` refuses them. The
    // group starts are then the same values that `blockStart` would get
    // from a checkpoint, and `blockStart` and `blockAt` walk at most
    // GROUP_BLOCKS - 1 durations from one, not 1023 from a checkpoint.
    const groupStart = new Float64Array(Math.ceil(numBlocks / GROUP_BLOCKS) || 1);
    let start = 0.0;
    let lastNonZeroBlock = -1;
    for (let i = 0; i < numBlocks; i++) {
      if (i % GROUP_BLOCKS === 0) groupStart[i / GROUP_BLOCKS] = start;
      if (i % CHECKPOINT_BLOCKS === 0 && tb.checkpoints[i / CHECKPOINT_BLOCKS] !== start) {
        throw new Error(
          `SeqLanes.decode: checkpoint ${i / CHECKPOINT_BLOCKS} is not the sum of the ` +
          "durations before it");
      }
      const duration = tb.durations[tb.duration_index[i]];
      if (duration > 0) lastNonZeroBlock = i;
      start += duration;
    }
    const durationS = start;

    const rfCount = tb.rf_delay.length;
    const gradCount = tb.grad_delay.length;
    const magStats = _eventStats(tb.rf_mag_n, tb.rf_mag_at, tb.rf_mag, rfCount);
    const phaseStats = _eventStats(tb.rf_phase_n, tb.rf_phase_at, tb.rf_phase, rfCount);
    const gradStats = _eventStats(tb.grad_n, tb.grad_at, tb.grad_value, gradCount);
    _checkOffsetOrder("RF magnitude", tb.rf_mag_n, tb.rf_mag_offset_at, tb.rf_mag_offset, rfCount);
    _checkOffsetOrder("RF phase", tb.rf_phase_n, tb.rf_phase_offset_at, tb.rf_phase_offset,
      rfCount);
    _checkOffsetOrder("gradient", tb.grad_n, tb.grad_offset_at, tb.grad_offset, gradCount);

    const model = {
      numBlocks,
      durationS,
      lastNonZeroBlock,
      groupStart,
      lanesMeta,
      tables: tb,
      rf: {
        count: rfCount,
        magMin: magStats.min, magMax: magStats.max,
        phaseMin: phaseStats.min, phaseMax: phaseStats.max,
      },
      grad: {count: gradCount, min: gradStats.min, max: gradStats.max},
      // The min/max pyramid of each value pool, by pool name, built on the
      // first render that needs it (`_poolMinMax`).
      pyramids: {},
    };
    model.groups = _buildGroups(model);
    return model;
  }

  // ---- The groups and the tree over them (section 4.5) ----

  // 64 blocks in each group. A zoomed-out render must find the minimum and
  // the maximum of millions of blocks in each of about 800 bins, so it can
  // not walk the blocks. It reads whole groups from a tree instead, and
  // touches single blocks only in the two groups that a bin's edges cut.
  const GROUP_BLOCKS = 64;

  // The lanes that carry values (the ADC gate is counted separately).
  const VALUE_LANES = ["rf_mag", "rf_phase", "gx", "gy", "gz"];

  // The minimum and the maximum of one block on one value lane, or null
  // when the block has no event on that lane. Both come from the per-event
  // values that `decode` computed, so this never expands a point.
  function _blockRange(model, i, laneId) {
    const tb = model.tables;
    if (laneId === "rf_mag" || laneId === "rf_phase") {
      const k = tb.rf[i];
      if (k === 0) return null;
      const n = laneId === "rf_mag" ? tb.rf_mag_n[k - 1] : tb.rf_phase_n[k - 1];
      if (n === 0) return null;
      return laneId === "rf_mag"
        ? [model.rf.magMin[k - 1], model.rf.magMax[k - 1]]
        : [model.rf.phaseMin[k - 1], model.rf.phaseMax[k - 1]];
    }
    const k = tb[laneId][i];
    if (k === 0 || tb.grad_n[k - 1] === 0) return null;
    return [model.grad.min[k - 1], model.grad.max[k - 1]];
  }

  // The number of points that block `i` contributes to `pointsIn`.
  function _blockPoints(model, i) {
    const tb = model.tables;
    let count = 0;
    const rfK = tb.rf[i];
    if (rfK !== 0) count += tb.rf_mag_n[rfK - 1] + tb.rf_phase_n[rfK - 1];
    for (const axis of ["gx", "gy", "gz"]) {
      const gK = tb[axis][i];
      if (gK !== 0) count += tb.grad_n[gK - 1];
    }
    if (tb.adc[i] !== 0) count += 2;
    return count;
  }

  // The block-table column and the per-event minimum, maximum and point
  // count of one value lane, resolved one time. The inner loops below then
  // read typed arrays only: no per-block function call, no lane name
  // comparison and no allocation, which is what keeps a whole-file render
  // inside its budget.
  function _laneArrays(model, laneId) {
    const tb = model.tables;
    if (laneId === "rf_mag") {
      return {col: tb.rf, n: tb.rf_mag_n, min: model.rf.magMin, max: model.rf.magMax};
    }
    if (laneId === "rf_phase") {
      return {col: tb.rf, n: tb.rf_phase_n, min: model.rf.phaseMin, max: model.rf.phaseMax};
    }
    return {col: tb[laneId], n: tb.grad_n, min: model.grad.min, max: model.grad.max};
  }

  // An iterative segment tree over the group minima or maxima. Leaves sit
  // at [n, 2n); node j holds the extreme of its two children. `query(lo,
  // hi)` combines [lo, hi) in O(log n). The comparison is written out for
  // the minimum and for the maximum rather than taken as a function, so
  // the query does not make an indirect call at each level. This layout
  // needs no power-of-two padding, so it costs 2n entries, not the
  // n log n of a sparse table (25 MB against 225 MB at 10^7 blocks).
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

  // The per-group summaries and the trees over them (section 4.5), built
  // once by `decode`. For each group and each value lane: the minimum, the
  // maximum and whether any block of the group has an event on that lane.
  // For each group: the number of points and whether any block has an ADC
  // window. The "has an event" and point counts are kept as prefix sums
  // over the groups, so a range total is O(1) and the previous or next
  // group with an event on a lane is a binary search, O(log N).
  function _buildGroups(model) {
    const N = model.numBlocks;
    const G = Math.ceil(N / GROUP_BLOCKS) || 1;
    const lanes = {};
    for (const laneId of VALUE_LANES) {
      const min = new Float64Array(G).fill(Infinity);
      const max = new Float64Array(G).fill(-Infinity);
      // hasCount[g] is the number of groups before g with an event on this
      // lane, so hasCount has G + 1 entries.
      const hasCount = new Uint32Array(G + 1);
      lanes[laneId] = {min, max, hasCount};
    }
    const pointsPrefix = new Float64Array(G + 1);
    const adcCount = new Uint32Array(G + 1);
    const laneCols = {};
    for (const laneId of VALUE_LANES) laneCols[laneId] = _laneArrays(model, laneId);

    for (let g = 0; g < G; g++) {
      const from = g * GROUP_BLOCKS;
      const to = Math.min(N, from + GROUP_BLOCKS);
      let groupPoints = 0;
      let groupAdc = 0;
      for (let i = from; i < to; i++) {
        groupPoints += _blockPoints(model, i);
        if (model.tables.adc[i] !== 0) groupAdc = 1;
        for (const laneId of VALUE_LANES) {
          const cols = laneCols[laneId];
          const k = cols.col[i];
          if (k === 0 || cols.n[k - 1] === 0) continue;
          const lane = lanes[laneId];
          const a = cols.min[k - 1], b = cols.max[k - 1];
          if (a < lane.min[g]) lane.min[g] = a;
          if (b > lane.max[g]) lane.max[g] = b;
        }
      }
      for (const laneId of VALUE_LANES) {
        const lane = lanes[laneId];
        const has = lane.max[g] > -Infinity ? 1 : 0;
        lane.hasCount[g + 1] = lane.hasCount[g] + has;
      }
      pointsPrefix[g + 1] = pointsPrefix[g] + groupPoints;
      adcCount[g + 1] = adcCount[g] + groupAdc;
    }

    const trees = {};
    for (const laneId of VALUE_LANES) {
      const lane = lanes[laneId];
      trees[laneId] = {
        min: _segTree(lane.min, G, true),
        max: _segTree(lane.max, G, false),
      };
    }
    return {count: G, lanes, trees, pointsPrefix, adcCount};
  }

  // The start (s) of block `i`, as the sequential sum from the start of its
  // group (section 4.3, with the group starts of `decode`, which equal the
  // checkpoints' sum): never a multiplication, never a cumulative array of
  // length N.
  function blockStart(model, i) {
    const tb = model.tables;
    const g = Math.floor(i / GROUP_BLOCKS);
    let s = model.groupStart[g];
    for (let j = g * GROUP_BLOCKS; j < i; j++) {
      s += tb.durations[tb.duration_index[j]];
    }
    return s;
  }

  // The index of the block with start <= t < start + duration. Blocks of
  // zero duration are never returned. For t at or past the end of the
  // file, the last block with a duration above zero. For t before the
  // start of the file, 0 (section 4.4, item 4).
  function blockAt(model, t) {
    return _blockAtStart(model, t)[0];
  }

  // `blockAt` and the start of that block, in one pass. Binary search over
  // the group starts for the group of the block, then a sequential scan of
  // at most GROUP_BLOCKS blocks: durations telescope with no gaps, so
  // every t in [0, durationS) falls in exactly one block with a duration
  // above zero, and that block is always in the group the search finds.
  // The start is the running sum of that scan, the same value as
  // `blockStart`.
  function _blockAtStart(model, t) {
    const N = model.numBlocks;
    if (N === 0 || t < 0) return [0, 0];
    if (t >= model.durationS) {
      const last = model.lastNonZeroBlock >= 0 ? model.lastNonZeroBlock : 0;
      return [last, blockStart(model, last)];
    }
    const tb = model.tables;
    const groupStart = model.groupStart;
    let lo = 0, hi = groupStart.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (groupStart[mid] <= t) lo = mid; else hi = mid - 1;
    }
    let i = lo * GROUP_BLOCKS;
    let start = groupStart[lo];
    const groupEnd = Math.min(N, (lo + 1) * GROUP_BLOCKS);
    while (i < groupEnd) {
      const duration = tb.durations[tb.duration_index[i]];
      if (duration > 0 && start <= t && t < start + duration) return [i, start];
      start += duration;
      i++;
    }
    // Unreachable when durations telescope with no gaps, as they always do
    // for a model built by `decode`. Kept as a defensive fallback.
    const j = Math.max(0, Math.min(N - 1, lo * GROUP_BLOCKS));
    return [j, blockStart(model, j)];
  }

  // Calls `fn(i, start, duration)` for each block `i` whose closed interval
  // [start, start + duration] overlaps [lo, hi] (both ends inclusive, so a
  // point exactly at lo or at hi is never missed), in play order. Starts
  // from `blockAt(model, lo)` and first walks back over any earlier blocks
  // that also overlap: the block before it when lo is exactly the start of
  // the block that `blockAt` gives (that earlier block's last point can be
  // exactly at lo), and any blocks of zero duration at the same instant.
  // Then it scans forward until a block starts after hi.
  function _forEachBlockInRange(model, lo, hi, fn) {
    const N = model.numBlocks;
    if (N === 0) return;
    const tb = model.tables;
    let i = Math.min(Math.max(blockAt(model, lo), 0), N - 1);
    let start = blockStart(model, i);
    while (i > 0) {
      const prevDur = tb.durations[tb.duration_index[i - 1]];
      // The earlier block's start comes from `blockStart`, never from
      // `start - prevDur`: subtraction is a different sequence of float64
      // operations from the forward sum that section 4.3 requires, and the
      // two differ often enough to move an emitted point (a short block
      // before a long one loses the short block's start almost entirely).
      const prevStart = blockStart(model, i - 1);
      if (prevStart + prevDur < lo || prevStart > hi) break;
      i--;
      start = prevStart;
    }
    for (; i < N; i++) {
      const duration = tb.durations[tb.duration_index[i]];
      if (start > hi) break;
      if (start + duration >= lo) fn(i, start, duration);
      start += duration;
    }
  }

  // The points `[t (s), value]` of one event, from its delay, offset and
  // value tables, for a block that starts at `start` (s): `(start + delay)
  // + offset`, in that order (section 4.3), so that the arithmetic is
  // bit-for-bit the same as `waveforms._block_events`.
  function _eventPoints(delayArr, nArr, offsetAtArr, atArr, offsetArr, valueArr, k, start) {
    const idx = k - 1;
    const n = nArr[idx];
    const offsetAt = offsetAtArr[idx];
    const at = atArr[idx];
    const base = start + delayArr[idx];
    const pts = new Array(n);
    for (let p = 0; p < n; p++) {
      pts[p] = [base + offsetArr[offsetAt + p], valueArr[at + p]];
    }
    return pts;
  }

  // The points that block `i` (starting at `start`) contributes to one
  // line lane ("rf_mag", "gx", "gy" or "gz"), or [] when the block has no
  // event on that lane.
  function _linePointsForBlock(model, i, start, laneId) {
    const tb = model.tables;
    if (laneId === "rf_mag") {
      const k = tb.rf[i];
      return k === 0
        ? []
        : _eventPoints(tb.rf_delay, tb.rf_mag_n, tb.rf_mag_offset_at, tb.rf_mag_at, tb.rf_mag_offset, tb.rf_mag, k, start);
    }
    const k = tb[laneId][i];
    return k === 0
      ? []
      : _eventPoints(tb.grad_delay, tb.grad_n, tb.grad_offset_at, tb.grad_at, tb.grad_offset, tb.grad_value, k, start);
  }

  // The RF phase points of block `i` (starting at `start`), or [] when the
  // block has no RF event or that event has no phase point kept (a pulse
  // with zero amplitude, section 4.4 item 1).
  function _rfPhasePoints(model, i, start) {
    const tb = model.tables;
    const k = tb.rf[i];
    return k === 0
      ? []
      : _eventPoints(tb.rf_delay, tb.rf_phase_n, tb.rf_phase_offset_at, tb.rf_phase_at, tb.rf_phase_offset, tb.rf_phase, k, start);
  }

  // The last point of the whole-file polyline of `laneId` with time <
  // `before`, searching block `fromBlock` (which starts at `fromStart`)
  // and, if needed, the blocks before it, down to block 0. null when there
  // is none (the caller then uses the zero point at time 0).
  //
  // Each earlier block's start is recomputed with `blockStart`, not by
  // subtracting durations out of a running total: subtraction is a
  // different sequence of float64 operations from the sequential sum
  // (`start += duration`, forward, from a checkpoint) that section 4.3
  // requires, and the two are not guaranteed to be bit-for-bit equal.
  function _prevLinePoint(model, laneId, fromBlock, fromStart, before) {
    let i = fromBlock, start = fromStart;
    while (i >= 0) {
      const pts = _linePointsForBlock(model, i, start, laneId);
      for (let p = pts.length - 1; p >= 0; p--) {
        if (pts[p][0] < before) return pts[p];
      }
      i--;
      if (i >= 0) start = blockStart(model, i);
    }
    return null;
  }

  // The first point of the whole-file polyline of `laneId` with time >
  // `after`, searching block `fromBlock` (which starts at `fromStart`)
  // and, if needed, the blocks after it, up to the last block. null when
  // there is none (the caller then uses the zero point at the end of the
  // file).
  function _nextLinePoint(model, laneId, fromBlock, fromStart, after) {
    const tb = model.tables;
    const N = model.numBlocks;
    let i = fromBlock, start = fromStart;
    while (i < N) {
      const pts = _linePointsForBlock(model, i, start, laneId);
      for (let p = 0; p < pts.length; p++) {
        if (pts[p][0] > after) return pts[p];
      }
      start += tb.durations[tb.duration_index[i]];
      i++;
    }
    return null;
  }

  // The points (s, value) of one line lane's single segment, restricted to
  // [t0, t1]: the in-range points of the whole-file polyline, the zero
  // point at time 0 when it is in range (else the last point before t0,
  // when one exists), and the zero point at the end of the file when it is
  // in range (else the first point after t1, when one exists). Section
  // 4.4, item 1; section 4.5, last two bullets (the two zero points belong
  // to no event; the model treats the first as a point of block 0 and the
  // last as a point of block N - 1, which is exactly what including them
  // through the same t0/t1 test as the real points does here).
  function _lineSegment(model, laneId, t0, t1) {
    const N = model.numBlocks;
    const durationS = model.durationS;
    const pts = [];
    _forEachBlockInRange(model, t0, t1, (i, start) => {
      for (const p of _linePointsForBlock(model, i, start, laneId)) {
        if (p[0] >= t0 && p[0] <= t1) pts.push(p);
      }
    });
    if (0 >= t0 && 0 <= t1) {
      pts.unshift([0, 0]);
    } else if (N > 0) {
      const a = Math.min(Math.max(blockAt(model, t0), 0), N - 1);
      const before = _prevLinePoint(model, laneId, a, blockStart(model, a), t0);
      pts.unshift(before || [0, 0]);
    }
    if (durationS >= t0 && durationS <= t1) {
      pts.push([durationS, 0]);
    } else if (N > 0) {
      const a = Math.min(Math.max(blockAt(model, t1), 0), N - 1);
      const after = _nextLinePoint(model, laneId, a, blockStart(model, a), t1);
      pts.push(after || [durationS, 0]);
    }
    return pts;
  }

  function _msPoints(pts) {
    return pts.map(([t, v]) => [t * 1000, v]);
  }

  function _lineLaneOutput(model, meta, t0, t1) {
    return {...meta, segments: [_msPoints(_lineSegment(model, meta.id, t0, t1))]};
  }

  // One segment for each RF pulse (each block with an RF event) that has a
  // phase point in [t0, t1], with all the phase points of that pulse. A
  // pulse with no phase point gives no segment (section 4.4, item 1).
  function _phaseLaneOutput(model, meta, t0, t1) {
    const segments = [];
    _forEachBlockInRange(model, t0, t1, (i, start) => {
      const pts = _rfPhasePoints(model, i, start);
      if (pts.length === 0) return;
      if (!pts.some(p => p[0] >= t0 && p[0] <= t1)) return;
      segments.push(_msPoints(pts));
    });
    return {...meta, segments};
  }

  // The ADC windows that overlap [t0, t1] (section 4.4, item 1).
  function _adcLaneOutput(model, meta, t0, t1) {
    const tb = model.tables;
    const windows = [];
    _forEachBlockInRange(model, t0, t1, (i, start) => {
      const k = tb.adc[i];
      if (k === 0) return;
      const idx = k - 1;
      const a0 = start + tb.adc_delay[idx];
      const a1 = a0 + tb.adc_length[idx];
      if (a1 >= t0 && a0 <= t1) windows.push([a0 * 1000, a1 * 1000]);
    });
    return {...meta, windows};
  }

  // The minimum and the maximum of one value lane over the blocks
  // [from, to] (both inclusive), without expanding a point: whole groups
  // come from the tree, and the blocks of the two partial groups at the
  // ends come one at a time from their event's own minimum and maximum.
  // Returns null when no block in the range has an event on the lane.
  function _rangeMinMax(model, laneId, from, to, lane) {
    const N = model.numBlocks;
    if (to < from || N === 0) return null;
    from = Math.max(0, from);
    to = Math.min(N - 1, to);
    const cols = lane || _laneArrays(model, laneId);
    const col = cols.col, cn = cols.n, emin = cols.min, emax = cols.max;
    const gFrom = Math.floor(from / GROUP_BLOCKS);
    const gTo = Math.floor(to / GROUP_BLOCKS);
    let lo = Infinity, hi = -Infinity;

    const scanFrom = gFrom === gTo ? from : from;
    const scanTo = gFrom === gTo ? to : (gFrom + 1) * GROUP_BLOCKS - 1;
    for (let i = scanFrom; i <= scanTo; i++) {
      const k = col[i];
      if (k === 0) continue;
      const idx = k - 1;
      if (cn[idx] === 0) continue;
      const a = emin[idx], b = emax[idx];
      if (a < lo) lo = a;
      if (b > hi) hi = b;
    }
    if (gFrom !== gTo) {
      for (let i = gTo * GROUP_BLOCKS; i <= to; i++) {
        const k = col[i];
        if (k === 0) continue;
        const idx = k - 1;
        if (cn[idx] === 0) continue;
        const a = emin[idx], b = emax[idx];
        if (a < lo) lo = a;
        if (b > hi) hi = b;
      }
      if (gTo - gFrom > 1) {
        const tree = model.groups.trees[laneId];
        const tLo = tree.min.query(gFrom + 1, gTo);
        const tHi = tree.max.query(gFrom + 1, gTo);
        if (tLo < lo) lo = tLo;
        if (tHi > hi) hi = tHi;
      }
    }
    return hi === -Infinity ? null : [lo, hi];
  }

  // The last group before `group` that has an event on `laneId`, or -1.
  // A binary search over the prefix counts, so it is O(log N) even when
  // the lane has no event for a long stretch of the file.
  function _prevGroupWithEvent(model, laneId, group) {
    const has = model.groups.lanes[laneId].hasCount;
    const target = has[Math.max(0, Math.min(group, model.groups.count))];
    if (target === 0) return -1;
    let lo = 0, hi = group;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (has[mid + 1] === target) hi = mid; else lo = mid + 1;
    }
    return lo;
  }

  // The first group at or after `group` that has an event on `laneId`, or
  // -1. Also a binary search over the prefix counts.
  function _nextGroupWithEvent(model, laneId, group) {
    const groups = model.groups;
    const has = groups.lanes[laneId].hasCount;
    const G = groups.count;
    if (group >= G) return -1;
    const base = has[group];
    if (has[G] === base) return -1;
    let lo = group, hi = G - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (has[mid + 1] > base) hi = mid; else lo = mid + 1;
    }
    return lo;
  }

  // The delay, offset and value tables of one lane's events, resolved one
  // time, so the edge search below reads typed arrays only.
  function _laneEvent(model, laneId) {
    const tb = model.tables;
    if (laneId === "rf_mag") {
      return {delay: tb.rf_delay, offsetAt: tb.rf_mag_offset_at, valueAt: tb.rf_mag_at,
        offset: tb.rf_mag_offset, value: tb.rf_mag, pool: "rf_mag"};
    }
    if (laneId === "rf_phase") {
      return {delay: tb.rf_delay, offsetAt: tb.rf_phase_offset_at, valueAt: tb.rf_phase_at,
        offset: tb.rf_phase_offset, value: tb.rf_phase, pool: "rf_phase"};
    }
    return {delay: tb.grad_delay, offsetAt: tb.grad_offset_at, valueAt: tb.grad_at,
      offset: tb.grad_offset, value: tb.grad_value, pool: "grad_value"};
  }

  // The first point `p` in [0, n) of an event whose time `base + offset[oAt
  // + p]` is >= t (lower bound), or > t (upper bound); `n` when there is
  // none. The offsets of an event never go down (`_checkOffsetOrder`), and
  // adding the same `base` keeps that order, so a binary search over the
  // point times is exact. The times are computed as everywhere else:
  // `(start + delay) + offset`, with `base = start + delay`.
  function _lowerBound(offset, oAt, n, base, t) {
    let lo = 0, hi = n;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (base + offset[oAt + mid] < t) lo = mid + 1; else hi = mid;
    }
    return lo;
  }

  function _upperBound(offset, oAt, n, base, t) {
    let lo = 0, hi = n;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (base + offset[oAt + mid] <= t) lo = mid + 1; else hi = mid;
    }
    return lo;
  }

  // A min/max pyramid over one value pool: level 0 holds the minimum and
  // the maximum of each 64 values of the pool, level 1 of each 64 entries
  // of level 0, and so on, up to a level of at most 64 entries. It costs
  // about 1/32 of the pool in extra float64 values. An event's points are
  // a contiguous range of its pool, so the extremes of any range of points
  // come from whole chunks of the highest levels that fit, plus exact scans
  // of at most 2 x 64 entries at each level: O(64 log n), whatever the
  // length of the event.
  const PYRAMID_CHUNK = 64;

  function _pyramid(values) {
    const levels = [];
    let mins = values, maxs = values;
    while (mins.length > PYRAMID_CHUNK) {
      const m = Math.ceil(mins.length / PYRAMID_CHUNK);
      const lo = new Float64Array(m), hi = new Float64Array(m);
      for (let c = 0; c < m; c++) {
        const from = c * PYRAMID_CHUNK;
        const to = Math.min(mins.length, from + PYRAMID_CHUNK);
        let a = mins[from], b = maxs[from];
        for (let j = from + 1; j < to; j++) {
          if (mins[j] < a) a = mins[j];
          if (maxs[j] > b) b = maxs[j];
        }
        lo[c] = a;
        hi[c] = b;
      }
      levels.push({min: lo, max: hi});
      mins = lo;
      maxs = hi;
    }
    return levels;
  }

  // Widens `out` ([min, max]) with the values `ev.value[lo .. hi - 1]` of
  // one pool, exactly. Short ranges are scanned; a longer range uses the
  // pool's pyramid, which is built on the first call that needs it and then
  // kept in `model.pyramids`.
  function _poolMinMax(model, ev, lo, hi, out) {
    let mins = ev.value, maxs = ev.value;
    if (hi - lo > 2 * PYRAMID_CHUNK) {
      let levels = model.pyramids[ev.pool];
      if (levels === undefined) levels = model.pyramids[ev.pool] = _pyramid(ev.value);
      for (let level = 0; hi - lo > 2 * PYRAMID_CHUNK && level < levels.length; level++) {
        const cLo = Math.ceil(lo / PYRAMID_CHUNK), cHi = Math.floor(hi / PYRAMID_CHUNK);
        for (let j = lo; j < cLo * PYRAMID_CHUNK; j++) {
          if (mins[j] < out[0]) out[0] = mins[j];
          if (maxs[j] > out[1]) out[1] = maxs[j];
        }
        for (let j = cHi * PYRAMID_CHUNK; j < hi; j++) {
          if (mins[j] < out[0]) out[0] = mins[j];
          if (maxs[j] > out[1]) out[1] = maxs[j];
        }
        lo = cLo;
        hi = cHi;
        mins = levels[level].min;
        maxs = levels[level].max;
      }
    }
    for (let j = lo; j < hi; j++) {
      if (mins[j] < out[0]) out[0] = mins[j];
      if (maxs[j] > out[1]) out[1] = maxs[j];
    }
  }

  // The value at time `e` of one RF phase pulse (event index `idx`, its
  // points starting at `base`), by linear interpolation over that pulse's
  // own points, or null when `e` is before its first point or after its
  // last (section 4.4, item 2: a phase edge value exists only inside one
  // pulse). On a point time, the value of the first point at that time, as
  // in `_edgeValue`.
  function _pulseValueAt(ev, cols, idx, base, e) {
    if (idx < 0) return null;
    const n = cols.n[idx], oAt = ev.offsetAt[idx], vAt = ev.valueAt[idx];
    const a = _lowerBound(ev.offset, oAt, n, base, e);
    if (a < n && base + ev.offset[oAt + a] === e) return ev.value[vAt + a];
    if (a === 0 || a === n) return null;
    const t1 = base + ev.offset[oAt + a - 1], t2 = base + ev.offset[oAt + a];
    const v1 = ev.value[vAt + a - 1], v2 = ev.value[vAt + a];
    return v1 + (v2 - v1) / (t2 - t1) * (e - t1);
  }

  // Narrows `state` to the last point at or before `t` and the first at or
  // after it, over the points that block `i` (starting at `start`)
  // contributes to one lane. It builds no array: a block with no event on
  // the lane costs one read, and a block with one reads its points
  // straight out of the pools. The point time is `(start + delay) +
  // offset`, in that order, as everywhere else (section 4.3).
  //
  // "Last" and "first" are in polyline order, also when several points
  // have the same time. A pypulseq RF magnitude event always ends with two
  // such points (the last sample, then the zero pad at the same offset),
  // and the polyline continues from the second one, so the point before
  // `t` is the LAST point at the largest time <= t, and the point after it
  // is the FIRST point at the smallest time >= t. The blocks are not
  // scanned in play order (the block that holds `t` comes first), so a tie
  // between blocks goes to the later block (before) or to the earlier
  // block (after). Inside a block, the upper bound minus one is the last
  // point at the largest time <= t, and the lower bound is the first point
  // at the smallest time >= t: O(log n) for an event of n points.
  function _narrowNeighbours(cols, ev, i, start, t, state) {
    const k = cols.col[i];
    if (k === 0) return;
    const idx = k - 1;
    const n = cols.n[idx];
    if (n === 0) return;
    const base = start + ev.delay[idx];
    const oAt = ev.offsetAt[idx], vAt = ev.valueAt[idx];
    const b = _upperBound(ev.offset, oAt, n, base, t) - 1;
    if (b >= 0) {
      const time = base + ev.offset[oAt + b];
      if (state.bt === null || time > state.bt || (time === state.bt && i >= state.bi)) {
        state.bt = time; state.bv = ev.value[vAt + b]; state.bi = i;
      }
    }
    const a = _lowerBound(ev.offset, oAt, n, base, t);
    if (a < n) {
      const time = base + ev.offset[oAt + a];
      if (state.at === null || time < state.at || (time === state.at && i < state.ai)) {
        state.at = time; state.av = ev.value[vAt + a]; state.ai = i;
      }
    }
  }

  // The value of one line lane's whole-file polyline at time `t` (s),
  // given the block that holds `t` and its start. The polyline runs from
  // the zero point at time 0 to the zero point at the end of the file,
  // straight between its points, so a value between two points is the
  // linear interpolation of `numpy.interp`, with the same formula (section
  // 4.4, item 2).
  //
  // Most edges of a zoomed-out view fall in a block with no event on the
  // lane, or in the gap after one, so the search usually has to look past
  // the block that holds `t`. It scans that block's group and, only if a
  // side is still missing, jumps straight to the previous or next group
  // that has an event on this lane (a binary search over the prefix
  // counts, section 4.5). A lane with a long gap between events therefore
  // costs O(log N + 64) for each edge, not a walk over the gap.
  function _edgeValue(model, laneId, cols, ev, t, at, atStart) {
    if (t <= 0 || t >= model.durationS) return 0;
    const tb = model.tables;
    const N = model.numBlocks;
    const state = {bt: null, bv: 0, bi: -1, at: null, av: 0, ai: -1};
    _narrowNeighbours(cols, ev, at, atStart, t, state);
    if (state.bt === null || state.at === null) {
      const g = Math.floor(at / GROUP_BLOCKS);
      const scanGroup = gg => {
        if (gg < 0) return;
        const from = gg * GROUP_BLOCKS;
        const to = Math.min(N, from + GROUP_BLOCKS);
        if (to <= from) return;
        let s = model.groupStart[gg];
        for (let i = from; i < to; i++) {
          if (i !== at) _narrowNeighbours(cols, ev, i, s, t, state);
          s += tb.durations[tb.duration_index[i]];
        }
      };
      scanGroup(g);
      if (state.bt === null) scanGroup(_prevGroupWithEvent(model, laneId, g));
      if (state.at === null) scanGroup(_nextGroupWithEvent(model, laneId, g + 1));
    }
    const lt = state.bt === null ? 0 : state.bt;
    const lv = state.bt === null ? 0 : state.bv;
    const ht = state.at === null ? model.durationS : state.at;
    const hv = state.at === null ? 0 : state.av;
    // `t` is exactly on a point time. With several points at that time,
    // the value is the first of them (`hv`), the value that the polyline
    // reaches from the left. The bin to the left of `t` reaches only that
    // value; the bin to the right holds all the points at `t` anyway.
    // (`numpy.interp` gives the last of them instead.)
    if (ht === lt) return hv;
    return lv + (hv - lv) / (ht - lt) * (t - lt);
  }

  // The exact chart lanes (file_lanes JSON form) of `model` for [t0, t1]
  // (s), in the order of `model.lanesMeta`. Times in the output are in ms
  // (`t * 1000`, at the output only, as section 4.3 requires); the values
  // themselves are never rounded, so a caller can require bit-for-bit
  // equality with the Python reference.
  function exactLanes(model, t0, t1) {
    return model.lanesMeta.map(meta => {
      if (meta.id === "adc") return _adcLaneOutput(model, meta, t0, t1);
      if (meta.id === "rf_phase") return _phaseLaneOutput(model, meta, t0, t1);
      return _lineLaneOutput(model, meta, t0, t1);
    });
  }

  // The first and the last block whose closed interval overlaps [lo, hi],
  // without walking the blocks between them.
  function _blockSpan(model, lo, hi) {
    const N = model.numBlocks;
    const tb = model.tables;
    let first = Math.min(Math.max(blockAt(model, lo), 0), N - 1);
    let start = blockStart(model, first);
    while (first > 0) {
      const prevDur = tb.durations[tb.duration_index[first - 1]];
      const prevStart = blockStart(model, first - 1);
      if (prevStart + prevDur < lo || prevStart > hi) break;
      first--;
      start = prevStart;
    }
    let last = Math.min(Math.max(blockAt(model, hi), 0), N - 1);
    // Blocks of zero duration at the same instant as `hi` still overlap it.
    let lastStart = blockStart(model, last);
    while (last + 1 < N) {
      const nextStart = lastStart + tb.durations[tb.duration_index[last]];
      if (nextStart > hi) break;
      last++;
      lastStart = nextStart;
    }
    return [first, last];
  }

  // The number of RF magnitude, RF phase and gradient points of the blocks
  // that overlap [t0, t1] (s), plus 2 for each ADC window: the size
  // `exactLanes` would give without the zero points and the neighbour
  // points (section 4.4, item 3).
  //
  // The whole groups between the two ends come from the prefix sums that
  // `decode` built, so this costs O(log N + 64) and not O(blocks in the
  // view). That matters because `lanesFor` calls this before every render
  // to choose between the exact and the minimum/maximum view: counting
  // block by block would make the choice itself as slow as the view it is
  // trying to avoid.
  function pointsIn(model, t0, t1) {
    const N = model.numBlocks;
    if (N === 0) return 0;
    const [first, last] = _blockSpan(model, t0, t1);
    const groups = model.groups;
    const gFirst = Math.floor(first / GROUP_BLOCKS);
    const gLast = Math.floor(last / GROUP_BLOCKS);
    let count = 0;
    if (gFirst === gLast) {
      for (let i = first; i <= last; i++) count += _blockPoints(model, i);
      return count;
    }
    for (let i = first; i < (gFirst + 1) * GROUP_BLOCKS; i++) count += _blockPoints(model, i);
    for (let i = gLast * GROUP_BLOCKS; i <= last; i++) count += _blockPoints(model, i);
    if (gLast - gFirst > 1) {
      count += groups.pointsPrefix[gLast] - groups.pointsPrefix[gFirst + 1];
    }
    return count;
  }

  // True when an ADC window overlaps the bin [e0, e1), given the blocks
  // that hold the bin's two edges. The blocks of the two groups at the
  // ends are checked one by one, because a window there can start before
  // the bin and reach into it, or start inside it and reach past its end.
  // The groups strictly between them are answered by the prefix count
  // alone: if any of them holds an ADC block, that block lies wholly
  // inside the bin, so a window starts inside the bin and the bin is on.
  // Without this, a bin of a whole-file view would walk every block it
  // spans, which is the whole file.
  function _adcOverlaps(model, e0, e1, isLastBin, first, last) {
    const N = model.numBlocks;
    if (N === 0) return false;
    const tb = model.tables;
    const groups = model.groups;
    const hit = (i, start) => {
      const k = tb.adc[i];
      if (k === 0) return false;
      const a0 = start + tb.adc_delay[k - 1];
      const a1 = a0 + tb.adc_length[k - 1];
      return isLastBin ? a1 >= e0 && a0 <= e1 : a1 >= e0 && a0 < e1;
    };
    // One block before the bin's first: its window can reach into the bin.
    const from = Math.max(0, first - 1);
    const gFrom = Math.floor(from / GROUP_BLOCKS);
    const gLast = Math.floor(last / GROUP_BLOCKS);
    const scan = (a, b) => {
      if (b < a) return false;
      let start = blockStart(model, a);
      for (let i = a; i <= b; i++) {
        if (hit(i, start)) return true;
        start += tb.durations[tb.duration_index[i]];
      }
      return false;
    };
    if (gFrom === gLast) return scan(from, last);
    if (scan(from, Math.min(N - 1, (gFrom + 1) * GROUP_BLOCKS - 1))) return true;
    if (scan(gLast * GROUP_BLOCKS, last)) return true;
    return gLast - gFrom > 1 && groups.adcCount[gLast] - groups.adcCount[gFrom + 1] > 0;
  }

  // The lanes of `model` for [t0, t1] (s) as the minimum and the maximum
  // in each of `bins` equal time bins (section 4.4, item 2). Each line
  // lane gets one segment of the pairs (bin start, minimum), (bin centre,
  // maximum). The RF phase lane starts a new segment after a bin with no
  // value. The ADC lane gets one window for each run of bins that an ADC
  // window overlaps. Every lane gets the key `minmax: true`, which tells
  // the chart's tooltip to show the range of the bin at the cursor
  // instead of interpolating the zigzag.
  //
  // The bin edges, and the block that holds each edge, are found one time
  // and shared by all six lanes. For each lane, the event of each edge's
  // block is found one time and used by the bins on both sides of it: a
  // bin reads only its own range of that event's points, found by binary
  // search, and takes their extremes from the pool's pyramid. The blocks
  // between two edges never expand a point: their minimum and maximum come
  // from the tree.
  function minMaxLanes(model, t0, t1, bins) {
    const N = model.numBlocks;
    const span = t1 - t0;
    const edges = new Float64Array(bins + 1);
    const edgeBlock = new Int32Array(bins + 1);
    const edgeStart = new Float64Array(bins + 1);
    for (let k = 0; k <= bins; k++) {
      edges[k] = t0 + span * k / bins;
      if (N === 0) continue;
      const found = _blockAtStart(model, edges[k]);
      edgeBlock[k] = found[0];
      edgeStart[k] = found[1];
    }
    const inBin = (time, k) =>
      k === bins - 1 ? time >= edges[k] && time <= edges[k + 1]
                     : time >= edges[k] && time < edges[k + 1];

    return model.lanesMeta.map(meta => {
      if (meta.id === "adc") {
        const windows = [];
        let runFrom = -1;
        for (let k = 0; k < bins; k++) {
          const on = _adcOverlaps(model, edges[k], edges[k + 1], k === bins - 1,
            edgeBlock[k], edgeBlock[k + 1]);
          if (on && runFrom < 0) runFrom = k;
          if (!on && runFrom >= 0) {
            windows.push([edges[runFrom] * 1000, edges[k] * 1000]);
            runFrom = -1;
          }
        }
        if (runFrom >= 0) windows.push([edges[runFrom] * 1000, edges[bins] * 1000]);
        return {...meta, windows, minmax: true};
      }

      const isPhase = meta.id === "rf_phase";
      const laneCols = _laneArrays(model, meta.id);
      const laneEv = _laneEvent(model, meta.id);
      // The event of each edge's block on this lane (its index into the
      // event tables, or -1) and the time of its first point's offset 0
      // (`start + delay`). No point is copied out: the bins below find the
      // points they need by binary search and read the pools directly.
      const edgeIdx = new Int32Array(bins + 1).fill(-1);
      const edgeBase = new Float64Array(bins + 1);
      for (let k = 0; k <= bins; k++) {
        if (N === 0) continue;
        const ev = laneCols.col[edgeBlock[k]];
        if (ev === 0 || laneCols.n[ev - 1] === 0) continue;
        edgeIdx[k] = ev - 1;
        edgeBase[k] = edgeStart[k] + laneEv.delay[ev - 1];
      }
      // Each edge's value, computed one time and used by the bins on both
      // sides of it. On the phase lane an edge has a value only inside one
      // pulse, the pulse of the edge's own block.
      const edgeValue = new Array(bins + 1);
      for (let k = 0; k <= bins; k++) {
        edgeValue[k] = isPhase
          ? _pulseValueAt(laneEv, laneCols, edgeIdx[k], edgeBase[k], edges[k])
          : _edgeValue(model, meta.id, laneCols, laneEv, edges[k], edgeBlock[k], edgeStart[k]);
      }

      const segments = [];
      let current = null;
      const out = [Infinity, -Infinity];
      // The points of the event of edge `j` that are in bin `k`: a
      // contiguous index range, found by binary search with the same rule as
      // a point test (e_k <= t < e_(k+1), or <= e_(k+1) in the last bin).
      const takeEdgeEvent = (j, k) => {
        const idx = edgeIdx[j];
        if (idx < 0) return;
        const n = laneCols.n[idx], oAt = laneEv.offsetAt[idx], base = edgeBase[j];
        const from = _lowerBound(laneEv.offset, oAt, n, base, edges[k]);
        const to = k === bins - 1
          ? _upperBound(laneEv.offset, oAt, n, base, edges[k + 1])
          : _lowerBound(laneEv.offset, oAt, n, base, edges[k + 1]);
        if (to > from) {
          const vAt = laneEv.valueAt[idx];
          _poolMinMax(model, laneEv, vAt + from, vAt + to, out);
        }
      };
      const inBin = (time, k) =>
        k === bins - 1 ? time >= edges[k] && time <= edges[k + 1]
                       : time >= edges[k] && time < edges[k + 1];
      for (let k = 0; k < bins; k++) {
        out[0] = Infinity;
        out[1] = -Infinity;
        const take = v => { if (v < out[0]) out[0] = v; if (v > out[1]) out[1] = v; };
        // The two blocks the bin's edges cut: only their points inside the
        // bin count.
        takeEdgeEvent(k, k);
        if (edgeBlock[k + 1] !== edgeBlock[k]) takeEdgeEvent(k + 1, k);
        // Everything strictly between is wholly inside the bin.
        if (edgeBlock[k + 1] - edgeBlock[k] > 1) {
          const range = _rangeMinMax(model, meta.id, edgeBlock[k] + 1, edgeBlock[k + 1] - 1,
            laneCols);
          if (range !== null) { take(range[0]); take(range[1]); }
        }
        if (!isPhase) {
          // The two zero pad points belong to no event (section 4.5).
          if (inBin(0, k)) take(0);
          if (inBin(model.durationS, k)) take(0);
        }
        if (edgeValue[k] !== null) take(edgeValue[k]);
        if (edgeValue[k + 1] !== null) take(edgeValue[k + 1]);

        const lo = out[0], hi = out[1];
        if (hi === -Infinity) {
          if (current !== null) { segments.push(current); current = null; }
          continue;
        }
        if (current === null) current = [];
        const centre = edges[k] + (edges[k + 1] - edges[k]) / 2;
        current.push([edges[k] * 1000, lo], [centre * 1000, hi]);
      }
      if (current !== null) segments.push(current);
      return {...meta, segments, minmax: true};
    });
  }

  // {lanes, exact}: the lanes for `laneChart`, for the view `viewMs` (ms)
  // and `bins` plot columns. The exact points when the view holds few
  // enough of them, and the minimum and the maximum in each bin when it
  // does not (section 4.4, item 3). There is no pre-selected window and no
  // point budget for the file as a whole: every view of every file answers
  // for itself.
  function lanesFor(model, viewMs, bins) {
    const t0 = viewMs[0] / 1000, t1 = viewMs[1] / 1000;
    if (pointsIn(model, t0, t1) <= EXACT_POINT_LIMIT) {
      return {lanes: exactLanes(model, t0, t1), exact: true};
    }
    return {lanes: minMaxLanes(model, t0, t1, bins), exact: false};
  }

  return {decode, blockStart, blockAt, exactLanes, minMaxLanes, lanesFor, pointsIn,
    EXACT_POINT_LIMIT};
})();
if (typeof module !== "undefined") module.exports = SeqLanes;
