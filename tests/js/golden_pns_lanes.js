// The Node half of the golden test of task 4.5 of docs/plans/diagram-lanes.md:
// tests/test_pns_lanes_golden.py (the Python half) writes a JSON file with one
// sequence's encoded diagram tables and one entry of the `file.pns` list of the diagram
// data (docs/plans/pulseq-checks-implementation.md, section 4.7); this script decodes
// both, builds a `PnsLanes` model, asks `exactView`
// for the whole file (forced to the "samples" kind by a bin count far larger than the
// sample count, so every sample comes back, never a minimum/maximum reduction), and
// writes the sample times, the totals as percent of the threshold of the entry
// (`PnsLanes.percent`) and the decoded pyramid (`model.levels`) as JSON, so the Python
// side can compare them against its own pns_levels pipeline.
//
// Not named `test_*.js`, so `node --test` (`scripts/check`) does not try to
// run it on its own: it is a helper program, run once per sequence by
// tests/test_pns_lanes_golden.py through `subprocess.run(["node", ...])`, the
// same way tests/js/golden_seq_lanes.js is run by test_seq_lanes_golden.py.
//
// Usage: node golden_pns_lanes.js IN.json OUT.json
//
// IN.json: {"tables": <pulseq_analysis.series.encode_array of each table>,
//           "pns": {"target", "color", "hardware", "asc_file", "hw", "dtS", "binSamples",
//                    "threshold", "summary",
//                    "levels": {"min": <pulseq_analysis.series.encode_array output>, "max": ...},
//                    "runs": {"start": ..., "end": ...}}}
//
// OUT.json: {"numSamples": <int>, "onRaster": <bool>,
//            "t": [<sample time, s>, ...], "percent": [<PNS total, % of the threshold>, ...],
//            "levels": [{"binSamples": <int>, "min": [...], "max": [...]}, ...]}
// (the levels are in Hz/T, as float32, as the matrix has them)
//
// Any error (a bad argument, an unknown dtype, a decoded length that does not
// match the declared length, or an error from PnsLanes itself, for example a
// file that is not on the gradient raster) is left to propagate as an
// uncaught exception, which Node reports on stderr with a non-zero exit code:
// there is no try/catch here to swallow or translate it, so a real bug in
// pns_lanes.js is never hidden behind a passing exit code.
"use strict";

const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

const assets = path.join(__dirname, "..", "..", "src", "pulseq_reports", "assets");
const PnsLanes = require(path.join(assets, "pns_lanes.js"));
const SeqLanes = require(path.join(assets, "seq_lanes.js"));

// The typed array constructor for each dtype that `pulseq_analysis.series.encode_array`
// can produce for the tables this script reads: the diagram tables themselves
// (uint8/uint16/uint32 index columns, float64 offsets and values) and the
// `pns.levels` min/max arrays (float32). Any other dtype
// name is a bug in the caller, not a case this script should paper over.
const TYPED_ARRAY_CTORS = {
  uint8: Uint8Array,
  uint16: Uint16Array,
  uint32: Uint32Array,
  float32: Float32Array,
  float64: Float64Array,
};

// One table's `{"dtype", "length", "data"}` (`pulseq_analysis.series.encode_array`'s wire form)
// decoded into a typed array: base64 to bytes, gzip to the little-endian
// bytes of the array, and those bytes copied into a fresh `ArrayBuffer` so
// the typed array view is aligned (the `Buffer` that `zlib.gunzipSync`
// returns is not guaranteed to start at an offset that suits a multi-byte
// element type). Identical to `golden_seq_lanes.js`'s `decodeTable`, plus
// `float32` in `TYPED_ARRAY_CTORS`.
function decodeTable(name, meta) {
  const Ctor = TYPED_ARRAY_CTORS[meta.dtype];
  if (!Ctor) {
    throw new Error(`golden_pns_lanes: table "${name}" has an unknown dtype "${meta.dtype}"`);
  }
  const compressed = Buffer.from(meta.data, "base64");
  const raw = zlib.gunzipSync(compressed);
  const aligned = new ArrayBuffer(raw.length);
  new Uint8Array(aligned).set(raw);
  const arr = new Ctor(aligned);
  if (arr.length !== meta.length) {
    throw new Error(
      `golden_pns_lanes: table "${name}" decoded to length ${arr.length}, ` +
      `but the input declared length ${meta.length}`
    );
  }
  return arr;
}

function main() {
  const [, , inPath, outPath] = process.argv;
  if (!inPath || !outPath) {
    throw new Error("usage: node golden_pns_lanes.js IN.json OUT.json");
  }
  const input = JSON.parse(fs.readFileSync(inPath, "utf8"));

  const tables = {};
  for (const [name, meta] of Object.entries(input.tables)) {
    tables[name] = decodeTable(name, meta);
  }

  const pnsIn = input.pns;
  const pns = {
    hw: pnsIn.hw,
    dtS: pnsIn.dtS,
    binSamples: pnsIn.binSamples,
    threshold: pnsIn.threshold,
    levels: {
      min: decodeTable("levels.min", pnsIn.levels.min),
      max: decodeTable("levels.max", pnsIn.levels.max),
    },
  };

  const model = PnsLanes.decode(tables, pns);

  const numSamples = model.numSamples;
  // A range and a bin count that together force exactView's "samples" kind
  // for the whole file (count <= 2 * bins, plan section 4.3, item 2), so the
  // result is every sample, never a minimum/maximum reduction: t0/t1 well
  // outside the file's own time span (sampleRangeFor clamps to [0,
  // numSamples - 1] regardless), and bins comfortably above numSamples / 2.
  const dt = model.dt;
  const t0 = -1.0;
  const t1 = numSamples * dt + 1.0;
  const bins = numSamples * 2 + 16;
  const view = PnsLanes.exactView(model, t0, t1, bins);
  if (view.kind !== "samples") {
    throw new Error(
      `golden_pns_lanes: exactView returned kind "${view.kind}", expected "samples"`
    );
  }

  const levels = model.levels.map((level) => ({
    binSamples: level.binSamples,
    min: Array.from(level.min),
    max: Array.from(level.max),
  }));

  fs.writeFileSync(
    outPath,
    JSON.stringify({
      numSamples,
      onRaster: model.onRaster,
      t: Array.from(view.t),
      percent: Array.from(view.total, (v) => PnsLanes.percent(v, model.threshold)),
      levels,
    })
  );
}

main();
