const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const R = require(
  path.join(__dirname, "..", "..", "src", "pulseq_reports", "assets", "rf_profiles.js")
);

// ---- Fakes ------------------------------------------------------------------
//
// `RfProfiles` reads a sequence view (the methods of `SeqLanes.sequenceView`) and the
// file data of the card (`RfProfiles.fileData` over the columns of
// `cards.rf_profile._rf_table`). The tests build both by hand: `newSeq` collects RF rows,
// gradient events (Hz/m, as the diagram tables keep them), ADC events and blocks, and
// `build` returns {view, file}. The pulses and gradients follow the Python tests
// (tests/test_rf_profiles.py): a 1 ms sinc of 200 samples at 5 µs from 100 µs, on a
// trapezoid whose flat top holds the whole RF.

const W = 5e-3; // m, the SliceThickness definition
const SINC_N = 200;
const SINC_DT = 5e-6;
const SINC_BW = 4 / (SINC_N * SINC_DT); // Hz: time-bandwidth product 4 over 1 ms
const RF_DELAY = 100e-6;
const CRUSHER = 4 / W; // 1/m: four cycles across W
const GX = 250 / 640e-6; // Hz/m: the readout amplitude
const TO_CENTRE = GX * (100e-6 / 2 + 320e-6); // 1/m: readout moment to the ADC centre

function trap(amp, rise, flat, fall = rise, delay = 0) {
  return {delay, offsets: [0, rise, rise + flat, rise + flat + fall], values: [0, amp, amp, 0]};
}

function hardShape(flip, n, dt) {
  return new Array(n).fill(flip / (2 * Math.PI * n * dt));
}

// A Hann-windowed sinc with time-bandwidth product 4, scaled to the flip angle.
function sincShape(flip, n = SINC_N, dt = SINC_DT) {
  const T = n * dt;
  const re = [];
  for (let k = 0; k < n; k++) {
    const t = (k + 0.5) * dt - T / 2;
    const x = (4 * t) / T;
    const sinc = x === 0 ? 1 : Math.sin(Math.PI * x) / (Math.PI * x);
    re.push(sinc * (0.5 + 0.5 * Math.cos((2 * Math.PI * t) / T)));
  }
  const scale = flip / (2 * Math.PI * dt * re.reduce((s, v) => s + v, 0));
  return re.map(v => v * scale);
}

// The columns of `rf_table` for the RF rows (dense RF index k = row + 1).
function rfTables(rows) {
  const n = rows.length;
  const t = {
    key: new Uint32Array(n), use: new Uint8Array(n), delay: new Float64Array(n),
    shape_dur: new Float64Array(n), center: new Float64Array(n), dt: new Float64Array(n),
    shape_at: new Uint32Array(n), shape_n: new Uint32Array(n),
    freq_offset_hz: new Float64Array(n), freq_ppm: new Float64Array(n),
    phase_offset_rad: new Float64Array(n), phase_ppm: new Float64Array(n),
  };
  const re = [], im = [];
  rows.forEach((r, i) => {
    t.key[i] = r.key ?? i;
    t.use[i] = R.USES.indexOf(r.use);
    t.delay[i] = r.delay;
    t.dt[i] = r.dt;
    t.shape_dur[i] = r.re.length * r.dt;
    t.center[i] = t.shape_dur[i] / 2;
    t.shape_at[i] = re.length;
    t.shape_n[i] = r.re.length;
    t.freq_offset_hz[i] = r.freq ?? 0;
    t.freq_ppm[i] = r.freqPpm ?? 0;
    t.phase_offset_rad[i] = r.phase ?? 0;
    t.phase_ppm[i] = r.phasePpm ?? 0;
    re.push(...r.re);
    im.push(...(r.im ?? new Array(r.re.length).fill(0)));
  });
  t.shape_re = Float64Array.from(re);
  t.shape_im = Float64Array.from(im);
  return t;
}

// A fake sequence view: the methods of `SeqLanes.sequenceView` over hand-made arrays.
function fakeView(blocks, grads, adcs, rows) {
  const starts = [];
  let t = 0;
  for (const b of blocks) {
    starts.push(t);
    t += b.dur;
  }
  const at = i => {
    if (!(i >= 0 && i < blocks.length)) throw new RangeError(`block ${i} is out of range`);
    return blocks[i];
  };
  return Object.freeze({
    numBlocks: blocks.length,
    durationS: t,
    blockStart: i => (at(i), starts[i]),
    blockDuration: i => at(i).dur,
    events: i => {
      const b = at(i);
      return {rf: b.rf ?? 0, gx: b.gx ?? 0, gy: b.gy ?? 0, gz: b.gz ?? 0, adc: b.adc ?? 0};
    },
    gradEvent: k => ({delayS: grads[k - 1].delay, offsetsS: Float64Array.from(grads[k - 1].offsets),
      values: Float64Array.from(grads[k - 1].values)}),
    adcEvent: k => ({delayS: adcs[k - 1].delay, lengthS: adcs[k - 1].length}),
    rfDelayS: k => rows[k - 1].delay,
  });
}

// The dense index of `item` in `list`: equal events share one index, as pypulseq's
// libraries share one id (so blocks with the same gradient have the same pulse key).
function denseIndex(list, item) {
  const text = JSON.stringify(item);
  const k = list.findIndex(other => JSON.stringify(other) === text);
  if (k >= 0) return k + 1;
  list.push(item);
  return list.length;
}

// The group of the file data that most tests use: the proton gamma and B0 of 3 T.
const GAMMA = 42.576e6;
const GROUP = {gamma_hz_per_t: GAMMA, b0_t: 3, names: [], color: null};

function newSeq({thickness = W, fov = null, groups = [GROUP]} = {}) {
  const rows = [], grads = [], adcs = [], blocks = [];
  const seq = {
    rf: row => denseIndex(rows, row),
    grad: g => denseIndex(grads, g),
    adc: a => denseIndex(adcs, a),
    block(b) { blocks.push(b); return blocks.length - 1; },
    // An RF pulse on its select trapezoid (flat top from RF_DELAY to RF_DELAY + 1 ms):
    // a sinc for a thickness, or a hard pulse (0.5 ms) without a gradient.
    pulse(use, flip, {axis = "gz", thickness: w = W, hard = false, freq = 0, phase = 0,
      freqPpm = 0, phasePpm = 0, key, scale = null} = {}) {
      if (hard) {
        const row = seq.rf({use, delay: RF_DELAY, dt: SINC_DT, re: hardShape(flip, 100, SINC_DT),
          freq, phase, freqPpm, phasePpm, key});
        return seq.block({dur: 0.6e-3, rf: row});
      }
      const row = seq.rf({use, delay: RF_DELAY, dt: SINC_DT, re: sincShape(flip), freq, phase,
        freqPpm, phasePpm, key});
      const G = SINC_BW / w;
      const block = {dur: 1.2e-3, rf: row};
      if (scale === null) block[axis] = seq.grad(trap(G, 100e-6, 1000e-6));
      else for (const [a, s] of Object.entries(scale)) block[a] = seq.grad(trap(G * s, 100e-6, 1000e-6));
      return seq.block(block);
    },
    // The rephaser of a pulse on `axis` (area -(the moment from the RF centre to the end
    // of the fall)) with an optional readout prephaser on x.
    rephaser(axis = "gz", prephase = 0) {
      const block = {dur: 0.6e-3, [axis]: seq.grad(trap(-1.1 * (SINC_BW / W), 100e-6, 400e-6))};
      if (prephase !== 0) block.gx = seq.grad(trap((prephase * TO_CENTRE) / 500e-6, 100e-6, 400e-6));
      return seq.block(block);
    },
    crusher(axis) {
      return seq.block({dur: 0.6e-3, [axis]: seq.grad(trap(CRUSHER / 500e-6, 100e-6, 400e-6))});
    },
    readout() {
      return seq.block({dur: 0.84e-3, gx: seq.grad(trap(GX, 100e-6, 640e-6)),
        adc: seq.adc({delay: 100e-6, length: 640e-6})});
    },
    build() {
      const first = blocks.findIndex(b => b.rf);
      const entry = {labeled: true, slice_thickness_m: thickness, fov_m: fov,
        groups, first_rf_block: first < 0 ? null : first};
      return {view: fakeView(blocks, grads, adcs, rows), file: R.fileData(entry, rfTables(rows))};
    },
  };
  return seq;
}

