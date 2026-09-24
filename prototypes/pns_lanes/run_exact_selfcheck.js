// Prototype for docs/plans/pns-lanes-prototype.md, task 3: the self-check of
// `pns_lanes.js`'s exact part (see README.md, "Task 3" and "Results").
// NOT library code; never merged.
//
// For each "accuracy" case: decodes the model, runs the brute-force
// per-sample recursion once over the whole file (`PnsLanes.wholeFileRecursion`,
// the same module's plain method, never the block maps), then compares
// `PnsLanes.exactView` (which DOES use the block maps and the checkpoints)
// against slices of that one brute-force pass, over several ranges: the
// whole file, a window straddling a group (checkpoint) border near the
// middle of the file, a single sample, and a window at the end. The two are
// the same model, so any difference is float rounding from the block maps
// only (expected well under 1e-9 of the peak; the plan's decision table
// requires at most 1e-9).
//
// For each "timing" case (the exvivo file and the 10^6-block repeating
// sequence): times `decode` and `exactView` only. No brute-force comparison
// at that scale (accuracy is already established by the smaller accuracy
// cases; a whole-file brute force of 10^6+ blocks would cost gigabytes and
// minutes for no new information). `exactView` is timed over the whole file
// only when the file is small enough that the four Float64Arrays it returns
// comfortably fit the process budget (see MAX_WHOLE_FILE_SAMPLES below);
// otherwise only a bounded window is timed, and the result says so.
//
// Usage: node run_exact_selfcheck.js MANIFEST.json OUT.json
//
// MANIFEST.json: {"accuracy": [{"name", "path"}, ...], "timing": [{"name", "path"}, ...]}
// where each "path" is the output of export_tables.py for that sequence (run in a
// fresh Python process by the caller, per the plan's "one fresh process for each
// measurement").
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const zlib = require("zlib");
const { spawnSync } = require("child_process");

const PnsLanes = require(path.join(__dirname, "pns_lanes.js"));

// Above this many samples, a whole-file `exactView` (which allocates five
// Float64Arrays of that length) is not timed, to stay inside the plan's 5
// minute / 8 GB budget for one measurement process; a bounded window is
// timed instead. 5e7 samples is 5 * 5e7 * 8 bytes = 2 GB for that one call.
const MAX_WHOLE_FILE_SAMPLES = 5e7;

const TYPED_ARRAY_CTORS = {
  uint8: Uint8Array,
  uint16: Uint16Array,
  uint32: Uint32Array,
  float64: Float64Array,
};

function decodeTable(name, meta) {
  const Ctor = TYPED_ARRAY_CTORS[meta.dtype];
  if (!Ctor) throw new Error(`run_exact_selfcheck: table "${name}" has an unknown dtype "${meta.dtype}"`);
  const compressed = Buffer.from(meta.data, "base64");
  const raw = zlib.gunzipSync(compressed);
  // A fresh ArrayBuffer so the typed-array view is aligned, as
  // tests/js/golden_seq_lanes.js does for the same reason.
  const aligned = new ArrayBuffer(raw.length);
  new Uint8Array(aligned).set(raw);
  const arr = new Ctor(aligned);
  if (arr.length !== meta.length) {
    throw new Error(
      `run_exact_selfcheck: table "${name}" decoded to length ${arr.length}, but the ` +
      `input declared length ${meta.length}`);
  }
  return arr;
}

function nowMs() {
  return Number(process.hrtime.bigint()) / 1e6;
}

function rssBytes() {
  return process.memoryUsage().rss;
}

// Loads one export_tables.py JSON file and decodes its model, timing `decode`
// itself (not the table decompression, which is fixed wire-format overhead
// that decode() does not do in the browser either: SeqLanes.decode has the
// same split, see tests/js/golden_seq_lanes.js).
function loadModel(jsonPath) {
  const input = JSON.parse(fs.readFileSync(jsonPath, "utf8"));
  const tables = {};
  for (const [name, meta] of Object.entries(input.tables)) {
    tables[name] = decodeTable(name, meta);
  }
  const t0 = nowMs();
  const model = PnsLanes.decode(tables, input.opts);
  const decodeMs = nowMs() - t0;
  return { model, input, decodeMs };
}

