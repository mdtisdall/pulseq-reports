// Task 4 of docs/plans/pns-lanes-prototype.md, question 2 (zoomed-in speed).
// Prototype code only; not part of the library, never merged (see README.md).
//
// Runs, in ONE fresh `node` process, for ONE already-exported tables JSON
// (export_tables.py's payload shape -- built once outside this script, per the
// task's instruction that the 10^7-block build is expensive and should be reused):
//
//   1. Decode: times PnsLanes.decode, and records process.memoryUsage() (rss,
//      heapUsed, arrayBuffers) right after it.
//   2. Speed: for each view length in VIEW_LENGTHS_S (1 ms, 10 ms, 100 ms, 1 s, 10 s),
//      100 exactView calls at random places (a fixed seed, derived from the
//      sequence name, so a re-run picks the same places), and the median, 95th
//      percentile and max of the per-call times. If the 10 s row's 95th percentile is
//      at most 50 ms, also times 30 s the same way. Reports the longest tested length
//      whose 95th percentile is at most 50 ms.
//
// Budget (plan section 4, "Limits of each run"): stop at 5 minutes or 8 GB RSS. This
// script's own decode() call is one synchronous, non-preemptible call -- plain Node
// cannot interrupt a running synchronous function or a blocked timer queue without
// worker_threads, so this script cannot abort *mid*-decode. Instead: (a) before each
// further phase (each view-length loop, and the optional 30 s length), it checks
// elapsed wall time and current RSS, and skips the rest of the run if either budget is
// already spent, recording that in the output; (b) the caller additionally runs this
// script under an external wall-clock timeout (`timeout 300 node run_speed.js ...`,
// matching the same budget), which is the only way to guarantee the 5-minute stop even
// if decode() itself never returns in time.
//
// Usage: node run_speed.js TABLES.json [OUT.json]
// With no OUT.json, the result JSON is printed to stdout.
"use strict";

const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

const PnsLanes = require(path.join(__dirname, "pns_lanes.js"));

const TIME_BUDGET_MS = 5 * 60 * 1000;
const RSS_BUDGET_BYTES = 8 * 1024 ** 3;
const VIEW_LENGTHS_S = [0.001, 0.01, 0.1, 1, 10];
const EXTRA_LENGTH_S = 30;
const SAMPLES_PER_LENGTH = 100;
const P95_BUDGET_MS = 50;

const TYPED_ARRAY_CTORS = {
  uint8: Uint8Array,
  uint16: Uint16Array,
  uint32: Uint32Array,
  float64: Float64Array,
};

// Duplicated from run_exact_selfcheck.js (read-only, no module.exports there) and
// from run_accuracy.js (this task's own sibling file), same reasoning as both: a
// small, self-contained helper is simpler than a shared module for a prototype this
// size.
function decodeTable(name, meta) {
  const Ctor = TYPED_ARRAY_CTORS[meta.dtype];
  if (!Ctor) throw new Error(`run_speed: table "${name}" has an unknown dtype "${meta.dtype}"`);
  const compressed = Buffer.from(meta.data, "base64");
  const raw = zlib.gunzipSync(compressed);
  const aligned = new ArrayBuffer(raw.length);
  new Uint8Array(aligned).set(raw);
  const arr = new Ctor(aligned);
  if (arr.length !== meta.length) {
    throw new Error(
      `run_speed: table "${name}" decoded to length ${arr.length}, expected ${meta.length}`);
  }
  return arr;
}

function loadTables(jsonPath) {
  const input = JSON.parse(fs.readFileSync(jsonPath, "utf8"));
  const tables = {};
  for (const [name, meta] of Object.entries(input.tables)) {
    tables[name] = decodeTable(name, meta);
  }
  return { input, tables };
}