// A GRE: [RF + gz, rephaser + prephaser, readout + ADC, spoiler] for each TR; `dummies`
// TRs first without the ADC. Each TR has its own RF row with a new phase (RF spoiling)
// and the same `key` (the RF event without its phase offsets).
function gre(numTrs = 3, dummies = 0) {
  const seq = newSeq();
  for (let tr = 0; tr < dummies + numTrs; tr++) {
    seq.pulse("excitation", Math.PI / 2, {phase: 0.3 * tr, key: 0});
    seq.rephaser("gz", -1);
    if (tr >= dummies) seq.readout();
    else seq.block({dur: 0.84e-3, gx: seq.grad(trap(GX, 100e-6, 640e-6))});
    seq.crusher("gz");
  }
  return seq.build();
}

// A spin echo: excitation on z, rephaser and prephaser, then for each refocusing pulse
// a crusher, the pulse (on `refAxis`, or hard) and a crusher, then the readout. Play
// indexes for numRef 1: 0 excitation, 1 rephaser, 2 crusher, 3 refocusing, 4 crusher,
// 5 readout.
function spinEcho(refAxis = "gy", {refThickness = W, hard = false, numRef = 1, fov = null} = {}) {
  const seq = newSeq({fov});
  seq.pulse("excitation", Math.PI / 2);
  seq.rephaser("gz", 1);
  for (let k = 0; k < numRef; k++) {
    seq.crusher(refAxis);
    seq.pulse("refocusing", Math.PI, {axis: refAxis, thickness: refThickness, hard, phase: Math.PI / 2});
    seq.crusher(refAxis);
  }
  seq.readout();
  return seq.build();
}

// Arbitrary gradients on x and y whose direction turns one time in 1 ms (as
// `_turning_gradients` of the Python tests), under a 0.8 ms hard pulse.
function turning({fov = null, thickness = W} = {}) {
  const seq = newSeq({fov, thickness});
  const T = 1e-3, n = 100, A = 2e5;
  const offsets = [0], vx = [0], vy = [0];
  for (let k = 0; k < n; k++) {
    const t = (k + 0.5) * 10e-6;
    const env = A * Math.sin((Math.PI * t) / T);
    offsets.push(t);
    vx.push(env * Math.cos((2 * Math.PI * t) / T));
    vy.push(env * Math.sin((2 * Math.PI * t) / T));
  }
  offsets.push(T); vx.push(0); vy.push(0);
  const row = seq.rf({use: "excitation", delay: RF_DELAY, dt: SINC_DT, re: hardShape(Math.PI / 6, 160, SINC_DT)});
  seq.block({dur: 1e-3, rf: row, gx: seq.grad({delay: 0, offsets, values: vx}),
    gy: seq.grad({delay: 0, offsets, values: vy})});
  seq.readout();
  return seq.build();
}

function assertClose(actual, expected, tol, message) {
  assert.ok(Math.abs(actual - expected) <= tol,
    `${message ?? ""}: ${actual} vs ${expected} (tolerance ${tol})`);
}

function assertSameArray(actual, expected, message) {
  assert.equal(actual.length, expected.length, message);
  for (let i = 0; i < actual.length; i++) {
    if (!Object.is(actual[i], expected[i])) {
      assert.fail(`${message ?? ""}: index ${i}: ${actual[i]} vs ${expected[i]}`);
    }
  }
}

// A direct DFT, with the twiddle of each index product reduced modulo N first (so each
// twiddle is as accurate as one Math.cos).
function directDft(re, im, N = re.length) {
  const wr = new Float64Array(N), wi = new Float64Array(N);
  for (let q = 0; q < N; q++) {
    wr[q] = Math.cos((2 * Math.PI * q) / N);
    wi[q] = -Math.sin((2 * Math.PI * q) / N);
  }
  const xr = new Float64Array(N), xi = new Float64Array(N);
  for (let k = 0; k < N; k++) {
    let sr = 0, si = 0;
    for (let j = 0; j < re.length; j++) {
      const q = (j * k) % N;
      sr += re[j] * wr[q] - im[j] * wi[q];
      si += re[j] * wi[q] + im[j] * wr[q];
    }
    xr[k] = sr;
    xi[k] = si;
  }
  return {re: xr, im: xi};
}

