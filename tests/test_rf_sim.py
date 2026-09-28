"""Tests for `pulseq_reports.rf_sim`, checked against independently derived physics and
against an independent oracle (`tests/oracles/rf_sim.py`).

Tests 1 to 6 below (all but the shape-validation test) come from vb-pulseq
`tests/tools/test_rf_sim.py` (commit 3a1c7dd), adapted to the new signatures: a 1D
simulation along z is `grad_hz_per_m` of shape (n, 3) with only the z column nonzero,
and `positions_m` of shape (m, 3) with only the z column nonzero. Every expected value
still comes from a closed-form rotation, a Fourier sum or free precession computed
directly with numpy, not from the simulator itself. Their tolerances and reasons are
kept from vb-pulseq.

Oracle: `tests/oracles/rf_sim.py`, which rotates the magnetization vector directly
(Rodrigues' formula) in each hold interval, without Cayley-Klein parameters. It is
compared with `rf_sim.spin_domain` + `rf_sim.magnetization` within 1e-10 (docs/plans/
rf-profiles.md, section 3.5, item 1): a shared error between the two methods is
unlikely.
"""

import numpy as np
import pytest
from oracles import rf_sim as oracle

from pulseq_reports import rf_sim


def _grad_z(g_scalar: float, n: int) -> np.ndarray:
    """An (n, 3) gradient array with amplitude `g_scalar` on z only, constant over the
    n intervals."""
    grad = np.zeros((n, 3))
    grad[:, 2] = g_scalar
    return grad


def _positions_z(z) -> np.ndarray:
    """An (m, 3) positions array with the given z coordinates, x = y = 0."""
    z = np.atleast_1d(np.asarray(z, dtype=float))
    positions = np.zeros((z.size, 3))
    positions[:, 2] = z
    return positions


def _hard_pulse_signal(flip_rad, n, dt, phase=0.0):
    """A constant-amplitude signal whose total rotation angle is flip_rad."""
    amplitude = flip_rad / (2 * np.pi * n * dt)
    return np.full(n, amplitude * np.exp(1j * phase))


def _rodrigues(axis, theta, v):
    """Right-handed rotation of v by theta about the unit vector axis."""
    return (
        v * np.cos(theta)
        + np.cross(axis, v) * np.sin(theta)
        + axis * np.dot(axis, v) * (1 - np.cos(theta))
    )


# ---- 1. The six vb-pulseq tests, adapted to the new signatures ----


@pytest.mark.parametrize("flip_deg", [30, 90, 180])
def test_hard_pulse_zero_gradient_flip_angle(flip_deg):
    # abs=1e-9: vb-pulseq's own tolerance for this comparison, the float error of
    # composing 1000 Cayley-Klein rotations (no analytic reason for a tighter bound).
    flip = np.deg2rad(flip_deg)
    dt = 1e-6
    n = 1000  # 1 ms hard pulse
    signal = _hard_pulse_signal(flip, n, dt)

    mxy, mz = rf_sim.magnetization(
        *rf_sim.spin_domain(signal, dt, _grad_z(0.0, n), _positions_z(0.0))
    )

    assert mz[0] == pytest.approx(np.cos(flip), abs=1e-9)
    assert abs(mxy[0]) == pytest.approx(abs(np.sin(flip)), abs=1e-9)


