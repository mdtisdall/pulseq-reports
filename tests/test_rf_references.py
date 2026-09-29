"""The Python reference of RF pulse profiles (`rf_profiles`, `rf_sim`) against external
references: phase 2b of `docs/plans/rf-profiles.md` (decision 5, section 3.5, item 4).

The fixtures in `tests/fixtures/rf_references/` come from `scripts/rf_references.py`
(MATLAB Pulseq's `mr.simRf` in GNU Octave, and sigpy 0.1.27); their provenance is in
each file. This test needs neither tool: it reads the `.seq` file of each fixture with
pypulseq and computes the same profiles with the reference functions of this project.

The tolerances are measured (2026-09-28) and each has its reason next to it. A larger
difference than its reason explains is a finding, not a reason to widen a tolerance.
"""

import base64
import functools
import gzip
import json
import tempfile
from pathlib import Path

import numpy as np
import pypulseq as pp
import pytest

from pulseq_reports import rf_profiles as rp
from pulseq_reports.rf_sim import magnetization, spin_domain

FIXTURES = Path(__file__).parent / "fixtures" / "rf_references"
MAX_FIXTURE_BYTES = 200_000  # the plan's limit for one fixture (task 2b.2)

MATLAB_CASES = (
    "sinc_excitation",
    "sinc_refocusing",
    "block_pulse",
    "sinc_offsets",
    "fat_saturation",
    "hyperbolic_secant",
    "slr_excitation",
)
SIGPY_CASES = ("sinc_excitation", "sinc_on_ramps", "sinc_oblique", "turning_gradient")
ALL_CASES = tuple(dict.fromkeys(MATLAB_CASES + SIGPY_CASES))

# The same rotation, computed by another program: float rounding only. mr.simRf
# composes quaternions and this project Cayley-Klein parameters; sigpy's abrm_nd and
# abrm use the same Cayley-Klein formulas with the operations in another order.
# Measured: at most 1.2e-14 (mr.simRf on its own resampled RF) and 1.6e-13 (abrm_nd,
# 3000 samples).
SAME_ROTATION_TOL = 1e-12

# The pulse as played against mr.simRf. mr.simRf resamples the RF: linear interpolation
# at the centres of steps of 10 µs (or 5, 2, 1 µs for a wide bandwidth), where the
# reference holds each sample of the RF raster (1 µs here). The test of the resampled RF
# shows that the rest of the computation agrees to float rounding, so the difference
# below is the effect of the resampling. The tolerance is the largest measured
# difference of |Mxy|, Mz and |β|² for that case, times 3, rounded up. A real error of
# the pulse as played is far larger: a frequency axis of the wrong sign gave 0.99, and a
# ppm offset with the wrong B0 gave 0.76.
AS_PLAYED_TOL = {
    "sinc_excitation": 2e-4,  # measured 6.3e-5
    "sinc_refocusing": 3e-4,  # measured 7.5e-5
    "sinc_offsets": 8e-4,  # measured 2.4e-4
    "fat_saturation": 3e-4,  # measured 7.0e-5
    "hyperbolic_secant": 2e-4,  # measured 5.2e-5
    # A constant pulse loses nothing to linear resampling (measured 1.8e-14).
    "block_pulse": SAME_ROTATION_TOL,
    # Each design sample is held for 10 µs, and mr.simRf takes one step of 10 µs at the
    # centre of each: the same pulse (measured 4.2e-14).
    "slr_excitation": SAME_ROTATION_TOL,
}

# The fingerprint of the pulse as block_pulse reads the fixture's .seq file: the same
# pypulseq and reference give the same floats; the tolerance only allows float rounding
# of another numpy or pypulseq version. A larger difference means that the input
# changed: write the fixtures again with scripts/rf_references.py.
FINGERPRINT_RTOL = 1e-12


# ---- The fixtures ----


@functools.cache
def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@functools.cache
def _pulse(name: str) -> rp.BlockPulse:
    """The pulse of the fixture's `.seq` file, read with the system values of the
    fixture (a `.seq` file does not store B0 or gamma)."""
    fixture = _fixture(name)
    system = pp.Opts(**fixture["system"])
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / f"{name}.seq"
        path.write_bytes(gzip.decompress(base64.b64decode(fixture["seq_gzip_base64"])))
        seq = pp.Sequence(system)
        seq.read(str(path))
    return rp.block_pulse(seq, fixture["block"])


