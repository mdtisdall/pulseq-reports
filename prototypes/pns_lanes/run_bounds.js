// Task 5 runner: correctness of pns_bounds.js against a brute force over the
// exact samples, and timings of minMaxView and of the whole-file peak.
//
//   node run_bounds.js check <tables.json>
//   node run_bounds.js time <tables.json> [--plain]
//
// <tables.json> comes from export_tables.py.

const fs = require("fs");
const path = require("path");
const zlib = require("zlib");
const PnsLanes = require(path.join(__dirname, "pns_lanes.js"));
const PnsBounds = require(path.join(__dirname, "pns_bounds.js"));

const CTORS = {uint8: Uint8Array, uint16: Uint16Array, uint32: Uint32Array, float64: Float64Array};
// Half a pixel of a 64 px lane whose scale is 1.1 × the limit (plan decision 2).
const EPS = 0.5 / 64 * 1.1;

function load(jsonPath) {
  const j = JSON.parse(fs.readFileSync(jsonPath, "utf8"));
  const tables = {};
  for (const [name, meta] of Object.entries(j.tables)) {
    const raw = zlib.gunzipSync(Buffer.from(meta.data, "base64"));
    const buf = new ArrayBuffer(raw.length);
    new Uint8Array(buf).set(raw);
    tables[name] = new CTORS[meta.dtype](buf);
  }
  return {tables, opts: j.opts, durationS: j.durationS};
}

const ms = () => Number(process.hrtime.bigint()) / 1e6;
const rssMb = () => Math.round(process.memoryUsage().rss / 2 ** 20);

function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

// Brute force: exact min/max of each lane in each bin from exactView.
function bruteMinMax(model, t0, t1, bins) {
  const v = PnsLanes.exactView(model, t0, t1);
  const out = {};
  for (const L of PnsBounds.LANES) {
    out[L] = {min: new Float64Array(bins).fill(NaN), max: new Float64Array(bins).fill(NaN)};
  }
  const edges = [];
  for (let k = 0; k <= bins; k++) edges.push(t0 + (t1 - t0) * k / bins);
  let b = 0;
  for (let i = 0; i < v.t.length; i++) {
    const t = v.t[i];
    while (b < bins - 1 && t >= edges[b + 1]) b++;
    const vals = {total: v.total[i], x: v.x[i], y: v.y[i], z: v.z[i]};
    for (const L of PnsBounds.LANES) {
      const o = out[L];
      if (!(vals[L] <= o.max[b])) o.max[b] = Number.isNaN(o.max[b]) ? vals[L] : Math.max(o.max[b], vals[L]);
      if (!(vals[L] >= o.min[b])) o.min[b] = Number.isNaN(o.min[b]) ? vals[L] : Math.min(o.min[b], vals[L]);
    }
  }
  return out;
}

function check(jsonPath) {
  const {tables, opts, durationS} = load(jsonPath);
  const model = PnsLanes.decode(tables, opts);
  const bm = PnsBounds.build(model);
  const views = [[0, durationS, 812], [0, durationS, 37], [0, durationS, 1],
    [durationS * 0.1234, durationS * 0.1734, 300], [durationS * 0.5, durationS * 0.5003, 97]];
  const results = [];
  for (const [t0, t1, bins] of views) {
    const bf = bruteMinMax(model, t0, t1, bins);
    for (const cache of [false, true]) {
      const q = PnsBounds.stateQuantumFor(model, EPS);
      const r = PnsBounds.minMaxView(model, bm, t0, t1, bins, EPS, {cache, stateQuantum: q});
      let worst = 0, nanMismatch = 0;
      for (const L of PnsBounds.LANES) {
        for (const kind of ["min", "max"]) {
          const a = r.lanes[L][kind], e = bf[L][kind];
          for (let b = 0; b < bins; b++) {
            if (Number.isNaN(a[b]) !== Number.isNaN(e[b])) { nanMismatch++; continue; }
            if (Number.isNaN(a[b])) continue;
            const d = Math.abs(a[b] - e[b]);
            if (d > worst) worst = d;
          }
        }
      }
      results.push({t0, t1, bins, cache, worstAbsDiff: worst, withinEps: worst <= EPS, nanMismatch,
        stats: r.stats});
    }
  }
  // Exact peak (eps = 0) against the plain recursion.
  const p = PnsBounds.peak(model, bm);
  const pp = PnsBounds.plainPeak(model);
  const out = {file: path.basename(jsonPath), eps: EPS, views: results,
    peak: {bounds: p.peak, plain: pp.peak, equal: p.peak === pp.peak,
      timeBounds: p.peakTimeS, timePlain: pp.peakTimeS, axisBounds: p.axisPeaks, axisPlain: pp.axisPeaks}};
  console.log(JSON.stringify(out, null, 1));
}

