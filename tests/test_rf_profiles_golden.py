"""The golden test of task 3.4 of `docs/plans/rf-profiles.md`: `RfProfiles`
(`src/pulseq_reports/assets/rf_profiles.js`) must give the same values as the Python
reference (`src/pulseq_reports/rf_profiles.py`) for the phase 2 test sequences and two
vb-pulseq-like sequences, the example GRE, and a few more that section 4.2/4.3 of the
plan singles out (a turning gradient, no `SliceThickness`, another nucleus).

`_run_golden` writes one sequence's encoded diagram tables, its lane metadata, its RF
profile card file entry (`cards.rf_profile._rf_profile_data`, with the RF table) and a
list of queries to a JSON file; runs `tests/js/golden_rf_profiles.js` with Node on it;
and reads back the JSON result. The Node half decodes the tables, builds
`SeqLanes.sequenceView`, decodes the RF table and builds `RfProfiles.fileData`, and
answers each query with `RfProfiles`. This file then recomputes the same values with
`rf_profiles.py` (the same block, the same view options) and compares, with the
tolerance of section 3.5, item 2 of the plan and the rules below for the other
quantities. Every tolerance is applied through one of a handful of small helpers below,
each named for its rule, so a comparison's tolerance is visible at its call site. There
is one test for each sequence.

Tolerances, each with its reason (also see the module-level constants below):

1. **Exact** (`_assert_exact`, `==`): the period fields (`first_block`, `last_block`,
   `first_adc_block`, `truncated`); a period's pulses in order (`use`, `first_block`,
   `last_block`, `count`); a block pulse's `use`, `gradient_kind`, `select_kind`,
   `constant_gradient`, `dt_s`, `freq_offset_hz`, `nominal_m`, `fov_m`, `notes`,
   `echo_reason`, the echo `sign` and `adc_block`; every reason text; the kinds and `n`
   of each spec axis; a combined profile's `reason`, blocks and `directions`. `dt_s` and
   `freq_offset_hz` are exact (not merely close) because both languages read them
   straight from the RF table's `dt` and `freq_hz` columns, which `rf_profiles.py`'s own
   `_pulse_core` computes with the same formula in the same order as
   `cards.rf_profile._rf_table`, so the two Python computations already agree bit for bit
   before either one is ever sent to JavaScript.
2. **The pulse key partition** (`_check_key_map`): a Python key is a tuple and a
   JavaScript key is a string, so they are never compared by value. Instead, every block
   this file asks about (every "pulse" query) builds a bijection between the two
   representations, and this file asserts that the bijection never sees a key on one
   side map to two different keys on the other -- exactly "the partition of the RF
   blocks by key must be the same" (task 3.4).
3. **Float rounding of the same arithmetic** (`_rel_tol_close`, `_rel_scalar`: relative
   1e-12 of the largest value of the array, or of the value itself for a scalar): the
   signal (`sigRe`, `sigIm` against `signal_hz`), the interval gradients (`grad_hz_per_m`;
   JavaScript multiplies the diagram table's mT/m by 42576 Hz/m per mT/m where Python
   divides pypulseq's Hz/m by `seq_utils.GAMMA` and multiplies by 1e3, so the round trip
   differs from Python's direct value by a relative 2e-16 or so -- far inside the 1e-12
   bound, as the measured differences below confirm), `direction`,
   `select_gradient_hz_per_m`, `slice_centre_m`, `flip_deg`, `peak_b1_ut`,
   `energy_ut2_ms`, a spec's `lo`/`hi` away from the spectrum-FWHM cases of rule 4, the
   grids, the combined `factor`, the line's `u`, and the maps' axes.
4. **The spectrum FWHM** (`_check_spectrum_axis`, `_spectrum_margin_is_safe`): the
   first axis of a "profile" or "z_df" spec of kind "none", and of kind "one" without a
   nominal thickness, comes from the FWHM of the zero-padded RF spectrum, which numpy's
   FFT and the mixed-radix FFT of `rf_profiles.js` compute independently. The FWHM is the
   distance between two discrete frequency bins, so it is equal unless a magnitude next
   to the edge of "at or above half the maximum" is within a relative 1e-9 of that half,
   where float rounding alone could pick another bin. The test sequences are outside
   that margin: `_check_spectrum_axis` asserts it (with numpy's FFT of the pulse's own
   `signal_hz`), and then holds `lo` and `hi` to rule 3. A bin of difference would move
   them by far more than 1e-12 (about 1e-3 relative for these pulses).
5. **`a` and `b`** (`_assert_ab`, absolute 1e-12, the plan's own rule, section 3.5 item
   2): both are bounded (`|a|^2 + |b|^2 = 1`), so an absolute tolerance is the natural
   one. `mxy_abs`, `mz` and `beta_sq` are simple algebra on `a` and `b`
   (`rf_sim.magnetization`, `rf_sim.crushed_echo`), so this file gives them the same
   absolute 1e-12 (`_assert_abs`).
6. **The echo moment** (`_assert_abs`, absolute 1e-9 /m): moments add terms of order
   1e2 /m (a slice-select gradient's area over a few hold intervals), so rounding is
   several orders below 1e-9; 1e-9 /m is a phase of about 6e-11 rad over 1 cm.
7. **The echo phase** (`_compare_echo_phase`, absolute 1e-9 rad where both are finite):
   the NaN masks (`|Mxy| < 10%` of its maximum) must be equal except where `|Mxy|` is
   within an absolute 1e-9 of that 10% threshold, where independent rounding in the two
   simulations could put a point on either side of the mask.
8. **Widths** (`_compare_one_step`, used for `fwhm`/`edge_width` and the combined
   `fwhm_m`/`edge_width_m`): equal within a relative 1e-12 of the axis (or line) range,
   or -- only where a profile value is within an absolute 1e-9 of that width's threshold
   (half the maximum for `fwhm`; 10% or 90% for `edge_width`) -- exactly one grid step
   apart, because `profile_metrics.fwhm`/`edge_width` read the width straight off the
   sample grid (no interpolation), so a value that sits within float rounding of the
   threshold can flip which grid point above/below it counts, in either implementation,
   independently. `passband_ripple`, `stopband_level`, `signal_kept`, `fraction_inside`
   and `centre_signal` get the relative-1e-12 rule of item 3 (plain algebra on the
   simulated profile); the phase numbers (`rephasing_error_rad`, `nonlinear_residual_rad`,
   `centre_phase_rad`) get the absolute 1e-9 rad of item 7 (they come from the same echo
   Mxy).
9. **Maps and lines of the combined profile** (`_assert_abs`, absolute 1e-12): the same
   reasoning as item 5, since a combined value is a product of `mxy_abs`/`beta_sq`
   values.

A comparison that is not covered by one of these numbered rules is a bug in this file,
not a reason to invent a new tolerance.

Measured (2026-09-28, 16 sequences, 1055 queries), the largest differences: `a`, `b`
1.1e-14; the quantities 2.1e-14; the combined lines and maps 7.9e-15; the signal
2.1e-16 and the interval gradients 2.9e-16 relative; `flip_deg` 1.9e-15, `energy_ut2_ms`
2.6e-15 relative; the echo moment 1.1e-13 /m; the echo phase 1.8e-14 rad; `fwhm`,
`edge_width` (and the combined `fwhm_m`, `edge_width_m`) and the spectrum-FWHM ranges
equal; `passband_ripple` 3.9e-14 and `stopband_level` 8.2e-15 relative; the phase
numbers 2.7e-15 rad; the combined `signal_kept`, `fraction_inside` and `centre_signal`
at most 8.9e-16 relative. So the one-grid-step branch of rule 8 was not needed.
"""