def _spec(entry: dict) -> rp.ProfileSpec:
    return rp.ProfileSpec(tuple(rp.ProfileAxis(**axis) for axis in entry["axes"]), entry["at"])


def _complex(entry: dict, name: str) -> np.ndarray:
    return np.asarray(entry[f"{name}_re"]) + 1j * np.asarray(entry[f"{name}_im"])


def _max_difference(actual: np.ndarray, expected: np.ndarray) -> float:
    return float(np.max(np.abs(np.asarray(actual) - np.asarray(expected))))


def test_fixtures_have_provenance_and_are_small():
    """Each fixture of the cases exists, is at most MAX_FIXTURE_BYTES, and records the
    tool and its version or commit for each reference in it; there is no other fixture."""
    names = sorted(path.stem for path in FIXTURES.glob("*.json"))
    assert names == sorted(ALL_CASES)
    for name in ALL_CASES:
        assert (FIXTURES / f"{name}.json").stat().st_size <= MAX_FIXTURE_BYTES, name
        fixture = _fixture(name)
        assert fixture["generated_by"] == "scripts/rf_references.py"
        assert fixture["pypulseq"]
        if "matlab" in fixture:
            assert len(fixture["matlab"]["matlab_pulseq_commit"]) == 40
            assert fixture["matlab"]["octave"]
        for key in ("sigpy", "slr"):
            if key in fixture:
                assert fixture[key]["versions"]["sigpy"] == "0.1.27"


@pytest.mark.parametrize("name", ALL_CASES)
def test_pulse_matches_the_fixture_fingerprint(name):
    """The pulse that block_pulse reads from the fixture's .seq file is the pulse that
    the references were given (its fingerprint), so a failure of the tests below is a
    difference of the simulation, not of the input."""
    pulse = _pulse(name)
    expected = _fixture(name)["pulse"]
    assert pulse.signal_hz.size == expected["num_samples"]
    assert pulse.gradient_kind == expected["gradient_kind"]
    assert pulse.dt_s == pytest.approx(expected["dt_s"], rel=FINGERPRINT_RTOL)
    # Each sum against the sum of the magnitudes of its terms, which can cancel (a sinc,
    # a bipolar gradient).
    signal_scale = FINGERPRINT_RTOL * float(np.abs(pulse.signal_hz).sum())
    signal = [pulse.signal_hz.real.sum(), pulse.signal_hz.imag.sum(), np.abs(pulse.signal_hz).max()]
    wanted = [expected["signal_sum_re"], expected["signal_sum_im"], expected["signal_abs_max"]]
    np.testing.assert_allclose(signal, wanted, rtol=0, atol=signal_scale)
    for axis in range(3):
        g = pulse.grad_hz_per_m[:, axis]
        grad_scale = FINGERPRINT_RTOL * float(np.abs(g).sum())
        assert abs(g.sum() - expected["grad_sum"][axis]) <= grad_scale
        assert abs(np.abs(g).max() - expected["grad_abs_max"][axis]) <= grad_scale


# ---- MATLAB Pulseq's mr.simRf ----


@pytest.mark.parametrize("name", MATLAB_CASES)
def test_simrf_of_its_resampled_rf(name):
    """rf_sim.spin_domain on the RF that mr.simRf simulates (after its own resampling,
    from the fixture) gives mr.simRf's Mz, |Mxy| and |refocusing efficiency| (= |β|²) at
    its frequencies: the same rotation, within SAME_ROTATION_TOL. The frequency of
    mr.simRf is the frequency offset `df` of this project (the same sign)."""
    matlab = _fixture(name)["matlab"]
    f = np.asarray(matlab["f_hz"])
    rf_hz = _complex(matlab, "resampled") / (2 * np.pi)  # mr.simRf keeps the RF in rad/s
    a, b = spin_domain(rf_hz, matlab["dt_s"], np.zeros((rf_hz.size, 3)), np.zeros((f.size, 3)), f)
    mxy, mz = magnetization(a, b)
    assert _max_difference(mz, matlab["mz"]) <= SAME_ROTATION_TOL
    assert _max_difference(np.abs(mxy), matlab["mxy_abs"]) <= SAME_ROTATION_TOL
    assert _max_difference(np.abs(b) ** 2, matlab["ref_eff_abs"]) <= SAME_ROTATION_TOL


