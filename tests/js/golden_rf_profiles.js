// The Node half of the golden test of task 3.4 of docs/plans/rf-profiles.md:
// tests/test_rf_profiles_golden.py (the Python half) writes a JSON file with one
// sequence's encoded diagram tables, its lane metadata, its RF profile card file entry
// (`cards.rf_profile.rf_profile_data`, with the RF table), and a list of queries; this
// script decodes the tables, builds a `SeqLanes` model and its `sequenceView`, decodes
// the RF table and builds the `RfProfiles` file data (`RfProfiles.fileData`), answers
// each query with `RfProfiles`, and writes the results as JSON, so the Python side can
// compare them with its own reference (`rf_profiles.py`).
//
// Not named `test_*.js`, so `node --test` (`scripts/check`) does not try to run it on
// its own: it is a helper program, run once for each sequence by
// tests/test_rf_profiles_golden.py through `subprocess.run(["node", ...])`, the same
// way tests/js/golden_seq_lanes.js and tests/js/golden_pns_lanes.js are run by their
// own Python halves.
//
// Usage: node golden_rf_profiles.js IN.json OUT.json
//
// IN.json: {"format": 1, "tables": <pulseq_analysis.series.encode_array of each table>,
//           "lanes": <diagram_data.lane_meta(...) output>,
//           "file": <cards.rf_profile.rf_profile_data(...) output, "rf" still encoded>,
//           "queries": [{"kind": "period", "block": b, "maxBlocks"?: m},
//                       {"kind": "pulse", "block": b},
//                       {"kind": "view", "block": b, "view": v, "plane"?, "extentM"?,
//                        "n"?, "echoMomentPerM"?: [x, y, z]},
//                       {"kind": "combined", "block": b, "view": "profile" | "2d",
//                        "n"?}, ...]}
//
// OUT.json: {"results": [<one JSON value per query, see the *Json functions below>]}
//
// JSON.stringify turns a NaN or an Infinity into `null` on its own (ECMA-262), which is
// exactly the "NaN as null" rule the Python side expects for `echoPhase` and any other
// array that can hold a NaN (for example the "no ADC" reason leaves the combined
// profile's `factor` as NaN); no code here has to do that conversion by hand.
//
// Any error (a bad argument, an unknown dtype, a decoded length that does not match the
// declared length, an unknown query kind, or an error from `SeqLanes` or `RfProfiles`
// itself) is left to propagate as an uncaught exception, which Node reports on stderr
// with a non-zero exit code: there is no try/catch here to swallow or translate it, so a
// real bug in `rf_profiles.js` is never hidden behind a passing exit code.
"use strict";

const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

const ASSETS = path.join(__dirname, "..", "..", "src", "pulseq_reports", "assets");
const SeqLanes = require(path.join(ASSETS, "seq_lanes.js"));
const RfProfiles = require(path.join(ASSETS, "rf_profiles.js"));

// The typed array constructor for each dtype that `pulseq_analysis.series.encode_array` can
// produce for the diagram tables and the RF table (uint8/uint16/uint32 index and code
// columns, float64 offsets, delays and samples). Identical to `golden_seq_lanes.js`'s
// `TYPED_ARRAY_CTORS`.
const TYPED_ARRAY_CTORS = {
  uint8: Uint8Array,
  uint16: Uint16Array,
  uint32: Uint32Array,
  float64: Float64Array,
};

// One table's `{"dtype", "length", "data"}` (`pulseq_analysis.series.encode_array`'s
// wire form) decoded into a typed array: base64 to bytes, gzip to the little-endian
// bytes of the array, and those bytes copied into a fresh `ArrayBuffer` so the typed
// array view is aligned. Identical to `golden_seq_lanes.js`'s `decodeTable`.
function decodeTable(name, meta) {
  const Ctor = TYPED_ARRAY_CTORS[meta.dtype];
  if (!Ctor) {
    throw new Error(`golden_rf_profiles: table "${name}" has an unknown dtype "${meta.dtype}"`);
  }
  const compressed = Buffer.from(meta.data, "base64");
  const raw = zlib.gunzipSync(compressed);
  const aligned = new ArrayBuffer(raw.length);
  new Uint8Array(aligned).set(raw);
  const arr = new Ctor(aligned);
  if (arr.length !== meta.length) {
    throw new Error(
      `golden_rf_profiles: table "${name}" decoded to length ${arr.length}, but the ` +
      `input declared length ${meta.length}`);
  }
  return arr;
}

function decodeTables(obj) {
  const out = {};
  for (const [name, meta] of Object.entries(obj)) out[name] = decodeTable(name, meta);
  return out;
}

// A typed array (or null) to a plain array for JSON, unchanged otherwise (see the file
// comment above for how a NaN becomes `null`).
function arr(a) {
  return a === null || a === undefined ? null : Array.from(a);
}

function axisJson(a) {
  return {kind: a.kind, lo: a.lo, hi: a.hi, n: a.n};
}

function specJson(spec) {
  if (spec === null) return null;
  return {axes: spec.axes.map(axisJson), at: spec.at};
}