import importlib.util
import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pypulseq as pp
import pytest
import test_rf_profiles as cases  # the phase 2 test sequences and their builders

from pulseq_reports import diagram_data
from pulseq_reports import rf_profiles as rp
from pulseq_reports.cards.rf_profile import _rf_profile_data
from pulseq_reports.seq_index import sequence_index

_GOLDEN_SCRIPT = Path(__file__).parent / "js" / "golden_rf_profiles.js"

# The number of points of a view's grid for most queries (task 3.4's own suggestion),
# small enough that the whole file stays well under its ~20 s budget even though most
# pulses here have a few hundred to a few thousand RF samples.
_SMALL_N = {"profile": 101, "z_df": 31, "2d": 31}
_SMALL_COMBINED_N = 21

# Rule 3: relative 1e-12 of the largest value of the array (or of the scalar itself).
_REL_TOL = 1e-12
# Rule 5/9: absolute 1e-12 on `a`, `b` and values derived from them by plain algebra.
_AB_TOL = 1e-12
# Rule 6: absolute 1e-9 /m on the echo moment.
_MOMENT_TOL = 1e-9
# Rule 7/8: absolute 1e-9 rad on an echo phase and the phase-fit numbers.
_PHASE_TOL = 1e-9
# Rule 8: a width may differ by exactly one grid step where a profile value is within
# this absolute margin of the width's own threshold.
_WIDTH_THRESHOLD_TOL = 1e-9
# Rule 4: a spectrum bin right at the edge of "at or above half the maximum" is
# borderline when its magnitude is within this relative margin of half the maximum.
_SPECTRUM_MARGIN_REL = 1e-9

_WIDTH_ONE_STEP_KEYS = ("fwhm", "edge_width")
_WIDTH_REL_KEYS = (
    "passband_ripple",
    "stopband_level",
    "signal_kept",
    "fraction_inside",
    "centre_signal",
)
_WIDTH_PHASE_KEYS = ("rephasing_error_rad", "nonlinear_residual_rad", "centre_phase_rad")


class _Worst:
    """The largest measured difference for each comparison category, for the report."""

    def __init__(self):
        self.data: dict[str, tuple[float, str]] = {}

    def note(self, category: str, diff: float, where: str) -> None:
        cur = self.data.get(category)
        if cur is None or not (diff <= cur[0]):  # a NaN diff also replaces (surfaces it)
            self.data[category] = (diff, where)

    def report(self) -> str:
        return "\n".join(
            f"  {cat:32s} {diff:.6e}  at {where}"
            for cat, (diff, where) in sorted(self.data.items())
        )


_WORST = _Worst()


# ---- Small comparison helpers, one per rule -----------------------------------------


def _assert_exact(js, py, category: str, where: str) -> None:
    assert js == py, f"{where}: {category}: js={js!r} py={py!r}"