@pytest.mark.parametrize("name", MATLAB_CASES)
def test_simrf_of_the_pulse_as_played(name):
    """rf_profiles.simulate of the pulse as played (block_pulse of the same .seq file:
    the hold samples with the offsets, B0 from the fixture for a ppm offset), on the
    frequency axis of mr.simRf at r = 0 (mr.simRf has no gradient), gives mr.simRf's
    Mz, |Mxy| and |β|² within AS_PLAYED_TOL of the case: the effect of the resampling of
    mr.simRf."""
    matlab = _fixture(name)["matlab"]
    f = np.asarray(matlab["f_hz"])
    spec = rp.ProfileSpec((rp.ProfileAxis("df", float(f[0]), float(f[-1]), f.size),))
    profile = rp.simulate(_pulse(name), spec)
    # numpy.linspace and MATLAB's linspace round the same axis differently (measured
    # 7e-12 Hz at most): a difference of the grid, not of the profile.
    assert _max_difference(profile.grid[0], f) <= 1e-9
    tol = AS_PLAYED_TOL[name]
    assert _max_difference(rp.quantity(profile, "mz"), matlab["mz"]) <= tol
    assert _max_difference(rp.quantity(profile, "mxy_abs"), matlab["mxy_abs"]) <= tol
    assert _max_difference(rp.quantity(profile, "beta_sq"), matlab["ref_eff_abs"]) <= tol


# ---- sigpy ----


@pytest.mark.parametrize("name", SIGPY_CASES)
def test_abrm_nd(name):
    """rf_profiles.simulate of the pulse (its hold samples and interval gradients) at the
    points of the fixture's grid gives the a and b of sigpy's abrm_nd within
    SAME_ROTATION_TOL: a slice-select gradient, one on its ramps, an oblique one, and one
    whose direction turns, at 1D and 2D points."""
    sigpy = _fixture(name)["sigpy"]
    profile = rp.simulate(_pulse(name), _spec(sigpy["spec"]))
    assert _max_difference(profile.a.ravel(), _complex(sigpy, "a")) <= SAME_ROTATION_TOL
    assert _max_difference(profile.b.ravel(), _complex(sigpy, "b")) <= SAME_ROTATION_TOL


def test_slr_profile_equals_sigpy_abrm_of_the_design():
    """The SLR 90° excitation designed by sigpy (dzrf), each design sample held for 10 µs
    on the RF raster: rf_profiles.simulate on its frequency axis gives the a and b of
    sigpy's own 1D simulator of SLR design (abrm) at x = f * duration (cycles per pulse),
    within SAME_ROTATION_TOL. abrm gets the design as the .seq file stores it: pypulseq
    writes RF shapes with about 7 significant digits (the fixture records the difference
    from the design, 7.5e-7 of its peak).

    The design ripples (d1 = d2 = 0.01) are not checked: they are not a bound for a
    90° 'ls' design, and sigpy's own simulation of its design exceeds them (the plan's
    results, phase 2b)."""
    slr = _fixture("slr_excitation")["slr"]
    pulse = _pulse("slr_excitation")
    # The design as stored: one sample of each held group, as a rotation (rad).
    repeat = round(slr["design"]["dwell_s"] / pulse.dt_s)
    stored = 2 * np.pi * slr["design"]["dwell_s"] * pulse.signal_hz[::repeat]
    assert _max_difference(stored, _complex(slr, "stored_rf")) <= SAME_ROTATION_TOL
    profile = rp.simulate(pulse, _spec(slr["spec"]))
    assert _max_difference(profile.a.ravel(), _complex(slr, "a")) <= SAME_ROTATION_TOL
    assert _max_difference(profile.b.ravel(), _complex(slr, "b")) <= SAME_ROTATION_TOL


# ---- The hyperbolic secant inversion (analytic) ----

HS_BETA = 800.0  # rad/s, pypulseq's default
HS_MU = 4.9  # pypulseq's default


