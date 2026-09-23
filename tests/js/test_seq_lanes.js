const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const SeqLanes = require(
  path.join(__dirname, "..", "..", "src", "pulseq_reports", "assets", "seq_lanes.js")
);

// ---- Model builders -------------------------------------------------------
//
// Two ways to build a model: `buildHandModel` makes a tiny 5-block model by
// hand, with every event worked out on paper, for tests that check an exact
// expected value. `buildRandomModel` makes a larger pseudo-random model (any
// block count, so it can cross the 1024-block checkpoint boundary), for the
// brute-force comparisons in the `minMaxLanes` tests, where hand-deriving
// every bin is not practical.

function laneMeta(id, kind) {
  return {
    id, title: id, unit: "", color: id, kind: kind || "line",
    domain: [0, 1], ticks: [0], tick_labels: ["0"], empty: false, fill: 0.0,
  };
}

const HAND_LANES_META = [
  laneMeta("rf_mag"),
  {...laneMeta("rf_phase"), fill: null},
  laneMeta("adc", "gate"),
  laneMeta("gx"),
  laneMeta("gy"),
  laneMeta("gz"),
];

// 5 blocks: RF pulse (block0, magnitude and phase), gx trapezoid (block1),
// gy arbitrary gradient (block2), ADC window (block3), empty delay-only
// block (block4). Block starts (sequential sum, s): 0, 0.002, 0.005, 0.0075,
// 0.0085. End of file (durationS): 0.01.
function buildHandModel() {
  const tables = {
    duration_index: Uint8Array.from([0, 1, 2, 3, 4]),
    durations: Float64Array.from([0.002, 0.003, 0.0025, 0.001, 0.0015]),
    checkpoints: Float64Array.from([0.0]),

    rf: Uint8Array.from([1, 0, 0, 0, 0]),
    gx: Uint8Array.from([0, 1, 0, 0, 0]),
    gy: Uint8Array.from([0, 0, 2, 0, 0]),
    gz: Uint8Array.from([0, 0, 0, 0, 0]),
    adc: Uint8Array.from([0, 0, 0, 1, 0]),

    rf_delay: Float64Array.from([0.0002]),
    rf_mag_n: Uint32Array.from([3]),
    rf_mag_offset_at: Uint32Array.from([0]),
    rf_mag_at: Uint32Array.from([0]),
    rf_mag_offset: Float64Array.from([0, 0.0005, 0.001]),
    rf_mag: Float64Array.from([0.0, 10.0, 0.0]),
    rf_phase_n: Uint32Array.from([1]),
    rf_phase_offset_at: Uint32Array.from([0]),
    rf_phase_at: Uint32Array.from([0]),
    rf_phase_offset: Float64Array.from([0.0005]),
    rf_phase: Float64Array.from([Math.PI / 2]),

    // grad event 1 = trapezoid (used as gx in block1): delay 0.0001,
    // rise 0.0005, flat 0.001, fall 0.0005, amplitude 10 mT/m.
    // grad event 2 = arbitrary (used as gy in block2): delay 0.00005,
    // offsets [0, 0.0004, 0.0012, 0.002], values [0, -3, -6, 0] mT/m.
    grad_delay: Float64Array.from([0.0001, 0.00005]),
    grad_n: Uint32Array.from([4, 4]),
    grad_offset_at: Uint32Array.from([0, 4]),
    grad_at: Uint32Array.from([0, 4]),
    grad_offset: Float64Array.from([0, 0.0005, 0.0015, 0.002, 0, 0.0004, 0.0012, 0.002]),
    grad_value: Float64Array.from([0, 10, 10, 0, 0, -3, -6, 0]),

    adc_delay: Float64Array.from([0.00002]),
    adc_length: Float64Array.from([0.0006]),
  };
  return {tables, model: SeqLanes.decode(1, tables, HAND_LANES_META)};
}

