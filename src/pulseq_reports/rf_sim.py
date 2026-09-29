"""Spin-domain (Cayley-Klein) simulation of RF pulses, without relaxation.

From vb-pulseq `rf_sim.py` (commit 3a1c7dd), generalized to points in 3D with a
frequency offset and a B1 factor for each point, and a gradient vector for each hold
interval (`docs/plans/rf-profiles.md`, section 4.2).
"""

import numpy as np


def spin_domain(
    signal_hz: np.ndarray,
    dt_s: float,
    grad_hz_per_m: np.ndarray,
    positions_m: np.ndarray,
    df_hz: np.ndarray | None = None,
    b1_scale: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Cayley-Klein alpha and beta after a pulse, at each point.

    signal_hz: (n,) complex RF samples (Hz), each held for `dt_s` (s).
    grad_hz_per_m: (n, 3) the mean gradient (Hz/m) of each hold interval, on x, y, z.
    positions_m: (m, 3) the position of each point (m).
    df_hz: (m,) the frequency offset of each point (Hz), or None for 0.
    b1_scale: (m,) a factor on the RF of each point, or None for 1.

    For interval k and point j, the RF angle is `2π * dt * b1_scale[j] * signal[k]`
    (complex) and the off-resonance angle is `2π * dt * (grad[k] · r[j] + df[j])`. The
    interval is one rotation with both angles, as in vb-pulseq `cayley_klein`: with
    grad[k] = (0, 0, G), r[j] = (0, 0, x[j]), df = 0 and b1_scale = 1, the result is
    `cayley_klein(signal, dt, G, x)`. Returns (a, b), each (m,) complex.
    """
    signal_hz = np.asarray(signal_hz)
    if signal_hz.ndim != 1:
        raise ValueError(f"signal_hz must have shape (n,), got {signal_hz.shape}")
    n = signal_hz.shape[0]

    grad_hz_per_m = np.asarray(grad_hz_per_m, dtype=float)
    if grad_hz_per_m.shape != (n, 3):
        raise ValueError(
            f"grad_hz_per_m must have shape (n, 3) = ({n}, 3) to match signal_hz's {n} "
            f"samples, got {grad_hz_per_m.shape}"
        )

    positions_m = np.asarray(positions_m, dtype=float)
    if positions_m.ndim != 2 or positions_m.shape[1] != 3:
        raise ValueError(f"positions_m must have shape (m, 3), got {positions_m.shape}")
    m = positions_m.shape[0]

    if df_hz is None:
        df_hz = np.zeros(m)
    else:
        df_hz = np.asarray(df_hz, dtype=float)
        if df_hz.shape != (m,):
            raise ValueError(
                f"df_hz must have shape (m,) = ({m},) to match positions_m's {m} points, "
                f"got {df_hz.shape}"
            )

    if b1_scale is None:
        b1_scale = np.ones(m)
    else:
        b1_scale = np.asarray(b1_scale, dtype=float)
        if b1_scale.shape != (m,):
            raise ValueError(
                f"b1_scale must have shape (m,) = ({m},) to match positions_m's {m} "
                f"points, got {b1_scale.shape}"
            )

    a = np.ones(m, dtype=complex)
    b = np.zeros(m, dtype=complex)
    two_pi_dt = 2 * np.pi * dt_s
    for k in range(n):
        # phi and b1 follow the formulas of the docstring exactly (dt applied once, to
        # the sum/product), not vb-pulseq's own order of multiplication: the two agree
        # only up to float reassociation (section 3.5, item 1 of the plan).
        phi = two_pi_dt * (positions_m @ grad_hz_per_m[k] + df_hz)
        b1 = two_pi_dt * b1_scale * signal_hz[k]
        theta = np.hypot(np.abs(b1), phi)
        safe = np.where(theta == 0, 1.0, theta)
        s, c = np.sin(theta / 2), np.cos(theta / 2)
        ak = c - 1j * (phi / safe) * s
        bk = -1j * (b1 / safe) * s
        a, b = ak * a - np.conj(bk) * b, bk * a + np.conj(ak) * b
    return a, b


def magnetization(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Mxy (complex, Mx + i*My) and Mz from Cayley-Klein alpha, beta, for M0 = (0, 0, 1)."""
    return 2 * np.conj(a) * b, np.abs(a) ** 2 - np.abs(b) ** 2


def crushed_echo(b: np.ndarray) -> np.ndarray:
    """Refocusing profile |beta|^2 of a crushed spin echo, from Cayley-Klein beta."""
    return np.abs(b) ** 2


def precess(mxy: np.ndarray, moment_per_m: np.ndarray, positions_m: np.ndarray) -> np.ndarray:
    """Mxy after free precession under a gradient moment vector (1/m, x y z) at each
    position (m, 3): `mxy * exp(2j*pi * (moment · r))`.

    The sign matches `spin_domain` with zero RF: Mxy gains the phase
    +2*pi*(moment · r).
    """
    moment_per_m = np.asarray(moment_per_m, dtype=float)
    positions_m = np.asarray(positions_m, dtype=float)
    return mxy * np.exp(2j * np.pi * (positions_m @ moment_per_m))