def _hs_analytic_mz(f_hz: np.ndarray, w1_max: float) -> np.ndarray:
    """Mz after an untruncated hyperbolic secant pulse, from Mz = 1: B1 = w1_max *
    sech(beta t), frequency sweep mu * beta * tanh(beta t) (rad/s), at the frequency
    offset f_hz. Silver, Joseph and Hoult, Phys. Rev. A 31, 2753 (1985), as Eq. [23] of
    Zhang, Garwood and Park, "The full analytical solution of the Bloch equation when
    using a hyperbolic-secant driving function", Magn. Reson. Med. 77, 1630 (2017), with
    their R pi^2 / (4 beta_Zhang) = pi mu / 2 and A = mu beta:

        |f|^2 = (cosh^2(pi mu / 2) - cosh^2(pi c / 2))
                / (cosh^2(pi Omega / (2 beta)) + sinh^2(pi c / 2)),
        c = sqrt(mu^2 - (w1_max / beta)^2),   Mz = (1 - |f|^2) / (1 + |f|^2).

    (For w1_max > mu beta, c is imaginary; cosh and sinh of an imaginary argument are
    real, so the complex square root gives the same formula.)"""
    omega = 2 * np.pi * np.asarray(f_hz)
    c = np.emath.sqrt(HS_MU**2 - (w1_max / HS_BETA) ** 2)
    f2 = (np.cosh(np.pi * HS_MU / 2) ** 2 - np.cosh(np.pi * c / 2) ** 2) / (
        np.cosh(np.pi * omega / (2 * HS_BETA)) ** 2 + np.sinh(np.pi * c / 2) ** 2
    )
    f2 = np.real(f2)
    return (1 - f2) / (1 + f2)


def _hs_profile(duration_s: float):
    """The pypulseq hyperbolic secant ('hypsec', its default beta, mu and adiabaticity 4)
    of `duration_s`, simulated on a frequency axis: (f, Mz, w1_max in rad/s)."""
    system = pp.Opts(rf_dead_time=100e-6, rf_ringdown_time=30e-6)
    seq = pp.Sequence(system)
    seq.add_block(
        pp.make_adiabatic_pulse(
            "hypsec", duration=duration_s, delay=100e-6, system=system, use="inversion"
        )
    )
    pulse = rp.block_pulse(seq, 0)
    profile = rp.simulate(pulse, rp.ProfileSpec((rp.ProfileAxis("df", -1500.0, 1500.0, 601),)))
    w1_max = 2 * np.pi * float(np.abs(pulse.signal_hz).max())
    return profile.grid[0], rp.quantity(profile, "mz"), w1_max


def test_hyperbolic_secant_inverts_its_analytic_band():
    """pypulseq's default hyperbolic secant (10 ms, truncated at beta t = ±4; w1_max =
    2 sqrt(mu) beta = 4.43 beta, measured, from its adiabaticity 4) gives Mz <= -0.9 at each frequency where the
    analytic Mz of the untruncated pulse (_hs_analytic_mz) is at most -0.99 (|f| <= 405 Hz
    of the ±624 Hz sweep). Measured: Mz <= -0.9926 there. The bound -0.9 is the plan's
    (task 2b.3, item 4); the truncation makes the pulse differ from the analytic profile
    by up to 0.12 near the band edges, so the band is where the analytic inversion is
    deep."""
    f, mz, w1_max = _hs_profile(10e-3)
    band = _hs_analytic_mz(f, w1_max) <= -0.99
    assert np.count_nonzero(band) > 100
    assert np.max(mz[band]) <= -0.9


def test_hyperbolic_secant_approaches_the_analytic_profile():
    """The same pulse, longer, so that the truncation of sech(beta t) is smaller: the
    profile approaches the analytic profile of the untruncated pulse at every frequency.
    Measured max |Mz - analytic|: 0.125 at 10 ms (sech(4) = 3.7e-2), 3.0e-3 at 20 ms
    (sech(8) = 6.7e-4), 5.9e-5 at 30 ms (sech(12) = 1.2e-5). The tolerances are the
    measured values times 3, rounded up: the difference is the truncation, and it falls
    with it."""
    for duration_s, tol in ((20e-3, 1e-2), (30e-3, 2e-4)):
        f, mz, w1_max = _hs_profile(duration_s)
        assert _max_difference(mz, _hs_analytic_mz(f, w1_max)) <= tol, duration_s