function time(jsonPath, plain) {
  let t = ms();
  const {tables, opts, durationS} = load(jsonPath);
  const tLoad = ms() - t;
  t = ms();
  const model = PnsLanes.decode(tables, opts);
  const tDecode = ms() - t;
  t = ms();
  const bm = PnsBounds.build(model);
  const tBuild = ms() - t;
  const rssAfterBuild = rssMb();
  const q = PnsBounds.stateQuantumFor(model, EPS);
  const res = {file: path.basename(jsonPath), numBlocks: model.numBlocks, numSamples: model.numSamples,
    durationS, loadMs: tLoad, decodeMs: tDecode, buildMs: tBuild, rssMbAfterBuild: rssAfterBuild};
  const stateCacheMap = new Map();
  for (const cache of [false, true]) {
    const o = {cache, stateQuantum: q, stateCacheMap};
    t = ms();
    const w = PnsBounds.minMaxView(model, bm, 0, durationS, 812, EPS, o);
    const whole = {ms: ms() - t, stats: w.stats};
    const r = rng(7);
    const times = [], stats = [];
    const nViews = Number(process.env.VIEWS || 100);
    for (let i = 0; i < nViews; i++) {
      // Views from 10 s (or a tenth of the file) to the whole file, log-uniform.
      const lo = Math.log(Math.min(10, durationS / 10)), hi = Math.log(durationS);
      const len = Math.exp(lo + (hi - lo) * r());
      const t0 = (durationS - len) * r();
      const s = ms();
      const v = PnsBounds.minMaxView(model, bm, t0, t0 + len, 812, EPS, o);
      times.push(ms() - s);
      stats.push(v.stats.samplesEvaluated);
    }
    times.sort((a, b) => a - b);
    const pick = f => times[Math.min(times.length - 1, Math.floor(f * times.length))];
    stats.sort((a, b) => a - b);
    res[cache ? "withCache" : "noCache"] = {
      wholeFile: whole,
      views: {n: times.length, median: pick(0.5), p95: pick(0.95), max: times[times.length - 1],
        samplesEvaluatedMedian: stats[Math.floor(stats.length / 2)], samplesEvaluatedP95: stats[Math.min(stats.length - 1, Math.floor(0.95 * stats.length))]},
    };
  }
  t = ms();
  const p = PnsBounds.peak(model, bm);
  res.peak = {ms: ms() - t, peak: p.peak, peakTimeS: p.peakTimeS, axisPeaks: p.axisPeaks, stats: p.stats};
  if (plain) {
    t = ms();
    const pp = PnsBounds.plainPeak(model);
    res.plainPeak = {ms: ms() - t, peak: pp.peak, peakTimeS: pp.peakTimeS, equal: pp.peak === p.peak,
      sameTime: pp.peakTimeS === p.peakTimeS};
  }
  res.rssMbEnd = rssMb();
  console.log(JSON.stringify(res, null, 1));
}

const [cmd, file, flag] = process.argv.slice(2);
if (cmd === "check") check(file);
else if (cmd === "time") time(file, flag === "--plain");
else { console.error("usage: node run_bounds.js check|time <tables.json> [--plain]"); process.exit(2); }