def _rel_tol_close(js_arr, py_arr, category: str, where: str, tol: float = _REL_TOL) -> None:
    js_arr = np.asarray(js_arr, dtype=np.float64).reshape(-1)
    py_arr = np.asarray(py_arr, dtype=np.float64).reshape(-1)
    assert js_arr.shape == py_arr.shape, (
        f"{where}: {category}: shape {js_arr.shape} (js) vs {py_arr.shape} (py)"
    )
    scale = float(np.max(np.abs(py_arr))) if py_arr.size else 0.0
    scale = scale or 1.0
    diff = float(np.max(np.abs(js_arr - py_arr))) if py_arr.size else 0.0
    _WORST.note(category, diff / scale, where)
    assert diff <= tol * scale, (
        f"{where}: {category}: max diff {diff!r} > {tol} * scale {scale!r} (rel {diff / scale!r})"
    )


def _rel_scalar(js_val, py_val, category: str, where: str, tol: float = _REL_TOL) -> None:
    scale = abs(py_val) or 1.0
    diff = abs(js_val - py_val)
    _WORST.note(category, diff / scale, where)
    assert diff <= tol * scale, (
        f"{where}: {category}: js={js_val!r} py={py_val!r} diff {diff!r} > {tol} * {scale!r}"
    )


def _assert_abs(js_arr, py_arr, tol: float, category: str, where: str) -> None:
    js_arr = np.asarray(js_arr, dtype=np.float64).reshape(-1)
    py_arr = np.asarray(py_arr, dtype=np.float64).reshape(-1)
    assert js_arr.shape == py_arr.shape, (
        f"{where}: {category}: shape {js_arr.shape} (js) vs {py_arr.shape} (py)"
    )
    diff = float(np.max(np.abs(js_arr - py_arr))) if py_arr.size else 0.0
    _WORST.note(category, diff, where)
    assert diff <= tol, f"{where}: {category}: max abs diff {diff!r} > {tol}"


def _complex_rel(js_re, js_im, py_complex, category: str, where: str) -> None:
    py_complex = np.asarray(py_complex).reshape(-1)
    js_re = np.asarray(js_re, dtype=np.float64)
    js_im = np.asarray(js_im, dtype=np.float64)
    scale = (
        float(
            max(
                np.max(np.abs(py_complex.real)) if py_complex.size else 0.0,
                np.max(np.abs(py_complex.imag)) if py_complex.size else 0.0,
            )
        )
        or 1.0
    )
    diff = float(
        max(
            np.max(np.abs(js_re - py_complex.real)) if py_complex.size else 0.0,
            np.max(np.abs(js_im - py_complex.imag)) if py_complex.size else 0.0,
        )
    )
    _WORST.note(category, diff / scale, where)
    assert diff <= _REL_TOL * scale, (
        f"{where}: {category}: max diff {diff!r} > {_REL_TOL} * scale {scale!r}"
    )


def _assert_ab(js_a, js_b, py_a, py_b, where: str) -> None:
    for label, js_part, py_part in (("a", js_a, py_a), ("b", js_b, py_b)):
        js_re = np.asarray(js_part["re"], dtype=np.float64)
        js_im = np.asarray(js_part["im"], dtype=np.float64)
        py_part = np.asarray(py_part).reshape(-1)
        diff = float(
            max(
                np.max(np.abs(js_re - py_part.real)),
                np.max(np.abs(js_im - py_part.imag)),
            )
        )
        _WORST.note(label, diff, where)
        assert diff <= _AB_TOL, f"{where}: {label}: max abs diff {diff!r} > {_AB_TOL}"


def _check_key_map(key_map: dict, rev_map: dict, py_key, js_key, where: str) -> None:
    prev_js = key_map.get(py_key)
    if prev_js is None:
        key_map[py_key] = js_key
    else:
        assert prev_js == js_key, (
            f"{where}: the python key {py_key!r} maps to two different js keys: "
            f"{prev_js!r} and {js_key!r}"
        )
    prev_py = rev_map.get(js_key)
    if prev_py is None:
        rev_map[js_key] = py_key
    else:
        assert prev_py == py_key, (
            f"{where}: the js key {js_key!r} maps to two different python keys: "
            f"{prev_py!r} and {py_key!r}"
        )


def _spectrum_margin_is_safe(signal_hz: np.ndarray, tol_rel: float = _SPECTRUM_MARGIN_REL) -> bool:
    """True when no magnitude bin right at the edge of "at or above half the maximum" of
    the zero-padded spectrum of `signal_hz` is within `tol_rel` of half the maximum
    (rule 4): away from that margin, two independently-computed FFTs must choose the
    same discrete bins, because a relative-1e-12-ish difference between them cannot
    change whether a bin safely above or below half the maximum crosses it."""
    n = rp.SPECTRUM_PADDING * signal_hz.size
    mag = np.abs(np.fft.fft(signal_hz, n))
    peak = float(mag.max())
    half = peak / 2
    above = np.flatnonzero(mag >= half)
    lo_i, hi_i = int(above.min()), int(above.max())
    candidates = [mag[lo_i], mag[hi_i]]
    if lo_i > 0:
        candidates.append(mag[lo_i - 1])
    if hi_i < mag.size - 1:
        candidates.append(mag[hi_i + 1])
    return all(abs(c - half) > tol_rel * peak for c in candidates)


def _check_spectrum_axis(signal_hz, py_lo, py_hi, js_lo, js_hi, where: str) -> None:
    assert _spectrum_margin_is_safe(signal_hz), (
        f"{where}: a bin of the RF spectrum is within {_SPECTRUM_MARGIN_REL} of half its "
        "maximum, so the two FFTs may pick different bins: use another test pulse (rule 4)"
    )
    _rel_scalar(js_lo, py_lo, "spec.lo (spectrum FWHM)", where)
    _rel_scalar(js_hi, py_hi, "spec.hi (spectrum FWHM)", where)


