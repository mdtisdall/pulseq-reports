"""The Python reference for the SAFE PNS model (task 2 of
`docs/plans/pns-lanes-prototype.md`). Not library code.

`pns_reference` computes the same model as pypulseq's `Sequence.calculate_pns`
(`pypulseq/Sequence/calc_pns.py`, `pypulseq/utils/safe_pns_prediction.py`), the exact
formulas and line numbers being in `prototypes/pns_lanes/README.md`, task 1:

1. Sample each axis's gradient `PPoly` (from one `seq.get_gradients()` call, with the
   block cache off) at `t[k] = (k + 0.5) * dt` for `k = 0 .. n_samples - 1`, in T/m.
2. `x[k] = (g[k] - g[k - 1]) / dt`, with `g[-1] = 0` (the padding zero before the
   first real sample; see the README's "Consequences" list).
3. Nine first-order low-pass filters (3 axes x tau1, tau2, tau3; the tau2 filter
   takes `|x|` instead of `x`), each `y[k] = alpha * u[k] + (1 - alpha) * y[k - 1]`,
   `y[-1] = 0`, `alpha = dt_ms / (tau_ms + dt_ms)`.
4. Per axis: `stim1 = a1 * |LP_tau1(x)|`, `stim2 = a2 * LP_tau2(|x|)`,
   `stim3 = a3 * |LP_tau3(x)|`, axis value `(stim1 + stim2 + stim3) / stim_limit *
   g_scale`.
5. Total: the root-sum-of-squares of the three axis values. The value 1 is the
   stimulation limit (matching `calculate_pns`'s `pns_norm`, not its 0-100 percent
   scale).

Unlike `calc_pns`, this does not evaluate the whole file into memory at once: it
samples and filters in chunks of `chunk_samples`, carrying each filter's state
(`scipy.signal.lfilter`'s `zi`/`zf`) and each axis's last gradient sample from one
chunk to the next. Peak memory stays bounded by `chunk_samples` (a few filters' worth
of float64 arrays that size), plus whatever `ranges` asks for explicitly.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import pypulseq as pp
from pypulseq.utils.safe_pns_prediction import safe_example_hw
from scipy.signal import lfilter

AXES = ("x", "y", "z")
TAUS = ("tau1", "tau2", "tau3")
# Samples within this fraction of the peak count as the peak, matching
# `pulseq_reports.pns.PnsPrediction.PEAK_TOLERANCE` (the first such sample is the
# peak time).
PEAK_TOLERANCE = 1e-6


def _empty_result(ranges: tuple[tuple[float, float], ...]) -> dict:
    empty = np.zeros(0)
    return {
        "peak": 0.0,
        "peak_time_s": None,
        "axis_peaks": {axis: 0.0 for axis in AXES},
        "n_samples": 0,
        "ranges": [
            {"t0": t0, "t1": t1, "t": empty, "total": empty, "x": empty, "y": empty, "z": empty}
            for t0, t1 in ranges
        ],
    }


def _chunk_filters(hw: SimpleNamespace, dt: float) -> dict:
    """`{axis: {tau_name: alpha}}` for the nine filters, `alpha = dt_ms / (tau_ms +
    dt_ms)`."""
    dt_ms = dt * 1000.0
    return {
        axis: {
            tau: dt_ms / (getattr(getattr(hw, axis), tau) + dt_ms) for tau in TAUS
        }
        for axis in AXES
    }


def _run_chunk(
    k0: int,
    k1: int,
    dt: float,
    gamma: float,
    gw_pp: list,
    hw: SimpleNamespace,
    alpha: dict,
    filt_state_in: dict,
    g_prev_in: dict,
) -> tuple[np.ndarray, np.ndarray, dict, dict, dict]:
    """The exact samples `t[k0:k1]` of `total` and each axis, and the filter/gradient
    state at the end of the chunk. `filt_state_in`/`g_prev_in` are the state at the
    start of the chunk (the `zi` of each of the nine filters, and each axis's last
    gradient sample); they are copied, not mutated, so a caller can re-run the same
    chunk from the same start (used for the peak-time second pass)."""
    filt_state = {axis: dict(filt_state_in[axis]) for axis in AXES}
    g_prev = dict(g_prev_in)

    t = (np.arange(k0, k1, dtype=np.float64) + 0.5) * dt
    axis_values = {}
    for axis, gw in zip(AXES, gw_pp, strict=True):
        g = gw(t) / gamma if gw is not None else np.zeros(t.shape[0])
        x = np.empty_like(g)
        x[0] = (g[0] - g_prev[axis]) / dt
        if g.shape[0] > 1:
            x[1:] = np.diff(g) / dt
        if g.shape[0]:
            g_prev[axis] = float(g[-1])

        hw_axis = getattr(hw, axis)
        y1, filt_state[axis]["tau1"] = lfilter(
            [alpha[axis]["tau1"]], [1.0, alpha[axis]["tau1"] - 1.0], x, zi=filt_state[axis]["tau1"]
        )
        y2, filt_state[axis]["tau2"] = lfilter(
            [alpha[axis]["tau2"]],
            [1.0, alpha[axis]["tau2"] - 1.0],
            np.abs(x),
            zi=filt_state[axis]["tau2"],
        )
        y3, filt_state[axis]["tau3"] = lfilter(
            [alpha[axis]["tau3"]], [1.0, alpha[axis]["tau3"] - 1.0], x, zi=filt_state[axis]["tau3"]
        )
        stim1 = hw_axis.a1 * np.abs(y1)
        stim2 = hw_axis.a2 * y2
        stim3 = hw_axis.a3 * np.abs(y3)
        axis_values[axis] = (stim1 + stim2 + stim3) / hw_axis.stim_limit * hw_axis.g_scale

    total = np.sqrt(sum(axis_values[axis] ** 2 for axis in AXES))
    return t, total, axis_values, filt_state, g_prev


def pns_reference(
    seq: pp.Sequence,
    hw: SimpleNamespace | None = None,
    chunk_samples: int = 2**20,
    ranges: tuple[tuple[float, float], ...] = (),
) -> dict:
    """The SAFE PNS prediction of `seq` with hardware `hw` (`safe_example_hw()` when
    None), computed in chunks of `chunk_samples` samples.

    Returns a dict:

    - `peak`: the maximum of the total over the whole file (0.0 with no gradients).
    - `peak_time_s`: the time of the first sample with total >= peak * (1 -
      PEAK_TOLERANCE), or None with no gradients.
    - `axis_peaks`: `{"x": ..., "y": ..., "z": ...}`, the maximum of each axis.
    - `n_samples`: the number of PNS samples in the whole file.
    - `ranges`: one dict per `(t0, t1)` of `ranges`, in the same order, each
      `{"t0", "t1", "t", "total", "x", "y", "z"}` with the samples `t0 <= t <= t1`
      (`t`/`total`/`x`/`y`/`z` are float64 arrays of the same length; a range that
      matches no sample gets length-0 arrays).
    """
    if hw is None:
        hw = safe_example_hw()
    dt = seq.grad_raster_time
    gamma = seq.system.gamma

    old_cache = seq.use_block_cache
    seq.use_block_cache = False
    try:
        gw_pp = seq.get_gradients()
    finally:
        seq.use_block_cache = old_cache

    if all(gw is None for gw in gw_pp):
        return _empty_result(ranges)

    max_t = max(gw.x[-1] for gw in gw_pp if gw is not None) - 1e-10
    n_samples = int(math.ceil(max_t / dt))
    alpha = _chunk_filters(hw, dt)

    filt_state = {axis: {tau: np.zeros(1) for tau in TAUS} for axis in AXES}
    g_prev = {axis: 0.0 for axis in AXES}

    peak = 0.0
    axis_peaks = {axis: 0.0 for axis in AXES}
    # One small entry per chunk (not per sample): the state at the chunk's start, its
    # sample bounds, and its own local peak. Used for the peak-time second pass below.
    chunk_starts = []
    range_chunks: list[list[dict]] = [[] for _ in ranges]

    for k0 in range(0, n_samples, chunk_samples):
        k1 = min(k0 + chunk_samples, n_samples)
        chunk_starts.append(
            {
                "k0": k0,
                "k1": k1,
                "filt_state": {axis: dict(filt_state[axis]) for axis in AXES},
                "g_prev": dict(g_prev),
            }
        )
        t, total, axis_values, filt_state, g_prev = _run_chunk(
            k0, k1, dt, gamma, gw_pp, hw, alpha, filt_state, g_prev
        )
        chunk_starts[-1]["local_peak"] = float(total.max())
        peak = max(peak, chunk_starts[-1]["local_peak"])
        for axis in AXES:
            axis_peaks[axis] = max(axis_peaks[axis], float(axis_values[axis].max()))

        for i, (t0, t1) in enumerate(ranges):
            mask = (t >= t0) & (t <= t1)
            if mask.any():
                range_chunks[i].append(
                    {
                        "t": t[mask],
                        "total": total[mask],
                        "x": axis_values["x"][mask],
                        "y": axis_values["y"][mask],
                        "z": axis_values["z"][mask],
                    }
                )

    peak_time_s = None
    threshold = peak * (1 - PEAK_TOLERANCE)
    for chunk in chunk_starts:
        if chunk["local_peak"] >= threshold:
            t2, total2, _, _, _ = _run_chunk(
                chunk["k0"], chunk["k1"], dt, gamma, gw_pp, hw, alpha, chunk["filt_state"], chunk["g_prev"]
            )
            idx = int(np.flatnonzero(total2 >= threshold)[0])
            peak_time_s = float(t2[idx])
            break

    range_results = []
    for i, (t0, t1) in enumerate(ranges):
        parts = range_chunks[i]
        if parts:
            range_results.append(
                {
                    "t0": t0,
                    "t1": t1,
                    "t": np.concatenate([p["t"] for p in parts]),
                    "total": np.concatenate([p["total"] for p in parts]),
                    "x": np.concatenate([p["x"] for p in parts]),
                    "y": np.concatenate([p["y"] for p in parts]),
                    "z": np.concatenate([p["z"] for p in parts]),
                }
            )
        else:
            empty = np.zeros(0)
            range_results.append(
                {"t0": t0, "t1": t1, "t": empty, "total": empty, "x": empty, "y": empty, "z": empty}
            )

    return {
        "peak": peak,
        "peak_time_s": peak_time_s,
        "axis_peaks": axis_peaks,
        "n_samples": n_samples,
        "ranges": range_results,
    }