// The brute-force per-sample recursion over the whole file, as one set of
// Float64Arrays (the reference that every range of one case is checked
// against). Uses PnsLanes.wholeFileRecursion's chunked callback so the peak
// memory is these five arrays plus one chunk, not two copies.
function bruteForceFull(model) {
  const n = model.numSamples;
  const t = new Float64Array(n);
  const total = new Float64Array(n);
  const x = new Float64Array(n);
  const y = new Float64Array(n);
  const z = new Float64Array(n);
  let pos = 0;
  const t0 = nowMs();
  PnsLanes.wholeFileRecursion(model, (chunk) => {
    t.set(chunk.t, pos);
    total.set(chunk.total, pos);
    x.set(chunk.x, pos);
    y.set(chunk.y, pos);
    z.set(chunk.z, pos);
    pos += chunk.count;
  });
  const ms = nowMs() - t0;
  if (pos !== n) {
    throw new Error(`run_exact_selfcheck: wholeFileRecursion emitted ${pos} samples, expected ${n}`);
  }
  return { t, total, x, y, z, ms };
}

// The largest of |Δt|, |Δtotal|, |Δx|, |Δy|, |Δz| between `view` (an
// exactView result, samples k0 .. k0 + view.t.length - 1) and `bf` (the
// whole-file brute force), and the largest |total| of `bf` over that same
// range (the "peak" that the difference is reported relative to).
function maxDiffAgainst(view, bf, k0) {
  let maxDiff = 0, peak = 0;
  for (let i = 0; i < view.t.length; i++) {
    const k = k0 + i;
    const d = Math.max(
      Math.abs(view.t[i] - bf.t[k]),
      Math.abs(view.total[i] - bf.total[k]),
      Math.abs(view.x[i] - bf.x[k]),
      Math.abs(view.y[i] - bf.y[k]),
      Math.abs(view.z[i] - bf.z[k]),
    );
    if (d > maxDiff) maxDiff = d;
    const p = Math.abs(bf.total[k]);
    if (p > peak) peak = p;
  }
  return { maxDiff, peak };
}

// The ranges of one accuracy case (README/plan task 4.3, adapted to task 3's
// self-check): the whole file; a window of 101 samples straddling the group
// border nearest the middle of the file (only when there is more than one
// group, i.e. more than `groupBlocks` blocks); a single sample near 41% of
// the file; and the last 200 samples plus the tail of the file. `bf.t` gives
// real, in-range sample times, so every range is guaranteed non-empty when
// the file has at least one sample.
function rangesFor(model, bf) {
  const n = model.numSamples;
  if (n === 0) return [{ label: "whole file", t0: 0, t1: 0 }];
  const lastT = bf.t[n - 1];
  const dt = model.dt;
  const fileEnd = lastT + dt; // past the last sample's time, well inside its half-open cell
  const ranges = [{ label: "whole file", t0: 0, t1: fileEnd }];

  const kSingle = Math.min(n - 1, Math.floor(n * 0.4127));
  ranges.push({ label: "single sample", t0: bf.t[kSingle], t1: bf.t[kSingle] });

  const kEndFrom = Math.max(0, n - 200);
  ranges.push({ label: "end", t0: bf.t[kEndFrom], t1: fileEnd });

  if (model.numGroups > 1) {
    const g = Math.floor(model.numGroups / 2);
    const kBoundary = model.groupFirstSample[g];
    const kFrom = Math.max(0, kBoundary - 50);
    const kTo = Math.min(n - 1, kBoundary + 50);
    ranges.push({
      label: "mid-file, across a group border",
      t0: bf.t[kFrom], t1: bf.t[kTo],
    });
  }
  return ranges;
}

function runAccuracyCase(name, jsonPath) {
  const { model, decodeMs } = loadModel(jsonPath);
  const memAfterDecodeBytes = rssBytes();
  const bf = bruteForceFull(model);
  const memAfterBruteForceBytes = rssBytes();

  const ranges = rangesFor(model, bf).map((r) => {
    const [k0raw] = PnsLanes.sampleRangeFor(model.dt, model.numSamples, r.t0, r.t1);
    const k0 = Math.max(0, k0raw);
    const t0 = nowMs();
    const view = PnsLanes.exactView(model, r.t0, r.t1);
    const exactViewMs = nowMs() - t0;
    const { maxDiff, peak } = maxDiffAgainst(view, bf, k0);
    return {
      label: r.label,
      t0: r.t0, t1: r.t1,
      samples: view.t.length,
      exactViewMs,
      maxAbsDiff: maxDiff,
      peak,
      maxDiffOverPeak: peak > 0 ? maxDiff / peak : 0,
    };
  });

  return {
    name,
    numBlocks: model.numBlocks,
    numSamples: model.numSamples,
    numGroups: model.numGroups,
    decodeMs,
    memAfterDecodeBytes,
    bruteForceWholeFileMs: bf.ms,
    memAfterBruteForceBytes,
    ranges,
  };
}