def test_hard_pulse_with_gradient_matches_rodrigues_rotation():
    # spin_domain rotates M by +angle (right-handed) about the effective field
    # (Re b1, Im b1, off-resonance). A simulation with the reversed direction fails
    # this test. abs=1e-9: vb-pulseq's own tolerance, the float error of composing
    # 1000 Cayley-Klein rotations.
    dt = 1e-6
    n = 1000
    duration = n * dt
    amplitude = 300.0  # Hz
    phase = 0.3  # rad, nonzero so the rotation axis tilts off the x-axis
    signal = np.full(n, amplitude * np.exp(1j * phase))
    gradient = 1.0e5  # Hz/m
    # Off-resonance at these positions: 0, 100, 200, 300, -250 Hz, comparable to the
    # 300 Hz B1 amplitude from x = 0.002 m up.
    x = np.array([0.0, 0.001, 0.002, 0.003, -0.0025])

    mxy_sim, mz_sim = rf_sim.magnetization(
        *rf_sim.spin_domain(signal, dt, _grad_z(gradient, n), _positions_z(x))
    )

    b1 = 2 * np.pi * amplitude * np.exp(1j * phase)  # rad/s
    off_resonance = 2 * np.pi * gradient * x  # rad/s
    field = np.stack([np.full_like(x, b1.real), np.full_like(x, b1.imag), off_resonance], axis=1)
    angle = np.linalg.norm(field, axis=1) * duration
    axis = field / np.linalg.norm(field, axis=1, keepdims=True)

    m0 = np.array([0.0, 0.0, 1.0])
    m_expected = np.array([_rodrigues(axis[i], angle[i], m0) for i in range(len(x))])

    np.testing.assert_allclose(mz_sim, m_expected[:, 2], atol=1e-9)
    np.testing.assert_allclose(mxy_sim.real, m_expected[:, 0], atol=1e-9)
    np.testing.assert_allclose(mxy_sim.imag, m_expected[:, 1], atol=1e-9)


def test_small_flip_angle_matches_fourier_prediction():
    # atol = 0.02 * peak: vb-pulseq's own tolerance, an empirical bound on the
    # small-tip-angle approximation error for a 5-degree sinc pulse (not a
    # rounding-error bound: the two sides use genuinely different formulas).
    duration = 4e-3
    time_bw_product = 4
    n = 400
    dt = duration / n
    t = np.arange(n) * dt
    bandwidth = time_bw_product / duration  # Hz
    t_centered = t - (n - 1) * dt / 2
    shape = np.sinc(bandwidth * t_centered) * np.hanning(n)

    flip = np.deg2rad(5)
    signal = shape * (flip / (2 * np.pi * dt * np.sum(shape)))

    thickness = 0.005  # m, nominal (bandwidth / gradient)
    gradient = bandwidth / thickness  # Hz/m
    x = np.linspace(-0.010, 0.010, 201)

    mxy_sim = np.abs(
        rf_sim.magnetization(
            *rf_sim.spin_domain(signal, dt, _grad_z(gradient, n), _positions_z(x))
        )[0]
    )

    phase = 2 * np.pi * gradient * x[:, None] * t[None, :]
    mxy_predicted = np.abs(2 * np.pi * dt * np.sum(signal[None, :] * np.exp(1j * phase), axis=1))

    tolerance = 0.02 * mxy_sim.max()
    np.testing.assert_allclose(mxy_sim, mxy_predicted, atol=tolerance)


def test_magnetization_and_crushed_echo_definitions():
    # default assert_allclose tolerance: these are direct algebraic definitions
    # applied to hand-picked a, b, not results of a simulation.
    a = np.array([0.6 + 0.0j, 0.3 - 0.4j])
    b = np.array([0.8j, 0.5 + 0.7071j])
    mxy, mz = rf_sim.magnetization(a, b)
    np.testing.assert_allclose(mxy, 2 * np.conj(a) * b)
    np.testing.assert_allclose(mz, np.abs(a) ** 2 - np.abs(b) ** 2)
    np.testing.assert_allclose(rf_sim.crushed_echo(b), np.abs(b) ** 2)


def test_precess_sign_matches_free_precession_in_spin_domain():
    # Zero RF under the same gradient continues the simulation with free precession,
    # so precess must reproduce it. The opposite sign must not. atol=1e-9: vb-pulseq's
    # own tolerance, the float error of composing 700 Cayley-Klein rotations.
    dt = 1e-6
    n = 200
    signal = _hard_pulse_signal(np.deg2rad(70), n, dt, phase=0.4)
    gradient = 1.0e5  # Hz/m
    x = np.linspace(-0.003, 0.003, 13)
    positions = _positions_z(x)
    n_free = 500
    moment = np.array([0.0, 0.0, gradient * n_free * dt])  # 1/m, 2*pi*moment.r up to ~0.94 rad

    mxy_pulse, _ = rf_sim.magnetization(
        *rf_sim.spin_domain(signal, dt, _grad_z(gradient, n), positions)
    )
    extended = np.concatenate([signal, np.zeros(n_free)])
    mxy_free, _ = rf_sim.magnetization(
        *rf_sim.spin_domain(extended, dt, _grad_z(gradient, n + n_free), positions)
    )

    np.testing.assert_allclose(
        rf_sim.precess(mxy_pulse, moment, positions), mxy_free, rtol=0, atol=1e-9
    )
    assert not np.allclose(
        rf_sim.precess(mxy_pulse, -moment, positions), mxy_free, rtol=0, atol=1e-3
    )


