// The Node half of the golden test of task 4.4 of
// docs/plans/diagram-event-table.md: `tests/test_seq_lanes_golden.py` (the
// Python half) writes a JSON file with the encoded tables and lane metadata
// of one sequence and a list of queries; this script decodes the tables,
// builds a SeqLanes model, answers each query, and writes the results as
// JSON, so that the Python side can compare them with the reference it
// builds from `waveforms.py`.
//
// Not named `test_*.js`, so `node --test` (`scripts/check`) does not try to
// run it on its own: it is a helper program, run once per sequence by
// `tests/test_seq_lanes_golden.py` through `subprocess.run(["node", ...])`.
//
// Usage: node golden_seq_lanes.js IN.json OUT.json
//
// IN.json: {"format": 1, "tables": <encode_tables(...) output>,
//           "lanes": <lane_meta(...) output>,
//           "queries": [{"kind": "exact", "t0": s, "t1": s} |
//                       {"kind": "minmax", "t0": s, "t1": s, "bins": int}]}
//
// OUT.json: {"results": [<SeqLanes.exactLanes or SeqLanes.minMaxLanes output>, ...],
//            "durationS": <model.durationS>}
//
// Any error (a bad argument, an unknown dtype, a decoded length that does
// not match the declared length, an unknown query kind, or an error from
// SeqLanes itself) is left to propagate as an uncaught exception, which
// Node reports on stderr with a non-zero exit code: there is no try/catch
// here to swallow or translate it, so a real bug in `seq_lanes.js` is never
// hidden behind a passing exit code.
"use strict";

const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

const SeqLanes = require(
  path.join(__dirname, "..", "..", "src", "pulseq_reports", "assets", "seq_lanes.js")
);

// The typed array constructor for each dtype that `encode_tables` can
// produce (section 4.2 of the plan). Any other dtype name is a bug in the
// caller, not a case this script should paper over.
const TYPED_ARRAY_CTORS = {
  uint8: Uint8Array,
  uint16: Uint16Array,
  uint32: Uint32Array,
  float64: Float64Array,
};

// One table's `{"dtype", "length", "data"}` (`encode_tables`'s wire form,
// section 4.1) decoded into a typed array: base64 to bytes, gzip to the
// little-endian bytes of the array, and those bytes copied into a fresh
// `ArrayBuffer` so the typed array view is aligned (the `Buffer` that
// `zlib.gunzipSync` returns is not guaranteed to start at an offset that
// suits a multi-byte element type).
function decodeTable(name, meta) {
  const Ctor = TYPED_ARRAY_CTORS[meta.dtype];
  if (!Ctor) {
    throw new Error(`golden_seq_lanes: table "${name}" has an unknown dtype "${meta.dtype}"`);
  }
  const compressed = Buffer.from(meta.data, "base64");
  const raw = zlib.gunzipSync(compressed);
  const aligned = new ArrayBuffer(raw.length);
  new Uint8Array(aligned).set(raw);
  const arr = new Ctor(aligned);
  if (arr.length !== meta.length) {
    throw new Error(
      `golden_seq_lanes: table "${name}" decoded to length ${arr.length}, ` +
      `but the input declared length ${meta.length}`
    );
  }
  return arr;
}

function runQuery(model, query) {
  if (query.kind === "exact") {
    return SeqLanes.exactLanes(model, query.t0, query.t1);
  }
  if (query.kind === "minmax") {
    return SeqLanes.minMaxLanes(model, query.t0, query.t1, query.bins);
  }
  throw new Error(`golden_seq_lanes: unknown query kind "${query.kind}"`);
}

function main() {
  const [, , inPath, outPath] = process.argv;
  if (!inPath || !outPath) {
    throw new Error("usage: node golden_seq_lanes.js IN.json OUT.json");
  }
  const input = JSON.parse(fs.readFileSync(inPath, "utf8"));

  const tables = {};
  for (const [name, meta] of Object.entries(input.tables)) {
    tables[name] = decodeTable(name, meta);
  }
  const model = SeqLanes.decode(input.format, tables, input.lanes);

  const results = input.queries.map(query => runQuery(model, query));

  // JSON.stringify writes each number in JavaScript's shortest round-trip
  // form, so no value changes on the way out.
  fs.writeFileSync(outPath, JSON.stringify({results, durationS: model.durationS}));
}

main();
