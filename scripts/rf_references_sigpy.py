# /// script
# requires-python = ">=3.12"
# dependencies = ["sigpy==0.1.27"]
# ///
"""The sigpy half of `scripts/rf_references.py`: runs sigpy on the jobs of an input
JSON file and writes the results to an output JSON file.

It runs in its own environment, locked in `rf_references_sigpy.py.lock` (sigpy is not
a dependency of this project):

    uv run --locked --script scripts/rf_references_sigpy.py IN.json OUT.json

IN.json: {"jobs": [job, ...]}. Each job is one of:

- {"kind": "abrm_nd", "rf_re", "rf_im", "g", "x"}: `sigpy.mri.rf.sim.abrm_nd(rf, x, g)`.
  `rf` is the RF rotation of each sample (rad, complex), `g` the gradient of each
  sample times gamma and dt (rad/m, shape (n, 3)), `x` the positions (m, shape (m, 3)).
- {"kind": "abrm", "rf_re", "rf_im", "x"}: `sigpy.mri.rf.sim.abrm(rf, x)`, the 1D
  simulator that SLR design uses: `rf` as for "abrm_nd", `x` the frequency in cycles per
  pulse.
- {"kind": "slr", "n", "tb", "ptype", "ftype", "d1", "d2"}: the SLR design
  `sigpy.mri.rf.slr.dzrf(n, tb, ptype, ftype, d1, d2)`, and its ripples and band edges
  (`calc_ripples`, `dinf`, as `dzls` and `dzlp` use them).

OUT.json: {"versions": {...}, "results": [result, ...]}, one result for each job:
`a_re`, `a_im`, `b_re`, `b_im` for "abrm_nd" and "abrm"; `rf_re`, `rf_im`, `beta_d1`,
`beta_d2`, `w`, `pass_edge_cycles` and `stop_edge_cycles` for "slr".
"""

import json
import platform
import sys

import numba
import numpy as np
import sigpy
from sigpy.mri.rf import sim, slr


def _ab(a, b) -> dict:
    return {
        "a_re": np.real(a).tolist(),
        "a_im": np.imag(a).tolist(),
        "b_re": np.real(b).tolist(),
        "b_im": np.imag(b).tolist(),
    }


def _abrm_nd(job: dict) -> dict:
    rf = np.asarray(job["rf_re"], dtype=float) + 1j * np.asarray(job["rf_im"], dtype=float)
    g = np.asarray(job["g"], dtype=float).reshape(-1, 3)
    x = np.asarray(job["x"], dtype=float).reshape(-1, 3)
    return _ab(*sim.abrm_nd(rf, x, g))


def _abrm(job: dict) -> dict:
    rf = np.asarray(job["rf_re"], dtype=float) + 1j * np.asarray(job["rf_im"], dtype=float)
    return _ab(*sim.abrm(rf, np.asarray(job["x"], dtype=float)))


def _slr(job: dict) -> dict:
    rf = slr.dzrf(
        n=job["n"],
        tb=job["tb"],
        ptype=job["ptype"],
        ftype=job["ftype"],
        d1=job["d1"],
        d2=job["d2"],
    )
    _, beta_d1, beta_d2 = slr.calc_ripples(job["ptype"], job["d1"], job["d2"])
    w = slr.dinf(beta_d1, beta_d2) / job["tb"]
    return {
        "rf_re": np.real(rf).tolist(),
        "rf_im": np.imag(rf).tolist(),
        "beta_d1": float(beta_d1),
        "beta_d2": float(beta_d2),
        "w": float(w),
        "pass_edge_cycles": float((1 - w) * job["tb"] / 2),
        "stop_edge_cycles": float((1 + w) * job["tb"] / 2),
    }


def main() -> None:
    source, target = sys.argv[1], sys.argv[2]
    with open(source, encoding="utf-8") as f:
        jobs = json.load(f)["jobs"]
    run = {"abrm_nd": _abrm_nd, "abrm": _abrm, "slr": _slr}
    results = [run[job["kind"]](job) for job in jobs]
    versions = {
        "sigpy": sigpy.__version__,
        "numba": numba.__version__,
        "numpy": np.__version__,
        "python": platform.python_version(),
    }
    with open(target, "w", encoding="utf-8") as f:
        json.dump({"versions": versions, "results": results}, f)


if __name__ == "__main__":
    main()