def test_magnetization_has_unit_length_for_random_pulses():
    # atol=1e-9: vb-pulseq's own tolerance. |M| = 1 is exact only in exact arithmetic;
    # this bounds the float error of composing up to 100 Cayley-Klein rotations.
    rng = np.random.default_rng(7)
    dt = 1e-5
    positions = _positions_z(np.linspace(-0.01, 0.01, 21))
    for _ in range(5):
        n = int(rng.integers(20, 100))
        signal = rng.normal(0, 200, n) + 1j * rng.normal(0, 200, n)  # Hz
        gradient = rng.uniform(-5e4, 5e4)  # Hz/m
        mxy, mz = rf_sim.magnetization(
            *rf_sim.spin_domain(signal, dt, _grad_z(gradient, n), positions)
        )
        np.testing.assert_allclose(np.abs(mxy) ** 2 + mz**2, 1.0, atol=1e-9)


# ---- 2. The oracle (docs/plans/rf-profiles.md, section 3.5, item 1) ----


def test_matches_oracle_for_random_rf_gradient_and_points():
    # atol=1e-10: the oracle rule of section 3.5, item 1 of the plan. spin_domain
    # composes Cayley-Klein parameters; the oracle rotates the magnetization vector
    # directly (Rodrigues) in each interval. A shared error between the two methods
    # is unlikely.
    rng = np.random.default_rng(1234)
    n, m = 250, 30  # at least 200 RF samples
    dt = 1e-6
    signal = rng.normal(0, 300, n) + 1j * rng.normal(0, 300, n)  # Hz
    grad = rng.uniform(-5e4, 5e4, size=(n, 3))  # a different vector in every interval
    positions = rng.uniform(-0.02, 0.02, size=(m, 3))
    df = rng.uniform(-200, 200, size=m)
    b1_scale = rng.uniform(0.5, 1.5, size=m)

    mxy_sim, mz_sim = rf_sim.magnetization(
        *rf_sim.spin_domain(signal, dt, grad, positions, df, b1_scale)
    )
    mxy_oracle, mz_oracle = oracle.magnetization(signal, dt, grad, positions, df, b1_scale)

    np.testing.assert_allclose(mxy_sim.real, mxy_oracle.real, atol=1e-10)
    np.testing.assert_allclose(mxy_sim.imag, mxy_oracle.imag, atol=1e-10)
    np.testing.assert_allclose(mz_sim, mz_oracle, atol=1e-10)


# ---- 3. Rotation invariance ----


def test_rotation_invariance_matches_1d_simulation_along_the_gradient_direction():
    # atol=1e-12: both sides compute the same rotation, just with the gradient and the
    # positions reindexed onto different axes; the difference is float reassociation
    # in a handful of extra multiply-adds (the zero x, y components), not an
    # approximation.
    rng = np.random.default_rng(5)
    n = 60
    dt = 1e-6
    signal = rng.normal(0, 250, n) + 1j * rng.normal(0, 250, n)
    gx, gy = 3e4, -7e4
    u = np.array([gx, gy, 0.0])
    g_mag = np.linalg.norm(u)
    u_hat = u / g_mag
    grad_2d = np.tile(u, (n, 1))  # constant (Gx, Gy, 0) in every interval

    dist = np.linspace(-0.01, 0.01, 11)
    positions_2d = dist[:, None] * u_hat[None, :]  # points along u

    a_2d, b_2d = rf_sim.spin_domain(signal, dt, grad_2d, positions_2d)
    a_1d, b_1d = rf_sim.spin_domain(signal, dt, _grad_z(g_mag, n), _positions_z(dist))

    np.testing.assert_allclose(a_2d, a_1d, atol=1e-12)
    np.testing.assert_allclose(b_2d, b_1d, atol=1e-12)


# ---- 4. df is a shift ----


