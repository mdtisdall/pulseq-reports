"""Independent check of `pulseq_reports.rf_sim.spin_domain` + `magnetization`.

This oracle simulates the same physics a different way: it never builds Cayley-Klein
parameters. In each hold interval it rotates the magnetization vector M directly by a
3x3 rotation matrix (Rodrigues' formula) about the interval's effective field, and
returns the resulting Mxy and Mz. A shared error between the two implementations is
unlikely (docs/plans/rf-profiles.md, section 3.5, item 1).

The rotation is by the angle |field| * dt_s about the axis field / |field|, with
field = (Re(b1), Im(b1), phi), b1 = 2*pi*b1_scale[j]*signal[k] (rad/s, complex) and
phi = 2*pi*(grad[k] . r[j] + df[j]) (rad/s): the same effective field as
`spin_domain`, but not multiplied by dt_s (the rotation angle carries the dt_s
factor instead). This is a +angle (right-handed) rotation, the same sign convention
as vb-pulseq `cayley_klein` (see vb-pulseq's
`test_hard_pulse_with_gradient_matches_rodrigues_rotation`, which derives the sign
from the same field definition).

Plain numpy, clarity over speed: a python loop over the m points and, inside it, a
python loop over the n intervals, composing one Rodrigues rotation of a 3-vector at a
time.
"""

import numpy as np


def _rodrigues(axis: np.ndarray, theta: float, v: np.ndarray) -> np.ndarray:
    """Right-handed rotation of the 3-vector v by theta (rad) about the unit 3-vector
    axis."""
    return (
        v * np.cos(theta)
        + np.cross(axis, v) * np.sin(theta)
        + axis * np.dot(axis, v) * (1 - np.cos(theta))
    )


def magnetization(
    signal_hz: np.ndarray,
    dt_s: float,
    grad_hz_per_m: np.ndarray,
    positions_m: np.ndarray,
    df_hz: np.ndarray | None = None,
    b1_scale: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Mxy (complex, Mx + i*My) and Mz at each point, from M0 = (0, 0, 1), simulated by
    composing one Rodrigues rotation per hold interval. Same arguments as
    `pulseq_reports.rf_sim.spin_domain`."""
    signal_hz = np.asarray(signal_hz)
    grad_hz_per_m = np.asarray(grad_hz_per_m, dtype=float)
    positions_m = np.asarray(positions_m, dtype=float)
    n = signal_hz.shape[0]
    m = positions_m.shape[0]
    df_hz = np.zeros(m) if df_hz is None else np.asarray(df_hz, dtype=float)
    b1_scale = np.ones(m) if b1_scale is None else np.asarray(b1_scale, dtype=float)

    mxy = np.empty(m, dtype=complex)
    mz = np.empty(m, dtype=float)
    for j in range(m):
        r = positions_m[j]
        M = np.array([0.0, 0.0, 1.0])
        for k in range(n):
            b1 = 2 * np.pi * b1_scale[j] * signal_hz[k]  # rad/s, complex
            phi = 2 * np.pi * (grad_hz_per_m[k] @ r + df_hz[j])  # rad/s
            field = np.array([b1.real, b1.imag, phi])
            magnitude = np.linalg.norm(field)
            if magnitude == 0:
                continue  # no field: this interval leaves M unchanged
            axis = field / magnitude
            angle = magnitude * dt_s
            M = _rodrigues(axis, angle, M)
        mxy[j] = M[0] + 1j * M[1]
        mz[j] = M[2]
    return mxy, mz
