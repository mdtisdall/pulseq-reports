// Task 4 of docs/plans/pns-lanes-prototype.md, question 1 (accuracy). Prototype code
// only; not part of the library, never merged (see README.md).
//
// Reads one manifest written by run_accuracy.py (build_manifest): the path to that
// sequence's diagram tables JSON (export_tables.py's payload shape) and a list of time
// ranges, each with the reference (pns_reference) samples t/total/x/y/z as raw
// little-endian float64 .bin files. For each range:
//
//   1. Decodes the tables and calls PnsLanes.exactView(model, t0, t1).
//   2. Checks the JS sample times against the reference's (they use the same t0/t1 and
//      the same "(k + 0.5) * dt in [t0, t1]" selection rule, so they should select the
//      exact same samples; a length or time mismatch is recorded, not silently
//      ignored).
//   3. Records the largest |JS - reference| for total, x, y, z in that range.
//
// The sequence's worst relative accuracy (question 1 of the plan) is
// max(largest |JS - reference|) / referencePeak, taken over every range and every
// lane (total, x, y, z) -- referencePeak is the whole-file reference peak from the
// manifest (pns_reference's `peak`, computed over the full file regardless of
// `ranges`), not a per-range peak.
//
// For the one range flagged isWholeFile (only present for the "up to ~12s" sequences,
// per run_accuracy.py's _ranges_for), also computes the JS whole-file peak and peak
// time from that exactView result (same peak-time rule as
// pulseq_reports.pns.PnsPrediction.peak_time_s / reference.py's PEAK_TOLERANCE: the
// first sample with total >= peak * (1 - 1e-6)), and reports them next to the
// reference's, for comparison.
//
// Usage: node run_accuracy.js MANIFEST.json [OUT.json]
// With no OUT.json, the result JSON is printed to stdout.
"use strict";

const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

const PnsLanes = require(path.join(__dirname, "pns_lanes.js"));

const PEAK_TOLERANCE = 1e-6; // matches reference.py's PEAK_TOLERANCE

const TYPED_ARRAY_CTORS = {
  uint8: Uint8Array,
  uint16: Uint16Array,
  uint32: Uint32Array,
  float64: Float64Array,
};

// Decodes one gzip+base64 diagram table (export_tables.py / run_exact_selfcheck.js's
// decodeTable), duplicated here rather than imported: run_exact_selfcheck.js has no
// module.exports (it runs its own main() on require), and it is read-only per this
// task's instructions.
function decodeTable(name, meta) {
  const Ctor = TYPED_ARRAY_CTORS[meta.dtype];
  if (!Ctor) throw new Error(`run_accuracy: table "${name}" has an unknown dtype "${meta.dtype}"`);
  const compressed = Buffer.from(meta.data, "base64");
  const raw = zlib.gunzipSync(compressed);
  const aligned = new ArrayBuffer(raw.length);
  new Uint8Array(aligned).set(raw);
  const arr = new Ctor(aligned);
  if (arr.length !== meta.length) {
    throw new Error(
      `run_accuracy: table "${name}" decoded to length ${arr.length}, expected ${meta.length}`);
  }
  return arr;
}

function loadModel(jsonPath) {
  const input = JSON.parse(fs.readFileSync(jsonPath, "utf8"));
  const tables = {};
  for (const [name, meta] of Object.entries(input.tables)) {
    tables[name] = decodeTable(name, meta);
  }
  const t0 = Number(process.hrtime.bigint());
  const model = PnsLanes.decode(tables, input.opts);
  const decodeMs = (Number(process.hrtime.bigint()) - t0) / 1e6;
  return { model, input, decodeMs };
}

// Reads one raw little-endian float64 .bin file (as written by numpy's
// `arr.astype("<f8").tofile(path)` in run_accuracy.py) as a Float64Array, in a fresh,
// aligned ArrayBuffer (the file's own buffer offset is not guaranteed 8-byte aligned).
function readF64Bin(p) {
  const raw = fs.readFileSync(p);
  const aligned = new ArrayBuffer(raw.length);
  new Uint8Array(aligned).set(raw);
  return new Float64Array(aligned);
}

function maxAbs(arr) {
  let m = 0;
  for (let i = 0; i < arr.length; i++) {
    const v = Math.abs(arr[i]);
    if (v > m) m = v;
  }
  return m;
}

function diffLane(jsArr, refArr) {
  // Only called when jsArr.length === refArr.length (checked by the caller).
  let m = 0;
  for (let i = 0; i < jsArr.length; i++) {
    const d = Math.abs(jsArr[i] - refArr[i]);
    if (d > m) m = d;
  }
  return m;
}