function pulseJson(p) {
  if (p === null) return null;
  return {
    use: p.use,
    sigRe: arr(p.sigRe),
    sigIm: arr(p.sigIm),
    dtS: p.dtS,
    grad: arr(p.grad),
    gradientKind: p.gradientKind,
    selectKind: p.selectKind,
    direction: arr(p.direction),
    selectGradientHzPerM: p.selectGradientHzPerM,
    constantGradient: p.constantGradient,
    freqOffsetHz: p.freqOffsetHz,
    sliceCentreM: p.sliceCentreM,
    flipDeg: p.flipDeg,
    peakB1Ut: p.peakB1Ut,
    energyUt2Ms: p.energyUt2Ms,
    nominalM: p.nominalM,
    fovM: p.fovM === null ? null : Array.from(p.fovM),
    key: p.key,
    echo: p.echo === null ? null : {
      momentPerM: Array.from(p.echo.momentPerM),
      sign: p.echo.sign,
      adcBlock: p.echo.adcBlock,
    },
    echoReason: p.echoReason,
    notes: Array.from(p.notes),
  };
}

function periodJson(per) {
  return {
    firstBlock: per.firstBlock,
    lastBlock: per.lastBlock,
    firstAdcBlock: per.firstAdcBlock,
    truncated: per.truncated,
    pulses: per.pulses.map(p => ({
      key: p.key, use: p.use, firstBlock: p.firstBlock, lastBlock: p.lastBlock, count: p.count,
    })),
  };
}

function mapJson(m) {
  return {axes: m.axes.map(axisJson), values: Array.from(m.values)};
}

function combinedJson(r) {
  return {
    reason: r.reason,
    excitationBlock: r.excitationBlock,
    refocusingBlocks: Array.from(r.refocusingBlocks),
    factor: r.factor,
    directions: Array.from(r.directions),
    line: r.line === null ? null : {u: Array.from(r.line.u), values: Array.from(r.line.values)},
    linePulses: r.linePulses.map(p => ({block: p.block, values: Array.from(p.values)})),
    maps: r.maps.map(mapJson),
    numbers: r.numbers,
  };
}

function runPeriod(view, file, q) {
  const opts = {};
  if (q.maxBlocks !== undefined && q.maxBlocks !== null) opts.maxBlocks = q.maxBlocks;
  return periodJson(RfProfiles.period(view, file, q.block, opts));
}

function runPulse(view, file, q) {
  return pulseJson(RfProfiles.blockPulse(view, file, q.block));
}

function runView(view, file, q) {
  const pulse = RfProfiles.blockPulse(view, file, q.block);
  const opts = {};
  if (q.plane !== undefined && q.plane !== null) opts.plane = q.plane;
  if (q.extentM !== undefined && q.extentM !== null) opts.extentM = q.extentM;
  if (q.n !== undefined && q.n !== null) opts.n = q.n;
  const {spec, reason} = RfProfiles.viewSpec(pulse, q.view, opts);
  const out = {reason, spec: specJson(spec)};
  if (spec === null) return out;
  const profile = RfProfiles.simulate(pulse, spec);
  out.grid = profile.grid.map(g => Array.from(g));
  out.a = {re: Array.from(profile.aRe), im: Array.from(profile.aIm)};
  out.b = {re: Array.from(profile.bRe), im: Array.from(profile.bIm)};
  out.q = {};
  for (const name of ["mxy_abs", "mz", "beta_sq"]) {
    out.q[name] = Array.from(RfProfiles.quantity(profile, name));
  }
  if (q.view === "profile") {
    out.widths = RfProfiles.widths(pulse, profile);
    out.echoPhase = arr(RfProfiles.echoPhase(pulse, profile));
    if (q.echoMomentPerM) {
      out.widthsM = RfProfiles.widths(pulse, profile, {echoMomentPerM: q.echoMomentPerM});
      out.echoPhaseM = arr(
        RfProfiles.echoPhase(pulse, profile, {echoMomentPerM: q.echoMomentPerM}));
    }
  }
  return out;
}

function runCombined(view, file, q) {
  const per = RfProfiles.period(view, file, q.block, {});
  const opts = {view: q.view};
  if (q.n !== undefined && q.n !== null) opts.n = q.n;
  const work = RfProfiles.combinedProfile(view, file, per, opts);
  work.step(Infinity);
  return combinedJson(work.result());
}

function runQuery(view, file, q) {
  if (q.kind === "period") return runPeriod(view, file, q);
  if (q.kind === "pulse") return runPulse(view, file, q);
  if (q.kind === "view") return runView(view, file, q);
  if (q.kind === "combined") return runCombined(view, file, q);
  throw new Error(`golden_rf_profiles: unknown query kind "${q.kind}"`);
}

function main() {
  const [, , inPath, outPath] = process.argv;
  if (!inPath || !outPath) {
    throw new Error("usage: node golden_rf_profiles.js IN.json OUT.json");
  }
  const input = JSON.parse(fs.readFileSync(inPath, "utf8"));

  const tables = decodeTables(input.tables);
  const model = SeqLanes.decode(input.format, tables, input.lanes);
  const view = SeqLanes.sequenceView(model);

  const rfTables = decodeTables(input.file.rf);
  const file = RfProfiles.fileData(input.file, rfTables);

  const results = input.queries.map(q => runQuery(view, file, q));
  fs.writeFileSync(outPath, JSON.stringify({results}));
}

main();