def _threshold_values(kind: str, profile_values: np.ndarray) -> list[float]:
    peak = float(np.max(profile_values))
    if kind == "fwhm":
        return [peak / 2]
    return [0.1 * peak, 0.9 * peak]


def _compare_one_step(
    js_val,
    py_val,
    lo: float,
    hi: float,
    n: int,
    profile_values,
    kind: str,
    category: str,
    where: str,
) -> None:
    axis_range = hi - lo
    step = axis_range / (n - 1)
    diff = abs(js_val - py_val)
    _WORST.note(category, diff / axis_range if axis_range else diff, where)
    tol = _REL_TOL * axis_range
    if diff <= tol:
        return
    assert abs(diff - step) <= 1e-9 * step, (
        f"{where}: {category}: diff {diff!r} is neither <= {tol!r} nor one grid step {step!r}"
    )
    thresholds = _threshold_values(kind, profile_values)
    near = any(np.any(np.abs(profile_values - t) <= _WIDTH_THRESHOLD_TOL) for t in thresholds)
    assert near, (
        f"{where}: {category}: one grid step apart ({diff!r}) but no profile value is "
        f"within {_WIDTH_THRESHOLD_TOL} of a threshold {thresholds!r}"
    )


def _width_profile_for_test(use: str, profile: rp.Profile) -> np.ndarray:
    """The profile for the widths, by use (section 4.3, item 2 of the plan; the same
    small rule as `rf_profiles._width_profile`, restated here rather than imported,
    since it is a private helper)."""
    if use == "refocusing":
        return rp.quantity(profile, "beta_sq")
    if use == "inversion":
        return (1 - rp.quantity(profile, "mz")) / 2
    if use == "saturation":
        return 1 - rp.quantity(profile, "mz")
    return rp.quantity(profile, "mxy_abs")


def _compare_widths(
    js_widths: dict, py_widths: dict, axis: rp.ProfileAxis, main_profile, where: str
) -> None:
    assert set(js_widths.keys()) == set(py_widths.keys()), (
        f"{where}: widths keys: js={sorted(js_widths)} py={sorted(py_widths)}"
    )
    for key, py_val in py_widths.items():
        js_val = js_widths[key]
        if key in _WIDTH_ONE_STEP_KEYS:
            _compare_one_step(
                js_val, py_val, axis.lo, axis.hi, axis.n, main_profile, key, f"width.{key}", where
            )
        elif key in _WIDTH_REL_KEYS:
            _rel_scalar(js_val, py_val, f"width.{key}", where)
        elif key in _WIDTH_PHASE_KEYS:
            diff = abs(js_val - py_val)
            _WORST.note(f"width.{key}", diff, where)
            assert diff <= _PHASE_TOL, f"{where}: width.{key}: diff {diff!r} > {_PHASE_TOL}"
        else:
            raise AssertionError(f"{where}: unknown width key {key!r}")


def _compare_echo_phase(
    js_phase, py_phase, mxy_abs: np.ndarray, where: str, category: str = "echo_phase_rad"
) -> None:
    if py_phase is None:
        assert js_phase is None, f"{where}: python echo_phase is None, js is not"
        return
    assert js_phase is not None, f"{where}: js echo_phase is None, python is not"
    js = np.array([math.nan if v is None else v for v in js_phase], dtype=np.float64)
    py = np.asarray(py_phase, dtype=np.float64)
    assert js.shape == py.shape, f"{where}: echo_phase shape: js={js.shape} py={py.shape}"
    nan_js, nan_py = np.isnan(js), np.isnan(py)
    limit = rp.PHASE_MIN_FRACTION * float(np.max(mxy_abs))
    borderline = np.abs(mxy_abs - limit) <= _WIDTH_THRESHOLD_TOL
    mismatch = nan_js != nan_py
    bad = mismatch & ~borderline
    assert not np.any(bad), (
        f"{where}: echo_phase NaN mask differs at a non-borderline point (indexes "
        f"{np.flatnonzero(bad)[:5].tolist()})"
    )
    both = ~nan_js & ~nan_py
    diff = float(np.max(np.abs(js[both] - py[both]))) if np.any(both) else 0.0
    _WORST.note(category, diff, where)
    assert diff <= _PHASE_TOL, f"{where}: {category}: diff {diff!r} > {_PHASE_TOL}"


# ---- The per-query comparisons --------------------------------------------------------


def _compare_period(
    seq, block: int, max_blocks, js: dict, key_map: dict, rev_map: dict, where: str
) -> None:
    per = (
        rp.period(seq, block)
        if max_blocks is None
        else rp.period(seq, block, max_blocks=max_blocks)
    )
    _assert_exact(js["firstBlock"], per.first_block, "period.first_block", where)
    _assert_exact(js["lastBlock"], per.last_block, "period.last_block", where)
    _assert_exact(js["firstAdcBlock"], per.first_adc_block, "period.first_adc_block", where)
    _assert_exact(js["truncated"], per.truncated, "period.truncated", where)
    assert len(js["pulses"]) == len(per.pulses), (
        f"{where}: period.pulses length: js={len(js['pulses'])} py={len(per.pulses)}"
    )
    for jp, pyp in zip(js["pulses"], per.pulses):
        _assert_exact(jp["use"], pyp.use, "period.pulse.use", where)
        _assert_exact(jp["firstBlock"], pyp.first_block, "period.pulse.first_block", where)
        _assert_exact(jp["lastBlock"], pyp.last_block, "period.pulse.last_block", where)
        _assert_exact(jp["count"], pyp.count, "period.pulse.count", where)
        _check_key_map(key_map, rev_map, pyp.key, jp["key"], where)


