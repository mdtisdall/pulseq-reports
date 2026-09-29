// Pure functions of the report charts, loaded first in the page (page.py), and by
// `require` in tests/js and in seq_lanes.js, pns_lanes.js and g_lanes.js under Node.
const ChartMath = (() => {
  // Returns v rounded to 3 significant digits, as text with no fixed decimal count (so 6.15,
  // 24.6, 393 and 1570 all read naturally, not "393.000" or "6.150000") and no trailing
  // zeros. A negative v keeps its ASCII minus sign. `fmt`, the |G| lane's tick label and
  // the PNS status line's bin width all use it.
  function sig3(v) {
    return Number(v.toPrecision(3)).toString();
  }

  // Returns the text of a value for display: an em dash (U+2014) for null or undefined, a
  // string as it is, "0" when |v| < 5e-4, and else v rounded to 3 significant digits (`sig3`)
  // with a minus sign (U+2212) for a negative v.
  const fmt = v => {
    if (v === null || v === undefined) return "\u2014";
    if (typeof v === "string") return v;
    if (Math.abs(v) < 5e-4) return "0";
    return sig3(v).replace("-", "\u2212");
  };

  // Returns the multiples of a step in [lo, hi], in increasing order. The step is the
  // smallest of 1, 2, 5 and 10 times a power of ten that is at least (hi - lo) / n, so a
  // whole number n gives at most n + 1 values. Each value is rounded to 9 decimals to drop
  // floating-point error.
  function niceTicks(lo, hi, n) {
    const raw = (hi - lo) / n, p = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 5, 10].map(m => m * p).find(s => s >= raw);
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) {
      out.push(Number(v.toFixed(9)));
    }
    return out;
  }

  // Returns the value of `lane` at `t`. For a gate lane, that is "on" when t is in one of
  // its `windows` and "off" when it is not. For another lane, that is the value in the
  // first of its `segments` that covers t, linear between the two points that bracket t,
  // and `lane.fill` where no segment covers t.
  function valueAt(lane, t) {
    if (lane.kind === "gate") {
      return lane.windows.some(([a, b]) => t >= a && t <= b) ? "on" : "off";
    }
    for (const seg of lane.segments) {
      if (seg.length && t >= seg[0][0] && t <= seg[seg.length - 1][0]) {
        let lo = 0, hi = seg.length - 1;
        while (hi - lo > 1) {
          const mid = (lo + hi) >> 1;
          if (seg[mid][0] <= t) lo = mid; else hi = mid;
        }
        const [t0, v0] = seg[lo], [t1, v1] = seg[hi];
        return t1 === t0 ? v1 : v0 + (v1 - v0) * (t - t0) / (t1 - t0);
      }
    }
    return lane.fill;
  }

  // Returns {min, max} of the minmax bin (section 4.4 item 2 of
  // docs/plans/diagram-event-table.md) that holds t, for a lane with the key
  // minmax: true. Such a lane's segments hold pairs of points (bin start,
  // minimum), (bin centre, maximum), one pair for each bin that has a
  // value. A bin's own right edge is not read from a following pair (there
  // may be none, or it may belong to the next, unrelated bin across a gap);
  // it is derived from the bin's own pair instead, as `2 * centre - start`,
  // which equals the bin's end up to rounding because centre is the
  // midpoint of the bin. Returns null when t is not covered by any bin: a
  // gap between two segments, for example an RF-phase pulse gap. A gate
  // lane has no such gap; it is read with valueAt instead.
  function minMaxAt(lane, t) {
    for (const seg of lane.segments) {
      for (let i = 0; i < seg.length; i += 2) {
        const [start, min] = seg[i];
        const [centre, max] = seg[i + 1];
        const hasNext = i + 2 < seg.length;
        const end = hasNext ? seg[i + 2][0] : 2 * centre - start;
        if (t >= start && (hasNext ? t < end : t <= end)) return {min, max};
      }
    }
    return null;
  }

  // Returns the points of one segment that must actually be drawn for the
  // view [lo, hi]: points outside the view are dropped (keeping one point
  // just past each edge so the edge-to-point line still draws), and when
  // there are far more points than pixels the rest are decimated into
  // `buckets` equal-width bins, keeping each bin's first, last, smallest and
  // largest value so peaks are never lost.
  function visiblePoints(points, lo, hi, buckets) {
    const n = points.length;
    if (n === 0) return [];
    if (points[n - 1][0] < lo || points[0][0] > hi) return [];

    // i0: largest index with x <= lo, or 0 if there is none.
    let i0 = 0;
    if (points[0][0] <= lo) {
      let a = 0, b = n - 1;
      while (a < b) {
        const mid = (a + b + 1) >> 1;
        if (points[mid][0] <= lo) a = mid; else b = mid - 1;
      }
      i0 = a;
    }

    // i1: smallest index with x >= hi, or the last index if there is none.
    let i1 = n - 1;
    if (points[n - 1][0] >= hi) {
      let a = 0, b = n - 1;
      while (a < b) {
        const mid = (a + b) >> 1;
        if (points[mid][0] >= hi) b = mid; else a = mid + 1;
      }
      i1 = a;
    }

    if (i1 - i0 + 1 <= 4 * buckets) return points.slice(i0, i1 + 1);

    // One pass over the interior points, tracking per-bin the first, last,
    // min-value and max-value indices without allocating an array per bin.
    const bins = new Array(buckets);
    const span = hi - lo;
    for (let i = i0 + 1; i < i1; i++) {
      const x = points[i][0], v = points[i][1];
      const bin = Math.min(buckets - 1, Math.max(0, Math.floor((x - lo) / span * buckets)));
      const b = bins[bin];
      if (!b) {
        bins[bin] = {firstIdx: i, lastIdx: i, minIdx: i, minVal: v, maxIdx: i, maxVal: v};
      } else {
        b.lastIdx = i;
        if (v < b.minVal) { b.minVal = v; b.minIdx = i; }
        if (v > b.maxVal) { b.maxVal = v; b.maxIdx = i; }
      }
    }

    const result = [points[i0]];
    for (let bin = 0; bin < buckets; bin++) {
      const b = bins[bin];
      if (!b) continue;
      const idxs = [b.firstIdx, b.minIdx, b.maxIdx, b.lastIdx].sort((x, y) => x - y);
      let prev = -1;
      for (const idx of idxs) {
        if (idx !== prev) result.push(points[idx]);
        prev = idx;
      }
    }
    result.push(points[i1]);
    return result;
  }

  // Returns [lo, hi] moved and, if needed, widened so it fits inside
  // `extent` at at least `minSpan` wide: a view at least as wide as the
  // extent (or a minSpan at least as wide as the extent) becomes the whole
  // extent; a view narrower than minSpan is widened about its own centre;
  // the (possibly widened) view is then shifted, with no change in width,
  // so it lies inside the extent.
  function clampView(view, extent, minSpan) {
    const [lo, hi] = view, [elo, ehi] = extent;
    const w = hi - lo, W = ehi - elo;
    if (w >= W || minSpan >= W) return [elo, ehi];
    let newLo = lo, newHi = hi;
    if (w < minSpan) {
      const c = (lo + hi) / 2;
      newLo = c - minSpan / 2;
      newHi = c + minSpan / 2;
    }
    if (newLo < elo) { newHi += elo - newLo; newLo = elo; }
    else if (newHi > ehi) { newLo -= newHi - ehi; newHi = ehi; }
    return [newLo, newHi];
  }

  // Returns [lo, hi] zoomed by `factor` (2 halves the width, 0.1 makes it 10
  // times wider) about `anchor` if it lies in the view, else about the
  // view's own centre, then clamped into `extent` at at least `minSpan`
  // wide.
  function zoomView(view, factor, anchor, extent, minSpan) {
    const [lo, hi] = view;
    const c = (anchor !== null && anchor >= lo && anchor <= hi) ? anchor : (lo + hi) / 2;
    const newW = (hi - lo) / factor;
    return clampView([c - newW / 2, c + newW / 2], extent, minSpan);
  }

  // Returns [lo, hi] shifted by `delta` with no change in width, then moved
  // inside `extent` (same rule as the last step of clampView); a view at
  // least as wide as the extent becomes the whole extent.
  function panView(view, delta, extent) {
    const [lo, hi] = view, [elo, ehi] = extent;
    const w = hi - lo, W = ehi - elo;
    if (w >= W) return [elo, ehi];
    let newLo = lo + delta, newHi = hi + delta;
    if (newLo < elo) { newHi += elo - newLo; newLo = elo; }
    else if (newHi > ehi) { newLo -= newHi - ehi; newHi = ehi; }
    return [newLo, newHi];
  }

  // Returns the view [min(x0, x1), max(x0, x1)] clamped into `extent` at at
  // least `minSpan` wide, or null when x0 and x1 are equal.
  function dragView(x0, x1, extent, minSpan) {
    if (x0 === x1) return null;
    return clampView([Math.min(x0, x1), Math.max(x0, x1)], extent, minSpan);
  }

  // Returns a Map from lane id to group id, from a `groups` list of
  // {id, laneIds, ...} (the `groups` option of `laneChart`, docs/plans/
  // diagram-lanes.md section 4.5 item 3). `laneChart` builds this once, when
  // the chart is made, and reads it on every render through `visibleLanes`.
  function laneGroupMap(groups) {
    const map = new Map();
    for (const group of groups) {
      for (const laneId of group.laneIds) map.set(laneId, group.id);
    }
    return map;
  }

  // Returns the lanes of `lanes` (each with an `id`) that either belong to no
  // group in `groupMap` (a lane no group claims is always drawn), or belong
  // to a group whose id is in `visibleGroupIds`. Used by `laneChart` to drop
  // the lanes of a hidden group, including one a `lanesFor` provider returns
  // despite being told which groups are visible.
  function visibleLanes(lanes, groupMap, visibleGroupIds) {
    return lanes.filter(lane => {
      const groupId = groupMap.get(lane.id);
      return groupId === undefined || visibleGroupIds.has(groupId);
    });
  }

  // Returns n RGB colors, linear between `stops` (a list of [r, g, b] triples, 0-255,
  // spaced equally along the ramp), as a flat Uint8ClampedArray of 3*n values: color k
  // is at ramp[3*k], ramp[3*k+1], ramp[3*k+2]. The first color is stops[0] and the last
  // is stops[stops.length - 1]. n = 1 gives stops[0] alone; n <= 0 gives an empty array.
  // Used by a map chart to build a canvas color lookup table from the CSS custom
  // properties of its color scale (report.css --map-seq-* and --map-div-*).
  function colorRamp(stops, n) {
    const out = new Uint8ClampedArray(Math.max(0, n) * 3);
    if (n <= 0) return out;
    const last = stops.length - 1;
    for (let k = 0; k < n; k++) {
      const t = n === 1 ? 0 : k / (n - 1) * last;
      const lo = Math.floor(t), hi = Math.min(lo + 1, last), f = t - lo;
      for (let c = 0; c < 3; c++) {
        out[k * 3 + c] = stops[lo][c] + (stops[hi][c] - stops[lo][c]) * f;
      }
    }
    return out;
  }

  // Returns the index (0 to n - 1) of `value` in an n-color ramp over [lo, hi] =
  // `domain`, clamped to the domain at each end. NaN returns -1, so a map chart can
  // draw it transparent instead of picking a color. A degenerate domain (lo === hi)
  // returns 0 for every value, since there is no range to place it in.
  function colorIndex(value, [lo, hi], n) {
    if (Number.isNaN(value)) return -1;
    if (hi === lo) return 0;
    const t = (value - lo) / (hi - lo);
    return Math.max(0, Math.min(n - 1, Math.round(t * (n - 1))));
  }

  // Returns the index (0 to n - 1) of the grid point of linspace(lo, hi, n) nearest to
  // `value`, clamped to [0, n - 1]. A degenerate domain (lo === hi) or a single grid
  // point (n <= 1) always returns 0. Used by a map chart to snap the hover cursor and
  // the arrow keys to the nearest grid point of an axis.
  function nearestIndex(lo, hi, n, value) {
    if (n <= 1 || hi === lo) return 0;
    return Math.max(0, Math.min(n - 1, Math.round((value - lo) / (hi - lo) * (n - 1))));
  }

  // An iterative segment tree over the group minima or maxima. Leaves sit at [n, 2n); node j
  // holds the extreme of its two children. `query(lo, hi)` combines [lo, hi) in O(log n).
  // The comparison is written out for the minimum and for the maximum rather than taken as a
  // function, so the query does not make an indirect call at each level. This layout needs no
  // power-of-two padding, so it costs 2n entries, not the n log n of a sparse table (25 MB
  // against 225 MB at 10^7 blocks). `seq_lanes.js` and `g_lanes.js` both build their group
  // trees with it.
  function segTree(values, n, isMin) {
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

  // Returns the zigzag segments of a minimum/maximum lane: the points [edge, min] and
  // [centre, max] for each bin that has a value, where the edge and the centre are in ms
  // (`edges` is in s). A bin with no value ends the current segment. `binAt(k)` returns the
  // [min, max] of bin k, already in the lane's unit (this function does not scale them), or
  // null when the bin has no value. The layout is the one of `SeqLanes.minMaxLanes`, so
  // `laneChart` draws every such lane alike. The points are not rounded.
  function minMaxSegments(edges, bins, binAt) {
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
      current.push([edges[k] * 1000, range[0]], [centre * 1000, range[1]]);
    }
    if (current !== null) segments.push(current);
    return segments;
  }

  return {fmt, sig3, segTree, minMaxSegments, niceTicks, valueAt, minMaxAt, visiblePoints,
    clampView, zoomView, panView, dragView, laneGroupMap, visibleLanes, colorRamp, colorIndex,
    nearestIndex};
})();
if (typeof module !== "undefined") module.exports = ChartMath;