function jsWholeFilePeak(view) {
  let peak = 0;
  for (let i = 0; i < view.total.length; i++) {
    if (view.total[i] > peak) peak = view.total[i];
  }
  const threshold = peak * (1 - PEAK_TOLERANCE);
  let peakTimeS = null;
  for (let i = 0; i < view.total.length; i++) {
    if (view.total[i] >= threshold) { peakTimeS = view.t[i]; break; }
  }
  return { peak, peakTimeS };
}

function runOne(manifest) {
  const { model, decodeMs } = loadModel(manifest.tablesPath);

  const ranges = [];
  const sampleMismatches = [];
  const worstRelDiff = { total: 0, x: 0, y: 0, z: 0 };
  let wholeFile = null;

  for (const r of manifest.ranges) {
    const refT = readF64Bin(r.tPath);
    const refTotal = readF64Bin(r.totalPath);
    const refX = readF64Bin(r.xPath);
    const refY = readF64Bin(r.yPath);
    const refZ = readF64Bin(r.zPath);

    const t0 = process.hrtime.bigint();
    const view = PnsLanes.exactView(model, r.t0, r.t1);
    const exactViewMs = Number(process.hrtime.bigint() - t0) / 1e6;

    const lengthMatch = view.t.length === refT.length;
    let maxAbsTDiff = null;
    const entry = {
      label: r.label,
      t0: r.t0,
      t1: r.t1,
      referenceN: refT.length,
      jsN: view.t.length,
      lengthMatch,
      exactViewMs,
    };

    if (!lengthMatch) {
      sampleMismatches.push({ label: r.label, referenceN: refT.length, jsN: view.t.length });
      ranges.push(entry);
      continue;
    }

    maxAbsTDiff = diffLane(view.t, refT);
    entry.maxAbsTDiff = maxAbsTDiff;
    if (maxAbsTDiff !== 0) {
      sampleMismatches.push({ label: r.label, maxAbsTDiff, note: "sample times differ" });
    }

    const dTotal = diffLane(view.total, refTotal);
    const dX = diffLane(view.x, refX);
    const dY = diffLane(view.y, refY);
    const dZ = diffLane(view.z, refZ);
    entry.maxAbsDiff = { total: dTotal, x: dX, y: dY, z: dZ };

    const peak = manifest.referencePeak;
    entry.maxDiffOverReferencePeak = peak > 0
      ? { total: dTotal / peak, x: dX / peak, y: dY / peak, z: dZ / peak }
      : { total: 0, x: 0, y: 0, z: 0 };

    if (peak > 0) {
      worstRelDiff.total = Math.max(worstRelDiff.total, dTotal / peak);
      worstRelDiff.x = Math.max(worstRelDiff.x, dX / peak);
      worstRelDiff.y = Math.max(worstRelDiff.y, dY / peak);
      worstRelDiff.z = Math.max(worstRelDiff.z, dZ / peak);
    }

    if (r.isWholeFile) {
      const { peak: jsPeak, peakTimeS: jsPeakTimeS } = jsWholeFilePeak(view);
      wholeFile = {
        label: r.label,
        jsPeak,
        jsPeakTimeS,
        referencePeak: manifest.referencePeak,
        referencePeakTimeS: manifest.referencePeakTimeS,
        peakAbsDiff: Math.abs(jsPeak - manifest.referencePeak),
        peakTimeAbsDiffS:
          jsPeakTimeS !== null && manifest.referencePeakTimeS !== null
            ? Math.abs(jsPeakTimeS - manifest.referencePeakTimeS)
            : null,
      };
    }

    ranges.push(entry);
  }

  return {
    name: manifest.name,
    numBlocks: manifest.numBlocks,
    numGroups: model.numGroups,
    numSamples: model.numSamples,
    decodeMs,
    referencePeak: manifest.referencePeak,
    referencePeakTimeS: manifest.referencePeakTimeS,
    referenceAxisPeaks: manifest.referenceAxisPeaks,
    worstRelDiff,
    wholeFile,
    sampleMismatches,
    ranges,
  };
}

function main() {
  const [manifestPath, outPath] = process.argv.slice(2);
  if (!manifestPath) {
    throw new Error("usage: node run_accuracy.js MANIFEST.json [OUT.json]");
  }
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const result = runOne(manifest);
  const text = JSON.stringify(result, null, 2);
  if (outPath) {
    fs.writeFileSync(outPath, text);
    process.stderr.write(
      `wrote ${outPath}; worst maxDiff/peak (total) = ${result.worstRelDiff.total}\n`);
  } else {
    console.log(text);
  }
}

main();