function seeded(seed) {
  let s = seed;
  return () => (s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff - 0.5;
}

// ---- 1. The spin-domain rotation ---------------------------------------------

test("test_spin_domain_hard_pulse_flip_angle_and_precess_sign", () => {
  // A 70° hard pulse (200 samples, phase 0.4 rad) without a gradient, at r = 0 and 0 Hz:
  // |Mxy| = sin(70°) and Mz = cos(70°) within 1e-12 (float rounding of 200 rotations).
  const flip = (70 * Math.PI) / 180, n = 200, dt = 1e-6;
  const amp = flip / (2 * Math.PI * n * dt);
  const sigRe = new Float64Array(n).fill(amp * Math.cos(0.4));
  const sigIm = new Float64Array(n).fill(amp * Math.sin(0.4));
  const {aRe, aIm, bRe, bIm} = R.spinDomain(sigRe, sigIm, dt, new Float64Array(3 * n),
    new Float64Array(3));
  const {mxyRe, mxyIm, mz} = R.magnetization(aRe, aIm, bRe, bIm);
  assertClose(Math.hypot(mxyRe[0], mxyIm[0]), Math.sin(flip), 1e-12, "|Mxy|");
  assertClose(mz[0], Math.cos(flip), 1e-12, "Mz");

  // The same pulse under a z gradient, then 500 samples of zero RF (free precession):
  // `precess` with the moment of those samples gives the same Mxy within 1e-9 (the
  // Python test's tolerance: the rounding of 700 rotations); the opposite sign does not
  // (1e-3), as `test_precess_sign_matches_free_precession_in_spin_domain`.
  const G = 1e5, free = 500, m = 13;
  const positions = new Float64Array(3 * m);
  for (let j = 0; j < m; j++) positions[3 * j + 2] = -0.003 + (0.006 * j) / (m - 1);
  const gradZ = count => {
    const g = new Float64Array(3 * count);
    for (let k = 0; k < count; k++) g[3 * k + 2] = G;
    return g;
  };
  const pulse = R.spinDomain(sigRe, sigIm, dt, gradZ(n), positions);
  const after = R.magnetization(pulse.aRe, pulse.aIm, pulse.bRe, pulse.bIm);
  const extRe = new Float64Array(n + free), extIm = new Float64Array(n + free);
  extRe.set(sigRe);
  extIm.set(sigIm);
  const longer = R.spinDomain(extRe, extIm, dt, gradZ(n + free), positions);
  const expected = R.magnetization(longer.aRe, longer.aIm, longer.bRe, longer.bIm);
  const moment = [0, 0, G * free * dt];
  const good = R.precess(after.mxyRe, after.mxyIm, moment, positions);
  const bad = R.precess(after.mxyRe, after.mxyIm, moment.map(v => -v), positions);
  let worstBad = 0;
  for (let j = 0; j < m; j++) {
    assertClose(good.re[j], expected.mxyRe[j], 1e-9, `precess re ${j}`);
    assertClose(good.im[j], expected.mxyIm[j], 1e-9, `precess im ${j}`);
    worstBad = Math.max(worstBad, Math.hypot(bad.re[j] - expected.mxyRe[j], bad.im[j] - expected.mxyIm[j]));
  }
  assert.ok(worstBad > 1e-3, `the opposite sign must differ: ${worstBad}`);
});

// ---- 2. linspace --------------------------------------------------------------

test("test_linspace_gives_the_numpy_values", () => {
  // Exact (the same float operations). The values are the reprs of numpy 2.5.3:
  //   np.linspace(0.1, 1.7, 6), np.linspace(-0.01, 0.01, 5), np.linspace(-2e-3, 3e-3, 4)
  // For 0.1 .. 1.7, 5 * step + 0.1 is 1.6999999999999997: numpy sets the last value to
  // the end itself, 1.7.
  assert.deepEqual(Array.from(R.linspace(0.1, 1.7, 6)),
    [0.1, 0.41999999999999993, 0.7399999999999999, 1.0599999999999998, 1.38, 1.7]);
  assert.deepEqual(Array.from(R.linspace(-0.01, 0.01, 5)),
    [-0.01, -0.005, 0.0, 0.004999999999999999, 0.01]);
  assert.deepEqual(Array.from(R.linspace(-2e-3, 3e-3, 4)),
    [-0.002, -0.00033333333333333327, 0.0013333333333333335, 0.003]);
});

// ---- 3. The FFT and the RF spectrum ---------------------------------------------

test("test_fft_matches_a_direct_dft_and_the_spectrum_fwhm_matches_numpy", () => {
  // The FFT against a direct DFT for lengths with each kind of factor (4, 2, 3, 5, a
  // small prime 7, and the primes 97 and 131 above the direct-stage limit, done with
  // Bluestein's method): within 1e-12 of the largest magnitude (both are exact up to
  // float rounding, about 1e-15 here).
  const rnd = seeded(7);
  for (const N of [1, 2, 3, 5, 7, 12, 30, 97, 128, 131, 3000]) {
    const re = Float64Array.from({length: N}, rnd), im = Float64Array.from({length: N}, rnd);
    const got = R.fft(re, im), want = directDft(re, im);
    let peak = 0, diff = 0;
    for (let k = 0; k < N; k++) {
      peak = Math.max(peak, Math.hypot(want.re[k], want.im[k]));
      diff = Math.max(diff, Math.hypot(got.re[k] - want.re[k], got.im[k] - want.im[k]));
    }
    assert.ok(diff <= 1e-12 * peak, `N = ${N}: ${diff} vs peak ${peak}`);
  }
  // The zero-padded spectrum (64 DFTs of length n of the pre-twiddled signal) against a
  // direct DFT of the signal padded to 64 n, the same tolerance; n = 97 needs Bluestein.
  for (const n of [7, 12, 97]) {
    const re = Float64Array.from({length: n}, rnd), im = Float64Array.from({length: n}, rnd);
    const mag = R.spectrumMagnitudes(re, im);
    const want = directDft(re, im, 64 * n);
    let peak = 0, diff = 0;
    for (let k = 0; k < 64 * n; k++) {
      const w = Math.hypot(want.re[k], want.im[k]);
      peak = Math.max(peak, w);
      diff = Math.max(diff, Math.abs(mag[k] - w));
    }
    assert.ok(diff <= 1e-12 * peak, `n = ${n}: ${diff} vs peak ${peak}`);
  }
  // A block pulse of 100 samples at 1 µs, as played with 1000 Hz and 0.4 rad: its
  // spectrum FWHM equals numpy's, exactly (the same frequencies, k / (N dt)):
  //   t = (np.arange(100) + 0.5) * 1e-6
  //   rf_profiles._spectrum_fwhm_hz(250.0 * np.exp(1j * (0.4 + 2 * np.pi * 1000.0 * t)), 1e-6)
  // gives 12031.25, and 11875.0 for np.full(100, 250.0 + 0j).
  const seq = newSeq();
  seq.block({dur: 0.2e-3, rf: seq.rf({use: "excitation", delay: 0, dt: 1e-6,
    re: new Array(100).fill(250), freq: 1000, phase: 0.4})});
  seq.block({dur: 0.2e-3, rf: seq.rf({use: "excitation", delay: 0, dt: 1e-6, re: new Array(100).fill(250)})});
  const {view, file} = seq.build();
  const offset = R.blockPulse(view, file, 0), plain = R.blockPulse(view, file, 1);
  assert.equal(R.spectrumFwhmHz(offset.sigRe, offset.sigIm, offset.dtS), 12031.25);
  assert.equal(R.spectrumFwhmHz(plain.sigRe, plain.sigIm, plain.dtS), 11875.0);
});

// ---- 4. unwrap ----------------------------------------------------------------------

test("test_unwrap_matches_numpy", () => {
  // Exact (the same float operations). The steps are 3, -6, exactly π, 0.858, exactly
  // -π, 4.64, -5, 2.7, 6.8, -14: a step of exactly ±π is kept, larger steps are moved
  // by multiples of 2π. The values are the reprs of numpy 2.5.3:
  //   p = np.array([0.0, 3.0, -3.0, -3.0 + np.pi, 1.0, 1.0 - np.pi, 2.5, -2.5, 0.2, 7.0, -7.0])
  //   np.unwrap(p)
  const p = [0.0, 3.0, -3.0, -3.0 + Math.PI, 1.0, 1.0 - Math.PI, 2.5, -2.5, 0.2, 7.0, -7.0];
  assert.equal(p[3] - p[2], Math.PI);
  assert.equal(p[5] - p[4], -Math.PI);
  assert.deepEqual(Array.from(R.unwrap(Float64Array.from(p))), [
    0.0, 3.0, 3.2831853071795862, 6.424777960769379, 7.283185307179586, 4.141592653589793,
    2.5, 3.7831853071795862, 6.483185307179586, 7.000000000000001, 5.5663706143591725,
  ]);
});

// ---- 5. The interval values of a trapezoid -------------------------------------------

test("test_interval_values_of_a_trapezoid_equal_the_hand_means", () => {
  // As the Python test of the same name: RF raster 3 µs (so the corners on the 10 µs
  // raster fall inside hold intervals), a 900 µs RF from 60 µs on a trapezoid of 100 µs
  // ramps and a 500 µs flat top. Relative 1e-12 (float rounding of the interval ends);
  // the flat top exactly (the value of the middle of a flat segment).
  const seq = newSeq();
  const amp = 2e5, rise = 100e-6, flat = 500e-6, dt = 3e-6;
  seq.block({dur: 1e-3, rf: seq.rf({use: "excitation", delay: 60e-6, dt, re: hardShape(0.5, 300, dt)}),
    gz: seq.grad(trap(amp, rise, flat))});
  const {view, file} = seq.build();
  const pulse = R.blockPulse(view, file, 0);
  const A = amp;
  const value = k => pulse.grad[3 * k + 2];
  const interval = k => [60e-6 + k * dt, 60e-6 + (k + 1) * dt];
  const rampUp = t => (A * t) / rise;
  const fall = t => (A * (rise + flat + rise - t)) / rise;
  const rel = (got, want) => assertClose(got, want, 1e-12 * Math.abs(want));
  let [a, b] = interval(0); // [60, 63] µs on the ramp
  rel(value(0), rampUp((a + b) / 2));
  [a, b] = interval(13); // [99, 102] µs: the corner at 100 µs
  rel(value(13), ((100e-6 - a) * (rampUp(a) + A) / 2 + (b - 100e-6) * A) / dt);
  assert.equal(value(80), A); // [300, 303] µs: the flat top
  [a, b] = interval(180); // [600, 603] µs on the fall
  rel(value(180), fall((a + b) / 2));
  [a, b] = interval(213); // [699, 702] µs: the end at 700 µs
  rel(value(213), ((700e-6 - a) * fall(a)) / 2 / dt);
  for (let k = 214; k < 300; k++) assert.equal(value(k), 0);
  for (let k = 0; k < 300; k++) assert.equal(pulse.grad[3 * k] + pulse.grad[3 * k + 1], 0);
  assert.equal(pulse.gradientKind, "one");
  assert.equal(pulse.selectKind, "z");
  assert.equal(pulse.constantGradient, false);
});

// ---- 6. The gradient kinds -------------------------------------------------------------

test("test_gradient_kinds_none_one_oblique_and_changing", () => {
  const seq = newSeq();
  seq.pulse("excitation", Math.PI / 2, {hard: true});
  seq.pulse("excitation", Math.PI / 2);
  seq.pulse("excitation", Math.PI / 2, {scale: {gx: 0.6, gy: 0.8}});
  const {view, file} = seq.build();
  const G = SINC_BW / W;

  // No gradient: kind "none", nothing else.
  const none = R.blockPulse(view, file, 0);
  assert.deepEqual([none.gradientKind, none.selectKind, none.direction, none.selectGradientHzPerM,
    none.constantGradient, none.sliceCentreM], ["none", null, null, null, false, null]);
  // A trapezoid on z whose flat top holds the RF: kind "one" on the logical axis z,
  // constant, each interval the flat-top amplitude (exact: the value of the middle of a
  // flat segment), and G their mean (relative 1e-12: the sum of the 200 values rounds).
  const onZ = R.blockPulse(view, file, 1);
  assert.deepEqual([onZ.gradientKind, onZ.selectKind, Array.from(onZ.direction),
    onZ.constantGradient], ["one", "z", [0, 0, 1], true]);
  for (let k = 0; k < SINC_N; k++) assert.equal(onZ.grad[3 * k + 2], G);
  assertClose(onZ.selectGradientHzPerM, G, 1e-12 * G);
  // The same trapezoid times 0.6 on x and 0.8 on y: kind "one", "select", the unit
  // vector (0.6, 0.8, 0) and G = |mean| within 1e-12 (the scaled values in mT/m round).
  const oblique = R.blockPulse(view, file, 2);
  assert.deepEqual([oblique.gradientKind, oblique.selectKind, oblique.constantGradient],
    ["one", "select", true]);
  assertClose(oblique.direction[0], 0.6, 1e-12);
  assertClose(oblique.direction[1], 0.8, 1e-12);
  assert.equal(oblique.direction[2], 0);
  assertClose(oblique.selectGradientHzPerM, G, 1e-12 * G);
  // A gradient that turns: kind "changing".
  const changing = turning();
  assert.equal(R.blockPulse(changing.view, changing.file, 0).gradientKind, "changing");
  // A bipolar gradient on one axis has a mean of zero: no direction, "changing".
  const bipolar = new Float64Array(6);
  bipolar[2] = 1e5;
  bipolar[5] = -1e5;
  assert.equal(R.gradientKind(bipolar).kind, "changing");
});

// ---- 7. The views -------------------------------------------------------------------------

test("test_views_for_each_kind", () => {
  // "profile", kind "one" with W: the select coordinate from c - 2W to c + 2W (exact),
  // 401 points, c = f / G (relative 1e-12: G is the mean of the interval values).
  const seq = newSeq();
  seq.pulse("excitation", Math.PI / 2, {freq: 800});
  seq.pulse("excitation", Math.PI / 2, {hard: true, freq: -200});
  const {view, file} = seq.build();
  const withW = R.blockPulse(view, file, 0);
  assert.deepEqual(withW.notes, []);
  const c = withW.sliceCentreM;
  assertClose(c, 800 / (SINC_BW / W), 1e-12 * c);
  assert.equal(c, 800 / withW.selectGradientHzPerM);
  assert.deepEqual(R.viewSpec(withW).spec.axes, [{kind: "z", lo: c - 2 * W, hi: c + 2 * W, n: 401}]);

  // Without W: 2 times the thickness from the RF spectrum (its FWHM / |G|) on each
  // side (exact: the same operations), and the note.
  const noW = newSeq({thickness: null});
  noW.pulse("excitation", Math.PI / 2, {freq: 800});
  const nw = noW.build();
  const pulse = R.blockPulse(nw.view, nw.file, 0);
  assert.deepEqual(pulse.notes, [R.REASONS.NO_SLICE_THICKNESS]);
  const half = 2 * (R.spectrumFwhmHz(pulse.sigRe, pulse.sigIm, pulse.dtS) / Math.abs(pulse.selectGradientHzPerM));
  assert.deepEqual(R.viewSpec(pulse, "profile", {n: 51}).spec.axes,
    [{kind: "z", lo: c - half, hi: c + half, n: 51}]);

  // Kind "none": df from f - 2B to f + 2B (B the spectrum FWHM); no z x df and no map.
  const hard = R.blockPulse(view, file, 1);
  const B = R.spectrumFwhmHz(hard.sigRe, hard.sigIm, hard.dtS);
  assert.deepEqual(R.viewSpec(hard).spec.axes, [{kind: "df", lo: -200 - 2 * B, hi: -200 + 2 * B, n: 401}]);
  assert.deepEqual(R.viewSpec(hard, "z_df"), {spec: null, reason: R.REASONS.NO_GRADIENT_Z_DF});
  assert.deepEqual(R.viewSpec(hard, "2d"), {spec: null, reason: R.REASONS.NO_MAP_NONE});

  // "z_df" of kind "one": the select range with 201 points, and df with 201 points
  // centred on 0 Hz, its step |G| times the z step (the operations of the reference).
  const zdf = R.viewSpec(withW, "z_df").spec.axes;
  const step = (Math.abs(withW.selectGradientHzPerM) * ((c + 2 * W) - (c - 2 * W))) / 200;
  assert.deepEqual(zdf, [{kind: "z", lo: c - 2 * W, hi: c + 2 * W, n: 201},
    {kind: "df", lo: -(100 * step), hi: 100 * step, n: 201}]);
  assert.deepEqual(R.viewSpec(withW, "2d"), {spec: null, reason: R.REASONS.NO_MAP_ONE});

  // Kind "changing": no profile, the reason; "2d" with `plane` and `extentM`, with the
  // FOV definition (the two axes with the largest RMS gradient, x and y), and with
  // neither (the reason).
  const t = turning();
  const changing = R.blockPulse(t.view, t.file, 0);
  assert.deepEqual(R.viewSpec(changing), {spec: null, reason: R.REASONS.DIRECTION_CHANGES});
  assert.deepEqual(R.viewSpec(changing, "z_df"), {spec: null, reason: R.REASONS.DIRECTION_CHANGES});
  assert.deepEqual(R.viewSpec(changing, "2d"), {spec: null, reason: R.REASONS.NO_FOV});
  assert.deepEqual(R.viewSpec(changing, "2d", {plane: ["y", "z"], extentM: 0.1}).spec.axes,
    [{kind: "y", lo: -0.05, hi: 0.05, n: R.MAP_POINTS}, {kind: "z", lo: -0.05, hi: 0.05, n: R.MAP_POINTS}]);
  const withFov = turning({fov: [0.2, 0.25, 0.005]});
  const fovPulse = R.blockPulse(withFov.view, withFov.file, 0);
  const spec = R.viewSpec(fovPulse, "2d", {n: 9}).spec;
  assert.deepEqual(spec.axes, [{kind: "x", lo: -0.1, hi: 0.1, n: 9}, {kind: "y", lo: -0.125, hi: 0.125, n: 9}]);
  assert.deepEqual(R.simulate(fovPulse, spec).shape, [9, 9]);
});

// ---- 8. The echo pathway ------------------------------------------------------------------

test("test_echo_pathway_of_a_gre_rephases_the_select_and_readout_moments", () => {
  // The rephaser in the next block cancels the dephasing of the pulse (the moment from
  // the RF centre to the RF end, `half`), and the prephaser the readout moment to the
  // ADC centre: the pathway ends at the ADC of the same TR with sign +1, and its moment
  // is -half on z and 0 on x, within 1e-9 of the moment each cancels (the plan's
  // rephasing tolerance; the float error here is about 1e-15).
  const {view, file} = gre(2);
  const pulse = R.blockPulse(view, file, 4);
  assert.equal(pulse.echoReason, null);
  assert.equal(pulse.echo.adcBlock, 6);
  assert.equal(pulse.echo.sign, 1);
  const half = SINC_BW / W * 0.5e-3;
  assertClose(pulse.echo.momentPerM[2], -half, 1e-9 * half, "z");
  assertClose(pulse.echo.momentPerM[0], 0, 1e-9 * TO_CENTRE, "x");
  assert.equal(pulse.echo.momentPerM[1], 0);
});

test("test_echo_pathway_of_a_spin_echo_has_sign_minus_one", () => {
  // Crushers around the refocusing pulse on y: the sign is -1, the z moment is +half
  // (the conjugation turns the dephasing), and the crusher and readout moments cancel
  // on y and x, within 1e-9 of the moment each cancels.
  const {view, file} = spinEcho("gy");
  const echo = R.blockPulse(view, file, 0).echo;
  assert.equal(echo.adcBlock, 5);
  assert.equal(echo.sign, -1);
  const half = SINC_BW / W * 0.5e-3;
  assertClose(echo.momentPerM[2], half, 1e-9 * half, "z");
  assertClose(echo.momentPerM[1], 0, 1e-9 * CRUSHER, "y");
  assertClose(echo.momentPerM[0], 0, 1e-9 * TO_CENTRE, "x");
  // Only an excitation has a pathway.
  const refocusing = R.blockPulse(view, file, 3);
  assert.deepEqual([refocusing.echo, refocusing.echoReason], [null, null]);
});

test("test_echo_pathway_without_an_adc_before_the_next_excitation", () => {
  // A dummy TR (no ADC) before the next excitation, the end of the file, and a walk
  // longer than `maxBlocks`: no pathway, NO_ADC. The last excitation before the ADC
  // has one.
  const {view, file} = gre(1, 1);
  const dummy = R.blockPulse(view, file, 0);
  assert.deepEqual([dummy.echo, dummy.echoReason], [null, R.REASONS.NO_ADC]);
  assert.equal(R.blockPulse(view, file, 4).echo.adcBlock, 6);
  assert.equal(R.blockPulse(view, file, 4, {maxBlocks: 1}).echoReason, R.REASONS.NO_ADC);
  const end = newSeq();
  end.pulse("excitation", Math.PI / 2);
  end.rephaser("gz");
  const e = end.build();
  assert.equal(R.blockPulse(e.view, e.file, 0).echoReason, R.REASONS.NO_ADC);
});

test("test_echo_pathway_stops_at_a_saturation_pulse", () => {
  // A saturation pulse between an excitation and its ADC: no pathway,
  // OTHER_RF_BEFORE_ADC.
  const seq = newSeq();
  seq.pulse("excitation", Math.PI / 2);
  seq.rephaser("gz");
  seq.pulse("saturation", Math.PI / 2, {hard: true});
  seq.readout();
  const {view, file} = seq.build();
  const pulse = R.blockPulse(view, file, 0);
  assert.deepEqual([pulse.echo, pulse.echoReason], [null, R.REASONS.OTHER_RF_BEFORE_ADC]);
});

// ---- 9. The period rule -----------------------------------------------------------------------

function periodRow(per) {
  return [per.firstBlock, per.lastBlock, per.firstAdcBlock, per.truncated];
}

test("test_period_of_a_gre_spin_echo_and_tse_like_train", () => {
  // A GRE: the period of a block of the second TR is that TR, with one excitation
  // (RF spoiling: each TR its own RF row with a new phase, one key); the last TR ends
  // at the end of the file.
  let s = gre(3);
  let per = R.period(s.view, s.file, 5);
  assert.deepEqual(periodRow(per), [4, 7, 6, false]);
  assert.deepEqual(per.pulses.map(p => [p.use, p.firstBlock, p.lastBlock, p.count]),
    [["excitation", 4, 4, 1]]);
  assert.equal(per.pulses[0].key, R.blockPulse(s.view, s.file, 4).key);
  assert.equal(R.blockPulse(s.view, s.file, 0).key, R.blockPulse(s.view, s.file, 8).key);
  assert.deepEqual(periodRow(R.period(s.view, s.file, 11)), [8, 11, 10, false]);

  // A spin echo: the excitation and the refocusing pulse in one period.
  s = spinEcho("gy");
  per = R.period(s.view, s.file, 3);
  assert.deepEqual(periodRow(per), [0, 5, 5, false]);
  assert.deepEqual(per.pulses.map(p => [p.use, p.firstBlock, p.count]),
    [["excitation", 0, 1], ["refocusing", 3, 1]]);

  // A TSE-like train (excitation, then [refocusing, crusher, readout] three times),
  // twice: refocusing pulses never start a period, so each train is one period with
  // one distinct refocusing pulse counted three times.
  const seq = newSeq();
  for (let train = 0; train < 2; train++) {
    seq.pulse("excitation", Math.PI / 2);
    seq.crusher("gz");
    for (let k = 0; k < 3; k++) {
      seq.pulse("refocusing", Math.PI, {phase: Math.PI / 2, key: 1});
      seq.crusher("gz");
      seq.readout();
    }
  }
  s = seq.build();
  for (const block of [0, 1, 6, 10]) {
    per = R.period(s.view, s.file, block);
    assert.deepEqual(periodRow(per), [0, 10, 4, false], `block ${block}`);
    assert.deepEqual(per.pulses.map(p => [p.use, p.count]), [["excitation", 1], ["refocusing", 3]]);
  }
  assert.deepEqual(periodRow(R.period(s.view, s.file, 13)), [11, 21, 15, false]);
});

test("test_period_with_fat_saturation_dummies_and_blocks_before_the_first_rf", () => {
  // A fat saturation and its spoiler before each excitation: the saturation starts the
  // period, and the excitation after it does not.
  let seq = newSeq();
  for (let tr = 0; tr < 2; tr++) {
    seq.pulse("saturation", Math.PI / 2, {hard: true, freq: -440, key: 0});
    seq.crusher("gz");
    seq.pulse("excitation", Math.PI / 2, {key: 1});
    seq.rephaser("gz");
    seq.readout();
  }
  let s = seq.build();
  let per = R.period(s.view, s.file, 7);
  assert.deepEqual(periodRow(per), [5, 9, 9, false]);
  assert.deepEqual(per.pulses.map(p => [p.use, p.firstBlock]), [["saturation", 5], ["excitation", 7]]);

  // Dummy TRs without an ADC join the period of the first ADC after them.
  s = gre(2, 3);
  per = R.period(s.view, s.file, 2);
  assert.deepEqual(periodRow(per), [0, 15, 14, false]);
  assert.deepEqual(per.pulses.map(p => [p.firstBlock, p.lastBlock, p.count]), [[0, 12, 4]]);

  // A block before the first RF block (a delay, then a gradient): the first period.
  seq = newSeq();
  seq.block({dur: 1e-3});
  seq.block({dur: 0.6e-3, gx: seq.grad(trap(1e6, 100e-6, 400e-6))});
  for (let tr = 0; tr < 2; tr++) {
    seq.pulse("excitation", Math.PI / 2, {key: 0});
    seq.rephaser("gz");
    seq.readout();
  }
  s = seq.build();
  assert.deepEqual(periodRow(R.period(s.view, s.file, 0)), [2, 4, 4, false]);
  assert.deepEqual(R.period(s.view, s.file, 1), R.period(s.view, s.file, 0));

  // Each block of a period gives the same period.
  s = gre(3, 1);
  per = R.period(s.view, s.file, 6);
  for (let block = per.firstBlock; block <= per.lastBlock; block++) {
    assert.deepEqual(R.period(s.view, s.file, block), per, `block ${block}`);
  }
});

test("test_period_truncated_after_max_blocks", () => {
  // An excitation, 30 gradient blocks, then the ADC: with maxBlocks 10 the period of
  // block 15 is cut 10 blocks each way and is truncated; with the default it is the
  // whole period.
  const seq = newSeq();
  seq.pulse("excitation", Math.PI / 2);
  for (let k = 0; k < 30; k++) seq.rephaser("gz");
  seq.readout();
  const {view, file} = seq.build();
  const short = R.period(view, file, 15, {maxBlocks: 10});
  assert.deepEqual(periodRow(short), [5, 25, null, true]);
  assert.deepEqual(short.pulses, []);
  assert.deepEqual(periodRow(R.period(view, file, 15)), [0, 31, 31, false]);
});

// ---- 10. The combined profile -----------------------------------------------------------------

function profileOf(pulse, n = null) {
  return R.simulate(pulse, R.viewSpec(pulse, "profile", {n}).spec);
}

test("test_combined_profile_of_one_direction_is_the_product_of_the_profiles", () => {
  // A spin echo with the refocusing pulse on z, 1.5 times as wide: one direction; the
  // line is the excitation |Mxy| times the refocusing |beta|^2 of their "profile" views
  // at the same points (exact: the same points and the same simulations), `linePulses`
  // holds each pulse's block and those same values (exact), and less signal is kept
  // than the excitation alone makes.
  const {view, file} = spinEcho("gz", {refThickness: 1.5 * W});
  const work = R.combinedProfile(view, file, R.period(view, file, 0));
  assert.equal(work.done, false);
  work.step(Infinity);
  const combined = work.result();
  assert.deepEqual([combined.reason, combined.excitationBlock, combined.refocusingBlocks,
    combined.directions, combined.maps], [null, 0, [3], ["z"], []]);
  const exc = profileOf(R.blockPulse(view, file, 0)), ref = profileOf(R.blockPulse(view, file, 3));
  assertSameArray(combined.line.u, exc.grid[0], "u");
  assertSameArray(ref.grid[0], exc.grid[0], "the same grid");
  const mxy = R.quantity(exc, "mxy_abs"), beta = R.quantity(ref, "beta_sq");
  assertSameArray(combined.line.values, mxy.map((v, i) => v * beta[i]), "line");
  assert.deepEqual(combined.linePulses.map(p => p.block), [0, 3]);
  assertSameArray(combined.linePulses[0].values, mxy, "the excitation on the line");
  assertSameArray(combined.linePulses[1].values, beta, "the refocusing pulse on the line");
  assert.ok(combined.numbers.signal_kept < 1);
  assert.deepEqual(Object.keys(combined.numbers),
    ["fwhm_m", "edge_width_m", "signal_kept", "fraction_inside", "centre_signal"]);
});

test("test_combined_profile_of_two_logical_directions_is_the_outer_product", () => {
  // Excitation on z, refocusing on y, view "2d": no line, one map on the axes y and z
  // (in the order x, y, z) whose values are the outer product of the refocusing
  // |beta|^2 on the y axis and the excitation |Mxy| on the z axis (exact: the same
  // simulations, times the factor 1).
  const {view, file} = spinEcho("gy");
  const work = R.combinedProfile(view, file, R.period(view, file, 0), {view: "2d", n: 21});
  work.step(Infinity);
  const combined = work.result();
  assert.equal(combined.line, null);
  assert.deepEqual(combined.linePulses, []);
  assert.deepEqual(combined.directions, ["z", "y"]);
  assert.deepEqual(Object.keys(combined.numbers), ["centre_signal", "fraction_inside"]);
  const [map] = combined.maps;
  const [yAxis, zAxis] = map.axes;
  assert.deepEqual([yAxis.kind, zAxis.kind, yAxis.n, zAxis.n], ["y", "z", 21, 21]);
  const beta = R.quantity(R.simulate(R.blockPulse(view, file, 3), {axes: [yAxis], at: {}}), "beta_sq");
  const mxy = R.quantity(R.simulate(R.blockPulse(view, file, 0), {axes: [zAxis], at: {}}), "mxy_abs");
  const outer = new Float64Array(21 * 21);
  for (let i = 0; i < 21; i++) for (let k = 0; k < 21; k++) outer[i * 21 + k] = beta[i] * mxy[k];
  assertSameArray(map.values, outer, "map");
});

test("test_line_cache_gives_the_same_results_and_reuses_the_profiles", () => {
  // The line cache (module comment of rf_profiles.js): a combined profile with a cache
  // that holds the "profile" views of the pulses gives the same line, pulses, maps and
  // numbers as one without a cache (equal numbers: the same points and the same
  // arithmetic; `===`, as the points along "select" can differ in the sign of a zero),
  // for a column spin echo (two logical directions), a spin echo on one axis with a 1.5
  // times thicker refocusing slice, with and without the SliceThickness definition W, a
  // train of two refocusing pulses with the same key before the first ADC, and an
  // oblique direction ("select"). The "profile" view of a pulse is c ± 2 W, so with W
  // every line of a combined profile is the grid of a pulse's own view: the work adds
  // no line, and it is done without a step. Without W, the view comes from the RF
  // spectrum and |G|, so the refocusing pulse on the grid of the excitation is one new
  // line. (For the oblique case the test checks only the results: whether the two
  // directions are equal to the last bit decides if the refocusing pulse's own view is
  // on the line.)
  const twoPulses = (scale, thickness) => {
    const seq = newSeq({thickness});
    seq.pulse("excitation", Math.PI / 2, {scale});
    seq.rephaser("gz", 1);
    seq.pulse("refocusing", Math.PI, {scale, thickness: 1.5 * W, phase: Math.PI / 2});
    seq.readout();
    return seq.build();
  };
  const cases = [
    ["column spin echo", spinEcho("gy"), 0, true],
    ["one axis", spinEcho("gz", {refThickness: 1.5 * W}), 0, true],
    ["one axis without W", twoPulses({gz: 1}, null), 1, false],
    ["train", spinEcho("gy", {numRef: 2}), 0, true],
    ["oblique", twoPulses({gx: 0.6, gz: 0.8}, W), null, null],
  ];
  const sameNumbers = (a, b, message) => {
    assert.equal(a.length, b.length, message);
    for (let i = 0; i < a.length; i++) {
      if (!(a[i] === b[i] || (Number.isNaN(a[i]) && Number.isNaN(b[i])))) {
        assert.fail(`${message}: index ${i}: ${a[i]} vs ${b[i]}`);
      }
    }
  };
  for (const [name, {view, file}, added, doneAtOnce] of cases) {
    const per = R.period(view, file, 0);
    for (const v of ["profile", "2d"]) {
      const plain = R.combinedProfile(view, file, per, {view: v});
      plain.step(Infinity);
      const expected = plain.result();
      const cache = new Map();
      for (const pulse of per.pulses) {
        const p = R.blockPulse(view, file, pulse.firstBlock);
        R.simulate(p, R.viewSpec(p).spec, {cache});
      }
      const seeded = cache.size;
      assert.equal(seeded, per.pulses.length, `${name}: one line for each distinct pulse`);
      const work = R.combinedProfile(view, file, per, {view: v, cache});
      if (v === "profile" && doneAtOnce !== null) {
        assert.equal(work.done, doneAtOnce, `${name}: done without a step`);
      }
      work.step(Infinity);
      const got = work.result();
      if (v === "profile" && added !== null) {
        assert.equal(cache.size, seeded + added, `${name}: the lines that the work added`);
      }
      assert.deepEqual([got.reason, got.excitationBlock, got.refocusingBlocks, got.factor,
        got.directions], [expected.reason, expected.excitationBlock,
        expected.refocusingBlocks, expected.factor, expected.directions], name);
      assert.deepEqual(got.numbers, expected.numbers, `${name} ${v}: numbers`);
      assert.equal(got.line === null, expected.line === null, `${name}: line`);
      if (got.line !== null) {
        sameNumbers(got.line.u, expected.line.u, `${name}: u`);
        sameNumbers(got.line.values, expected.line.values, `${name}: line values`);
      }
      assert.deepEqual(got.linePulses.map(p => p.block), expected.linePulses.map(p => p.block));
      got.linePulses.forEach((p, k) => {
        sameNumbers(p.values, expected.linePulses[k].values, `${name}: pulse ${p.block}`);
      });
      assert.equal(got.maps.length, expected.maps.length, `${name}: maps`);
      got.maps.forEach((m, k) => {
        assert.deepEqual(m.axes, expected.maps[k].axes);
        sameNumbers(m.values, expected.maps[k].values, `${name}: map ${k}`);
      });
    }
  }
});

test("test_simulation_with_the_line_cache", () => {
  // A 1D spatial line is done at once when it is in the cache, with the same arrays as
  // the work that added it; a "df" line, a 2D grid and a spec with an `at` value are not
  // lines of the cache and leave it unchanged.
  const {view, file} = spinEcho("gy");
  const exc = R.blockPulse(view, file, 0);
  const cache = new Map();
  const spec = R.viewSpec(exc).spec;
  const first = R.simulation(exc, spec, {cache});
  assert.equal(first.done, false);
  first.step(Infinity);
  assert.equal(cache.size, 1);
  const again = R.simulation(exc, spec, {cache});
  assert.equal(again.done, true);
  assert.equal(again.step(0), 1);
  for (const key of ["aRe", "aIm", "bRe", "bIm"]) {
    assert.equal(again.result()[key], first.result()[key], key);
  }
  assertSameArray(again.result().grid[0], first.result().grid[0], "grid");
  const others = [
    {axes: [{kind: "df", lo: -1000, hi: 1000, n: 11}], at: {}},
    R.viewSpec(exc, "z_df", {n: 11}).spec,
    {axes: [{kind: "z", lo: -0.01, hi: 0.01, n: 11}], at: {df: 100}},
  ];
  for (const other of others) R.simulate(exc, other, {cache});
  assert.equal(cache.size, 1);
});

// ---- 11. Sliced work ------------------------------------------------------------------------------

test("test_step_with_small_budgets_gives_the_same_arrays", () => {
  // step(0) until done gives exactly the arrays of one step(Infinity), for a 1D
  // profile, a z x df shear, a 2D grid and a combined profile; the fraction grows to 1.
  // Exact: each point is computed on its own, whatever the slices.
  const {view, file} = spinEcho("gy");
  const exc = R.blockPulse(view, file, 0);
  const specs = [
    R.viewSpec(exc).spec,
    R.viewSpec(exc, "z_df", {n: 41}).spec,
    {axes: [{kind: "z", lo: -0.01, hi: 0.01, n: 17}, {kind: "x", lo: -0.1, hi: 0.1, n: 13}], at: {}},
  ];
  for (const spec of specs) {
    const once = R.simulate(exc, spec);
    const sliced = R.simulation(exc, spec);
    let steps = 0, last = 0;
    while (!sliced.done) {
      const f = sliced.step(0);
      assert.ok(f > last && f <= 1, `the fraction grows: ${f}`);
      last = f;
      steps += 1;
    }
    assert.equal(last, 1);
    assert.ok(steps > 1, "several slices");
    const got = sliced.result();
    for (const key of ["aRe", "aIm", "bRe", "bIm"]) assertSameArray(got[key], once[key], key);
  }
  const per = R.period(view, file, 0);
  const once = R.combinedProfile(view, file, per, {view: "2d", n: 21});
  once.step(Infinity);
  const sliced = R.combinedProfile(view, file, per, {view: "2d", n: 21});
  assert.throws(() => sliced.result(), /before the work is done/);
  let steps = 0, last = 0;
  while (!sliced.done) {
    const f = sliced.step(0);
    assert.ok(f >= last && f <= 1, `the fraction grows: ${f}`);
    last = f;
    steps += 1;
  }
  assert.ok(steps > 1, "several slices");
  assertSameArray(sliced.result().maps[0].values, once.result().maps[0].values, "map");
  assert.deepEqual(sliced.result().numbers, once.result().numbers);
});

// ---- 12. The z x df shear -----------------------------------------------------------------------

test("test_z_df_shear_equals_the_full_grid", () => {
  // With a constant gradient, the z x df view is one 1D simulation of the distinct
  // values z + df / G. It equals `spinDomain` at each (z, df) grid point within 1e-12
  // (float rounding of z + df / G against G z + df), for both signs of G.
  for (const sign of [1, -1]) {
    const seq = newSeq();
    seq.pulse("excitation", Math.PI / 2, {freq: 300, scale: {gz: sign}});
    const {view, file} = seq.build();
    const pulse = R.blockPulse(view, file, 0);
    assert.equal(pulse.constantGradient, true);
    const spec = R.viewSpec(pulse, "z_df", {n: 25}).spec;
    const sheared = R.simulate(pulse, spec);
    const [z, df] = sheared.grid;
    const positions = new Float64Array(3 * 25 * 25), dfs = new Float64Array(25 * 25);
    for (let i = 0; i < 25; i++) {
      for (let j = 0; j < 25; j++) {
        positions[3 * (i * 25 + j) + 2] = z[i];
        dfs[i * 25 + j] = df[j];
      }
    }
    const full = R.spinDomain(pulse.sigRe, pulse.sigIm, pulse.dtS, pulse.grad, positions, dfs);
    for (const key of ["aRe", "aIm", "bRe", "bIm"]) {
      for (let q = 0; q < 25 * 25; q++) assertClose(sheared[key][q], full[key][q], 1e-12, `${key} ${q}`);
    }
  }
});

// ---- 13. Errors -----------------------------------------------------------------------------------

test("test_spec_and_argument_errors", () => {
  const {view, file} = spinEcho("gy");
  const onZ = R.blockPulse(view, file, 0);
  const obliqueSeq = newSeq();
  obliqueSeq.pulse("excitation", Math.PI / 2, {scale: {gx: 0.6, gy: 0.8}});
  const o = obliqueSeq.build();
  const oblique = R.blockPulse(o.view, o.file, 0);
  const z = {kind: "z", lo: -0.01, hi: 0.01, n: 11};
  const select = {kind: "select", lo: -0.01, hi: 0.01, n: 11};
  const spec = (axes, at = {}) => ({axes, at});
  // Each rule of the specs, with the messages of `_check_spec`.
  const cases = [
    [onZ, spec([{kind: "w", lo: 0, hi: 1, n: 3}]), Error, /a spec kind must be one of \('x', 'y', 'z', 'select', 'df'\): 'w'/],
    [onZ, spec([z, z]), Error, /each kind at most once in the axes and `at` together: \['z', 'z'\]/],
    [onZ, spec([z], {z: 0}), Error, /each kind at most once/],
    [oblique, spec([select], {z: 0}), Error, /'select' cannot be in a spec together with 'x', 'y' or 'z'/],
    [onZ, spec([select]), Error, /'select' needs a pulse whose select coordinate is 'select'.*this pulse has 'z'/],
    [onZ, spec([{...z, n: 5.5}]), TypeError, /the number of points must be an int: 5.5/],
    [onZ, spec([{...z, n: 1}]), Error, /an axis needs at least 2 points: ProfileAxis\(kind='z', lo=-0.01, hi=0.01, n=1\)/],
    [onZ, spec([{...z, lo: 0.01}]), Error, /an axis needs finite lo < hi/],
    [onZ, spec([z], {df: Infinity}), Error, /the `at` value of 'df' must be finite: inf/],
    [onZ, spec([{...z, n: 300}, {kind: "df", lo: -1, hi: 1, n: 300}]), Error, /the grid has 90000 points, more than MAX_POINTS = 65536/],
  ];
  for (const [pulse, s, type, message] of cases) {
    assert.throws(() => R.simulation(pulse, s), err => err instanceof type && message.test(err.message));
  }
  // The other arguments.
  const t = turning();
  const changing = R.blockPulse(t.view, t.file, 0);
  assert.throws(() => R.viewSpec(changing, "3d"), /view must be 'profile', 'z_df' or '2d': '3d'/);
  assert.throws(() => R.viewSpec(changing, "2d", {plane: ["x", "x"], extentM: 0.1}), /plane must be two different axes/);
  assert.throws(() => R.viewSpec(changing, "2d", {plane: ["x", "q"], extentM: 0.1}), /plane must be two different axes/);
  assert.throws(() => R.viewSpec(changing, "2d", {extentM: -0.1}), /extent_m must be a positive length \(m\): -0.1/);
  assert.throws(() => R.viewSpec(changing, "profile", {n: 1}), /n must be at least 2: 1/);
  assert.throws(() => R.quantity(R.simulate(onZ, R.viewSpec(onZ).spec), "phase"), /quantity must be/);
  assert.throws(() => R.combinedProfile(view, file, R.period(view, file, 0), {view: "z_df"}),
    /view must be 'profile' or '2d': 'z_df'/);
  for (const block of [-1, 6]) {
    assert.throws(() => R.blockPulse(view, file, block),
      err => err instanceof RangeError && /is not a play index: the sequence has 6 blocks/.test(err.message));
    assert.throws(() => R.period(view, file, block), RangeError);
  }
  assert.throws(() => R.blockPulse(view, file, 0, {maxBlocks: 0}),
    err => err instanceof RangeError && /max_blocks must be at least 1: 0/.test(err.message));
  assert.throws(() => R.period(view, file, 0, {maxBlocks: 0}), RangeError);
  const noRf = newSeq();
  noRf.readout();
  const n = noRf.build();
  assert.throws(() => R.period(n.view, n.file, 0), /period: the sequence has no RF pulse, so it has no period/);
  assert.throws(() => R.simulation(onZ, R.viewSpec(onZ).spec).result(), /before the work is done/);
});

// ---- More: the file data and the keys of the widths ----------------------------------------------------

test("test_file_data_checks_the_rf_table", () => {
  // `fileData` refuses a file without use labels, a missing column and a column of
  // another length; the pools may have another length than the columns.
  const {file} = spinEcho("gy");
  const entry = {labeled: true, slice_thickness_m: null, fov_m: [0.2, 0.2, 0.01],
    groups: [GROUP], first_rf_block: 0};
  const data = R.fileData(entry, file.rf);
  assert.deepEqual([data.sliceThicknessM, data.fovM, data.firstRfBlock], [null, [0.2, 0.2, 0.01], 0]);
  assert.ok(Object.isFrozen(data));
  assert.throws(() => R.fileData({labeled: false}, file.rf), /use label/);
  assert.throws(() => R.fileData({...entry, groups: []}, file.rf), /no groups/);
  const {center, ...missing} = file.rf;
  assert.equal(center.length, file.rf.key.length);
  assert.throws(() => R.fileData(entry, missing), /no column "center"/);
  assert.throws(() => R.fileData(entry, {...file.rf, dt: new Float64Array(1)}), /"dt" has 1 values, not 2/);
});

test("test_widths_keys_follow_the_reference", () => {
  // The keys of `widths` (a key is missing when Python leaves it out): an excitation
  // with W and a pathway has all seven; with a moment of the caller too; a df profile
  // has only the two widths; a refocusing pulse has no phase numbers.
  const {view, file} = spinEcho("gy");
  const exc = R.blockPulse(view, file, 0);
  const all = ["fwhm", "edge_width", "passband_ripple", "stopband_level", "centre_phase_rad",
    "rephasing_error_rad", "nonlinear_residual_rad"];
  const profile = profileOf(exc);
  assert.deepEqual(Object.keys(R.widths(exc, profile)), all);
  assert.deepEqual(Object.keys(R.widths(exc, profile, {echoMomentPerM: [0, 0, 1]})), all);
  const ref = R.blockPulse(view, file, 3);
  assert.deepEqual(Object.keys(R.widths(ref, profileOf(ref))), all.slice(0, 4));
  const df = R.simulate(exc, {axes: [{kind: "df", lo: -2000, hi: 2000, n: 41}], at: {}});
  assert.deepEqual(Object.keys(R.widths(exc, df)), ["fwhm", "edge_width"]);
  // The echo phase: 0 at the grid point of the slice centre within 1e-15 (the angle of
  // z exp(-i angle(z)): rounding, as the Python test), NaN below 10 % of max |Mxy|.
  const phase = R.echoPhase(exc, profile);
  assert.ok(Math.abs(phase[200]) <= 1e-15, `${phase[200]}`);
  assert.ok(Number.isNaN(phase[0]));
  assert.throws(() => R.echoPhase(exc, profile, {echoMomentPerM: [1, 2]}), /3 values \(x y z\): \(2,\)/);
});

// ---- 12. The groups: gamma and B0 -----------------------------------------------------------------

const GROUPS = [
  {gamma_hz_per_t: GAMMA, b0_t: 1.5, names: ["a"], color: "target-1"},
  {gamma_hz_per_t: GAMMA, b0_t: 3, names: ["b"], color: "target-2"},
  {gamma_hz_per_t: -GAMMA, b0_t: 3, names: ["c"], color: "target-3"},
  {gamma_hz_per_t: GAMMA, b0_t: null, names: ["d"], color: "target-4"},
  {gamma_hz_per_t: GAMMA / 2, b0_t: 1.5, names: ["e"], color: "target-5"},
];

// A hard saturation pulse with `ppm` offsets (block 0) and a hard excitation pulse with
// Hz offsets only (block 1), in the groups of GROUPS.
function ppmSequence() {
  const seq = newSeq({groups: GROUPS});
  seq.pulse("saturation", Math.PI / 2, {hard: true, freq: 100, freqPpm: -3.45, phase: 0.3,
    phasePpm: 0.7});
  seq.pulse("excitation", Math.PI / 2, {hard: true, freq: 200, phase: 0.1});
  return seq.build();
}

test("test_ppm_offsets_change_into_hz_with_the_signed_gamma_and_b0_of_the_group", () => {
  // freq = freq_offset + freq_ppm * 1e-6 * gamma * B0 and the same form for the phase,
  // with the signed gamma: the ppm part flips sign with gamma. |B1| uses |gamma|. A ppm
  // offset in a group without B0 has no offsets in Hz; a pulse without ppm terms does.
  const {view, file} = ppmSequence();
  const ppm = (group, term) => term * 1e-6 * GROUPS[group].gamma_hz_per_t * GROUPS[group].b0_t;
  for (const group of [0, 1, 2, 4]) {
    const pulse = R.blockPulse(view, file, 0, {group});
    const offsets = R.pulseOffset(view, file, 0, group);
    assertClose(pulse.freqOffsetHz, 100 + ppm(group, -3.45), 1e-6, `group ${group}: freq`);
    assert.equal(offsets.freqHz, pulse.freqOffsetHz);
    assertClose(offsets.phaseRad, 0.3 + ppm(group, 0.7), 1e-6, `group ${group}: phase`);
  }
  const [plus, minus] = [1, 2].map(group => R.blockPulse(view, file, 0, {group}));
  assertClose(plus.freqOffsetHz - 100, -(minus.freqOffsetHz - 100), 1e-9, "the ppm part flips");
  assert.ok(Math.abs(plus.freqOffsetHz - 100) > 100, "a ppm part of a few hundred Hz");
  assert.equal(minus.peakB1Ut, plus.peakB1Ut);
  assert.equal(minus.energyUt2Ms, plus.energyUt2Ms);
  const half = R.blockPulse(view, file, 0, {group: 4});
  assertClose(half.peakB1Ut / plus.peakB1Ut, 2, 1e-12, "|B1| for half the gamma");

  assert.equal(R.pulseOffset(view, file, 0, 3), null);
  assert.throws(() => R.blockPulse(view, file, 0, {group: 3}), /needs B0/);
  const noB0 = R.blockPulse(view, file, 1, {group: 3});
  const withB0 = R.blockPulse(view, file, 1, {group: 0});
  assert.equal(noB0.freqOffsetHz, 200);
  assertSameArray(noB0.sigRe, withB0.sigRe, "a pulse without ppm terms does not use B0");
  assert.deepEqual(R.pulseOffset(view, file, 1, 3), {freqHz: 200, phaseRad: 0.1});
  assert.equal(R.pulseKey(view, file, 0), R.blockPulse(view, file, 0, {group: 0}).key);
  assert.throws(() => R.blockPulse(view, file, 0, {group: 5}), /group 5 is not a group/);

  // The combined profile reads the pulses of its period in the group.
  const spin = newSeq({groups: [GROUPS[0], GROUPS[3]]});
  spin.pulse("excitation", Math.PI / 2, {freqPpm: -3.45});
  spin.crusher("gy");
  spin.pulse("refocusing", Math.PI, {axis: "gy", phase: Math.PI / 2});
  spin.crusher("gy");
  spin.readout();
  const echo = spin.build();
  const per = R.period(echo.view, echo.file, 0);
  assert.equal(R.combinedProfile(echo.view, echo.file, per, {group: 0}).done, false);
  assert.throws(() => R.combinedProfile(echo.view, echo.file, per, {group: 1}), /needs B0/);
});

test("test_line_cache_keeps_the_offsets_of_the_groups_apart", () => {
  // A selective pulse with a ppm offset has the same pulse key in each group, and a line
  // of the cache for each frequency offset in Hz: groups with another B0 do not share a
  // line, and groups with the same offset in Hz (another gamma with the B0 that keeps
  // gamma * B0) do.
  const groups = [
    {gamma_hz_per_t: GAMMA, b0_t: 1.5, names: [], color: null},
    {gamma_hz_per_t: GAMMA, b0_t: 3, names: [], color: null},
    {gamma_hz_per_t: 2 * GAMMA, b0_t: 0.75, names: [], color: null},
  ];
  const seq = newSeq({groups});
  seq.pulse("excitation", Math.PI / 2, {freqPpm: -3.45});
  const {view, file} = seq.build();
  const pulses = [0, 1, 2].map(group => R.blockPulse(view, file, 0, {group}));
  assert.equal(pulses[0].key, pulses[1].key);
  assert.equal(pulses[0].freqOffsetHz, pulses[2].freqOffsetHz);
  assert.notEqual(pulses[0].freqOffsetHz, pulses[1].freqOffsetHz);

  const cache = new Map();
  const results = pulses.map(pulse => R.simulate(pulse, R.viewSpec(pulse).spec, {cache}));
  assert.equal(cache.size, 2);
  assertSameArray(results[2].aRe, results[0].aRe, "the same offset in Hz gives the same line");
  assert.notDeepEqual(Array.from(results[1].aRe), Array.from(results[0].aRe));
  const direct = R.simulate(pulses[1], R.viewSpec(pulses[1]).spec);
  assertSameArray(results[1].aRe, direct.aRe, "a cached line is the line without a cache");
});

test("test_a_pulse_shared_between_groups_has_the_b1_of_each_group", () => {
  // The card shares the simulation of a pulse between the groups with the same offsets in
  // Hz, and each group reads the shared pulse with its own |gamma|: the peak B1 and the
  // energy are those of `blockPulse` in that group (relative 1e-12), the signal and the
  // gradients are the shared ones, and the pulse of the first group is not changed. The
  // groups of a negative gamma have |gamma|. A group with other offsets in Hz, or none, throws.
  const groups = [
    {gamma_hz_per_t: GAMMA, b0_t: 3, names: [], color: null},
    {gamma_hz_per_t: -GAMMA / 3.6, b0_t: 3, names: [], color: null},
    {gamma_hz_per_t: GAMMA, b0_t: 3, names: [], color: null},
    {gamma_hz_per_t: GAMMA, b0_t: 1.5, names: [], color: null},
    {gamma_hz_per_t: GAMMA, b0_t: null, names: [], color: null},
  ];
  const seq = newSeq({groups});
  seq.pulse("refocusing", Math.PI, {axis: "gy", phase: Math.PI / 2});
  seq.pulse("saturation", Math.PI / 2, {hard: true, freqPpm: -3.45});
  const {view, file} = seq.build();
  const first = R.blockPulse(view, file, 0, {group: 0});
  const peak = first.peakB1Ut, energy = first.energyUt2Ms;

  for (const group of [1, 2]) {
    const shared = R.pulseInGroup(view, file, first, group);
    const own = R.blockPulse(view, file, 0, {group});
    assertClose(shared.peakB1Ut / own.peakB1Ut, 1, 1e-12, `group ${group}: peak B1`);
    assertClose(shared.energyUt2Ms / own.energyUt2Ms, 1, 1e-12, `group ${group}: energy`);
    assert.equal(shared.sigRe, first.sigRe);
    assert.equal(shared.grad, first.grad);
  }
  assertClose(R.pulseInGroup(view, file, first, 1).peakB1Ut / peak, 3.6, 1e-12, "|gamma| of 1/3.6");
  assert.equal(R.pulseInGroup(view, file, first, 2), first);
  assert.equal(first.peakB1Ut, peak);
  assert.equal(first.energyUt2Ms, energy);

  // A pulse with a ppm offset has other offsets in Hz in a group with another B0.
  const ppm = R.blockPulse(view, file, 1, {group: 0});
  assert.equal(R.pulseInGroup(view, file, ppm, 2), ppm);
  assert.throws(() => R.pulseInGroup(view, file, ppm, 3), /another offset in Hz/);
  assert.throws(() => R.pulseInGroup(view, file, ppm, 4), /another offset in Hz/);
});