function runTimingCase(name, jsonPath) {
  const { model, input, decodeMs } = loadModel(jsonPath);
  const memAfterDecodeBytes = rssBytes();
  const durationS = input.durationS;
  const dt = model.dt;
  const n = model.numSamples;

  const views = [];

  // A short window (about 1 s of samples, clamped to the file), timed on
  // its own: this is the case the design is actually for (a zoomed-in
  // browser view), and it is cheap regardless of file size.
  {
    const windowS = Math.min(1.0, durationS);
    const t0Start = Math.max(0, durationS / 2 - windowS / 2);
    const t0 = nowMs();
    const view = PnsLanes.exactView(model, t0Start, t0Start + windowS);
    const ms = nowMs() - t0;
    views.push({ label: `~${windowS.toFixed(3)}s window at mid-file`, samples: view.t.length, exactViewMs: ms });
  }

  // The whole file, only when its sample count is within budget (see
  // MAX_WHOLE_FILE_SAMPLES above); otherwise recorded as skipped, with the
  // sample count that would have been produced.
  if (n <= MAX_WHOLE_FILE_SAMPLES) {
    const t0 = nowMs();
    const view = PnsLanes.exactView(model, 0, durationS + dt);
    const ms = nowMs() - t0;
    views.push({ label: "whole file", samples: view.t.length, exactViewMs: ms });
  } else {
    views.push({
      label: "whole file",
      skipped: true,
      reason: `${n} samples exceeds MAX_WHOLE_FILE_SAMPLES (${MAX_WHOLE_FILE_SAMPLES}); ` +
        "not timed here (task 4 measures zoomed-in speed at this scale properly)",
    });
  }

  return {
    name,
    numBlocks: model.numBlocks,
    numSamples: n,
    numGroups: model.numGroups,
    durationS,
    decodeMs,
    memAfterDecodeBytes,
    views,
  };
}

// Runs exactly one case (kind "accuracy" or "timing") and writes its result
// alone to `outPath`, as its own top-level object (no wrapping). Used both
// directly (`--single`) and by `main`, which launches one of these per case
// in a fresh `node` child process (plan section 4, "Limits of each run":
// "One fresh process for each measurement"), so that `memAfterDecodeBytes`
// and the RSS figures of one case are never inflated by an earlier case's
// arrays still sitting in the same process, and one case's memory can never
// count against another's 8 GB budget.
function runSingle(kind, name, jsonPath, outPath) {
  const result = kind === "accuracy" ? runAccuracyCase(name, jsonPath)
    : kind === "timing" ? runTimingCase(name, jsonPath)
    : (() => { throw new Error(`run_exact_selfcheck: unknown case kind "${kind}"`); })();
  fs.writeFileSync(outPath, JSON.stringify(result));
}

// Runs one case in a fresh `node` child process (this same script, called
// with --single) and returns its parsed result. Fails loudly (throws, with
// the child's stderr attached) on a non-zero exit, rather than silently
// dropping a case.
function runInFreshProcess(kind, name, jsonPath) {
  const outPath = path.join(
    os.tmpdir(), `pns-lanes-selfcheck-${kind}-${name}-${process.pid}-${Date.now()}.json`);
  process.stderr.write(`${kind} (fresh process): ${name}\n`);
  const res = spawnSync(
    process.execPath,
    [__filename, "--single", kind, name, jsonPath, outPath],
    { stdio: ["ignore", "inherit", "inherit"] });
  if (res.status !== 0) {
    throw new Error(
      `run_exact_selfcheck: child process for ${kind} "${name}" exited with ` +
      `status ${res.status} (signal ${res.signal})`);
  }
  const result = JSON.parse(fs.readFileSync(outPath, "utf8"));
  fs.unlinkSync(outPath);
  return result;
}

function main() {
  const argv = process.argv.slice(2);
  if (argv[0] === "--single") {
    const [, kind, name, jsonPath, outPath] = argv;
    runSingle(kind, name, jsonPath, outPath);
    return;
  }

  const [manifestPath, outPath] = argv;
  if (!manifestPath || !outPath) {
    throw new Error(
      "usage: node run_exact_selfcheck.js MANIFEST.json OUT.json\n" +
      "       node run_exact_selfcheck.js --single accuracy|timing NAME TABLES.json OUT.json");
  }
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));

  const accuracy = (manifest.accuracy || []).map(({ name, path: p }) =>
    runInFreshProcess("accuracy", name, p));
  const timing = (manifest.timing || []).map(({ name, path: p }) =>
    runInFreshProcess("timing", name, p));

  const worstOverPeak = Math.max(
    0, ...accuracy.flatMap((c) => c.ranges.map((r) => r.maxDiffOverPeak)));

  const results = {
    nodeVersion: process.version,
    generatedAt: new Date().toISOString(),
    worstMaxDiffOverPeak: worstOverPeak,
    accuracy,
    timing,
  };
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2));
  process.stderr.write(`wrote ${outPath}; worst maxDiff/peak = ${worstOverPeak}\n`);
}

main();