def _compare_pulse(seq, block: int, js: dict, key_map: dict, rev_map: dict, where: str) -> None:
    p = rp.block_pulse(seq, block)
    assert p is not None, f"{where}: python block_pulse is None, js returned a pulse"

    _assert_exact(js["use"], p.use, "use", where)
    _assert_exact(js["gradientKind"], p.gradient_kind, "gradient_kind", where)
    _assert_exact(js["selectKind"], p.select_kind, "select_kind", where)
    _assert_exact(js["constantGradient"], p.constant_gradient, "constant_gradient", where)
    _assert_exact(js["dtS"], p.dt_s, "dt_s", where)
    _assert_exact(js["freqOffsetHz"], p.freq_offset_hz, "freq_offset_hz", where)
    _assert_exact(js["nominalM"], p.nominal_m, "nominal_m", where)
    js_fov = js["fovM"]
    py_fov = None if p.fov_m is None else list(p.fov_m)
    _assert_exact(js_fov, py_fov, "fov_m", where)
    _assert_exact(js["notes"], list(p.notes), "notes", where)
    _assert_exact(js["echoReason"], p.echo_reason, "echo_reason", where)

    if p.echo is None:
        _assert_exact(js["echo"], None, "echo", where)
    else:
        assert js["echo"] is not None, f"{where}: python has an echo pathway, js does not"
        _assert_exact(js["echo"]["sign"], p.echo.sign, "echo.sign", where)
        _assert_exact(js["echo"]["adcBlock"], p.echo.adc_block, "echo.adc_block", where)
        _assert_abs(
            js["echo"]["momentPerM"], p.echo.moment_per_m, _MOMENT_TOL, "echo.moment_per_m", where
        )

    _check_key_map(key_map, rev_map, p.key, js["key"], where)

    _complex_rel(js["sigRe"], js["sigIm"], p.signal_hz, "signal_hz", where)
    _rel_tol_close(js["grad"], p.grad_hz_per_m.reshape(-1), "grad_hz_per_m", where)
    if p.direction is None:
        _assert_exact(js["direction"], None, "direction", where)
    else:
        _rel_tol_close(js["direction"], p.direction, "direction", where)
    if p.select_gradient_hz_per_m is None:
        _assert_exact(js["selectGradientHzPerM"], None, "select_gradient_hz_per_m", where)
    else:
        _rel_scalar(
            js["selectGradientHzPerM"],
            p.select_gradient_hz_per_m,
            "select_gradient_hz_per_m",
            where,
        )
    if p.slice_centre_m is None:
        _assert_exact(js["sliceCentreM"], None, "slice_centre_m", where)
    else:
        _rel_scalar(js["sliceCentreM"], p.slice_centre_m, "slice_centre_m", where)
    _rel_scalar(js["flipDeg"], p.flip_deg, "flip_deg", where)
    _rel_scalar(js["peakB1Ut"], p.peak_b1_ut, "peak_b1_ut", where)
    _rel_scalar(js["energyUt2Ms"], p.energy_ut2_ms, "energy_ut2_ms", where)


def _compare_view(seq, query: dict, js: dict, where: str) -> None:
    pulse = rp.block_pulse(seq, query["block"])
    view = query["view"]
    spec, reason = rp.view_spec(pulse, view, n=query.get("n"))
    _assert_exact(js["reason"], reason, "view.reason", where)
    if spec is None:
        assert js["spec"] is None, f"{where}: python spec is None, js spec is not"
        return
    assert js["spec"] is not None, f"{where}: js spec is None, python spec is not"

    js_axes = js["spec"]["axes"]
    assert len(js_axes) == len(spec.axes), (
        f"{where}: axis count: js={len(js_axes)} py={len(spec.axes)}"
    )
    uses_spectrum0 = view in ("profile", "z_df") and (
        pulse.gradient_kind == "none" or (pulse.gradient_kind == "one" and pulse.nominal_m is None)
    )
    for i, (ja, pa) in enumerate(zip(js_axes, spec.axes)):
        _assert_exact(ja["kind"], pa.kind, f"axis{i}.kind", where)
        _assert_exact(int(ja["n"]), int(pa.n), f"axis{i}.n", where)
        if i == 0 and uses_spectrum0:
            _check_spectrum_axis(pulse.signal_hz, pa.lo, pa.hi, ja["lo"], ja["hi"], where)
        else:
            _rel_scalar(ja["lo"], pa.lo, "spec.lo", where)
            _rel_scalar(ja["hi"], pa.hi, "spec.hi", where)

    profile = rp.simulate(pulse, spec)
    for k, g in enumerate(profile.grid):
        _rel_tol_close(js["grid"][k], g, "grid", where)
    _assert_ab(js["a"], js["b"], profile.a, profile.b, where)
    for name in ("mxy_abs", "mz", "beta_sq"):
        py_q = rp.quantity(profile, name)
        _assert_abs(js["q"][name], py_q, _AB_TOL, f"quantity.{name}", where)

    if view != "profile":
        return

    main_profile = _width_profile_for_test(pulse.use, profile)
    py_widths = rp.widths(pulse, profile)
    _compare_widths(js["widths"], py_widths, spec.axes[0], main_profile, where)

    mxy_abs = rp.quantity(profile, "mxy_abs")
    py_echo_phase = rp.echo_phase(pulse, profile)
    _compare_echo_phase(js["echoPhase"], py_echo_phase, mxy_abs, where)

    if "echoMomentPerM" in query:
        m = np.asarray(query["echoMomentPerM"], dtype=np.float64)
        py_widths_m = rp.widths(pulse, profile, echo_moment_per_m=m)
        _compare_widths(js["widthsM"], py_widths_m, spec.axes[0], main_profile, where)
        py_echo_phase_m = rp.echo_phase(pulse, profile, echo_moment_per_m=m)
        _compare_echo_phase(
            js["echoPhaseM"],
            py_echo_phase_m,
            mxy_abs,
            where,
            category="echo_phase_rad (echo_moment_per_m override)",
        )


