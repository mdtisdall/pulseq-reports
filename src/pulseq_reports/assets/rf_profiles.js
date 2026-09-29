// The RF pulse profiles of the RF profile card, in the browser, with no DOM and no
// network: the JavaScript copy of the Python reference (`rf_profiles.py`, `rf_sim.py`
// and `profile_metrics.py`; docs/plans/rf-profiles.md, sections 4.2, 4.3 and 4.6). A
// golden test holds it to the reference (section 3.5, item 2): `a` and `b` within 1e-12.
// So each function ports one Python function, with the same rules, the same constants,
// the same texts, and the same order of float operations where the plan asks for it.
//
// The inputs are the sequence view of a diagram card (`SeqLanes.sequenceView`, section
// 4.1) and the file data of the card (`fileData`: the RF table of
// `cards.rf_profile.rf_table`, already decoded to typed arrays by the caller). The
// module is pure and synchronous: the long work (`simulation`, `combinedProfile`) is an
// object whose `step(budgetMs)` the card calls in slices.
//
// Names are camelCase; arrays of numbers are Float64Array (C order for grids). One
// global `RfProfiles` in the browser (a classic script), `module.exports` in Node.
const RfProfiles = (() => {
  "use strict";

  // ---- Constants (the same values as rf_profiles.py and seq_utils.py) ----

  const USES = Object.freeze(
    ["excitation", "refocusing", "inversion", "saturation", "preparation", "other"]);
  const AXIS_KINDS = Object.freeze(["x", "y", "z", "select", "df"]);
  const MAX_POINTS = 65536; // 256 x 256, the most points of one simulation
  const NUM_POSITIONS = 401; // the points of a 1D profile
  const MAP_POINTS = 128; // the points on each axis of a 2D map
  const PERIOD_MAX_BLOCKS = 100000; // the longest walk of `period` in each direction
  const PARALLEL_TOL = 1e-9; // relative: a gradient vector parallel to the mean direction
  const CONSTANT_TOL = 1e-9; // relative: a gradient vector equal to the mean vector
  const SPECTRUM_PADDING = 64; // zero padding of the RF spectrum
  const PHASE_MIN_FRACTION = 0.1; // the phase is shown where |Mxy| >= this * max |Mxy|
  const PASSBAND_FRACTION = 0.4; // the phase fits use |u - c| <= this * W
  const TIME_TOLERANCE = 1e-9; // s, seq_utils.TIME_TOLERANCE
  // The z x df grid of a constant gradient is one 1D simulation when the df step is |G|
  // times the step of the select coordinate within this relative tolerance.
  const SHEAR_RTOL = 1e-12;

  // The reasons and notes of rf_profiles.py, character for character.
  const REASONS = Object.freeze({
    NO_ADC: "no ADC before the next excitation",
    OTHER_RF_BEFORE_ADC:
      "an RF pulse that is not a refocusing pulse lies between this pulse and the ADC",
    DIRECTION_CHANGES: "the gradient direction changes during the RF",
    NO_FOV: "no FOV definition: give extent_m",
    NO_SLICE_THICKNESS: "no SliceThickness definition",
    NO_GRADIENT_Z_DF: "no gradient: the profile against Δf is the 1D profile",
    NO_MAP_ONE: "the gradient has one direction: a 2d map of this pulse is only stripes",
    NO_MAP_NONE: "no gradient: a 2d map of this pulse is uniform",
    OFF_CENTRE_CHANGES:
      "the gradient changes during the RF: an off-centre slice is not a shift of this profile",
    NO_EXCITATION: "no excitation before the first ADC of the period",
    NO_REFOCUSING: "no refocusing pulse between the excitation and the ADC",
    THREE_OBLIQUE: "the combined profile of three oblique directions is not supported",
    MORE_THAN_THREE: "the pulses have more than three directions",
  });

  const AXIS_NAMES = ["x", "y", "z"];
  const GRAD_ATTRS = ["gx", "gy", "gz"];
  // The columns of one row of the RF table (`rf_table`), all with one length, and its
  // two pools of baseband samples.
  const RF_COLUMNS = ["key", "use", "delay", "shape_dur", "center", "dt", "shape_at",
    "shape_n", "freq_hz", "phase_rad"];
  const RF_POOLS = ["shape_re", "shape_im"];
  // The sliced work checks the clock after about this many point-samples of the
  // spin-domain loop, not after each point, so the clock costs nothing for short
  // pulses. A slice then ends at most one chunk after its budget (0.2 ms or less in
  // Node 24).
  const CHECK_WORK = 4096;

  // ---- Python-like text for error messages ----

  // The Python repr of a float: the shortest digits that give the same double (as
  // JavaScript's), with an exponent when the decimal point is at or before the 4th zero
  // or after the 16th digit ("1e-05", "1e+16"), and ".0" on an integer value.
  function _pyFloat(x) {
    if (Number.isNaN(x)) return "nan";
    if (x === Infinity) return "inf";
    if (x === -Infinity) return "-inf";
    if (x === 0) return Object.is(x, -0) ? "-0.0" : "0.0";
    const [mant, expText] = Math.abs(x).toExponential().split("e");
    const exp = Number(expText);
    const digits = mant.replace(".", "");
    const decpt = exp + 1;
    let body;
    if (decpt <= -4 || decpt > 16) {
      const tail = digits.length > 1 ? "." + digits.slice(1) : "";
      body = `${digits[0]}${tail}e${exp < 0 ? "-" : "+"}${String(Math.abs(exp)).padStart(2, "0")}`;
    } else if (decpt <= 0) {
      body = "0." + "0".repeat(-decpt) + digits;
    } else if (decpt >= digits.length) {
      body = digits + "0".repeat(decpt - digits.length) + ".0";
    } else {
      body = digits.slice(0, decpt) + "." + digits.slice(decpt);
    }
    return (x < 0 ? "-" : "") + body;
  }

  // A Python-like repr for the messages: strings in single quotes, null as None,
  // integers as ints, other numbers as floats, arrays as tuples.
  function _pyRepr(v) {
    if (v === null || v === undefined) return "None";
    if (typeof v === "string") return `'${v}'`;
    if (typeof v === "boolean") return v ? "True" : "False";
    if (typeof v === "number") return Number.isInteger(v) ? String(v) : _pyFloat(v);
    if (Array.isArray(v)) {
      const items = v.map(_pyRepr);
      return items.length === 1 ? `(${items[0]},)` : `(${items.join(", ")})`;
    }
    return String(v);
  }

  function _pyList(values) {
    return `[${values.map(_pyRepr).join(", ")}]`;
  }

  // The repr of a `ProfileAxis` dataclass.
  function _axisRepr(axis) {
    const num = v => (typeof v === "number" ? _pyFloat(v) : _pyRepr(v));
    return `ProfileAxis(kind=${_pyRepr(axis.kind)}, lo=${num(axis.lo)}, ` +
      `hi=${num(axis.hi)}, n=${_pyRepr(axis.n)})`;
  }

  // `operator.index(v)`: a TypeError for a value that is not an integer.
  function _index(v) {
    if (typeof v !== "number" || !Number.isInteger(v)) {
      const type = typeof v === "number" ? "float" : typeof v === "string" ? "str" : typeof v;
      throw new TypeError(`'${type}' object cannot be interpreted as an integer`);
    }
    return v;
  }

  // ---- Small numpy helpers ----

  // `numpy.linspace(lo, hi, n)`: y[i] = i * step + lo with step = (hi - lo) / (n - 1),
  // and y[n - 1] = hi. When the step is 0 (numpy's special case for a denormal step),
  // y[i] = (i / (n - 1)) * (hi - lo) + lo.
  function linspace(lo, hi, n) {
    const y = new Float64Array(n);
    const div = n - 1;
    const delta = hi - lo;
    if (div > 0) {
      const step = delta / div;
      if (step === 0) {
        for (let i = 0; i < n; i++) y[i] = (i / div) * delta + lo;
      } else {
        for (let i = 0; i < n; i++) y[i] = i * step + lo;
      }
      y[n - 1] = hi;
    } else if (n === 1) {
      y[0] = 0 * delta + lo;
    }
    return y;
  }

  // `numpy.max` of a non-empty array: NaN when any value is NaN.
  function _max(a) {
    let m = a[0];
    for (let i = 1; i < a.length; i++) {
      const v = a[i];
      if (v > m || v !== v) m = v;
      if (m !== m) return m;
    }
    return m;
  }

  function _min(a) {
    let m = a[0];
    for (let i = 1; i < a.length; i++) {
      const v = a[i];
      if (v < m || v !== v) m = v;
      if (m !== m) return m;
    }
    return m;
  }

  // The values of `x` where `keep(i)` is true (numpy boolean indexing).
  function _select(x, keep) {
    const out = [];
    for (let i = 0; i < x.length; i++) if (keep(i)) out.push(x[i]);
    return out;
  }

  // `numpy.argmin`: the first index of the minimum.
  function _argmin(a) {
    let best = 0;
    for (let i = 1; i < a.length; i++) if (a[i] < a[best]) best = i;
    return best;
  }

  // numpy's float `mod` (`npy_remainder`): the C fmod, moved to the sign of `b`.
  function _mod(a, b) {
    let r = a % b;
    if (r !== 0 && (b < 0) !== (r < 0)) r += b;
    else if (r === 0) r = b < 0 ? -0 : 0;
    return r;
  }

  // `numpy.unwrap(p)` (period 2π, discont π): out[0] = p[0], out[i] = p[i] + the
  // cumulative sum of the corrections of the steps before it.
  function unwrap(p) {
    const n = p.length;
    const out = new Float64Array(n);
    if (n === 0) return out;
    out[0] = p[0];
    const period = 2 * Math.PI;
    const high = period / 2;
    const low = -high;
    let cum = 0;
    for (let i = 1; i < n; i++) {
      const dd = p[i] - p[i - 1];
      let ddmod = _mod(dd - low, period) + low;
      if (ddmod === low && dd > 0) ddmod = high;
      let corr = ddmod - dd;
      if (Math.abs(dd) < high) corr = 0;
      cum = i === 1 ? corr : cum + corr;
      out[i] = p[i] + cum;
    }
    return out;
  }

  // `numpy.trapezoid(y, x)`: the sum of (x[i+1] - x[i]) * (y[i+1] + y[i]) / 2.
  function _trapezoid(y, x) {
    let s = 0;
    for (let i = 0; i + 1 < y.length; i++) s += (x[i + 1] - x[i]) * (y[i + 1] + y[i]) / 2.0;
    return s;
  }

  // `numpy.interp(x, xp, fp)` for one x and an increasing `xp`: fp[0] before xp[0],
  // fp[-1] after xp[-1], else slope * (x - xp[j]) + fp[j] with xp[j] <= x < xp[j + 1].
  function _interp(x, xp, fp) {
    const n = xp.length;
    if (x !== x) return x;
    if (x > xp[n - 1]) return fp[n - 1];
    if (x < xp[0]) return fp[0];
    let lo = 0, hi = n - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (xp[mid] <= x) lo = mid; else hi = mid;
    }
    let j = lo;
    if (x === xp[n - 1]) j = n - 1;
    if (j === n - 1) return fp[j];
    if (xp[j] === x) return fp[j];
    const slope = (fp[j + 1] - fp[j]) / (xp[j + 1] - xp[j]);
    let v = slope * (x - xp[j]) + fp[j];
    if (v !== v) {
      v = slope * (x - xp[j + 1]) + fp[j + 1];
      if (v !== v && fp[j] === fp[j + 1]) v = fp[j];
    }
    return v;
  }

  // ---- profile_metrics.py ----

  function _nonEmpty(values) {
    if (values.length === 0) {
      throw new Error("zero-size array to reduction operation maximum which has no identity");
    }
    return values;
  }

  // `profile_metrics.fwhm`: the distance between the outermost positions where the
  // profile is at or above half its maximum.
  function fwhm(x, p) {
    const half = _max(p) / 2;
    const above = _nonEmpty(_select(x, i => p[i] >= half));
    return _max(above) - _min(above);
  }

  // `profile_metrics.edge_width`: the mean width of the two 10%-90% edges.
  function edgeWidth(x, p) {
    const maxVal = _max(p);
    const at10 = _nonEmpty(_select(x, i => p[i] >= 0.1 * maxVal));
    const at90 = _nonEmpty(_select(x, i => p[i] >= 0.9 * maxVal));
    const left = _min(at90) - _min(at10);
    const right = _max(at10) - _max(at90);
    return (left + right) / 2;
  }

  // `profile_metrics.passband_ripple`: (max - min) / max over |x| <= 0.4 * nominal.
  function passbandRipple(x, p, nominal) {
    const region = _select(p, i => Math.abs(x[i]) <= 0.4 * nominal);
    if (region.length === 0) {
      throw new Error("passband_ripple: no samples with |x| <= 0.4 * nominal");
    }
    return (_max(region) - _min(region)) / _max(region);
  }

  // `profile_metrics.stopband_level`: the maximum over |x| >= nominal, divided by the
  // maximum of the whole profile.
  function stopbandLevel(x, p, nominal) {
    const region = _select(p, i => Math.abs(x[i]) >= nominal);
    if (region.length === 0) throw new Error("stopband_level: no samples with |x| >= nominal");
    return _max(region) / _max(p);
  }

  // ---- rf_sim.py ----

  // `rf_sim.spin_domain` for the points [j0, j1) of `positions`, into `out` ({aRe, aIm,
  // bRe, bIm}). One point at a time over all samples, with plain numbers only (section
  // 2.3 of the plan). The float operations are those of numpy for each interval k and
  // point j:
  //   phi = 2π dt ((x gx + y gy + z gz) + df), b1 = (2π dt b1Scale) * signal,
  //   theta = |(b1, phi)|, ak = cos(theta/2) - i (phi/theta) sin(theta/2),
  //   bk = -i (b1 * (1/theta)) sin(theta/2) (numpy divides a complex by a real as a
  //   product with 1/theta), a' = ak a - conj(bk) b, b' = bk a + conj(ak) b.
  // Except theta: numpy uses hypot, and this loop uses sqrt(b1r² + b1i² + phi²), because
  // Math.hypot makes the loop about 3 times slower in V8 (about 38 ns instead of 14 ns
  // for each point and sample in Node 24), which breaks the time budgets of section 2.4.
  // The two differ by float rounding only (the angles of one interval are far from
  // overflow and underflow).
  // Each point is independent of the others, so any split into ranges gives the same
  // values.
  function spinDomainRange(sigRe, sigIm, dtS, grad, positions, df, b1Scale, j0, j1, out) {
    const n = sigRe.length;
    const twoPiDt = 2 * Math.PI * dtS;
    const aRe = out.aRe, aIm = out.aIm, bRe = out.bRe, bIm = out.bIm;
    for (let j = j0; j < j1; j++) {
      const x = positions[3 * j], y = positions[3 * j + 1], z = positions[3 * j + 2];
      const dfj = df === null ? 0 : df[j];
      const s1 = twoPiDt * (b1Scale === null ? 1 : b1Scale[j]);
      let ar = 1, ai = 0, br = 0, bi = 0;
      for (let k = 0; k < n; k++) {
        const q = 3 * k;
        const phi = twoPiDt * ((x * grad[q] + y * grad[q + 1] + z * grad[q + 2]) + dfj);
        const b1r = s1 * sigRe[k], b1i = s1 * sigIm[k];
        const theta = Math.sqrt(b1r * b1r + b1i * b1i + phi * phi);
        const safe = theta === 0 ? 1 : theta;
        const s = Math.sin(theta / 2), c = Math.cos(theta / 2);
        const akr = c, aki = -((phi / safe) * s);
        const inv = 1 / safe;
        const qr = b1r * inv, qi = b1i * inv;
        const bkr = qi * s, bki = -(qr * s);
        const nar = (akr * ar - aki * ai) - (bkr * br - (-bki) * bi);
        const nai = (akr * ai + aki * ar) - (bkr * bi + (-bki) * br);
        const nbr = (bkr * ar - bki * ai) + (akr * br - (-aki) * bi);
        const nbi = (bkr * ai + bki * ar) + (akr * bi + (-aki) * br);
        ar = nar; ai = nai; br = nbr; bi = nbi;
      }
      aRe[j] = ar; aIm[j] = ai; bRe[j] = br; bIm[j] = bi;
    }
  }

  // `rf_sim.spin_domain`: Cayley-Klein alpha and beta after the pulse at each point.
  // `grad`: n * 3 (x y z of each hold interval); `positions`: m * 3; `df`, `b1Scale`: m
  // values, or null for 0 and 1.
  function spinDomain(sigRe, sigIm, dtS, grad, positions, df = null, b1Scale = null) {
    const n = sigRe.length;
    if (sigIm.length !== n) {
      throw new Error(`the imaginary part must have the ${n} samples of the real part, ` +
        `got ${sigIm.length}`);
    }
    if (grad.length !== 3 * n) {
      throw new Error(`grad_hz_per_m must have shape (n, 3) = (${n}, 3) to match ` +
        `signal_hz's ${n} samples, got ${grad.length} values`);
    }
    if (positions.length % 3 !== 0) {
      throw new Error(`positions_m must have shape (m, 3), got ${positions.length} values`);
    }
    const m = positions.length / 3;
    if (df !== null && df.length !== m) {
      throw new Error(`df_hz must have shape (m,) = (${m},) to match positions_m's ${m} ` +
        `points, got (${df.length},)`);
    }
    if (b1Scale !== null && b1Scale.length !== m) {
      throw new Error(`b1_scale must have shape (m,) = (${m},) to match positions_m's ${m} ` +
        `points, got (${b1Scale.length},)`);
    }
    const out = {aRe: new Float64Array(m), aIm: new Float64Array(m),
      bRe: new Float64Array(m), bIm: new Float64Array(m)};
    spinDomainRange(sigRe, sigIm, dtS, grad, positions, df, b1Scale, 0, m, out);
    return out;
  }

  // `rf_sim.magnetization`: Mxy = 2 conj(a) b and Mz = |a|^2 - |b|^2 (numpy computes
  // |a| as hypot, then squares it).
  function magnetization(aRe, aIm, bRe, bIm) {
    const m = aRe.length;
    const mxyRe = new Float64Array(m), mxyIm = new Float64Array(m), mz = new Float64Array(m);
    for (let j = 0; j < m; j++) {
      const car = 2 * aRe[j], cai = -(2 * aIm[j]);
      mxyRe[j] = car * bRe[j] - cai * bIm[j];
      mxyIm[j] = car * bIm[j] + cai * bRe[j];
      const ha = Math.hypot(aRe[j], aIm[j]), hb = Math.hypot(bRe[j], bIm[j]);
      mz[j] = ha * ha - hb * hb;
    }
    return {mxyRe, mxyIm, mz};
  }

  // `rf_sim.crushed_echo`: |b|^2.
  function crushedEcho(bRe, bIm) {
    const out = new Float64Array(bRe.length);
    for (let j = 0; j < bRe.length; j++) {
      const h = Math.hypot(bRe[j], bIm[j]);
      out[j] = h * h;
    }
    return out;
  }

  // `rf_sim.precess`: mxy * exp(2πi (moment · r)) at each position (m * 3), the dot
  // product in the order x, y, z.
  function precess(mxyRe, mxyIm, moment, positions) {
    const m = mxyRe.length;
    const re = new Float64Array(m), im = new Float64Array(m);
    const twoPi = 2 * Math.PI;
    for (let j = 0; j < m; j++) {
      const d = positions[3 * j] * moment[0] + positions[3 * j + 1] * moment[1] +
        positions[3 * j + 2] * moment[2];
      const angle = twoPi * d;
      const c = Math.cos(angle), s = Math.sin(angle);
      re[j] = mxyRe[j] * c - mxyIm[j] * s;
      im[j] = mxyRe[j] * s + mxyIm[j] * c;
    }
    return {re, im};
  }

  // ---- The FFT (for the RF spectrum) ----

  // The factors of `n`: 4s, then 2, 3, 5, then any other primes.
  function _factors(n) {
    const f = [];
    while (n % 4 === 0) { f.push(4); n /= 4; }
    for (const p of [2, 3, 5]) while (n % p === 0) { f.push(p); n /= p; }
    for (let p = 7; p * p <= n; p += 2) while (n % p === 0) { f.push(p); n /= p; }
    if (n > 1) f.push(n);
    return f;
  }

  // exp(-2πik/N) for k = 0 .. N-1. When 8 divides N, only the first eighth is computed
  // with Math.cos and Math.sin, from angles of at most π/4, and the rest by symmetry
  // (exact sign changes and swaps); else the first half, and the second half as the
  // conjugates.
  function _twiddles(N) {
    const re = new Float64Array(N), im = new Float64Array(N);
    if (N % 8 === 0) {
      const eighth = N / 8, quarter = N / 4, half = N / 2;
      for (let k = 0; k <= eighth; k++) {
        const a = (2 * Math.PI * k) / N;
        const c = Math.cos(a), s = Math.sin(a);
        re[k] = c; im[k] = -s;
        re[quarter - k] = s; im[quarter - k] = -c;
      }
      for (let k = 0; k < quarter; k++) {
        re[quarter + k] = im[k];
        im[quarter + k] = -re[k];
      }
      for (let k = 0; k < half; k++) {
        re[half + k] = -re[k];
        im[half + k] = -im[k];
      }
    } else {
      const top = Math.floor(N / 2);
      for (let k = 0; k <= top; k++) {
        const a = (2 * Math.PI * k) / N;
        re[k] = Math.cos(a); im[k] = -Math.sin(a);
      }
      for (let k = top + 1; k < N; k++) {
        re[k] = re[N - k]; im[k] = -im[N - k];
      }
    }
    return {re, im};
  }

  // A prime factor above this is done with Bluestein's method, not a direct stage.
  const MAX_DIRECT_FACTOR = 64;
  // The plans of the last few lengths: the factors and the twiddles, or for Bluestein's
  // method the chirp and the FFT of its kernel.
  const _plans = new Map();

  function _plan(N) {
    let plan = _plans.get(N);
    if (plan === undefined) {
      const factors = _factors(N);
      plan = factors.some(f => f > MAX_DIRECT_FACTOR)
        ? _bluesteinPlan(N)
        : {bluestein: false, factors, w: _twiddles(N)};
      if (_plans.size >= 8) _plans.delete(_plans.keys().next().value);
      _plans.set(N, plan);
    }
    return plan;
  }

  // The stages of the Stockham autosort FFT (decimation in frequency): for the current
  // length len = r * m and stride s (len * s = N), y[q + s(r p + u)] = w_len^(p u) *
  // sum_t x[q + s(p + t m)] w_r^(t u), with w_len^v = W[v s] and w_r^v = W[v N / r].
  // One small function for each radix: V8 optimizes them sooner than one function with a
  // branch for each radix, which shortens the first FFT of a page (measured in Node 24).
  function _radix4(m, s, xr, xi, yr, yi, wr, wi) {
    const sm = s * m;
    for (let p = 0; p < m; p++) {
      const w1 = p * s, w2 = 2 * w1, w3 = 3 * w1;
      const c1 = wr[w1], d1 = wi[w1], c2 = wr[w2], d2 = wi[w2], c3 = wr[w3], d3 = wi[w3];
      for (let q = 0; q < s; q++) {
        const i0 = q + s * p;
        const a0r = xr[i0], a0i = xi[i0];
        const a1r = xr[i0 + sm], a1i = xi[i0 + sm];
        const a2r = xr[i0 + 2 * sm], a2i = xi[i0 + 2 * sm];
        const a3r = xr[i0 + 3 * sm], a3i = xi[i0 + 3 * sm];
        const t0r = a0r + a2r, t0i = a0i + a2i, t1r = a0r - a2r, t1i = a0i - a2i;
        const t2r = a1r + a3r, t2i = a1i + a3i, t3r = a1r - a3r, t3i = a1i - a3i;
        const o = q + s * 4 * p;
        yr[o] = t0r + t2r; yi[o] = t0i + t2i;
        // y1 = t1 - i t3, y2 = t0 - t2, y3 = t1 + i t3.
        const y1r = t1r + t3i, y1i = t1i - t3r;
        yr[o + s] = y1r * c1 - y1i * d1; yi[o + s] = y1r * d1 + y1i * c1;
        const y2r = t0r - t2r, y2i = t0i - t2i;
        yr[o + 2 * s] = y2r * c2 - y2i * d2; yi[o + 2 * s] = y2r * d2 + y2i * c2;
        const y3r = t1r - t3i, y3i = t1i + t3r;
        yr[o + 3 * s] = y3r * c3 - y3i * d3; yi[o + 3 * s] = y3r * d3 + y3i * c3;
      }
    }
  }

  function _radix2(m, s, xr, xi, yr, yi, wr, wi) {
    const sm = s * m;
    for (let p = 0; p < m; p++) {
      const c1 = wr[p * s], d1 = wi[p * s];
      for (let q = 0; q < s; q++) {
        const i0 = q + s * p;
        const ar = xr[i0], ai = xi[i0], br = xr[i0 + sm], bi = xi[i0 + sm];
        const o = q + s * 2 * p;
        yr[o] = ar + br; yi[o] = ai + bi;
        const dr = ar - br, di = ai - bi;
        yr[o + s] = dr * c1 - di * d1; yi[o + s] = dr * d1 + di * c1;
      }
    }
  }

  function _radix3(m, s, xr, xi, yr, yi, wr, wi) {
    const sm = s * m;
    const s3 = Math.sqrt(3) / 2; // sin(2π/3)
    for (let p = 0; p < m; p++) {
      const w1 = p * s, w2 = 2 * w1;
      const c1 = wr[w1], d1 = wi[w1], c2 = wr[w2], d2 = wi[w2];
      for (let q = 0; q < s; q++) {
        const i0 = q + s * p;
        const a0r = xr[i0], a0i = xi[i0];
        const a1r = xr[i0 + sm], a1i = xi[i0 + sm];
        const a2r = xr[i0 + 2 * sm], a2i = xi[i0 + 2 * sm];
        const tr = a1r + a2r, ti = a1i + a2i;
        const mr = a0r - 0.5 * tr, mi = a0i - 0.5 * ti;
        const dr = s3 * (a1r - a2r), di = s3 * (a1i - a2i);
        const o = q + s * 3 * p;
        yr[o] = a0r + tr; yi[o] = a0i + ti;
        // y1 = m - i d, y2 = m + i d.
        const y1r = mr + di, y1i = mi - dr;
        yr[o + s] = y1r * c1 - y1i * d1; yi[o + s] = y1r * d1 + y1i * c1;
        const y2r = mr - di, y2i = mi + dr;
        yr[o + 2 * s] = y2r * c2 - y2i * d2; yi[o + 2 * s] = y2r * d2 + y2i * c2;
      }
    }
  }

  function _radix5(m, s, xr, xi, yr, yi, wr, wi) {
    const sm = s * m;
    const k1 = (2 * Math.PI) / 5;
    const c51 = Math.cos(k1), s51 = Math.sin(k1), c52 = Math.cos(2 * k1), s52 = Math.sin(2 * k1);
    for (let p = 0; p < m; p++) {
      const w1 = p * s;
      const c1 = wr[w1], d1 = wi[w1], c2 = wr[2 * w1], d2 = wi[2 * w1];
      const c3 = wr[3 * w1], d3 = wi[3 * w1], c4 = wr[4 * w1], d4 = wi[4 * w1];
      for (let q = 0; q < s; q++) {
        const i0 = q + s * p;
        const a0r = xr[i0], a0i = xi[i0];
        const a1r = xr[i0 + sm], a1i = xi[i0 + sm];
        const a2r = xr[i0 + 2 * sm], a2i = xi[i0 + 2 * sm];
        const a3r = xr[i0 + 3 * sm], a3i = xi[i0 + 3 * sm];
        const a4r = xr[i0 + 4 * sm], a4i = xi[i0 + 4 * sm];
        const b1r = a1r + a4r, b1i = a1i + a4i, e1r = a1r - a4r, e1i = a1i - a4i;
        const b2r = a2r + a3r, b2i = a2i + a3i, e2r = a2r - a3r, e2i = a2i - a3i;
        const A1r = a0r + c51 * b1r + c52 * b2r, A1i = a0i + c51 * b1i + c52 * b2i;
        const A2r = a0r + c52 * b1r + c51 * b2r, A2i = a0i + c52 * b1i + c51 * b2i;
        const B1r = s51 * e1r + s52 * e2r, B1i = s51 * e1i + s52 * e2i;
        const B2r = s52 * e1r - s51 * e2r, B2i = s52 * e1i - s51 * e2i;
        const o = q + s * 5 * p;
        yr[o] = a0r + b1r + b2r; yi[o] = a0i + b1i + b2i;
        // y1 = A1 - i B1, y4 = A1 + i B1, y2 = A2 - i B2, y3 = A2 + i B2.
        const y1r = A1r + B1i, y1i = A1i - B1r;
        const y4r = A1r - B1i, y4i = A1i + B1r;
        const y2r = A2r + B2i, y2i = A2i - B2r;
        const y3r = A2r - B2i, y3i = A2i + B2r;
        yr[o + s] = y1r * c1 - y1i * d1; yi[o + s] = y1r * d1 + y1i * c1;
        yr[o + 2 * s] = y2r * c2 - y2i * d2; yi[o + 2 * s] = y2r * d2 + y2i * c2;
        yr[o + 3 * s] = y3r * c3 - y3i * d3; yi[o + 3 * s] = y3r * d3 + y3i * c3;
        yr[o + 4 * s] = y4r * c4 - y4i * d4; yi[o + 4 * s] = y4r * d4 + y4i * c4;
      }
    }
  }

  // Any other (prime) factor r: the r-point DFT written out, O(r^2).
  function _radixAny(r, m, s, N, xr, xi, yr, yi, wr, wi) {
    const sm = s * m;
    const step = N / r;
    const ar = new Float64Array(r), ai = new Float64Array(r);
    for (let p = 0; p < m; p++) {
      for (let q = 0; q < s; q++) {
        const i0 = q + s * p;
        for (let t = 0; t < r; t++) { ar[t] = xr[i0 + t * sm]; ai[t] = xi[i0 + t * sm]; }
        const o = q + s * r * p;
        for (let u = 0; u < r; u++) {
          let sr = 0, si = 0;
          for (let t = 0; t < r; t++) {
            const w = ((t * u) % r) * step;
            sr += ar[t] * wr[w] - ai[t] * wi[w];
            si += ar[t] * wi[w] + ai[t] * wr[w];
          }
          const w = p * u * s;
          yr[o + u * s] = sr * wr[w] - si * wi[w];
          yi[o + u * s] = sr * wi[w] + si * wr[w];
        }
      }
    }
  }

  function _stage(r, m, s, N, xr, xi, yr, yi, wr, wi) {
    if (r === 4) _radix4(m, s, xr, xi, yr, yi, wr, wi);
    else if (r === 2) _radix2(m, s, xr, xi, yr, yi, wr, wi);
    else if (r === 3) _radix3(m, s, xr, xi, yr, yi, wr, wi);
    else if (r === 5) _radix5(m, s, xr, xi, yr, yi, wr, wi);
    else _radixAny(r, m, s, N, xr, xi, yr, yi, wr, wi);
  }

  // Bluestein's method for the length N: the chirp w_k = exp(-πik²/N) (k² taken modulo
  // 2N, the period of the chirp), the power-of-two length M >= 2N - 1 of the
  // convolution, and the FFT of its kernel conj(w_k) (k = -(N-1) .. N-1, cyclic).
  function _bluesteinPlan(N) {
    let M = 1;
    while (M < 2 * N - 1) M *= 2;
    const cr = new Float64Array(N), ci = new Float64Array(N);
    for (let k = 0; k < N; k++) {
      const a = (Math.PI * ((k * k) % (2 * N))) / N;
      cr[k] = Math.cos(a);
      ci[k] = -Math.sin(a);
    }
    const hr = new Float64Array(M), hi = new Float64Array(M);
    for (let k = 0; k < N; k++) {
      hr[k] = cr[k]; hi[k] = -ci[k];
      if (k > 0) { hr[M - k] = cr[k]; hi[M - k] = -ci[k]; }
    }
    return {bluestein: true, M, cr, ci, h: fft(hr, hi)};
  }

  // The DFT of `re` + i `im` with Bluestein's method: X_k = w_k sum_j (x_j w_j)
  // conj(w_(k-j)), the convolution done with power-of-two FFTs.
  function _bluestein(re, im, plan) {
    const N = re.length;
    const {M, cr, ci, h} = plan;
    const xr = new Float64Array(M), xi = new Float64Array(M);
    for (let k = 0; k < N; k++) {
      xr[k] = re[k] * cr[k] - im[k] * ci[k];
      xi[k] = re[k] * ci[k] + im[k] * cr[k];
    }
    const X = fft(xr, xi);
    // The inverse FFT as conj(fft(conj(.))) / M.
    for (let k = 0; k < M; k++) {
      xr[k] = X.re[k] * h.re[k] - X.im[k] * h.im[k];
      xi[k] = -(X.re[k] * h.im[k] + X.im[k] * h.re[k]);
    }
    const Y = fft(xr, xi);
    const outRe = new Float64Array(N), outIm = new Float64Array(N);
    for (let k = 0; k < N; k++) {
      const yr = Y.re[k] / M, yi = -Y.im[k] / M;
      outRe[k] = yr * cr[k] - yi * ci[k];
      outIm[k] = yr * ci[k] + yi * cr[k];
    }
    return {re: outRe, im: outIm};
  }

  // The DFT X[k] = sum_j x[j] exp(-2πijk/N) of any length N (numpy.fft.fft, without
  // normalization): a mixed-radix Stockham FFT (radix 4, 2, 3, 5 and small primes), or
  // Bluestein's method when N has a prime factor above MAX_DIRECT_FACTOR.
  function fft(re, im) {
    const N = re.length;
    if (N <= 1) return {re: Float64Array.from(re), im: Float64Array.from(im)};
    const plan = _plan(N);
    if (plan.bluestein) return _bluestein(re, im, plan);
    let xr = Float64Array.from(re), xi = Float64Array.from(im);
    let yr = new Float64Array(N), yi = new Float64Array(N);
    let s = 1, len = N;
    for (const r of plan.factors) {
      const m = len / r;
      _stage(r, m, s, N, xr, xi, yr, yi, plan.w.re, plan.w.im);
      [xr, yr] = [yr, xr];
      [xi, yi] = [yi, xi];
      s *= r;
      len = m;
    }
    return {re: xr, im: xi};
  }

  // The twiddles exp(-2πiq/N) of the zero-padded spectrum, for the last length.
  let _padTwiddles = null;

  // |fft(signal, N)| (numpy's order), N = SPECTRUM_PADDING * n: the signal zero padded
  // to N. The zero padding makes the spectrum SPECTRUM_PADDING DFTs of length n: with
  // k = P m + r (P = SPECTRUM_PADDING), X[k] = sum_j (x_j exp(-2πijr/N)) exp(-2πijm/n).
  // The small FFTs are optimized sooner than one FFT of length N (the first spectrum of
  // a page is shorter, measured in Node 24), and a prime n needs Bluestein's method only
  // on length n.
  function spectrumMagnitudes(sigRe, sigIm) {
    const n = sigRe.length;
    const P = SPECTRUM_PADDING;
    const N = P * n;
    if (_padTwiddles === null || _padTwiddles.re.length !== N) _padTwiddles = _twiddles(N);
    const wr = _padTwiddles.re, wi = _padTwiddles.im;
    const mag = new Float64Array(N);
    const yr = new Float64Array(n), yi = new Float64Array(n);
    for (let r = 0; r < P; r++) {
      for (let j = 0; j < n; j++) {
        const c = wr[j * r], d = wi[j * r];
        yr[j] = sigRe[j] * c - sigIm[j] * d;
        yi[j] = sigRe[j] * d + sigIm[j] * c;
      }
      const Y = fft(yr, yi);
      for (let m = 0; m < n; m++) mag[P * m + r] = Math.hypot(Y.re[m], Y.im[m]);
    }
    return mag;
  }

  // `rf_profiles._spectrum_fwhm_hz`: the FWHM (Hz) of |fft(signal, N)|, N =
  // SPECTRUM_PADDING * n (zero padded), on the frequencies of numpy.fft.fftfreq(N, dt):
  // k * (1 / (N dt)) for k = 0 .. floor((N - 1) / 2), and k - N for the rest. The
  // largest minus the smallest frequency with a magnitude at or above half the maximum
  // (`profile_metrics.fwhm`; numpy's fftshift does not change them).
  function spectrumFwhmHz(sigRe, sigIm, dtS) {
    const mag = spectrumMagnitudes(sigRe, sigIm);
    const N = mag.length;
    const half = _max(mag) / 2;
    const val = 1.0 / (N * dtS);
    const positive = Math.floor((N - 1) / 2);
    let lo = Infinity, hi = -Infinity;
    for (let k = 0; k < N; k++) {
      if (mag[k] >= half) {
        const f = (k <= positive ? k : k - N) * val;
        if (f < lo) lo = f;
        if (f > hi) hi = f;
      }
    }
    return hi - lo;
  }

  // ---- The file data ----

  // One labeled file entry of the card data (`cards.rf_profile.rf_profile_data`) and its
  // RF table (`entry.rf`, decoded to typed arrays by the caller), as the object that the
  // functions below read.
  function fileData(entry, rfTables) {
    if (!entry.labeled) {
      throw new Error(
        `RfProfiles.fileData needs a use label on each RF event, and the file ` +
        `${_pyRepr(entry.name)} has an RF event with the use 'undefined' (labeled is ` +
        "false): set use= in the pypulseq make_*_pulse functions");
    }
    for (const name of [...RF_COLUMNS, ...RF_POOLS]) {
      if (!rfTables || !(name in rfTables)) {
        throw new Error(`RfProfiles.fileData: the RF table has no column "${name}"`);
      }
    }
    const rows = rfTables.key.length;
    for (const name of RF_COLUMNS) {
      if (rfTables[name].length !== rows) {
        throw new Error(`RfProfiles.fileData: the RF table column "${name}" has ` +
          `${rfTables[name].length} values, not ${rows}`);
      }
    }
    if (rfTables.shape_re.length !== rfTables.shape_im.length) {
      throw new Error("RfProfiles.fileData: the pools shape_re and shape_im have " +
        "different lengths");
    }
    const fov = entry.fov_m;
    return Object.freeze({
      name: entry.name,
      rf: rfTables,
      sliceThicknessM: entry.slice_thickness_m ?? null,
      fovM: fov === null || fov === undefined ? null : Object.freeze(Array.from(fov, Number)),
      gammaHzPerT: entry.gamma_hz_per_t,
      b0T: entry.b0_t,
      firstRfBlock: entry.first_rf_block ?? null,
    });
  }

  // ---- One block (rf_profiles.block_pulse and its helpers) ----

  function _checkMaxBlocks(maxBlocks) {
    if (_index(maxBlocks) < 1) {
      throw new RangeError(`max_blocks must be at least 1: ${_pyRepr(maxBlocks)}`);
    }
  }

  function _playIndex(seqView, block) {
    const i = _index(block);
    if (!(i >= 0 && i < seqView.numBlocks)) {
      throw new RangeError(`block ${block} is not a play index: the sequence has ` +
        `${seqView.numBlocks} blocks`);
    }
    return i;
  }

  // `rf_profiles._plays_during`: the gradient event plays during the RF (block times)
  // when [delay, delay + last offset] overlaps [rfStart, rfEnd] by more than
  // TIME_TOLERANCE. (Python uses pp.calc_duration(g) for the end, the same time.)
  function _playsDuring(ge, rfStart, rfEnd) {
    const n = ge.offsetsS.length;
    const end = ge.delayS + (n > 0 ? ge.offsetsS[n - 1] : 0);
    return ge.delayS < rfEnd - TIME_TOLERANCE && end > rfStart + TIME_TOLERANCE;
  }

  // The points of one gradient event (`seq_utils.gradient_points(g, 0.0)`): times
  // delay + offset (s) and amplitudes in Hz/m, with the cumulative trapezoid of
  // `_piecewise_integral`.
  function _gradPoints(seqView, k) {
    const ge = seqView.gradEvent(k);
    const P = ge.offsetsS.length;
    const t = new Float64Array(P), g = new Float64Array(P);
    for (let p = 0; p < P; p++) {
      t[p] = ge.delayS + ge.offsetsS[p];
      g[p] = ge.values[p] * seqView.gradHzPerValue;
    }
    return {t, g, cum: _cumulative(t, g)};
  }

  // [0, cumsum((t[i+1] - t[i]) * (g[i+1] + g[i]) / 2)]: the integral from t[0] to each
  // point.
  function _cumulative(t, g) {
    const P = t.length;
    const cum = new Float64Array(Math.max(P, 1));
    let c = 0;
    for (let i = 0; i + 1 < P; i++) {
      const term = (t[i + 1] - t[i]) * (g[i + 1] + g[i]) / 2;
      c = i === 0 ? term : c + term;
      cum[i + 1] = c;
    }
    return cum;
  }

  // First index with t[idx] > x (numpy.searchsorted side "right").
  function _searchRight(t, x) {
    let lo = 0, hi = t.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (t[mid] <= x) lo = mid + 1; else hi = mid;
    }
    return lo;
  }

  // First index with t[idx] >= x (numpy.searchsorted side "left").
  function _searchLeft(t, x) {
    let lo = 0, hi = t.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (t[mid] < x) lo = mid + 1; else hi = mid;
    }
    return lo;
  }

  // The value at x of the segment i of the piecewise-linear function (t, g).
  function _segmentValue(t, g, x, i) {
    const span = t[i + 1] - t[i];
    const slope = span > 0 ? (g[i + 1] - g[i]) / span : 0.0;
    return g[i] + (x - t[i]) * slope;
  }

  // `rf_profiles._piecewise_integral` for one interval [a, b]: sets `out.total` (the
  // integral of the function through (t, g), 0 outside [t[0], t[-1]]) and `out.mid`
  // (its mean when the whole interval is inside one segment, else NaN). The same
  // clipping, searchsorted sides and sums as the numpy code.
  function _intervalIntegral(t, g, cum, a, b, out) {
    const P = t.length;
    if (P < 2) {
      out.total = 0;
      out.mid = NaN;
      return;
    }
    const t0 = t[0], tN = t[P - 1];
    const aa = a > t0 ? a : t0, bb = b > t0 ? b : t0;
    const lo = aa < tN ? aa : tN, hi = bb < tN ? bb : tN;
    const last = P - 2;
    let i0 = _searchRight(t, lo) - 1;
    i0 = i0 < 0 ? 0 : i0 > last ? last : i0;
    let i1 = _searchLeft(t, hi) - 1;
    i1 = i1 < 0 ? 0 : i1 > last ? last : i1;
    const same = i0 === i1;
    const mid = _segmentValue(t, g, (lo + hi) / 2, i0);
    let total = 0.0;
    if (hi > lo) {
      if (same) {
        total = (hi - lo) * mid;
      } else {
        const head = (t[i0 + 1] - lo) * (_segmentValue(t, g, lo, i0) + g[i0 + 1]) / 2;
        const tail = (hi - t[i1]) * (g[i1] + _segmentValue(t, g, hi, i1)) / 2;
        total = head + (cum[i1] - cum[i0 + 1]) + tail;
      }
    }
    const inside = same && hi > lo && a >= t0 && b <= tN;
    out.total = total;
    out.mid = inside ? mid : NaN;
  }

  // `rf_profiles._piecewise_integral` for the intervals [a[i], b[i]] (arrays or
  // numbers): {total, mid}, each a Float64Array.
  function pieceWiseIntegral(t, g, a, b) {
    const as = typeof a === "number" ? [a] : a, bs = typeof b === "number" ? [b] : b;
    const tt = Float64Array.from(t), gg = Float64Array.from(g);
    const cum = _cumulative(tt, gg);
    const total = new Float64Array(as.length), mid = new Float64Array(as.length);
    const out = {total: 0, mid: 0};
    for (let i = 0; i < as.length; i++) {
      _intervalIntegral(tt, gg, cum, as[i], bs[i], out);
      total[i] = out.total;
      mid[i] = out.mid;
    }
    return {total, mid};
  }

  // `rf_profiles._gradient_kind` of the interval gradients (n * 3): {kind, selectKind,
  // direction, selectGradient, constant}. The mean is the sum over the intervals in
  // order, divided by n; the norms are Math.hypot.
  function gradientKind(grad) {
    const n = grad.length / 3;
    let any = false;
    for (let q = 0; q < grad.length; q++) {
      if (grad[q] !== 0) { any = true; break; }
    }
    const none = {kind: "none", selectKind: null, direction: null, selectGradient: null,
      constant: false};
    if (!any) return none;
    let sx = grad[0], sy = grad[1], sz = grad[2];
    for (let k = 1; k < n; k++) {
      sx += grad[3 * k]; sy += grad[3 * k + 1]; sz += grad[3 * k + 2];
    }
    const mean = [sx / n, sy / n, sz / n];
    const norm = Math.hypot(mean[0], mean[1], mean[2]);
    if (norm > 0) {
      const ux = mean[0] / norm, uy = mean[1] / norm, uz = mean[2] / norm;
      let peak = -Infinity;
      for (let k = 0; k < n; k++) {
        const h = Math.hypot(grad[3 * k], grad[3 * k + 1], grad[3 * k + 2]);
        if (h > peak || h !== h) peak = h;
      }
      const limit = PARALLEL_TOL * peak;
      let parallel = true;
      for (let k = 0; k < n && parallel; k++) {
        const gx = grad[3 * k], gy = grad[3 * k + 1], gz = grad[3 * k + 2];
        const d = gx * ux + gy * uy + gz * uz;
        if (!(Math.hypot(gx - d * ux, gy - d * uy, gz - d * uz) <= limit)) parallel = false;
      }
      if (parallel) {
        let spread = -Infinity;
        for (let k = 0; k < n; k++) {
          for (let j = 0; j < 3; j++) {
            const v = Math.abs(grad[3 * k + j] - mean[j]);
            if (v > spread || v !== v) spread = v;
          }
        }
        const constant = spread <= CONSTANT_TOL * norm;
        const on = [];
        for (let j = 0; j < 3; j++) {
          for (let k = 0; k < n; k++) {
            if (grad[3 * k + j] !== 0) { on.push(j); break; }
          }
        }
        if (on.length === 1) {
          const j = on[0];
          const direction = new Float64Array(3);
          direction[j] = 1.0;
          return {kind: "one", selectKind: AXIS_NAMES[j], direction, selectGradient: mean[j],
            constant};
        }
        return {kind: "one", selectKind: "select", direction: Float64Array.of(ux, uy, uz),
          selectGradient: norm, constant};
      }
    }
    // A mean of zero (for example a bipolar gradient on one axis) has no direction.
    return {kind: "changing", selectKind: null, direction: null, selectGradient: null,
      constant: false};
  }

  // `rf_profiles._pulse_core` of the block `i` (with RF): the RF as played, its numbers,
  // and the gradient of each hold interval.
  function _pulseCore(seqView, file, i) {
    const ev = seqView.events(i);
    const r = ev.rf - 1;
    const rf = file.rf;
    const gamma = file.gammaHzPerT;
    const at = rf.shape_at[r], n = rf.shape_n[r];
    const dt = rf.dt[r];
    const f = rf.freq_hz[r], phase = rf.phase_rad[r];
    const baseRe = rf.shape_re, baseIm = rf.shape_im;

    // As played: baseband * exp(i (phase + (2π f) t)), t = (k + 0.5) dt.
    const sigRe = new Float64Array(n), sigIm = new Float64Array(n);
    const twoPiF = 2 * Math.PI * f;
    let sumRe = 0, sumIm = 0, peak = -Infinity, energy = 0;
    for (let k = 0; k < n; k++) {
      const br = baseRe[at + k], bi = baseIm[at + k];
      const t = (k + 0.5) * dt;
      const angle = phase + twoPiF * t;
      const c = Math.cos(angle), s = Math.sin(angle);
      sigRe[k] = br * c - bi * s;
      sigIm[k] = br * s + bi * c;
      // The numbers use the baseband, without the offsets.
      sumRe += br;
      sumIm += bi;
      const b1 = Math.hypot(br, bi) / gamma * 1e6;
      if (b1 > peak || b1 !== b1) peak = b1;
      energy += b1 * b1;
    }

    // The gradient of each hold interval [rfStart + k dt, rfStart + (k + 1) dt].
    const rfStart = rf.delay[r];
    const rfEnd = rfStart + rf.shape_dur[r];
    const edges = new Float64Array(n + 1);
    for (let k = 0; k <= n; k++) edges[k] = k * dt + rfStart;
    const grad = new Float64Array(3 * n);
    const out = {total: 0, mid: 0};
    for (let j = 0; j < 3; j++) {
      const k = ev[GRAD_ATTRS[j]];
      if (k === 0 || !_playsDuring(seqView.gradEvent(k), rfStart, rfEnd)) continue;
      const pts = _gradPoints(seqView, k);
      for (let q = 0; q < n; q++) {
        _intervalIntegral(pts.t, pts.g, pts.cum, edges[q], edges[q + 1], out);
        grad[3 * q + j] = out.mid !== out.mid ? out.total / dt : out.mid;
      }
    }
    const kind = gradientKind(grad);

    return {
      use: USES[rf.use[r]],
      sigRe, sigIm, dt, grad, kind,
      freqOffset: f,
      flipDeg: (2 * Math.PI * Math.hypot(sumRe * dt, sumIm * dt)) * (180.0 / Math.PI),
      peakB1Ut: peak,
      energyUt2Ms: energy * dt * 1e3,
    };
  }

  // `rf_profiles._pulse_key`: the RF event without its phase offsets and its use (the
  // `key` column), and the dense index of the gradient event of each axis that plays
  // during the RF (0 for none). The dense indexes stand for the pypulseq ids: each maps
  // one to one to one id.
  function _pulseKey(seqView, file, i) {
    const ev = seqView.events(i);
    const r = ev.rf - 1;
    const rfStart = file.rf.delay[r];
    const rfEnd = rfStart + file.rf.shape_dur[r];
    const parts = [file.rf.key[r]];
    for (const attr of GRAD_ATTRS) {
      const k = ev[attr];
      parts.push(k !== 0 && _playsDuring(seqView.gradEvent(k), rfStart, rfEnd) ? k : 0);
    }
    return parts.join("|");
  }

  // `rf_profiles._echo_pathway` of the excitation in the block `i`: {echo, reason}.
  // Block by block in play order, in block times: the own block from the RF end, then
  // the blocks after it, at most `maxBlocks`. A block without RF and ADC adds the whole
  // integral of each of its gradient events (kept for each dense event). In a block with
  // RF or ADC, the events in time order (the ADC first at the same time): a refocusing
  // RF at delay + center changes the sign of the moment; an excitation RF at its delay
  // stops (NO_ADC); an RF of another use stops (OTHER_RF_BEFORE_ADC); the ADC centre
  // stops with the pathway, when it is not before the start of the walk in that block.
  function _echoPathway(seqView, file, i, maxBlocks) {
    const rf = file.rf;
    const moment = new Float64Array(3);
    let count = 0;
    const points = new Map();
    const whole = new Map();
    const tmp = {total: 0, mid: 0};
    const pointsOf = k => {
      let p = points.get(k);
      if (p === undefined) { p = _gradPoints(seqView, k); points.set(k, p); }
      return p;
    };
    const add = (ev, a, b) => {
      for (let j = 0; j < 3; j++) {
        const k = ev[GRAD_ATTRS[j]];
        if (k === 0) continue;
        const p = pointsOf(k);
        _intervalIntegral(p.t, p.g, p.cum, a, b, tmp);
        moment[j] += tmp.total;
      }
    };
    const walk = (block, start, duration, own) => {
      const ev = seqView.events(block);
      const events = [];
      if (ev.rf !== 0 && !own) {
        const r = ev.rf - 1;
        const use = USES[rf.use[r]];
        if (use === "refocusing") events.push([rf.delay[r] + rf.center[r], 1, "refocusing"]);
        else if (use === "excitation") events.push([rf.delay[r], 1, REASONS.NO_ADC]);
        else events.push([rf.delay[r], 1, REASONS.OTHER_RF_BEFORE_ADC]);
      }
      if (ev.adc !== 0) {
        const adc = seqView.adcEvent(ev.adc);
        const centre = adc.delayS + adc.lengthS / 2;
        if (centre >= start) events.push([centre, 0, "adc"]);
      }
      events.sort((p, q) => (p[0] < q[0] ? -1 : p[0] > q[0] ? 1 : p[1] - q[1]));
      let at = start;
      for (const [time, , what] of events) {
        add(ev, at, time);
        at = time;
        if (what !== "refocusing") return what;
        for (let j = 0; j < 3; j++) moment[j] = -moment[j];
        count += 1;
      }
      add(ev, at, duration);
      return null;
    };
    const result = (stop, j) => {
      if (stop === "adc") {
        const echo = Object.freeze({momentPerM: Float64Array.from(moment),
          sign: count % 2 === 0 ? 1 : -1, adcBlock: j});
        return {echo, reason: null};
      }
      return {echo: null, reason: stop};
    };

    const r = seqView.events(i).rf - 1;
    let stop = walk(i, rf.delay[r] + rf.shape_dur[r], seqView.blockDuration(i), true);
    if (stop !== null) return result(stop, i);
    const last = Math.min(seqView.numBlocks - 1, i + maxBlocks);
    for (let j = i + 1; j <= last; j++) {
      const ev = seqView.events(j);
      if (ev.rf === 0 && ev.adc === 0) {
        for (let axis = 0; axis < 3; axis++) {
          const k = ev[GRAD_ATTRS[axis]];
          if (k === 0) continue;
          let value = whole.get(k);
          if (value === undefined) {
            const p = pointsOf(k);
            _intervalIntegral(p.t, p.g, p.cum, p.t[0], p.t[p.t.length - 1], tmp);
            value = tmp.total;
            whole.set(k, value);
          }
          moment[axis] += value;
        }
        continue;
      }
      stop = walk(j, 0.0, seqView.blockDuration(j), false);
      if (stop !== null) return result(stop, j);
    }
    return {echo: null, reason: REASONS.NO_ADC};
  }

  // `rf_profiles._block_pulse`: the pulse of the block `i`, or null without RF. The
  // echo pathway only for an excitation with `withEcho`.
  function _blockPulse(seqView, file, i, withEcho, maxBlocks) {
    const ev = seqView.events(i);
    if (ev.rf === 0) return null;
    const core = _pulseCore(seqView, file, i);
    const kind = core.kind;
    const nominal = file.sliceThicknessM;
    const notes = [];
    let centre = null;
    if (kind.kind === "one") {
      centre = core.freqOffset / kind.selectGradient;
      if (nominal === null) notes.push(REASONS.NO_SLICE_THICKNESS);
      if (!kind.constant && core.freqOffset !== 0) notes.push(REASONS.OFF_CENTRE_CHANGES);
    }
    let echo = null, reason = null;
    if (withEcho && core.use === "excitation") {
      ({echo, reason} = _echoPathway(seqView, file, i, maxBlocks));
    }
    return Object.freeze({
      block: i,
      use: core.use,
      sigRe: core.sigRe,
      sigIm: core.sigIm,
      dtS: core.dt,
      grad: core.grad,
      gradientKind: kind.kind,
      selectKind: kind.selectKind,
      direction: kind.direction,
      selectGradientHzPerM: kind.selectGradient,
      constantGradient: kind.constant,
      freqOffsetHz: core.freqOffset,
      sliceCentreM: centre,
      flipDeg: core.flipDeg,
      peakB1Ut: core.peakB1Ut,
      energyUt2Ms: core.energyUt2Ms,
      nominalM: nominal,
      fovM: file.fovM,
      key: _pulseKey(seqView, file, i),
      echo,
      echoReason: reason,
      notes: Object.freeze(notes),
    });
  }

  // `rf_profiles.block_pulse`: the RF pulse of the block at play index `block`, as
  // played, or null when it has no RF.
  function blockPulse(seqView, file, block, {maxBlocks = PERIOD_MAX_BLOCKS} = {}) {
    _checkMaxBlocks(maxBlocks);
    const i = _playIndex(seqView, block);
    return _blockPulse(seqView, file, i, true, maxBlocks);
  }

  // ---- The period (rf_profiles.period) ----

  // A block with an RF or an ADC.
  function _hasEvent(ev) {
    return ev.rf !== 0 || ev.adc !== 0;
  }

  // The last block at or before `b` with an RF or an ADC, or -1 (no limit, as
  // `_last_event_before`).
  function _lastEventAtOrBefore(seqView, b) {
    for (let p = b; p >= 0; p--) if (_hasEvent(seqView.events(p))) return p;
    return -1;
  }

  // `_starts_among` for one block `b` with an RF or an ADC: a start when it has an RF
  // that is not a refocusing pulse and the last block before it with an RF or an ADC has
  // an ADC (`lastWasAdc`, true when there is none); the first RF block always is.
  function _isStart(file, b, ev, lastWasAdc) {
    if (b === file.firstRfBlock) return true;
    return ev.rf !== 0 && USES[file.rf.use[ev.rf - 1]] !== "refocusing" && lastWasAdc;
  }

  // `rf_profiles.period`: the period that contains the block `block`. The rule of each
  // block depends only on the block and the last event before it, so the walks look
  // only as far as they need: back from `block` to the last start (at most `maxBlocks`
  // blocks, else `truncated`), and forward from max(start, block) to the next start (at
  // most `maxBlocks` blocks, else `truncated`, except at the end of the file).
  function period(seqView, file, block, {maxBlocks = PERIOD_MAX_BLOCKS} = {}) {
    _checkMaxBlocks(maxBlocks);
    const i = _playIndex(seqView, block);
    if (file.firstRfBlock === null) {
      throw new Error("period: the sequence has no RF pulse, so it has no period");
    }
    let truncated = false;
    const firstRf = file.firstRfBlock;
    let first = -1;
    if (i < firstRf) {
      first = firstRf;
    } else {
      const lo = Math.max(0, i - maxBlocks);
      // Down from i: each event block waits for the event block before it.
      let cand = -1, candEv = null;
      for (let b = i; b >= lo; b--) {
        const ev = seqView.events(b);
        if (!_hasEvent(ev)) continue;
        if (cand >= 0 && _isStart(file, cand, candEv, ev.adc !== 0)) {
          first = cand;
          break;
        }
        cand = b;
        candEv = ev;
      }
      if (first < 0 && cand >= 0) {
        // The lowest event block of the walk: the event before it is before `lo`.
        if (cand === firstRf) {
          first = cand;
        } else {
          const p = _lastEventAtOrBefore(seqView, cand - 1);
          if (_isStart(file, cand, candEv, p < 0 || seqView.events(p).adc !== 0)) first = cand;
        }
      }
      if (first < 0) {
        // The first RF block is a start before `lo`, so the period starts before the
        // limit of the walk.
        first = lo;
        truncated = true;
      }
    }

    const anchor = Math.max(first, i);
    const hi = Math.min(seqView.numBlocks, anchor + maxBlocks + 1);
    const before = _lastEventAtOrBefore(seqView, anchor);
    let lastWasAdc = before < 0 || seqView.events(before).adc !== 0;
    let last = -1;
    for (let b = anchor + 1; b < hi; b++) {
      const ev = seqView.events(b);
      if (!_hasEvent(ev)) continue;
      if (_isStart(file, b, ev, lastWasAdc)) {
        last = b - 1;
        break;
      }
      lastWasAdc = ev.adc !== 0;
    }
    if (last < 0) {
      last = hi - 1;
      if (hi !== seqView.numBlocks) truncated = true;
    }

    // The first ADC block, and the RF blocks grouped by the pulse key (computed once for
    // each distinct (rf, gx, gy, gz)), in the order of their first block.
    let firstAdc = null;
    const keyOfCombo = new Map();
    const groups = new Map();
    for (let b = first; b <= last; b++) {
      const ev = seqView.events(b);
      if (ev.adc !== 0 && firstAdc === null) firstAdc = b;
      if (ev.rf === 0) continue;
      const combo = `${ev.rf},${ev.gx},${ev.gy},${ev.gz}`;
      let key = keyOfCombo.get(combo);
      if (key === undefined) {
        key = _pulseKey(seqView, file, b);
        keyOfCombo.set(combo, key);
      }
      let group = groups.get(key);
      if (group === undefined) {
        group = {key, use: USES[file.rf.use[ev.rf - 1]], firstBlock: b, lastBlock: b, count: 0};
        groups.set(key, group);
      }
      group.lastBlock = b;
      group.count += 1;
    }
    return Object.freeze({
      firstBlock: first,
      lastBlock: last,
      pulses: Object.freeze(Array.from(groups.values(), g => Object.freeze(g))),
      firstAdcBlock: firstAdc,
      truncated,
    });
  }

  // ---- The views (rf_profiles.view_spec) ----

  function _checkN(n) {
    if (n !== null && n !== undefined && _index(n) < 2) {
      throw new Error(`n must be at least 2: ${_pyRepr(n)}`);
    }
  }

  function _axis(kind, lo, hi, n) {
    return Object.freeze({kind, lo, hi, n});
  }

  function _spec(axes) {
    return Object.freeze({axes: Object.freeze(axes), at: Object.freeze({})});
  }

  // `rf_profiles._select_range`: the select range [lo, hi] of the "profile" view of a
  // pulse of kind "one": c ± 2 W, or c ± 2 (spectrum FWHM / |G|) without W.
  function _selectRange(pulse) {
    let half;
    if (pulse.nominalM !== null) {
      half = 2 * pulse.nominalM;
    } else {
      const thickness = spectrumFwhmHz(pulse.sigRe, pulse.sigIm, pulse.dtS) /
        Math.abs(pulse.selectGradientHzPerM);
      half = 2 * thickness;
    }
    const c = pulse.sliceCentreM;
    return [c - half, c + half];
  }

  // `rf_profiles.view_spec`: {spec, reason} of the view "profile", "z_df" or "2d" of
  // `pulse`; `spec` is {axes: [{kind, lo, hi, n}], at: {}}, or null with the reason.
  function viewSpec(pulse, view = "profile", {plane = null, extentM = null, n = null} = {}) {
    if (view !== "profile" && view !== "z_df" && view !== "2d") {
      throw new Error(`view must be 'profile', 'z_df' or '2d': ${_pyRepr(view)}`);
    }
    _checkN(n);
    const kind = pulse.gradientKind;
    const done = (spec, reason) => Object.freeze({spec, reason});
    if (view === "profile") {
      if (kind === "changing") return done(null, REASONS.DIRECTION_CHANGES);
      const points = n || NUM_POSITIONS;
      if (kind === "none") {
        const half = 2 * spectrumFwhmHz(pulse.sigRe, pulse.sigIm, pulse.dtS);
        const f = pulse.freqOffsetHz;
        return done(_spec([_axis("df", f - half, f + half, points)]), null);
      }
      const [lo, hi] = _selectRange(pulse);
      return done(_spec([_axis(pulse.selectKind, lo, hi, points)]), null);
    }

    if (view === "z_df") {
      if (kind === "none") return done(null, REASONS.NO_GRADIENT_Z_DF);
      if (kind === "changing") return done(null, REASONS.DIRECTION_CHANGES);
      const points = n || Math.floor((NUM_POSITIONS + 1) / 2);
      const [lo, hi] = _selectRange(pulse);
      const step = Math.abs(pulse.selectGradientHzPerM) * (hi - lo) / (points - 1);
      const half = (points - 1) / 2 * step;
      return done(_spec([_axis(pulse.selectKind, lo, hi, points),
        _axis("df", -half, half, points)]), null);
    }

    if (kind === "one") return done(null, REASONS.NO_MAP_ONE);
    if (kind === "none") return done(null, REASONS.NO_MAP_NONE);
    let names;
    if (plane === null || plane === undefined) {
      // The two axes with the largest RMS gradient (a stable sort), in the order x, y, z.
      const g = pulse.grad;
      const count = g.length / 3;
      const rms = [0, 0, 0];
      for (let j = 0; j < 3; j++) {
        let s = g[j] * g[j];
        for (let k = 1; k < count; k++) s += g[3 * k + j] * g[3 * k + j];
        rms[j] = Math.sqrt(s / count);
      }
      const order = [0, 1, 2].sort((p, q) => (-rms[p] < -rms[q] ? -1 : -rms[p] > -rms[q] ? 1 : p - q));
      const top = order.slice(0, 2).sort((p, q) => p - q);
      names = [AXIS_NAMES[top[0]], AXIS_NAMES[top[1]]];
    } else if (plane.length !== 2 || plane[0] === plane[1] ||
               !AXIS_NAMES.includes(plane[0]) || !AXIS_NAMES.includes(plane[1])) {
      throw new Error(`plane must be two different axes of 'x', 'y', 'z': ${_pyRepr(Array.from(plane))}`);
    } else {
      names = [plane[0], plane[1]];
    }
    let extents;
    if (extentM !== null && extentM !== undefined) {
      if (!(Number.isFinite(extentM) && extentM > 0)) {
        throw new Error(`extent_m must be a positive length (m): ${_pyRepr(extentM)}`);
      }
      extents = [extentM, extentM];
    } else if (pulse.fovM !== null) {
      extents = names.map(name => pulse.fovM[AXIS_NAMES.indexOf(name)]);
    } else {
      return done(null, REASONS.NO_FOV);
    }
    const points = n || MAP_POINTS;
    return done(_spec(names.map((name, k) => _axis(name, -extents[k] / 2, extents[k] / 2, points))),
      null);
  }

  // ---- Simulation (rf_profiles.simulate) ----

  // `rf_profiles._check_spec`: the rules of the specs, with Python's messages.
  function _checkSpec(pulse, spec) {
    const at = spec.at || {};
    const kinds = spec.axes.map(axis => axis.kind).concat(Object.keys(at));
    for (const kind of kinds) {
      if (!AXIS_KINDS.includes(kind)) {
        throw new Error(`a spec kind must be one of ${_pyRepr(AXIS_KINDS.slice())}: ${_pyRepr(kind)}`);
      }
    }
    if (new Set(kinds).size !== kinds.length) {
      throw new Error(`each kind at most once in the axes and \`at\` together: ${_pyList(kinds)}`);
    }
    if (kinds.includes("select")) {
      if (AXIS_NAMES.some(name => kinds.includes(name))) {
        throw new Error("'select' cannot be in a spec together with 'x', 'y' or 'z'");
      }
      if (pulse.selectKind !== "select") {
        throw new Error("'select' needs a pulse whose select coordinate is 'select' (a " +
          "gradient of kind 'one' on more than one axis); this pulse has " +
          _pyRepr(pulse.selectKind));
      }
    }
    let total = 1;
    for (const axis of spec.axes) {
      if (typeof axis.n !== "number" || !Number.isInteger(axis.n)) {
        throw new TypeError(`the number of points must be an int: ${_pyRepr(axis.n)}`);
      }
      if (axis.n < 2) throw new Error(`an axis needs at least 2 points: ${_axisRepr(axis)}`);
      if (!(Number.isFinite(axis.lo) && Number.isFinite(axis.hi) && axis.lo < axis.hi)) {
        throw new Error(`an axis needs finite lo < hi: ${_axisRepr(axis)}`);
      }
      total *= axis.n;
    }
    for (const kind of Object.keys(at)) {
      if (!Number.isFinite(Number(at[kind]))) {
        throw new Error(`the \`at\` value of ${_pyRepr(kind)} must be finite: ${_pyRepr(at[kind])}`);
      }
    }
    if (total > MAX_POINTS) {
      throw new Error(`the grid has ${total} points, more than MAX_POINTS = ${MAX_POINTS}`);
    }
  }

  // `rf_profiles._grid_values`: the grid (numpy.linspace of each axis), the shape, the
  // number of points, and the value of each kind at each point (meshgrid "ij", C order:
  // the first axis slowest), with the `at` values.
  function _gridValues(spec) {
    const axes = spec.axes;
    const grid = axes.map(axis => linspace(axis.lo, axis.hi, axis.n));
    const shape = axes.map(axis => axis.n);
    let count = 1;
    for (const n of shape) count *= n;
    const values = {};
    for (let d = 0; d < axes.length; d++) {
      const v = new Float64Array(count);
      let inner = 1;
      for (let e = d + 1; e < axes.length; e++) inner *= shape[e];
      const g = grid[d], n = shape[d];
      for (let p = 0; p < count; p++) v[p] = g[Math.floor(p / inner) % n];
      values[axes[d].kind] = v;
    }
    const at = spec.at || {};
    for (const kind of Object.keys(at)) values[kind] = new Float64Array(count).fill(Number(at[kind]));
    return {grid, shape, count, values};
  }

  // `rf_profiles._positions`: the (count, 3) positions: x, y, z from their values (else
  // 0), or the "select" value times the pulse direction (added to the zeros).
  function _positions(pulse, values, count) {
    const pos = new Float64Array(3 * count);
    for (let j = 0; j < 3; j++) {
      const v = values[AXIS_NAMES[j]];
      if (v === undefined) continue;
      for (let p = 0; p < count; p++) pos[3 * p + j] = v[p];
    }
    const s = values.select;
    if (s !== undefined) {
      const dir = pulse.direction;
      for (let p = 0; p < count; p++) {
        for (let j = 0; j < 3; j++) pos[3 * p + j] = pos[3 * p + j] + s[p] * dir[j];
      }
    }
    return pos;
  }

  // `rf_profiles._shear_simulation`: a z x df spec of a constant gradient G whose df
  // step is |G| times the u step (SHEAR_RTOL) is one 1D simulation of the distinct
  // values v = (u.lo + f.lo / G) + (m_min + i) * du; the grid point (i, j) takes the
  // value m = i + sign(G) j. Returns {count, positions, index} or null.
  function _shearPlan(pulse, spec) {
    const axes = spec.axes;
    if (pulse.gradientKind !== "one" || !pulse.constantGradient || axes.length !== 2 ||
        axes[0].kind !== pulse.selectKind || axes[1].kind !== "df") {
      return null;
    }
    const [u, f] = axes;
    const g = pulse.selectGradientHzPerM;
    const du = (u.hi - u.lo) / (u.n - 1);
    const step = (f.hi - f.lo) / (f.n - 1);
    if (Math.abs(step - Math.abs(g) * du) > SHEAR_RTOL * Math.abs(g) * du) return null;
    const sign = g > 0 ? 1 : -1;
    const mMin = sign > 0 ? 0 : -(f.n - 1);
    const count = u.n + f.n - 1;
    const v = new Float64Array(count);
    const base = u.lo + f.lo / g;
    for (let q = 0; q < count; q++) v[q] = base + (mMin + q) * du;
    const values = {[pulse.selectKind]: v};
    const at = spec.at || {};
    for (const kind of Object.keys(at)) values[kind] = new Float64Array(count).fill(Number(at[kind]));
    const index = new Int32Array(u.n * f.n);
    for (let i = 0; i < u.n; i++) {
      for (let j = 0; j < f.n; j++) index[i * f.n + j] = i + sign * j - mMin;
    }
    return {count, positions: _positions(pulse, values, count), index};
  }

  function _now() {
    return performance.now();
  }

  // The number of points between two looks at the clock.
  function _chunkPoints(samples) {
    return Math.max(1, Math.floor(CHECK_WORK / Math.max(1, samples)));
  }

  // `rf_profiles.simulate` as sliced work: {step(budgetMs), done, result()}. `step`
  // computes points until the clock passes its start plus `budgetMs` (at least one
  // chunk of points in each call, so step(0) makes progress) and returns the fraction
  // done (1 when done). Each point is computed on its own, so the result does not
  // depend on the slices. `result()` throws before the work is done.
  function simulation(pulse, spec) {
    _checkSpec(pulse, spec);
    const {grid, shape, count, values} = _gridValues(spec);
    const shear = _shearPlan(pulse, spec);
    let positions, df, m;
    if (shear !== null) {
      positions = shear.positions;
      df = null;
      m = shear.count;
    } else {
      positions = _positions(pulse, values, count);
      df = values.df === undefined ? null : values.df;
      m = count;
    }
    const out = {aRe: new Float64Array(m), aIm: new Float64Array(m),
      bRe: new Float64Array(m), bIm: new Float64Array(m)};
    const chunk = _chunkPoints(pulse.sigRe.length);
    let j = 0;
    let profile = null;
    return {
      step(budgetMs) {
        if (j >= m) return 1;
        const end = _now() + budgetMs;
        do {
          const j1 = Math.min(m, j + chunk);
          spinDomainRange(pulse.sigRe, pulse.sigIm, pulse.dtS, pulse.grad, positions, df, null,
            j, j1, out);
          j = j1;
        } while (j < m && _now() < end);
        return j / m;
      },
      get done() {
        return j >= m;
      },
      result() {
        if (j < m) throw new Error("RfProfiles.simulation: result() before the work is done");
        if (profile === null) {
          let {aRe, aIm, bRe, bIm} = out;
          if (shear !== null) {
            const take = src => Float64Array.from(shear.index, q => src[q]);
            aRe = take(aRe); aIm = take(aIm); bRe = take(bRe); bIm = take(bIm);
          }
          profile = Object.freeze({spec, grid: Object.freeze(grid), shape: Object.freeze(shape),
            aRe, aIm, bRe, bIm});
        }
        return profile;
      },
    };
  }

  // `rf_profiles.simulate`: the whole simulation in one call.
  function simulate(pulse, spec) {
    const work = simulation(pulse, spec);
    work.step(Infinity);
    return work.result();
  }

  // `rf_profiles.quantity`: "mxy_abs", "mz" or "beta_sq" of a profile, in C order.
  function quantity(profile, name) {
    if (name === "mxy_abs" || name === "mz") {
      const {mxyRe, mxyIm, mz} = magnetization(profile.aRe, profile.aIm, profile.bRe, profile.bIm);
      if (name === "mz") return mz;
      return Float64Array.from(mxyRe, (re, j) => Math.hypot(re, mxyIm[j]));
    }
    if (name === "beta_sq") return crushedEcho(profile.bRe, profile.bIm);
    throw new Error(`quantity must be 'mxy_abs', 'mz' or 'beta_sq': ${_pyRepr(name)}`);
  }

  // ---- Phase and widths (echo_phase, widths) ----

  // `rf_profiles._echo_mxy`: {re, im} of the Mxy of the primary echo at each point of a
  // 1D select-coordinate profile, or null.
  function _echoMxy(pulse, profile, echoMomentPerM) {
    if (pulse.use !== "excitation" || pulse.gradientKind !== "one") return null;
    const axes = profile.spec.axes;
    if (axes.length !== 1 || axes[0].kind !== pulse.selectKind) {
      throw new Error("the echo phase needs the 1D 'profile' view of the pulse");
    }
    let moment, sign;
    if (echoMomentPerM !== null && echoMomentPerM !== undefined) {
      moment = Array.from(echoMomentPerM, Number);
      if (moment.length !== 3) {
        throw new Error(`echo_moment_per_m must be 3 values (x y z): (${moment.length},)`);
      }
      sign = 1;
    } else if (pulse.echo !== null) {
      moment = pulse.echo.momentPerM;
      sign = pulse.echo.sign;
    } else {
      return null;
    }
    const {count, values} = _gridValues(profile.spec);
    const positions = _positions(pulse, values, count);
    const {mxyRe, mxyIm} = magnetization(profile.aRe, profile.aIm, profile.bRe, profile.bIm);
    if (sign < 0) for (let j = 0; j < mxyIm.length; j++) mxyIm[j] = -mxyIm[j];
    return precess(mxyRe, mxyIm, moment, positions);
  }

  // `rf_profiles.echo_phase`: the echo phase (rad) along the "profile" view, relative
  // to its value at the grid point nearest to the slice centre, NaN where |Mxy| <
  // PHASE_MIN_FRACTION * max |Mxy|; or null.
  function echoPhase(pulse, profile, {echoMomentPerM = null} = {}) {
    const echo = _echoMxy(pulse, profile, echoMomentPerM);
    if (echo === null) return null;
    const u = profile.grid[0];
    const centre = _argmin(Float64Array.from(u, v => Math.abs(v - pulse.sliceCentreM)));
    const theta = Math.atan2(echo.im[centre], echo.re[centre]);
    const c = Math.cos(-theta), s = Math.sin(-theta);
    const m = echo.re.length;
    const phase = new Float64Array(m), magnitude = new Float64Array(m);
    for (let j = 0; j < m; j++) {
      const er = echo.re[j], ei = echo.im[j];
      phase[j] = Math.atan2(er * s + ei * c, er * c - ei * s);
      magnitude[j] = Math.hypot(er, ei);
    }
    const limit = PHASE_MIN_FRACTION * _max(magnitude);
    for (let j = 0; j < m; j++) if (magnitude[j] < limit) phase[j] = NaN;
    return phase;
  }

  // `rf_profiles._width_profile`: the profile for the widths, by use.
  function _widthProfile(use, profile) {
    if (use === "refocusing") return crushedEcho(profile.bRe, profile.bIm);
    const {mxyRe, mxyIm, mz} = magnetization(profile.aRe, profile.aIm, profile.bRe, profile.bIm);
    if (use === "inversion") return Float64Array.from(mz, v => (1 - v) / 2);
    if (use === "saturation") return Float64Array.from(mz, v => 1 - v);
    return Float64Array.from(mxyRe, (re, j) => Math.hypot(re, mxyIm[j]));
  }

  // `rf_profiles._phase_numbers`: the centre phase, and the weighted least-squares line
  // through the unwrapped echo phase over |u - c| <= PASSBAND_FRACTION * W.
  function _phaseNumbers(rel, echo, nominal) {
    const out = {};
    const centre = _argmin(Float64Array.from(rel, v => Math.abs(v)));
    out.centre_phase_rad = Math.atan2(echo.im[centre], echo.re[centre]);
    const region = [];
    for (let j = 0; j < rel.length; j++) {
      if (Math.abs(rel[j]) <= PASSBAND_FRACTION * nominal) region.push(j);
    }
    if (region.length < 2) return out;
    const x = Float64Array.from(region, j => rel[j]);
    const y = unwrap(Float64Array.from(region, j => Math.atan2(echo.im[j], echo.re[j])));
    const w = Float64Array.from(region, j => Math.hypot(echo.re[j], echo.im[j]));
    const r = region.length;
    let total = 0;
    for (let q = 0; q < r; q++) total += w[q];
    if (total > 0) {
      let wx = 0, wy = 0;
      for (let q = 0; q < r; q++) { wx += w[q] * x[q]; wy += w[q] * y[q]; }
      const xMean = wx / total, yMean = wy / total;
      const dx = Float64Array.from(x, v => v - xMean);
      let spread = 0;
      for (let q = 0; q < r; q++) spread += w[q] * dx[q] * dx[q];
      if (spread > 0) {
        let cross = 0;
        for (let q = 0; q < r; q++) cross += w[q] * dx[q] * (y[q] - yMean);
        const slope = cross / spread;
        const resid = Float64Array.from(y, (v, q) => v - (yMean + slope * dx[q]));
        out.rephasing_error_rad = slope * nominal;
        out.nonlinear_residual_rad = _max(resid) - _min(resid);
      }
    }
    return out;
  }

  // `rf_profiles.widths`: the numbers of a 1D "profile" view, in the units of its axis.
  // A key is missing when its number does not apply.
  function widths(pulse, profile, {echoMomentPerM = null} = {}) {
    const axes = profile.spec.axes;
    if (axes.length !== 1) throw new Error("widths needs a 1D profile (the 'profile' view)");
    const kind = axes[0].kind;
    if (kind !== "df" && kind !== pulse.selectKind) {
      throw new Error(`widths needs a profile along the select coordinate or df, not ${_pyRepr(kind)}`);
    }
    const x = profile.grid[0];
    const main = _widthProfile(pulse.use, profile);
    const out = {fwhm: fwhm(x, main), edge_width: edgeWidth(x, main)};
    const nominal = pulse.nominalM;
    if (kind === "df" || nominal === null) return out;
    const rel = Float64Array.from(x, v => v - pulse.sliceCentreM);
    if (rel.some(v => Math.abs(v) <= 0.4 * nominal)) {
      out.passband_ripple = passbandRipple(rel, main, nominal);
    }
    if (rel.some(v => Math.abs(v) >= nominal)) {
      out.stopband_level = stopbandLevel(rel, main, nominal);
    }
    const echo = _echoMxy(pulse, profile, echoMomentPerM);
    if (echo !== null) Object.assign(out, _phaseNumbers(rel, echo, nominal));
    return out;
  }

  // ---- The combined profile (rf_profiles.combined_profile) ----

  // `_pulse_values` as sliced work: |Mxy| of an excitation, or |beta|^2 of a refocusing
  // pulse, at `positions` (m * 3) and df = 0. It yields before each chunk of points,
  // and counts the point-samples in `state.done`.
  function* _pulseValuesGen(p, positions, state) {
    const m = positions.length / 3;
    const out = {aRe: new Float64Array(m), aIm: new Float64Array(m),
      bRe: new Float64Array(m), bIm: new Float64Array(m)};
    const chunk = _chunkPoints(p.sigRe.length);
    for (let j = 0; j < m; j += chunk) {
      yield;
      const j1 = Math.min(m, j + chunk);
      spinDomainRange(p.sigRe, p.sigIm, p.dtS, p.grad, positions, null, null, j, j1, out);
      state.done += (j1 - j) * p.sigRe.length;
    }
    return _valuesOf(p, out);
  }

  function _valuesOf(p, out) {
    if (p.use === "excitation") {
      const {mxyRe, mxyIm} = magnetization(out.aRe, out.aIm, out.bRe, out.bIm);
      return Float64Array.from(mxyRe, (re, j) => Math.hypot(re, mxyIm[j]));
    }
    return crushedEcho(out.bRe, out.bIm);
  }

  // `_pulse_values` at one point, at once.
  function _pulseValues(p, positions) {
    return _valuesOf(p, spinDomain(p.sigRe, p.sigIm, p.dtS, p.grad, positions));
  }

  // `rf_profiles._directions`: the distinct select directions of the pulses of kind
  // "one", in the order of the pulses (parallel or antiparallel within PARALLEL_TOL).
  function _directions(pulses) {
    const directions = [];
    for (const p of pulses) {
      if (p.gradientKind !== "one") continue;
      const b = p.direction;
      let found = false;
      for (const d of directions) {
        const a = d.unit;
        const cx = a[1] * b[2] - a[2] * b[1];
        const cy = a[2] * b[0] - a[0] * b[2];
        const cz = a[0] * b[1] - a[1] * b[0];
        if (Math.hypot(cx, cy, cz) <= PARALLEL_TOL) {
          d.pulses.push(p);
          d.signs.push(a[0] * b[0] + a[1] * b[1] + a[2] * b[2] > 0 ? 1.0 : -1.0);
          found = true;
          break;
        }
      }
      if (!found) directions.push({kind: p.selectKind, unit: p.direction, pulses: [p], signs: [1.0]});
    }
    return directions;
  }

  // `rf_profiles._direction_points`: the 3D points at the coordinates `u` along `d`.
  function _directionPoints(d, u) {
    const pos = new Float64Array(3 * u.length);
    const axis = AXIS_NAMES.indexOf(d.kind);
    for (let i = 0; i < u.length; i++) {
      if (axis >= 0) {
        pos[3 * i + axis] = u[i];
      } else {
        for (let j = 0; j < 3; j++) pos[3 * i + j] = u[i] * d.unit[j];
      }
    }
    return pos;
  }

  // `rf_profiles._direction_product`: the product of the values of the pulses of `d`.
  function* _directionProductGen(d, positions, state) {
    let values = new Float64Array(positions.length / 3).fill(1);
    for (const p of d.pulses) {
      const v = yield* _pulseValuesGen(p, positions, state);
      values = Float64Array.from(values, (x, i) => x * v[i]);
    }
    return values;
  }

  // The select range of the "profile" view of a pulse (`view_spec(p, "profile")`),
  // kept for each pulse of one combined profile. It yields before a spectrum.
  function* _rangeGen(p, ranges) {
    let range = ranges.get(p);
    if (range === undefined) {
      if (p.nominalM === null) yield;
      range = _selectRange(p);
      ranges.set(p, range);
    }
    return range;
  }

  // `rf_profiles._direction_range`: the union of the "profile" ranges of the pulses of
  // `d`, in its coordinate.
  function* _directionRangeGen(d, ranges) {
    const lows = [], highs = [];
    for (let k = 0; k < d.pulses.length; k++) {
      const [lo, hi] = yield* _rangeGen(d.pulses[k], ranges);
      const s = d.signs[k];
      lows.push(s > 0 ? lo : -hi);
      highs.push(s > 0 ? hi : -lo);
    }
    let lo = lows[0], hi = highs[0];
    for (let k = 1; k < lows.length; k++) {
      if (lows[k] < lo) lo = lows[k];
      if (highs[k] > hi) hi = highs[k];
    }
    return [lo, hi];
  }

  // `rf_profiles._fraction_inside`: the sum of the values over |u - c| <= W / 2 divided
  // by the sum over the grid.
  function _fractionInside(u, values, centre, nominal) {
    let inside = 0, all = 0;
    for (let i = 0; i < u.length; i++) {
      if (Math.abs(u[i] - centre) <= nominal / 2) inside += values[i];
      all += values[i];
    }
    return inside / all;
  }

  // `rf_profiles._one_direction`.
  function* _oneDirectionGen(c, n, state) {
    const excitation = c.pulses[0];
    const d = c.directions[0];
    const first = d.pulses[0];
    const [lo, hi] = yield* _rangeGen(first, c.ranges);
    const u = linspace(lo, hi, n || NUM_POSITIONS);
    const positions = _directionPoints(d, u);
    let combined = new Float64Array(u.length).fill(1);
    let reference = null;
    for (const p of d.pulses) {
      const values = yield* _pulseValuesGen(p, positions, state);
      if (p === excitation) reference = values;
      combined = Float64Array.from(combined, (x, i) => x * values[i]);
    }
    combined = Float64Array.from(combined, x => x * c.factor);
    if (reference === null) {
      // An excitation of kind "none": its |Mxy| is the same at each point.
      reference = new Float64Array(u.length).fill(c.centreValue.get(excitation));
    }
    const centre = first.sliceCentreM;
    const numbers = {
      fwhm_m: fwhm(u, combined),
      edge_width_m: edgeWidth(u, combined),
      signal_kept: _trapezoid(combined, u) / _trapezoid(reference, u),
    };
    if (c.nominal !== null) numbers.fraction_inside = _fractionInside(u, combined, centre, c.nominal);
    numbers.centre_signal = _interp(centre, u, combined);
    return {line: Object.freeze({u, values: combined}), numbers};
  }

  // `rf_profiles._several_directions`.
  function* _severalDirectionsGen(c, n, state) {
    let fraction = 1.0, centreSignal = 1.0;
    for (const d of c.directions) {
      const [lo, hi] = yield* _directionRangeGen(d, c.ranges);
      const u = linspace(lo, hi, n || NUM_POSITIONS);
      const values = yield* _directionProductGen(d, _directionPoints(d, u), state);
      const centre = d.pulses[0].sliceCentreM;
      if (c.nominal !== null) fraction *= _fractionInside(u, values, centre, c.nominal);
      centreSignal *= _interp(centre, u, values);
    }
    const numbers = {centre_signal: centreSignal * c.factor};
    if (c.nominal !== null) numbers.fraction_inside = fraction;
    return numbers;
  }

  // `np.outer(a, b) * f1 (* f2)`: row-major a.length x b.length.
  function _outer(a, b, f1, f2) {
    const out = new Float64Array(a.length * b.length);
    for (let i = 0; i < a.length; i++) {
      for (let k = 0; k < b.length; k++) {
        const v = a[i] * b[k] * f1;
        out[i * b.length + k] = f2 === undefined ? v : v * f2;
      }
    }
    return out;
  }

  // `rf_profiles._combined_maps`.
  function* _combinedMapsGen(c, n, state) {
    const points = n || MAP_POINTS;
    const directions = c.directions;
    if (directions.every(d => AXIS_NAMES.includes(d.kind))) {
      const ordered = directions.slice().sort(
        (p, q) => AXIS_NAMES.indexOf(p.kind) - AXIS_NAMES.indexOf(q.kind));
      const axes = [], lines = [];
      for (const d of ordered) {
        const [lo, hi] = yield* _directionRangeGen(d, c.ranges);
        axes.push(_axis(d.kind, lo, hi, points));
        const u = linspace(lo, hi, points);
        lines.push(yield* _directionProductGen(d, _directionPoints(d, u), state));
      }
      if (ordered.length === 2) {
        return [Object.freeze({axes: Object.freeze([axes[0], axes[1]]),
          values: _outer(lines[0], lines[1], c.factor)})];
      }
      const maps = [];
      for (const [first, second, third] of [[0, 1, 2], [0, 2, 1], [1, 2, 0]]) {
        const d = ordered[third];
        const centre = Float64Array.of(d.pulses[0].sliceCentreM);
        const through = (yield* _directionProductGen(d, _directionPoints(d, centre), state))[0];
        maps.push(Object.freeze({axes: Object.freeze([axes[first], axes[second]]),
          values: _outer(lines[first], lines[second], through, c.factor)}));
      }
      return maps;
    }

    // Two directions, at least one oblique: in-plane axes s1 (along the first direction)
    // and s2 (perpendicular to it, in the plane of both).
    const [d1, d2] = directions;
    const e1 = d1.unit, u2 = d2.unit;
    const dot12 = u2[0] * e1[0] + u2[1] * e1[1] + u2[2] * e1[2];
    const across = [u2[0] - dot12 * e1[0], u2[1] - dot12 * e1[1], u2[2] - dot12 * e1[2]];
    const len = Math.hypot(across[0], across[1], across[2]);
    const e2 = [across[0] / len, across[1] / len, across[2] / len];
    const cos = dot12, sin = u2[0] * e2[0] + u2[1] * e2[1] + u2[2] * e2[2];
    const [lo1, hi1] = yield* _directionRangeGen(d1, c.ranges);
    const [lo2, hi2] = yield* _directionRangeGen(d2, c.ranges);
    const c1 = d1.pulses[0].sliceCentreM;
    // The s2 range that puts the whole range of d2 on the line s1 = c1.
    const s2Lo = (lo2 - c1 * cos) / sin, s2Hi = (hi2 - c1 * cos) / sin;
    const s1 = linspace(lo1, hi1, points), s2 = linspace(s2Lo, s2Hi, points);
    const positions = new Float64Array(3 * points * points);
    for (let i = 0; i < points; i++) {
      for (let k = 0; k < points; k++) {
        const p = i * points + k;
        for (let j = 0; j < 3; j++) positions[3 * p + j] = s1[i] * e1[j] + s2[k] * e2[j];
      }
    }
    let values = new Float64Array(points * points).fill(1);
    for (const d of directions) {
      const v = yield* _directionProductGen(d, positions, state);
      values = Float64Array.from(values, (x, i) => x * v[i]);
    }
    values = Float64Array.from(values, x => x * c.factor);
    const axes = Object.freeze([_axis("s1", lo1, hi1, points), _axis("s2", s2Lo, s2Hi, points)]);
    return [Object.freeze({axes, values})];
  }

  // The work of a combined profile after its setup: the line or the numbers, then the
  // maps.
  function* _combinedGen(c, view, n, state) {
    let line = null, maps = [], numbers;
    if (c.directions.length === 1) {
      ({line, numbers} = yield* _oneDirectionGen(c, n, state));
    } else {
      numbers = yield* _severalDirectionsGen(c, n, state);
      if (view === "2d") maps = yield* _combinedMapsGen(c, n, state);
    }
    return _combinedResult(c, line, maps, numbers);
  }

  function _combinedResult(c, line, maps, numbers) {
    return Object.freeze({
      reason: null,
      excitationBlock: c.excitationBlock,
      refocusingBlocks: Object.freeze(c.refocusingBlocks),
      factor: c.factor,
      directions: Object.freeze(c.directions.map(d => d.kind)),
      line,
      maps: Object.freeze(maps),
      numbers: Object.freeze(numbers),
    });
  }

  function _noCombined(reason) {
    return Object.freeze({
      reason,
      excitationBlock: null,
      refocusingBlocks: Object.freeze([]),
      factor: NaN,
      directions: Object.freeze([]),
      line: null,
      maps: Object.freeze([]),
      numbers: Object.freeze({}),
    });
  }

  // The part of `combined_profile` before the long work: the pulses, the reasons, the
  // factor of the pulses of kind "none", and the directions. Returns a result with a
  // reason, or the setup {excitationBlock, refocusingBlocks, pulses, factor,
  // centreValue, directions, nominal, ranges}.
  function _combinedSetup(seqView, file, per) {
    const adcBlock = per.firstAdcBlock;
    if (adcBlock === null) return _noCombined(REASONS.NO_ADC);
    const rfBlocks = [];
    for (let b = per.firstBlock; b <= adcBlock; b++) {
      if (seqView.events(b).rf !== 0) rfBlocks.push(b);
    }
    const uses = rfBlocks.map(b => USES[file.rf.use[seqView.events(b).rf - 1]]);
    const k0 = uses.lastIndexOf("excitation");
    if (k0 < 0) return _noCombined(REASONS.NO_EXCITATION);
    if (uses.slice(k0 + 1).some(use => use !== "refocusing")) {
      return _noCombined(REASONS.OTHER_RF_BEFORE_ADC);
    }
    const refocusingBlocks = rfBlocks.slice(k0 + 1);
    if (refocusingBlocks.length === 0) return _noCombined(REASONS.NO_REFOCUSING);
    const excitationBlock = rfBlocks[k0];
    const pulses = [excitationBlock, ...refocusingBlocks].map(
      b => _blockPulse(seqView, file, b, false, 0));
    if (pulses.some(p => p.gradientKind === "changing")) {
      return _noCombined(REASONS.DIRECTION_CHANGES);
    }
    let factor = 1.0;
    const centreValue = new Map();
    for (const p of pulses) {
      if (p.gradientKind === "none") {
        const v = _pulseValues(p, new Float64Array(3))[0];
        centreValue.set(p, v);
        factor *= v;
      }
    }
    const directions = _directions(pulses);
    if (directions.length > 3) return _noCombined(REASONS.MORE_THAN_THREE);
    if (directions.length === 3 && directions.some(d => !AXIS_NAMES.includes(d.kind))) {
      return _noCombined(REASONS.THREE_OBLIQUE);
    }
    return {excitationBlock, refocusingBlocks, pulses, factor, centreValue, directions,
      nominal: pulses[0].nominalM, ranges: new Map()};
  }

  // The point-samples of the whole work of a combined profile (for the fraction done).
  function _combinedTotal(c, view, n) {
    const samples = d => d.pulses.reduce((s, p) => s + p.sigRe.length, 0);
    const line = n || NUM_POSITIONS, map = n || MAP_POINTS;
    const dirs = c.directions;
    let total = 0;
    for (const d of dirs) total += line * samples(d);
    if (dirs.length > 1 && view === "2d") {
      if (dirs.every(d => AXIS_NAMES.includes(d.kind))) {
        for (const d of dirs) total += map * samples(d);
        if (dirs.length === 3) for (const d of dirs) total += samples(d);
      } else {
        total += map * map * (samples(dirs[0]) + samples(dirs[1]));
      }
    }
    return total;
  }

  // `rf_profiles.combined_profile` as sliced work, like `simulation`: {step(budgetMs),
  // done, result()}. `per` is a result of `period`. A period with a reason, or without
  // a direction, is done at once. The pulses come from the blocks without their echo
  // pathway. `result()`: {reason, excitationBlock, refocusingBlocks, factor,
  // directions, line ({u, values} or null), maps ([{axes, values}]), numbers}.
  function combinedProfile(seqView, file, per, {view = "profile", n = null} = {}) {
    if (view !== "profile" && view !== "2d") {
      throw new Error(`view must be 'profile' or '2d': ${_pyRepr(view)}`);
    }
    _checkN(n);
    const c = _combinedSetup(seqView, file, per);
    let result = null;
    let gen = null;
    const state = {done: 0, total: 0};
    if (c.reason !== undefined) {
      result = c;
    } else if (c.directions.length === 0) {
      result = _combinedResult(c, null, [], {centre_signal: c.factor});
    } else {
      state.total = _combinedTotal(c, view, n);
      gen = _combinedGen(c, view, n, state);
      // Run to the first yield, which comes before the first piece of work.
      gen.next();
    }
    return {
      step(budgetMs) {
        if (result !== null) return 1;
        const end = _now() + budgetMs;
        do {
          const r = gen.next();
          if (r.done) {
            result = r.value;
            return 1;
          }
        } while (_now() < end);
        return state.done / state.total;
      },
      get done() {
        return result !== null;
      },
      result() {
        if (result === null) {
          throw new Error("RfProfiles.combinedProfile: result() before the work is done");
        }
        return result;
      },
    };
  }

  return Object.freeze({
    USES, AXIS_KINDS, MAX_POINTS, NUM_POSITIONS, MAP_POINTS, PERIOD_MAX_BLOCKS,
    PARALLEL_TOL, CONSTANT_TOL, SPECTRUM_PADDING, PHASE_MIN_FRACTION, PASSBAND_FRACTION,
    TIME_TOLERANCE, SHEAR_RTOL, REASONS,
    fileData,
    spinDomain, spinDomainRange, magnetization, crushedEcho, precess,
    fwhm, edgeWidth, passbandRipple, stopbandLevel,
    linspace, unwrap, fft, spectrumMagnitudes, spectrumFwhmHz,
    pieceWiseIntegral, gradientKind,
    blockPulse, period, viewSpec, simulation, simulate, quantity, echoPhase, widths,
    combinedProfile,
  });
})();
if (typeof module !== "undefined") module.exports = RfProfiles;