def test_df_is_a_shift_along_the_gradient():
    # atol=1e-12: both points see the same total off-resonance angle in every interval
    # (G*(z + df/G) + 0 == G*z + df, up to reassociation of the same multiply-add); the
    # difference is float rounding in one extra division and addition, not an
    # approximation.
    n = 80
    dt = 1e-6
    rng = np.random.default_rng(9)
    signal = rng.normal(0, 200, n) + 1j * rng.normal(0, 200, n)
    grad = _grad_z(5e4, n)
    G = 5e4
    z = 0.004
    df = 137.0

    a_shift, b_shift = rf_sim.spin_domain(signal, dt, grad, _positions_z(z + df / G))
    a_df, b_df = rf_sim.spin_domain(signal, dt, grad, _positions_z(z), df_hz=np.array([df]))

    np.testing.assert_allclose(a_shift, a_df, atol=1e-12)
    np.testing.assert_allclose(b_shift, b_df, atol=1e-12)


# ---- 5. b1_scale ----


def test_b1_scale_gives_s_times_the_flip_angle_of_a_hard_pulse():
    # abs=1e-12: for a hard pulse with zero gradient, every interval rotates about the
    # same fixed axis, so composing n identical small rotations is exactly one
    # rotation by n times the per-interval angle, in exact arithmetic; this bounds the
    # float error of composing 300 such rotations (much tighter than the 1e-9 bound of
    # the 1000-interval tests above, because there the rotation axis also changes).
    flip = np.deg2rad(40)
    dt = 1e-6
    n = 300
    signal = _hard_pulse_signal(flip, n, dt)
    positions = _positions_z(0.0)
    s = 1.7

    mxy_s, mz_s = rf_sim.magnetization(
        *rf_sim.spin_domain(signal, dt, _grad_z(0.0, n), positions, b1_scale=np.array([s]))
    )

    assert mz_s[0] == pytest.approx(np.cos(s * flip), abs=1e-12)
    assert abs(mxy_s[0]) == pytest.approx(np.sin(s * flip), abs=1e-12)


# ---- 6. precess with a moment vector ----


def test_precess_matches_scalar_form_along_one_axis():
    # exact: positions_m @ moment_per_m reduces to x * area plus two products with a
    # zero component (0*0 + 0*0 + x*area), which does not change the float value
    # (verified: positions_m @ moment_per_m == area * x exactly, for this rng seed).
    # The expected value keeps the same "2j*pi * (the dot product)" grouping as the
    # docstring formula and `precess` itself, rather than a left-to-right
    # 2j*pi*area*x, which associates differently and is not bit-identical.
    rng = np.random.default_rng(3)
    m = 25
    x = rng.uniform(-0.02, 0.02, m)
    mxy = rng.normal(0, 1, m) + 1j * rng.normal(0, 1, m)
    area = 137.0  # 1/m

    moment = np.array([0.0, 0.0, area])
    result = rf_sim.precess(mxy, moment, _positions_z(x))
    expected = mxy * np.exp(2j * np.pi * (area * x))

    np.testing.assert_array_equal(result, expected)


# ---- 7. Shape validation ----


def test_spin_domain_raises_value_error_for_mismatched_shapes():
    # ValueError, not a silent broadcast or a cryptic numpy error: the shape contract
    # of docs/plans/rf-profiles.md, section 4.2.
    n, m = 10, 5
    signal = np.zeros(n, dtype=complex)
    dt = 1e-6
    good_grad = np.zeros((n, 3))
    good_positions = np.zeros((m, 3))

    with pytest.raises(ValueError):
        rf_sim.spin_domain(signal, dt, np.zeros((n - 1, 3)), good_positions)  # wrong n
    with pytest.raises(ValueError):
        rf_sim.spin_domain(signal, dt, np.zeros((n, 2)), good_positions)  # not 3 axes
    with pytest.raises(ValueError):
        rf_sim.spin_domain(signal, dt, good_grad, np.zeros((m, 2)))  # not 3 axes
    with pytest.raises(ValueError):
        rf_sim.spin_domain(signal, dt, good_grad, good_positions, df_hz=np.zeros(m - 1))
    with pytest.raises(ValueError):
        rf_sim.spin_domain(signal, dt, good_grad, good_positions, b1_scale=np.zeros(m + 1))