def _compare_combined(seq, query: dict, js: dict, where: str) -> None:
    per = rp.period(seq, query["block"])
    c = rp.combined_profile(seq, per, view=query["view"], n=query.get("n"))
    _assert_exact(js["reason"], c.reason, "combined.reason", where)
    if c.reason is not None:
        assert js["reason"] is not None, f"{where}: js has no reason, python does"
        return

    _assert_exact(js["excitationBlock"], c.excitation_block, "combined.excitation_block", where)
    _assert_exact(
        list(js["refocusingBlocks"]), list(c.refocusing_blocks), "combined.refocusing_blocks", where
    )
    _assert_exact(list(js["directions"]), list(c.directions), "combined.directions", where)
    _rel_scalar(js["factor"], c.factor, "combined.factor", where)

    main_profile = None
    lo = hi = n = None
    if c.line is None:
        assert js["line"] is None, f"{where}: python line is None, js line is not"
    else:
        assert js["line"] is not None, f"{where}: js line is None, python line is not"
        u, values = c.line
        _rel_tol_close(js["line"]["u"], u, "combined.line.u", where)
        _assert_abs(js["line"]["values"], values, _AB_TOL, "combined.line.values", where)
        main_profile = values
        lo, hi, n = float(u[0]), float(u[-1]), u.size
    _assert_exact(
        [p["block"] for p in js["linePulses"]],
        [block for block, _ in c.line_pulses],
        "combined.line_pulses blocks",
        where,
    )
    for jp, (block, values) in zip(js["linePulses"], c.line_pulses, strict=True):
        _assert_abs(
            jp["values"], values, _AB_TOL, "combined.line_pulses.values", f"{where} block {block}"
        )

    assert len(js["maps"]) == len(c.maps), (
        f"{where}: maps length: js={len(js['maps'])} py={len(c.maps)}"
    )
    for i, (jm, cm) in enumerate(zip(js["maps"], c.maps)):
        for k, (ja, pa) in enumerate(zip(jm["axes"], cm.axes)):
            _assert_exact(ja["kind"], pa.kind, f"map{i}.axis{k}.kind", where)
            _assert_exact(int(ja["n"]), int(pa.n), f"map{i}.axis{k}.n", where)
            _rel_scalar(ja["lo"], pa.lo, f"map{i}.axis{k}.lo", where)
            _rel_scalar(ja["hi"], pa.hi, f"map{i}.axis{k}.hi", where)
        _assert_abs(jm["values"], cm.values, _AB_TOL, f"map{i}.values", where)

    assert set(js["numbers"].keys()) == set(c.numbers.keys()), (
        f"{where}: combined numbers keys: js={sorted(js['numbers'])} py={sorted(c.numbers)}"
    )
    for key, py_val in c.numbers.items():
        js_val = js["numbers"][key]
        if key in ("fwhm_m", "edge_width_m"):
            assert main_profile is not None, f"{where}: {key} without a combined line"
            _compare_one_step(
                js_val,
                py_val,
                lo,
                hi,
                n,
                main_profile,
                "fwhm" if key == "fwhm_m" else "edge_width",
                f"combined.{key}",
                where,
            )
        else:
            _rel_scalar(js_val, py_val, f"combined.{key}", where)


# ---- Building the sequences (item list of task 3.4) ------------------------------------


def _press_like():
    """PRESS-like: excitation on x, refocusing on y and on z (item 5)."""
    rf_ex, gz_ex, gzr = cases._sinc("excitation")
    gx, adc, _ = cases._readout()
    seq = cases._new()
    seq.add_block(rf_ex, cases._on_axis(gz_ex, "x"))
    seq.add_block(cases._on_axis(gzr, "x"))
    for axis in ("y", "z"):
        rf_ref, gz_ref, _ = cases._sinc("refocusing", math.pi, phase_offset=math.pi / 2)
        seq.add_block(cases._trap(axis, cases.CRUSHER_AREA))
        seq.add_block(rf_ref, cases._on_axis(gz_ref, axis))
        seq.add_block(cases._trap(axis, cases.CRUSHER_AREA))
    seq.add_block(gx, adc)
    return seq


