// Pure functions of the report charts, loaded before report.js in the page and by
// `require` in tests/js.
const ChartMath = (() => {
  const fmt = v => {
    if (v === null || v === undefined) return "\u2014";
    if (typeof v === "string") return v;
    if (Math.abs(v) < 5e-4) return "0";
    return Number(v.toPrecision(3)).toString().replace("-", "\u2212");
  };

  function niceTicks(lo, hi, n) {
    const raw = (hi - lo) / n, p = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 5, 10].map(m => m * p).find(s => s >= raw);
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) {
      out.push(Number(v.toFixed(9)));
    }
    return out;
  }

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
  // which is exact because centre is the midpoint of the bin. Returns null
  // when t is not covered by any bin: a gap between two segments, for
  // example an RF-phase pulse gap. A gate lane has no such gap; it is read
  // with valueAt instead.
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

  return {fmt, niceTicks, valueAt, minMaxAt, visiblePoints, clampView, zoomView, panView,
    dragView};
})();
if (typeof module !== "undefined") module.exports = ChartMath;