// A small, fixed, dependency-free seeded PRNG (mulberry32), so "100 random places"
// is reproducible across runs without adding a dependency.
function mulberry32(seed) {
  let s = seed >>> 0;
  return function () {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hashString(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function memSnapshot() {
  const m = process.memoryUsage();
  return { rss: m.rss, heapUsed: m.heapUsed, arrayBuffers: m.arrayBuffers };
}

function quantileSorted(sorted, q) {
  const n = sorted.length;
  if (n === 0) return null;
  const idx = Math.min(n - 1, Math.max(0, Math.ceil(q * n) - 1));
  return sorted[idx];
}

function medianSorted(sorted) {
  const n = sorted.length;
  if (n === 0) return null;
  const mid = (n - 1) / 2;
  const lo = Math.floor(mid), hi = Math.ceil(mid);
  return (sorted[lo] + sorted[hi]) / 2;
}

// Times SAMPLES_PER_LENGTH exactView calls of length `lengthS`, at random start
// times drawn from `rng` (uniform in [0, max(0, durationS - lengthS)]; 0 when the
// file is shorter than the view). Returns {lengthS, medianMs, p95Ms, maxMs, samples}.
function timeViewsForLength(model, durationS, lengthS, rng) {
  const span = Math.max(0, durationS - lengthS);
  const timesMs = new Array(SAMPLES_PER_LENGTH);
  let totalSamplesEmitted = 0;
  for (let i = 0; i < SAMPLES_PER_LENGTH; i++) {
    const t0 = span > 0 ? rng() * span : 0;
    const t1 = t0 + lengthS;
    const start = process.hrtime.bigint();
    const view = PnsLanes.exactView(model, t0, t1);
    const ms = Number(process.hrtime.bigint() - start) / 1e6;
    timesMs[i] = ms;
    totalSamplesEmitted += view.t.length;
  }
  const sorted = timesMs.slice().sort((a, b) => a - b);
  return {
    lengthS,
    n: SAMPLES_PER_LENGTH,
    medianMs: medianSorted(sorted),
    p95Ms: quantileSorted(sorted, 0.95),
    maxMs: sorted[sorted.length - 1],
    minMs: sorted[0],
    meanSamplesPerView: totalSamplesEmitted / SAMPLES_PER_LENGTH,
  };
}

function budgetExceeded(startMs) {
  return Date.now() - startMs > TIME_BUDGET_MS || process.memoryUsage().rss > RSS_BUDGET_BYTES;
}

function main() {
  const [tablesPath, outPath] = process.argv.slice(2);
  if (!tablesPath) {
    throw new Error("usage: node run_speed.js TABLES.json [OUT.json]");
  }

  const startMs = Date.now();
  const { input, tables } = loadTables(tablesPath);

  const t0 = process.hrtime.bigint();
  const model = PnsLanes.decode(tables, input.opts);
  const decodeMs = Number(process.hrtime.bigint() - t0) / 1e6;
  const memAfterDecode = memSnapshot();
  const decodeOverBudget = budgetExceeded(startMs);

  const durationS = input.durationS;
  const sequenceName = input.sequenceName || path.basename(tablesPath);
  const rng = mulberry32(hashString(sequenceName) ^ 0xc0ffee);

  const lengths = [];
  let longestLengthSWithP95Under50ms = null;

  if (decodeOverBudget) {
    lengths.push({
      lengthS: null,
      skipped: true,
      reason: "decode() itself exceeded the 5 min / 8 GB RSS budget; no views timed",
    });
  } else {
    for (const L of VIEW_LENGTHS_S) {
      if (budgetExceeded(startMs)) {
        lengths.push({ lengthS: L, skipped: true, reason: "time/RSS budget exceeded before this length" });
        continue;
      }
      const row = timeViewsForLength(model, durationS, L, rng);
      lengths.push(row);
      if (row.p95Ms !== null && row.p95Ms <= P95_BUDGET_MS) longestLengthSWithP95Under50ms = L;
    }

    const tenRow = lengths.find((r) => r.lengthS === 10 && !r.skipped);
    if (
      tenRow && tenRow.p95Ms !== null && tenRow.p95Ms <= P95_BUDGET_MS &&
      durationS >= EXTRA_LENGTH_S && !budgetExceeded(startMs)
    ) {
      const row = timeViewsForLength(model, durationS, EXTRA_LENGTH_S, rng);
      lengths.push(row);
      if (row.p95Ms !== null && row.p95Ms <= P95_BUDGET_MS) longestLengthSWithP95Under50ms = EXTRA_LENGTH_S;
    }
  }

  const memFinal = memSnapshot();
  const result = {
    tablesPath,
    sequenceName,
    numBlocks: model.numBlocks,
    numSamples: model.numSamples,
    numGroups: model.numGroups,
    durationS,
    dt: model.dt,
    decodeMs,
    decodeOverBudget,
    memAfterDecodeBytes: memAfterDecode,
    memFinalBytes: memFinal,
    elapsedMsTotal: Date.now() - startMs,
    lengths,
    longestLengthSWithP95Under50ms,
  };

  const text = JSON.stringify(result, null, 2);
  if (outPath) {
    fs.writeFileSync(outPath, text);
    process.stderr.write(
      `wrote ${outPath}; longest length with p95 <= 50ms = ${longestLengthSWithP95Under50ms}\n`);
  } else {
    console.log(text);
  }
}

main();