def _oblique_seq():
    """Excitation on x, refocusing oblique in the x-y plane (item 5)."""
    angle = math.radians(60)
    rf_ex, gz_ex, gzr = cases._sinc("excitation")
    rf_ref, gz_ref, _ = cases._sinc("refocusing", math.pi, phase_offset=math.pi / 2)
    gx, adc, _ = cases._readout()
    seq = cases._new()
    seq.add_block(rf_ex, cases._on_axis(gz_ex, "x"))
    seq.add_block(cases._on_axis(gzr, "x"))
    seq.add_block(
        rf_ref,
        cases._on_axis(gz_ref, "x", math.cos(angle)),
        cases._on_axis(gz_ref, "y", math.sin(angle)),
    )
    seq.add_block(gx, adc)
    return seq


def _changing_grad_fov():
    """A pulse with a turning gradient, with a FOV definition, for the "2d" view (item 6)."""
    turn_x, turn_y = cases._turning_gradients()
    gx, adc, _ = cases._readout()
    seq = cases._new()
    seq.set_definition("FOV", [0.25, 0.2, 0.005])
    seq.add_block(cases._hard("excitation", math.radians(30), duration=0.8e-3), turn_x, turn_y)
    seq.add_block(gx, adc)
    return seq


def _block_no_grad_no_w():
    """A block pulse without a gradient and without SliceThickness: kind "none", the
    spectrum FWHM gives the Delta-f range (item 7)."""
    seq = cases._new(thickness=None)
    seq.add_block(cases._hard("excitation"))
    return seq


def _sinc_no_w():
    """A sinc without SliceThickness: kind "one", the spectrum FWHM gives the range
    (item 7)."""
    seq = cases._new(thickness=None)
    rf, gz, gzr = cases._sinc("excitation")
    seq.add_block(rf, gz)
    seq.add_block(gzr)
    return seq


def _fat_sat_se():
    """A fat saturation before the excitation (item 4)."""
    before = ((cases._hard("saturation", freq_ppm=-3.45),), (cases._trap("z", cases.CRUSHER_AREA),))
    return cases._spin_echo("y", before=before)


_SODIUM_SYSTEM = pp.Opts(
    max_grad=30,
    grad_unit="mT/m",
    max_slew=150,
    slew_unit="T/m/s",
    rf_dead_time=100e-6,
    rf_ringdown_time=30e-6,
    adc_dead_time=10e-6,
    rf_raster_time=5e-6,
    gamma=11.262e6,  # sodium (23Na): a sequence of another nucleus (item 9)
)


def _another_nucleus_seq():
    """A hard excitation (as `test_peak_b1_of_another_nucleus` does: sodium's smaller
    gamma makes the same slice-select gradient of a sinc pulse infeasible at this
    system's `max_grad`), then a readout, so the sequence still has a period and an
    echo pathway to query (item 9)."""
    seq = cases._new(system=_SODIUM_SYSTEM)
    seq.add_block(cases._hard("excitation", math.pi / 2, duration=0.5e-3, system=_SODIUM_SYSTEM))
    # The flat area is well below sodium's smaller max gradient in Hz/m (max_grad in
    # mT/m is the same as `cases.SYSTEM`, but Hz/m = mT/m * gamma, and sodium's gamma is
    # about a quarter of the proton's), as `_sodium_sequence` of the PNS golden test does.
    gx = pp.make_trapezoid("x", flat_area=150, flat_time=1.2e-3, system=_SODIUM_SYSTEM)
    adc = pp.make_adc(
        num_samples=32, duration=gx.flat_time, delay=gx.rise_time, system=_SODIUM_SYSTEM
    )
    seq.add_block(gx, adc)
    return seq


_PPM_SYSTEM = pp.Opts(
    max_grad=30,
    grad_unit="mT/m",
    max_slew=150,
    slew_unit="T/m/s",
    rf_dead_time=100e-6,
    rf_ringdown_time=30e-6,
    adc_dead_time=10e-6,
    rf_raster_time=5e-6,
    B0=2.89,  # a system with B0 set, for freq_ppm (item 9)
)


def _freq_ppm_seq():
    rf = cases._hard("saturation", system=_PPM_SYSTEM, freq_ppm=-3.45, phase_ppm=0.7)
    seq = cases._new(system=_PPM_SYSTEM)
    seq.add_block(rf)
    return seq