// A larger pseudo-random model of `nBlocks` blocks, for a block count that
// can be picked to cross the 1024-block checkpoint boundary, and for the
// brute-force `minMaxLanes` comparisons below (where the exact points are
// too many to derive by hand). `seed` makes it deterministic. The generator,
// the table shapes and the lane list are the validated ones of the
// scratchpad's `validate_minmax.js`/`validate_phase_adc.js`, copied here so
// this file reads nothing from the scratchpad at run time.
function buildRandomModel(nBlocks, seed) {
  let s = seed;
  const rnd = () => (s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
  const durations = new Float64Array([1e-3, 2.5e-3, 4e-3]);
  const duration_index = new Uint8Array(nBlocks);
  const rf = new Uint16Array(nBlocks), gx = new Uint16Array(nBlocks);
  const gy = new Uint16Array(nBlocks), gz = new Uint16Array(nBlocks);
  const adc = new Uint8Array(nBlocks);
  for (let i = 0; i < nBlocks; i++) {
    duration_index[i] = Math.floor(rnd() * 3);
    rf[i] = rnd() < 0.3 ? 1 + Math.floor(rnd() * 2) : 0;
    gx[i] = rnd() < 0.5 ? 1 + Math.floor(rnd() * 3) : 0;
    gy[i] = rnd() < 0.3 ? 1 + Math.floor(rnd() * 3) : 0;
    gz[i] = rnd() < 0.2 ? 1 + Math.floor(rnd() * 3) : 0;
    adc[i] = rnd() < 0.2 ? 1 : 0;
  }
  const nCp = Math.ceil(nBlocks / 1024);
  const checkpoints = new Float64Array(nCp);
  let t = 0.0;
  for (let i = 0; i < nBlocks; i++) {
    if (i % 1024 === 0) checkpoints[i / 1024] = t;
    t += durations[duration_index[i]];
  }
  const tables = {
    duration_index, durations, checkpoints, rf, gx, gy, gz, adc,
    rf_delay: new Float64Array([1e-4, 2e-4]),
    rf_mag_n: new Uint32Array([5, 5]),
    rf_mag_offset_at: new Uint32Array([0, 0]),
    rf_mag_at: new Uint32Array([0, 5]),
    rf_mag_offset: new Float64Array([0, 1e-4, 2e-4, 3e-4, 4e-4]),
    rf_mag: new Float64Array([0, 8, 12, 6, 0, 0, 5, 9, 3, 0]),
    rf_phase_n: new Uint32Array([3, 3]),
    rf_phase_offset_at: new Uint32Array([0, 0]),
    rf_phase_at: new Uint32Array([0, 3]),
    rf_phase_offset: new Float64Array([1e-4, 2e-4, 3e-4]),
    rf_phase: new Float64Array([0.5, -1.2, 2.0, -2.9, 1.1, 0.2]),
    grad_delay: new Float64Array([0, 5e-5, 1e-4]),
    grad_n: new Uint32Array([4, 4, 4]),
    grad_offset_at: new Uint32Array([0, 0, 0]),
    grad_at: new Uint32Array([0, 4, 8]),
    grad_offset: new Float64Array([0, 1e-4, 6e-4, 7e-4]),
    grad_value: new Float64Array([0, 15, 15, 0, 0, -22, -22, 0, 0, 9, 9, 0]),
    adc_delay: new Float64Array([2e-4]),
    adc_length: new Float64Array([1.2e-3]),
  };
  const ids = ["rf_mag", "rf_phase", "adc", "gx", "gy", "gz"];
  const lanesMeta = ids.map(id => ({
    id, title: id, unit: "", color: id, kind: id === "adc" ? "gate" : "line",
    domain: [-30, 30], ticks: [0], tick_labels: ["0"], empty: false,
    fill: id === "rf_phase" ? null : 0.0,
  }));
  return {tables, model: SeqLanes.decode(1, tables, lanesMeta)};
}

// 3 blocks, built to force an RF phase gap in `minMaxLanes`: block0 has an
// RF pulse with one phase point, block1 is empty, block2 has a second RF
// pulse with one phase point. Block starts: 0, 0.001, 0.003. End: 0.004.
function buildPhaseGapModel() {
  const tables = {
    duration_index: Uint8Array.from([0, 1, 0]),
    durations: Float64Array.from([0.001, 0.002]),
    checkpoints: Float64Array.from([0.0]),

    rf: Uint8Array.from([1, 0, 2]),
    gx: Uint8Array.from([0, 0, 0]),
    gy: Uint8Array.from([0, 0, 0]),
    gz: Uint8Array.from([0, 0, 0]),
    adc: Uint8Array.from([0, 0, 0]),

    rf_delay: Float64Array.from([0.0001, 0.0001]),
    rf_mag_n: Uint32Array.from([0, 0]),
    rf_mag_offset_at: Uint32Array.from([0, 0]),
    rf_mag_at: Uint32Array.from([0, 0]),
    rf_mag_offset: Float64Array.from([]),
    rf_mag: Float64Array.from([]),
    rf_phase_n: Uint32Array.from([1, 1]),
    rf_phase_offset_at: Uint32Array.from([0, 1]),
    rf_phase_at: Uint32Array.from([0, 1]),
    rf_phase_offset: Float64Array.from([0.0003, 0.0003]),
    rf_phase: Float64Array.from([0.7, -0.9]),

    grad_delay: Float64Array.from([]),
    grad_n: Uint32Array.from([]),
    grad_offset_at: Uint32Array.from([]),
    grad_at: Uint32Array.from([]),
    grad_offset: Float64Array.from([]),
    grad_value: Float64Array.from([]),

    adc_delay: Float64Array.from([]),
    adc_length: Float64Array.from([]),
  };
  return {tables, model: SeqLanes.decode(1, tables, HAND_LANES_META)};
}

// 3 blocks, built like pypulseq RF events: each magnitude event is
// `[0, |B1|..., 0]` at offsets `[0, rt..., rt[-1]]`, so a pulse ends with two
// points at the same time, the last sample then the zero pad. Block0 (1 ms)
// has RF event 1 (delay 0.1 ms): points (0.1 ms, 0), (0.2, 2), (0.5, 5),
// (0.9, 3), (0.9, 0). Block1 (4 ms) is empty. Block2 (1 ms) has RF event 2,
// a block pulse with rt[0] = 0 (delay 0): points (5.0 ms, 0), (5.0, 4),
// (5.3, 4), (5.3, 0), so it also starts with two points at the same time.
// Block starts: 0, 0.001, 0.005. End: 0.006. Between the pulses, the
// whole-file polyline is 0: it runs from (0.9 ms, 0) to (5.0 ms, 0).
function buildRepeatedTimeModel() {
  const tables = {
    duration_index: Uint8Array.from([0, 1, 0]),
    durations: Float64Array.from([0.001, 0.004]),
    checkpoints: Float64Array.from([0.0]),

    rf: Uint8Array.from([1, 0, 2]),
    gx: Uint8Array.from([0, 0, 0]),
    gy: Uint8Array.from([0, 0, 0]),
    gz: Uint8Array.from([0, 0, 0]),
    adc: Uint8Array.from([0, 0, 0]),

    rf_delay: Float64Array.from([0.0001, 0.0]),
    rf_mag_n: Uint32Array.from([5, 4]),
    rf_mag_offset_at: Uint32Array.from([0, 5]),
    rf_mag_at: Uint32Array.from([0, 5]),
    rf_mag_offset: Float64Array.from([0, 0.0001, 0.0004, 0.0008, 0.0008, 0, 0, 0.0003, 0.0003]),
    rf_mag: Float64Array.from([0, 2, 5, 3, 0, 0, 4, 4, 0]),
    rf_phase_n: Uint32Array.from([0, 0]),
    rf_phase_offset_at: Uint32Array.from([0, 0]),
    rf_phase_at: Uint32Array.from([0, 0]),
    rf_phase_offset: Float64Array.from([]),
    rf_phase: Float64Array.from([]),

    grad_delay: Float64Array.from([]),
    grad_n: Uint32Array.from([]),
    grad_offset_at: Uint32Array.from([]),
    grad_at: Uint32Array.from([]),
    grad_offset: Float64Array.from([]),
    grad_value: Float64Array.from([]),

    adc_delay: Float64Array.from([]),
    adc_length: Float64Array.from([]),
  };
  return {tables, model: SeqLanes.decode(1, tables, HAND_LANES_META)};
}

// 4 blocks with long events, so that a bin's range of points inside one
// event is far longer than the 64-value chunks of `minMaxLanes`'s pyramid.
// Block0 (20 ms) has RF event 1: 20,000 samples at a 1 µs dwell, with
// pseudo-random |B1| and phase values and a few narrow spikes (a spike is
// the extreme of its bin only if the search finds that one sample). Its
// magnitude offsets are `[0, rt..., rt[-1]]`, as pypulseq gives them.
// Block1 (10 ms) is empty. Block2 (30 ms) has gradient event 1 on gx:
// 30,000 points at a 1 µs raster. Its sample at each 64-value chunk start
// is a spike that grows to the right, and its sample at each chunk end is
// a negative spike that grows to the left. So the maximum of any range of
// its points is the first sample of a chunk, and the minimum is the last
// sample of a chunk: a range scan that misses one value at a chunk edge
// gives a wrong bin. Block3 (20 ms) has RF event 1 again and
// gradient event 1 on gy. End: 0.08 s.
function buildLongEventModel() {
  let s = 12345;
  const rnd = () => (s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
  const nRf = 20000, nGrad = 30000, dwell = 1e-6;
  const rt = Float64Array.from({length: nRf}, (_, p) => (p + 0.5) * dwell);
  const mag = Float64Array.from({length: nRf}, () => 1 + rnd());
  const phase = Float64Array.from({length: nRf}, () => 2 * rnd() - 1);
  for (const p of [0, 777, 12345, nRf - 1]) mag[p] = 9;
  for (const p of [5, 4321, 19000]) phase[p] = 3;
  phase[16000] = -3;
  const grad = Float64Array.from({length: nGrad}, () => 10 * rnd() - 5);
  for (let m = 0; 64 * m < nGrad; m++) {
    grad[64 * m] = 50 + m * 1e-3;
    if (64 * m + 63 < nGrad) grad[64 * m + 63] = -50 - (1000 - m) * 1e-3;
  }
  grad[0] = 0;
  grad[nGrad - 1] = 0;

  const magOffset = new Float64Array(nRf + 2);
  magOffset.set(rt, 1);
  magOffset[nRf + 1] = rt[nRf - 1];
  const magValue = new Float64Array(nRf + 2);
  magValue.set(mag, 1);

  const tables = {
    duration_index: Uint8Array.from([0, 1, 2, 0]),
    durations: Float64Array.from([0.02, 0.01, 0.03]),
    checkpoints: Float64Array.from([0.0]),

    rf: Uint8Array.from([1, 0, 0, 1]),
    gx: Uint8Array.from([0, 0, 1, 0]),
    gy: Uint8Array.from([0, 0, 0, 1]),
    gz: Uint8Array.from([0, 0, 0, 0]),
    adc: Uint8Array.from([0, 0, 0, 0]),

    rf_delay: Float64Array.from([0.0]),
    rf_mag_n: Uint32Array.from([nRf + 2]),
    rf_mag_offset_at: Uint32Array.from([0]),
    rf_mag_at: Uint32Array.from([0]),
    rf_mag_offset: magOffset,
    rf_mag: magValue,
    rf_phase_n: Uint32Array.from([nRf]),
    rf_phase_offset_at: Uint32Array.from([0]),
    rf_phase_at: Uint32Array.from([0]),
    rf_phase_offset: rt,
    rf_phase: phase,

    grad_delay: Float64Array.from([0.0]),
    grad_n: Uint32Array.from([nGrad]),
    grad_offset_at: Uint32Array.from([0]),
    grad_at: Uint32Array.from([0]),
    grad_offset: Float64Array.from({length: nGrad}, (_, p) => p * dwell),
    grad_value: grad,

    adc_delay: Float64Array.from([]),
    adc_length: Float64Array.from([]),
  };
  return {tables, model: SeqLanes.decode(1, tables, HAND_LANES_META)};
}

// 4 blocks, built to force two ADC windows that land in adjacent bins with
// no "off" bin between them, closer together than one bin's width: block0
// is a pad, block1 and block2 each have a short ADC window, block3 is a
// pad. Block starts: 0, 0.001, 0.002, 0.003. End: 0.004.
function buildAdcCloseModel() {
  const tables = {
    duration_index: Uint8Array.from([0, 0, 0, 0]),
    durations: Float64Array.from([0.001]),
    checkpoints: Float64Array.from([0.0]),

    rf: Uint8Array.from([0, 0, 0, 0]),
    gx: Uint8Array.from([0, 0, 0, 0]),
    gy: Uint8Array.from([0, 0, 0, 0]),
    gz: Uint8Array.from([0, 0, 0, 0]),
    adc: Uint8Array.from([0, 1, 2, 0]),

    rf_delay: Float64Array.from([]),
    rf_mag_n: Uint32Array.from([]),
    rf_mag_offset_at: Uint32Array.from([]),
    rf_mag_at: Uint32Array.from([]),
    rf_mag_offset: Float64Array.from([]),
    rf_mag: Float64Array.from([]),
    rf_phase_n: Uint32Array.from([]),
    rf_phase_offset_at: Uint32Array.from([]),
    rf_phase_at: Uint32Array.from([]),
    rf_phase_offset: Float64Array.from([]),
    rf_phase: Float64Array.from([]),

    grad_delay: Float64Array.from([]),
    grad_n: Uint32Array.from([]),
    grad_offset_at: Uint32Array.from([]),
    grad_at: Uint32Array.from([]),
    grad_offset: Float64Array.from([]),
    grad_value: Float64Array.from([]),

    // window1 = [0.0011, 0.0014], window2 = [0.0021, 0.0024]: a 0.7 ms gap.
    adc_delay: Float64Array.from([0.0001, 0.0001]),
    adc_length: Float64Array.from([0.0003, 0.0003]),
  };
  return {tables, model: SeqLanes.decode(1, tables, HAND_LANES_META)};
}

// A model where every block contributes exactly the same, known number of
// points to `pointsIn` (section 4.4, item 3): an RF pulse (3 magnitude
// points + 1 phase point) and a gx event (4 points), on gy and gz and no
// ADC, for 8 points a block. All blocks share the same single RF and
// gradient event. Used to put `SeqLanes.EXACT_POINT_LIMIT` (20000) at an
// exact multiple of the per-block count, so a view can be built that holds
// exactly the limit.
const POINTS_PER_BLOCK = 8;

function buildPointBudgetModel(nBlocks) {
  const duration_index = new Uint16Array(nBlocks); // all 0
  const durations = Float64Array.from([0.001]);
  const nCp = Math.ceil(nBlocks / 1024);
  // The checkpoints are the sequential sum of the durations (section 4.3),
  // which `decode` checks: not `c * 1024 * 0.001`.
  const checkpoints = new Float64Array(nCp);
  let sum = 0.0;
  for (let i = 0; i < nBlocks; i++) {
    if (i % 1024 === 0) checkpoints[i / 1024] = sum;
    sum += durations[duration_index[i]];
  }

  const tables = {
    duration_index, durations, checkpoints,
    rf: new Uint8Array(nBlocks).fill(1),
    gx: new Uint8Array(nBlocks).fill(1),
    gy: new Uint8Array(nBlocks), // all 0, no event
    gz: new Uint8Array(nBlocks), // all 0, no event
    adc: new Uint8Array(nBlocks), // all 0, no event

    rf_delay: Float64Array.from([0.0001]),
    rf_mag_n: Uint32Array.from([3]),
    rf_mag_offset_at: Uint32Array.from([0]),
    rf_mag_at: Uint32Array.from([0]),
    rf_mag_offset: Float64Array.from([0, 0.0003, 0.0006]),
    rf_mag: Float64Array.from([0, 5, 0]),
    rf_phase_n: Uint32Array.from([1]),
    rf_phase_offset_at: Uint32Array.from([0]),
    rf_phase_at: Uint32Array.from([0]),
    rf_phase_offset: Float64Array.from([0.0003]),
    rf_phase: Float64Array.from([0.2]),

    grad_delay: Float64Array.from([0.0001]),
    grad_n: Uint32Array.from([4]),
    grad_offset_at: Uint32Array.from([0]),
    grad_at: Uint32Array.from([0]),
    grad_offset: Float64Array.from([0, 0.0003, 0.0006, 0.0009]),
    grad_value: Float64Array.from([0, 3, 3, 0]),

    adc_delay: Float64Array.from([]),
    adc_length: Float64Array.from([]),
  };
  return {tables, model: SeqLanes.decode(1, tables, HAND_LANES_META)};
}

// ---- decode: format and table-name checks ---------------------------------

test("test_decode_throws_for_an_unsupported_format", () => {
  const {tables} = buildHandModel();
  assert.throws(() => SeqLanes.decode(2, tables, HAND_LANES_META));
});

test("test_decode_throws_for_an_unknown_table_name", () => {
  const {tables} = buildHandModel();
  assert.throws(() => SeqLanes.decode(1, {...tables, rotation: new Uint8Array(5)}, HAND_LANES_META));
});

test("test_decode_throws_for_offsets_out_of_time_order", () => {
  // The minimum/maximum view finds the points of an event by binary search
  // on their times, so `decode` refuses an event whose offsets go down.
  const {tables} = buildHandModel();
  const offsets = Float64Array.from(tables.grad_offset);
  offsets[6] = 0.0001; // grad event 2: [0, 0.0004, 0.0001, 0.002]
  assert.throws(
    () => SeqLanes.decode(1, {...tables, grad_offset: offsets}, HAND_LANES_META),
    /not in time order/);
});

test("test_decode_throws_for_a_checkpoint_that_is_not_the_sum_of_durations", () => {
  // The checkpoints are the sequential sum of the durations (section 4.3).
  // `decode` checks this, because `blockStart` then starts from its own
  // group starts, which are that same sum.
  const {tables} = buildRandomModel(2048, 5);
  const checkpoints = Float64Array.from(tables.checkpoints);
  checkpoints[1] = checkpoints[1] + 1e-9;
  assert.throws(
    () => SeqLanes.decode(1, {...tables, checkpoints}, HAND_LANES_META),
    /checkpoint 1/);
});

test("test_decode_throws_for_a_missing_table", () => {
  const {tables} = buildHandModel();
  const {checkpoints, ...missing} = tables;
  assert.throws(() => SeqLanes.decode(1, missing, HAND_LANES_META));
});

// ---- blockStart -------------------------------------------------------------

test("test_block_start_is_a_sequential_sum_from_zero_exactly", () => {
  const {model} = buildHandModel();
  assert.equal(SeqLanes.blockStart(model, 0), 0);
  assert.equal(SeqLanes.blockStart(model, 1), 0.002);
  assert.equal(SeqLanes.blockStart(model, 2), 0.005);
  assert.equal(SeqLanes.blockStart(model, 3), 0.0075);
  assert.equal(SeqLanes.blockStart(model, 4), 0.0085);
});

test("test_block_start_is_exact_across_a_checkpoint_boundary", () => {
  // 2500 blocks: checkpoints at block 0, 1024 and 2048 (section 4.2), so
  // this crosses two checkpoint boundaries. The reference value for each
  // block is a plain sequential sum from 0.0, the same one `durationS`
  // itself is built from in `buildRandomModel`/`decode`: since it is built
  // by the same forward, one-duration-at-a-time addition as `blockStart`
  // (section 4.3), and floating-point addition of the same two operands
  // always gives the same bit pattern, the two must agree exactly, with no
  // tolerance.
  const nBlocks = 2500;
  const {tables, model} = buildRandomModel(nBlocks, 11);
  assert.equal(tables.checkpoints.length, 3);

  let want = 0.0;
  for (let i = 0; i < nBlocks; i++) {
    assert.equal(SeqLanes.blockStart(model, i), want, `block ${i}`);
    want += tables.durations[tables.duration_index[i]];
  }
});

// ---- blockAt ------------------------------------------------------------

test("test_block_at_before_the_file_returns_block_zero", () => {
  const {model} = buildHandModel();
  assert.equal(SeqLanes.blockAt(model, -0.001), 0);
});

test("test_block_at_at_a_block_start_returns_that_block", () => {
  const {model} = buildHandModel();
  assert.equal(SeqLanes.blockAt(model, 0), 0);
  assert.equal(SeqLanes.blockAt(model, 0.002), 1);
  assert.equal(SeqLanes.blockAt(model, 0.005), 2);
  assert.equal(SeqLanes.blockAt(model, 0.0075), 3);
  assert.equal(SeqLanes.blockAt(model, 0.0085), 4);
});

test("test_block_at_inside_a_block_returns_that_block", () => {
  const {model} = buildHandModel();
  assert.equal(SeqLanes.blockAt(model, 0.0019), 0);
  assert.equal(SeqLanes.blockAt(model, 0.0086), 4);
});

test("test_block_at_at_the_end_of_the_file_returns_the_last_nonzero_block", () => {
  const {model} = buildHandModel();
  assert.equal(SeqLanes.blockAt(model, 0.01), 4);
});

test("test_block_at_past_the_end_of_the_file_returns_the_last_nonzero_block", () => {
  const {model} = buildHandModel();
  assert.equal(SeqLanes.blockAt(model, 0.02), 4);
});

// ---- exactLanes -----------------------------------------------------------
//
// All of these read the whole file [0, 0.01] of `buildHandModel`, except the
// two that ask for a narrower range. Every point is in seconds in the model
// and in ms (`* 1000`) in `exactLanes`'s output, per section 4.3.

test("test_exact_lanes_rf_pulse_with_phase", () => {
  const {model} = buildHandModel();
  const lanes = SeqLanes.exactLanes(model, 0, 0.01);

  const rfMag = lanes.find(l => l.id === "rf_mag");
  // block0 starts at 0; the RF event's delay is 0.0002, its magnitude
  // offsets are [0, 0.0005, 0.001] and its values are [0, 10, 0]. The
  // whole-file polyline also carries the zero point at time 0 and the zero
  // point at the end of the file (0.01 s = 10 ms).
  const magBase = 0 + 0.0002;
  const magOffsets = [0, 0.0005, 0.001], magValues = [0, 10, 0];
  assert.deepEqual(rfMag.segments, [[
    [0, 0],
    ...magOffsets.map((o, i) => [(magBase + o) * 1000, magValues[i]]),
    [10, 0],
  ]]);

  const rfPhase = lanes.find(l => l.id === "rf_phase");
  // One pulse, one phase point: (0 + 0.0002 + 0.0005) s = 0.7 ms.
  assert.deepEqual(rfPhase.segments, [[
    [0.7, Math.PI / 2],
  ]]);
});

test("test_exact_lanes_trapezoid_gradient_block", () => {
  const {model} = buildHandModel();
  const lanes = SeqLanes.exactLanes(model, 0, 0.01);
  const gx = lanes.find(l => l.id === "gx");
  // block1 starts at 0.002; the trapezoid's delay is 0.0001 and its offsets
  // are [0, 0.0005, 0.0015, 0.002] with values [0, 10, 10, 0].
  const base = 0.002 + 0.0001;
  const offsets = [0, 0.0005, 0.0015, 0.002], values = [0, 10, 10, 0];
  assert.deepEqual(gx.segments, [[
    [0, 0],
    ...offsets.map((o, i) => [(base + o) * 1000, values[i]]),
    [10, 0],
  ]]);
});

test("test_exact_lanes_arbitrary_gradient_block", () => {
  const {model} = buildHandModel();
  const lanes = SeqLanes.exactLanes(model, 0, 0.01);
  const gy = lanes.find(l => l.id === "gy");
  // block2 starts at 0.005; the arbitrary gradient's delay is 0.00005 and
  // its offsets are [0, 0.0004, 0.0012, 0.002] with values [0, -3, -6, 0].
  const base = 0.005 + 0.00005;
  const offsets = [0, 0.0004, 0.0012, 0.002], values = [0, -3, -6, 0];
  assert.deepEqual(gy.segments, [[
    [0, 0],
    ...offsets.map((o, i) => [(base + o) * 1000, values[i]]),
    [10, 0],
  ]]);
});

test("test_exact_lanes_adc_window", () => {
  const {model} = buildHandModel();
  const lanes = SeqLanes.exactLanes(model, 0, 0.01);
  const adc = lanes.find(l => l.id === "adc");
  // block3 starts at 0.0075; the ADC's delay is 0.00002 and its length is
  // 0.0006.
  const a0 = 0.0075 + 0.00002, a1 = a0 + 0.0006;
  assert.deepEqual(adc.windows, [[a0 * 1000, a1 * 1000]]);
});

test("test_exact_lanes_zero_pads_when_a_lane_has_no_event", () => {
  const {model} = buildHandModel();
  const lanes = SeqLanes.exactLanes(model, 0, 0.01);
  // gz has no event anywhere in the file: its whole-file segment is just
  // the two zero pad points, at time 0 and at the end of the file.
  const gz = lanes.find(l => l.id === "gz");
  assert.deepEqual(gz.segments, [[[0, 0], [10, 0]]]);
});

test("test_exact_lanes_range_that_cuts_a_block", () => {
  const {model} = buildHandModel();
  // [0.0021, 0.0049] s is strictly inside block 1 (the gx trapezoid): all 4
  // of its points are in range. The "before" neighbour is the zero point at
  // time 0 (nothing on the gx lane before the trapezoid), and the "after"
  // neighbour is the zero point at the end of the file (nothing on the gx
  // lane after it).
  const lanes = SeqLanes.exactLanes(model, 0.0021, 0.0049);
  const gx = lanes.find(l => l.id === "gx");
  const base = 0.002 + 0.0001;
  const offsets = [0, 0.0005, 0.0015, 0.002], values = [0, 10, 10, 0];
  assert.deepEqual(gx.segments, [[
    [0, 0],
    ...offsets.map((o, i) => [(base + o) * 1000, values[i]]),
    [10, 0],
  ]]);
});

// ---- minMaxLanes: brute-force helpers --------------------------------------
//
// These recompute each bin the slow way, straight from the exact whole-file
// points that `exactLanes` gives, and compare against `minMaxLanes`'s
// output. Ported from the scratchpad's `validate_minmax.js` (line lanes)
// and `validate_phase_adc.js` (RF phase and ADC), which already validated
// this approach against `seq_lanes.js`.

// `numpy.interp`'s formula (section 4.4, item 2): the value of `pts` (an
// array of [x, y] pairs sorted by x) at `x`, clamped at the ends.
function numpyInterp(pts, x) {
  if (!pts.length) return null;
  if (x <= pts[0][0]) return pts[0][1];
  if (x >= pts[pts.length - 1][0]) return pts[pts.length - 1][1];
  for (let j = 0; j + 1 < pts.length; j++) {
    if (pts[j][0] <= x && x <= pts[j + 1][0]) {
      const [x0, y0] = pts[j], [x1, y1] = pts[j + 1];
      return x1 === x0 ? y1 : y0 + (y1 - y0) / (x1 - x0) * (x - x0);
    }
  }
  return null;
}

// Interpolated edge values need about 1e-12 relative tolerance: `minMaxLanes`
// and this brute-force check reach the same mathematical value by different
// sequences of floating-point operations (a segment tree of group extremes
// against a linear scan of every point), so they need not always land on the
// same bit pattern.
function relClose(a, b) {
  return Math.abs(a - b) <= 1e-12 * Math.max(1, Math.abs(a), Math.abs(b));
}

// The brute-force minimum and maximum of line lane `laneId` (one of
// "rf_mag", "gx", "gy", "gz") in each of `bins` bins over [t0, t1], from the
// exact whole-file polyline, with `numpyInterp` at the bin edges. Returns
// one entry for each bin: {want: [lo, hi] | null, hadPoint: bool}, where
// `hadPoint` is true only when an actual point of the polyline (not just an
// edge interpolation) fell inside the bin.
function bruteForceLineWant(model, laneId, t0, t1, bins) {
  const idx = model.lanesMeta.findIndex(m => m.id === laneId);
  const poly = SeqLanes.exactLanes(model, 0, model.durationS)[idx].segments[0]
    .map(([tm, v]) => [tm / 1000, v]);
  const out = [];
  for (let k = 0; k < bins; k++) {
    const e0 = t0 + (t1 - t0) * k / bins, e1 = t0 + (t1 - t0) * (k + 1) / bins;
    const last = k === bins - 1;
    let lo = Infinity, hi = -Infinity, hadPoint = false;
    for (const [ts, v] of poly) {
      const inBin = last ? (ts >= e0 && ts <= e1) : (ts >= e0 && ts < e1);
      if (inBin) { if (v < lo) lo = v; if (v > hi) hi = v; hadPoint = true; }
    }
    for (const e of [e0, e1]) {
      const v = numpyInterp(poly, e);
      if (v !== null) { if (v < lo) lo = v; if (v > hi) hi = v; }
    }
    out.push(hi === -Infinity ? {want: null, hadPoint} : {want: [lo, hi], hadPoint});
  }
  return out;
}

// The {bin-start-ms: [lo, hi]} map that `minMaxLanes` gave for one line
// lane, read out of its single segment's (edge, min), (centre, max) pairs.
function gotLineBins(minMaxLane) {
  const map = new Map();
  for (const seg of minMaxLane.segments) {
    for (let p = 0; p + 1 < seg.length; p += 2) map.set(seg[p][0], [seg[p][1], seg[p + 1][1]]);
  }
  return map;
}

// Compares `minMaxLanes(model, t0, t1, bins)` for one line lane against
// `bruteForceLineWant`. Returns an array of problem strings (empty when
// every bin matches).
function lineLaneProblems(model, laneId, t0, t1, bins) {
  const idx = model.lanesMeta.findIndex(m => m.id === laneId);
  const want = bruteForceLineWant(model, laneId, t0, t1, bins);
  const got = SeqLanes.minMaxLanes(model, t0, t1, bins)[idx];
  assert.equal(got.minmax, true, `${laneId}: missing minmax key`);
  const gotMap = gotLineBins(got);
  const problems = [];
  for (let k = 0; k < bins; k++) {
    const e0 = t0 + (t1 - t0) * k / bins;
    const have = gotMap.get(e0 * 1000) || null;
    const w = want[k].want;
    if (w === null && have === null) continue;
    if (w === null || have === null) {
      problems.push(`${laneId} bin ${k}: want ${JSON.stringify(w)} have ${JSON.stringify(have)}`);
      continue;
    }
    if (!relClose(w[0], have[0]) || !relClose(w[1], have[1])) {
      problems.push(`${laneId} bin ${k}: want [${w}] have [${have}]`);
    }
  }
  return problems;
}

// The same idea for the RF phase lane: the brute force works over each
// pulse's own points separately (an edge value only counts when it falls
// between two points of the same pulse, section 4.4 item 2), and compares
// against `minMaxLanes`'s phase output the same way as a line lane.
function phaseLaneProblems(model, t0, t1, bins) {
  const idx = model.lanesMeta.findIndex(m => m.id === "rf_phase");
  const pulses = SeqLanes.exactLanes(model, 0, model.durationS)[idx].segments
    .map(seg => seg.map(([tm, v]) => [tm / 1000, v]));
  const got = SeqLanes.minMaxLanes(model, t0, t1, bins)[idx];
  assert.equal(got.minmax, true, "rf_phase: missing minmax key");
  const gotMap = gotLineBins(got);
  const problems = [];
  for (let k = 0; k < bins; k++) {
    const e0 = t0 + (t1 - t0) * k / bins, e1 = t0 + (t1 - t0) * (k + 1) / bins;
    const last = k === bins - 1;
    let lo = Infinity, hi = -Infinity;
    for (const pulse of pulses) {
      for (const [ts, v] of pulse) {
        const inBin = last ? (ts >= e0 && ts <= e1) : (ts >= e0 && ts < e1);
        if (inBin) { if (v < lo) lo = v; if (v > hi) hi = v; }
      }
      for (const e of [e0, e1]) {
        for (let j = 0; j + 1 < pulse.length; j++) {
          const [x0, y0] = pulse[j], [x1, y1] = pulse[j + 1];
          if (x0 <= e && e <= x1) {
            const v = x1 === x0 ? y1 : y0 + (y1 - y0) / (x1 - x0) * (e - x0);
            if (v < lo) lo = v; if (v > hi) hi = v;
            break;
          }
        }
      }
    }
    const want = hi === -Infinity ? null : [lo, hi];
    const have = gotMap.get(e0 * 1000) || null;
    if (want === null && have === null) continue;
    const ok = want !== null && have !== null && relClose(want[0], have[0]) && relClose(want[1], have[1]);
    if (!ok) problems.push(`rf_phase bin ${k}: want ${JSON.stringify(want)} have ${JSON.stringify(have)}`);
  }
  return problems;
}

// The same idea for the ADC lane: a bin is "on" when a whole-file ADC
// window overlaps it, runs of "on" bins are merged into one window (section
// 4.4, item 2), and the result is compared against `minMaxLanes`'s windows.
function adcLaneProblems(model, t0, t1, bins) {
  const idx = model.lanesMeta.findIndex(m => m.id === "adc");
  const wins = SeqLanes.exactLanes(model, 0, model.durationS)[idx].windows
    .map(([a, b]) => [a / 1000, b / 1000]);
  const got = SeqLanes.minMaxLanes(model, t0, t1, bins)[idx];
  assert.equal(got.minmax, true, "adc: missing minmax key");
  const onBins = [];
  for (let k = 0; k < bins; k++) {
    const e0 = t0 + (t1 - t0) * k / bins, e1 = t0 + (t1 - t0) * (k + 1) / bins;
    const last = k === bins - 1;
    onBins.push(wins.some(([a, b]) => (last ? b >= e0 && a <= e1 : b >= e0 && a < e1)));
  }
  const wantRuns = [];
  let run = -1;
  for (let k = 0; k < bins; k++) {
    if (onBins[k] && run < 0) run = k;
    if (!onBins[k] && run >= 0) { wantRuns.push([run, k]); run = -1; }
  }
  if (run >= 0) wantRuns.push([run, bins]);
  const edge = k => (t0 + (t1 - t0) * k / bins) * 1000;
  const wantMs = wantRuns.map(([a, b]) => [edge(a), edge(b)]);
  const haveMs = got.windows;
  if (JSON.stringify(wantMs) === JSON.stringify(haveMs)) return [];
  return [`adc: want ${JSON.stringify(wantMs)} have ${JSON.stringify(haveMs)}`];
}

test("test_exact_lanes_range_with_no_event_still_returns_neighbour_points", () => {
  const {model} = buildHandModel();
  // [0.009, 0.0095] s is inside block 4 (the empty delay block): no gx
  // point is in range, but the neighbouring points still come: the last gx
  // point before (the end of the block-1 trapezoid, at 0.0041 s) and the
  // first after (the zero point at the end of the file, since nothing
  // follows).
  const lanes = SeqLanes.exactLanes(model, 0.009, 0.0095);
  const gx = lanes.find(l => l.id === "gx");
  const lastPointMs = (0.002 + 0.0001 + 0.002) * 1000; // block1's last point
  assert.deepEqual(gx.segments, [[[lastPointMs, 0], [10, 0]]]);
});

// ---- minMaxLanes: brute-force comparisons ----------------------------------

test("test_min_max_lanes_matches_brute_force_for_line_lanes_over_several_views", () => {
  // The same models and views as the scratchpad's `validate_minmax.js`,
  // which already found 0 mismatches for these: a whole-ish view and a
  // zoomed-in view of a 300-block model, a whole-file and a zoomed-in view
  // of a 3000-block model (crossing the first checkpoint boundary once,
  // since 3000 > 1024), and an odd bin count over 2500 blocks (crossing the
  // checkpoint boundary at 1024 and 2048).
  const cases = [
    [300, 7, 0, 0.3, 40],
    [300, 7, 0.05, 0.15, 25],
    [3000, 99, 0, 7.0, 60],
    [3000, 99, 1.0, 1.05, 30],
    [2500, 11, 0, 5.0, 137],
  ];
  const laneIds = ["rf_mag", "gx", "gy", "gz"];
  for (const [nBlocks, seed, t0, t1, bins] of cases) {
    const {model} = buildRandomModel(nBlocks, seed);
    for (const laneId of laneIds) {
      const problems = lineLaneProblems(model, laneId, t0, t1, bins);
      assert.deepEqual(problems, [], `nBlocks=${nBlocks} seed=${seed} [${t0},${t1}] bins=${bins}`);
    }
  }
});

test("test_min_max_lanes_matches_brute_force_for_the_rf_phase_lane", () => {
  const cases = [
    [300, 7, 0, 0.3, 40],
    [300, 7, 0.05, 0.15, 25],
    [3000, 99, 0, 7.0, 60],
    [2500, 11, 0, 5.0, 137],
  ];
  for (const [nBlocks, seed, t0, t1, bins] of cases) {
    const {model} = buildRandomModel(nBlocks, seed);
    const problems = phaseLaneProblems(model, t0, t1, bins);
    assert.deepEqual(problems, [], `nBlocks=${nBlocks} seed=${seed} [${t0},${t1}] bins=${bins}`);
  }
});

test("test_min_max_lanes_matches_brute_force_for_adc_windows", () => {
  const cases = [
    [300, 7, 0, 0.3, 40],
    [300, 7, 0.05, 0.15, 25],
    [3000, 99, 0, 7.0, 60],
    [2500, 11, 0, 5.0, 137],
  ];
  for (const [nBlocks, seed, t0, t1, bins] of cases) {
    const {model} = buildRandomModel(nBlocks, seed);
    const problems = adcLaneProblems(model, t0, t1, bins);
    assert.deepEqual(problems, [], `nBlocks=${nBlocks} seed=${seed} [${t0},${t1}] bins=${bins}`);
  }
});

test("test_min_max_lanes_matches_brute_force_across_a_checkpoint_boundary", () => {
  // 2500 blocks crosses both the 1024 and the 2048 checkpoint boundary
  // (section 4.2). A whole-file view with many bins puts several bin edges
  // inside the second and third checkpoint segments.
  const {model} = buildRandomModel(2500, 23);
  for (const laneId of ["rf_mag", "gx", "gy", "gz"]) {
    const problems = lineLaneProblems(model, laneId, 0, model.durationS, 200);
    assert.deepEqual(problems, [], laneId);
  }
  assert.deepEqual(phaseLaneProblems(model, 0, model.durationS, 200), []);
  assert.deepEqual(adcLaneProblems(model, 0, model.durationS, 200), []);
});

test("test_min_max_lanes_bin_with_no_point_uses_only_edge_values", () => {
  // The hand model's gx trapezoid has its points inside [0.0021, 0.0041] s;
  // no other gx point exists, and the pad points at time 0 and at the end
  // of the file (0.01 s) are themselves gx points of the whole-file
  // polyline. Bin 5, [0.005, 0.006) s (inside block 2, the gy block), holds
  // none of those: it is away from both pads and after the trapezoid, so
  // its minimum and maximum come only from `_edgeValue`'s interpolation at
  // 0.005 and 0.006 s, between the trapezoid's last point (0.0041 s, value
  // 0) and the pad at the end of the file (0.01 s, value 0). That
  // interpolation multiplies by a zero numerator, so the result is exactly
  // 0, with no floating-point rounding.
  const {model} = buildHandModel();
  const bins = 10; // bin width 0.001 s.
  const want = bruteForceLineWant(model, "gx", 0, 0.01, bins);
  const bin5 = want[5];
  assert.equal(bin5.hadPoint, false, "bin 5 must have no gx point in range, edges only");
  assert.deepEqual(bin5.want, [0, 0]);

  const problems = lineLaneProblems(model, "gx", 0, 0.01, bins);
  assert.deepEqual(problems, []);
});

test("test_min_max_lanes_edge_values_follow_the_last_of_repeated_point_times", () => {
  // `buildRepeatedTimeModel`: RF event 1 ends with (0.9 ms, 3) then (0.9 ms,
  // 0), and RF event 2 starts with (5.0 ms, 0) then (5.0 ms, 4). The
  // polyline leaves the first pulse from its LAST point at 0.9 ms (value 0)
  // and enters the second at its FIRST point at 5.0 ms (value 0), so it is 0
  // everywhere in the gap. A whole-file view of 5 bins (width 1.2 ms) puts
  // the edges 1.2, 2.4, 3.6 and 4.8 ms in the gap, none of them on a
  // repeated time. Bins 1 to 3 have no point: their minimum and maximum
  // come only from edge values, which must be exactly 0 (the interpolation
  // between two zero values multiplies by a zero numerator). Taking the
  // FIRST point at 0.9 ms (value 3) instead would give a value near 3.
  const {model} = buildRepeatedTimeModel();
  const bins = 5;
  const idx = model.lanesMeta.findIndex(m => m.id === "rf_mag");
  const got = gotLineBins(SeqLanes.minMaxLanes(model, 0, model.durationS, bins)[idx]);
  for (const k of [1, 2, 3]) {
    const e0 = model.durationS * k / bins;
    assert.deepEqual(got.get(e0 * 1000), [0, 0], `bin ${k}`);
  }
  assert.deepEqual(got.get(0), [0, 5]);
  assert.deepEqual(lineLaneProblems(model, "rf_mag", 0, model.durationS, bins), []);
});

test("test_min_max_lanes_matches_brute_force_inside_long_events", () => {
  // `buildLongEventModel`: bins that hold thousands of points of one event
  // (the pyramid), bins that hold fewer than 2 x 64 (a plain scan), and
  // bin edges that cut inside an event (the binary search), for the line
  // lanes and the RF phase lane.
  const {model} = buildLongEventModel();
  const views = [
    [0, model.durationS, 3],
    [0, model.durationS, 7],
    [0, model.durationS, 50],
    [0.0001, 0.0199, 3],
    [0.003, 0.0171, 333],
    [0.0301, 0.0599, 11],
    [0.0301, 0.0599, 1],
    [0.0301, 0.0599, 2],
    [0.0301, 0.0599, 5],
    [0.0301, 0.0599, 13],
    [0.02, 0.05, 1],
    [0.0337, 0.0521, 3],
  ];
  for (const [t0, t1, bins] of views) {
    const where = `[${t0}, ${t1}] bins=${bins}`;
    for (const laneId of ["rf_mag", "gx", "gy"]) {
      assert.deepEqual(lineLaneProblems(model, laneId, t0, t1, bins), [], `${laneId} ${where}`);
    }
    assert.deepEqual(phaseLaneProblems(model, t0, t1, bins), [], `rf_phase ${where}`);
  }
});

test("test_min_max_lanes_edge_on_a_repeated_point_time", () => {
  // One 5 ms block with a gx event whose points are (0, 0), (2.5 ms, 1),
  // (2.5 ms, 9), (5 ms, 0): the polyline rises to 1, jumps to 9 at 2.5 ms,
  // and falls to 0. With 2 bins over [0, 5 ms], the edge between them is
  // exactly 2.5 ms (0.005 * 1 / 2 has no rounding), on the two points.
  // - Bin 0, [0, 2.5 ms), holds only (0, 0); the line in it reaches 1 at
  //   its right end. Its edge value at 2.5 ms must be the FIRST point there
  //   (1), not the last (9, which `numpy.interp` would give).
  // - Bin 1, [2.5 ms, 5 ms], must hold both points at 2.5 ms: its maximum
  //   9 comes only from the point (2.5 ms, 9), because both of its edge
  //   values are 1 and 0. A search that misses points exactly at a bin's
  //   start edge gives 1 here.
  const tables = {
    duration_index: Uint8Array.from([0]),
    durations: Float64Array.from([0.005]),
    checkpoints: Float64Array.from([0.0]),
    rf: Uint8Array.from([0]),
    gx: Uint8Array.from([1]),
    gy: Uint8Array.from([0]),
    gz: Uint8Array.from([0]),
    adc: Uint8Array.from([0]),
    rf_delay: Float64Array.from([]),
    rf_mag_n: Uint32Array.from([]),
    rf_mag_offset_at: Uint32Array.from([]),
    rf_mag_at: Uint32Array.from([]),
    rf_mag_offset: Float64Array.from([]),
    rf_mag: Float64Array.from([]),
    rf_phase_n: Uint32Array.from([]),
    rf_phase_offset_at: Uint32Array.from([]),
    rf_phase_at: Uint32Array.from([]),
    rf_phase_offset: Float64Array.from([]),
    rf_phase: Float64Array.from([]),
    grad_delay: Float64Array.from([0.0]),
    grad_n: Uint32Array.from([4]),
    grad_offset_at: Uint32Array.from([0]),
    grad_at: Uint32Array.from([0]),
    grad_offset: Float64Array.from([0, 0.0025, 0.0025, 0.005]),
    grad_value: Float64Array.from([0, 1, 9, 0]),
    adc_delay: Float64Array.from([]),
    adc_length: Float64Array.from([]),
  };
  const model = SeqLanes.decode(1, tables, HAND_LANES_META);
  const idx = model.lanesMeta.findIndex(m => m.id === "gx");
  assert.equal(0.005 * 1 / 2, 0.0025);
  const got = gotLineBins(SeqLanes.minMaxLanes(model, 0, 0.005, 2)[idx]);
  assert.deepEqual(got.get(0), [0, 1], "bin 0");
  assert.deepEqual(got.get(2.5), [0, 9], "bin 1");
});

test("test_min_max_lanes_rf_phase_gap_splits_into_two_segments", () => {
  // `buildPhaseGapModel`'s two RF pulses (at 0.4 ms and 3.4 ms) are
  // separated by an empty block; with a whole-file view of 4 bins (bin
  // width 1 ms), the two middle bins have no phase value at all (no point
  // of either pulse and no edge inside one pulse's own points, since each
  // pulse has only a single phase point, section 4.4 item 2). A bin with no
  // value ends a segment, and the next bin with a value starts a new one,
  // so the phase lane's output must have exactly two one-bin segments.
  const {model} = buildPhaseGapModel();
  const bins = 4;
  const idx = model.lanesMeta.findIndex(m => m.id === "rf_phase");
  const got = SeqLanes.minMaxLanes(model, 0, model.durationS, bins)[idx];
  assert.equal(got.segments.length, 2, JSON.stringify(got.segments));

  const problems = phaseLaneProblems(model, 0, model.durationS, bins);
  assert.deepEqual(problems, []);
});

test("test_min_max_lanes_adc_windows_closer_than_one_bin_merge_into_one_window", () => {
  // `buildAdcCloseModel`'s two ADC windows are 0.7 ms apart; with a
  // whole-file view of 4 bins (bin width 1 ms), the first window falls in
  // bin 1 and the second in bin 2, adjacent bins with no "off" bin between
  // them. `minMaxLanes` therefore reports one merged window covering both,
  // wider than either physical window, rather than two separate ones.
  const {model} = buildAdcCloseModel();
  const bins = 4;
  const idx = model.lanesMeta.findIndex(m => m.id === "adc");
  const got = SeqLanes.minMaxLanes(model, 0, model.durationS, bins)[idx];
  assert.equal(got.windows.length, 1, JSON.stringify(got.windows));

  const problems = adcLaneProblems(model, 0, model.durationS, bins);
  assert.deepEqual(problems, []);
});

// ---- lanesFor: the exact/min-max switch ------------------------------------

test("test_lanes_for_switches_from_exact_to_min_max_at_the_point_limit", () => {
  // `buildPointBudgetModel` gives every block exactly 8 points, so
  // `EXACT_POINT_LIMIT` (20000) is an exact multiple: 2500 blocks. A view
  // ending at the midpoint of block 2499 (the 2500th block, 0-based) holds
  // blocks 0..2499, exactly 20000 points; one more block (ending at the
  // midpoint of block 2500) holds 20008 points, over the limit.
  assert.equal(SeqLanes.EXACT_POINT_LIMIT, 20000);
  assert.equal(POINTS_PER_BLOCK * 2500, SeqLanes.EXACT_POINT_LIMIT);

  const {model} = buildPointBudgetModel(2600);
  const half = model.tables.durations[0] / 2;
  const tAtLimit = SeqLanes.blockStart(model, 2499) + half;
  const tOverLimit = SeqLanes.blockStart(model, 2500) + half;

  assert.equal(SeqLanes.pointsIn(model, 0, tAtLimit), 20000);
  assert.equal(SeqLanes.pointsIn(model, 0, tOverLimit), 20008);

  const bins = 100;
  const atLimit = SeqLanes.lanesFor(model, [0, tAtLimit * 1000], bins);
  assert.equal(atLimit.exact, true);
  assert.deepEqual(atLimit.lanes, SeqLanes.exactLanes(model, 0, tAtLimit));

  const overLimit = SeqLanes.lanesFor(model, [0, tOverLimit * 1000], bins);
  assert.equal(overLimit.exact, false);
  assert.deepEqual(overLimit.lanes, SeqLanes.minMaxLanes(model, 0, tOverLimit, bins));
});