def _load_gre_report_module():
    """`examples/gre_report.py`, loaded by path (it is not on `sys.path`), the same way
    `scripts/cards_scale.py` loads `diagram_scale.py` (item 10)."""
    path = Path(__file__).resolve().parent.parent / "examples" / "gre_report.py"
    spec = importlib.util.spec_from_file_location("golden_rf_profiles_gre_report", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# (builder, full_size) for each sequence of task 3.4's list. `full_size` marks the few
# sequences whose view and combined queries use the default grid sizes (401, 201, 128)
# instead of the small ones (task 3.4: "the default sizes ... for a few"): their pulses
# are short, with a constant gradient and no oblique combined map, so the default sizes
# stay inside the time of the test.
_SEQUENCES = {
    "gre_spoiled_dummies": (  # item 1
        lambda: cases._gre(3, rf_spoiling=True, slices=(-5e-3, 5e-3), dummies=2),
        True,
    ),
    "se_col": (lambda: cases._spin_echo(), True),  # item 2: excitation z, refocusing y
    "se_z_wide_ref": (lambda: cases._spin_echo("z", 1.5 * cases.W), False),  # item 2
    "tse_train": (lambda: cases._spin_echo(num_ref=4), False),  # item 3
    "se_hard_ref": (lambda: cases._spin_echo(hard_ref=True), False),  # item 3
    "fat_sat_se": (_fat_sat_se, False),  # item 4
    "inversion_before_adc": (cases._with_inversion_before_adc, False),  # item 4
    "press": (_press_like, False),  # item 5
    "oblique": (_oblique_seq, False),  # item 5
    "changing_grad_fov": (_changing_grad_fov, False),  # item 6
    "block_no_grad_no_w": (_block_no_grad_no_w, False),  # item 7
    "sinc_no_w": (_sinc_no_w, False),  # item 7
    "mprage_like": (cases._mprage_like, True),  # item 8
    "another_nucleus": (_another_nucleus_seq, False),  # item 9
    "freq_ppm_with_b0": (_freq_ppm_seq, False),  # item 9
    "example_gre": (lambda: _load_gre_report_module().gre_sequence(), False),  # item 10
}


# ---- Building the queries for one sequence -------------------------------------------


def _num_blocks(seq) -> int:
    return int(sequence_index(seq).num_blocks)


def _rf_blocks(seq) -> list[int]:
    index = sequence_index(seq)
    return np.flatnonzero(index.rf > 0).tolist()


def _period_starts(seq, nblocks: int) -> list[int]:
    return sorted({rp.period(seq, b).first_block for b in range(nblocks)})


def _build_queries(seq, nblocks: int, *, full_size: bool, echo_moment_added: list) -> list[dict]:
    queries: list[dict] = []

    for b in range(nblocks):
        queries.append({"kind": "period", "block": b})
    # A few maxBlocks-limited queries, for `truncated` (task 3.4's query list).
    for b in sorted({0, nblocks // 2, nblocks - 1}):
        queries.append({"kind": "period", "block": b, "maxBlocks": 1})

    for b in _rf_blocks(seq):
        queries.append({"kind": "pulse", "block": b})

    starts = _period_starts(seq, nblocks)
    for s in starts:
        per = rp.period(seq, s)
        for pulse_row in per.pulses:
            b0 = pulse_row.first_block
            pulse = rp.block_pulse(seq, b0)
            for view in ("profile", "z_df", "2d"):
                q = {"kind": "view", "block": b0, "view": view}
                if not full_size:
                    q["n"] = _SMALL_N[view]
                if (
                    view == "profile"
                    and not echo_moment_added[0]
                    and pulse_row.use == "excitation"
                    and pulse.gradient_kind == "one"
                ):
                    vector = (-pulse.select_gradient_hz_per_m * 1e-3) * pulse.direction
                    q["echoMomentPerM"] = [float(v) for v in vector]
                    echo_moment_added[0] = True
                queries.append(q)
        for view in ("profile", "2d"):
            q = {"kind": "combined", "block": s, "view": view}
            if not full_size:
                q["n"] = _SMALL_COMBINED_N
            queries.append(q)
    return queries


# ---- The test ---------------------------------------------------------------------


@pytest.mark.parametrize("name", list(_SEQUENCES))
def test_rf_profiles_js_matches_python_reference(name, tmp_path):
    """For every block (its period), every RF block (its pulse), the first block of every
    distinct pulse of every period (its three views, with widths and echo phase) and the
    first block of every period (its combined profile, "profile" and "2d") of one
    sequence, `RfProfiles` (run through Node) gives the values of `rf_profiles.py` within
    the rules of the module docstring (task 3.4 of `docs/plans/rf-profiles.md`). One
    "profile" query of the first excitation of kind "one" also passes
    `echoMomentPerM`."""
    if shutil.which("node") is None:
        pytest.fail(
            "node is required to run tests/js/golden_rf_profiles.js (the golden test of "
            "RfProfiles against the Python reference), but it was not found on PATH"
        )
    builder, full_size = _SEQUENCES[name]
    seq = builder()
    nblocks = _num_blocks(seq)
    queries = _build_queries(seq, nblocks, full_size=full_size, echo_moment_added=[False])
    tables = diagram_data.diagram_tables(seq)
    payload = {
        "format": 1,
        "tables": diagram_data.encode_tables(tables),
        "lanes": diagram_data.lane_meta(seq, tables=tables),
        "file": _rf_profile_data(seq),
        "queries": queries,
    }
    in_path = tmp_path / "in.json"
    out_path = tmp_path / "out.json"
    in_path.write_text(json.dumps(payload))
    subprocess.run(["node", str(_GOLDEN_SCRIPT), str(in_path), str(out_path)], check=True)
    results = json.loads(out_path.read_text())["results"]
    assert len(results) == len(queries), f"{len(results)} results from js, {len(queries)} queries"

    key_map: dict = {}
    rev_map: dict = {}
    for q, r in zip(queries, results, strict=True):
        where = f"{name} {q}"
        if q["kind"] == "period":
            _compare_period(seq, q["block"], q.get("maxBlocks"), r, key_map, rev_map, where)
        elif q["kind"] == "pulse":
            _compare_pulse(seq, q["block"], r, key_map, rev_map, where)
        elif q["kind"] == "view":
            _compare_view(seq, q, r, where)
        elif q["kind"] == "combined":
            _compare_combined(seq, q, r, where)
        else:
            raise AssertionError(f"unknown query kind {q['kind']!r}")
    print(f"\n{name}: {len(queries)} queries")
    print(_WORST.report())
