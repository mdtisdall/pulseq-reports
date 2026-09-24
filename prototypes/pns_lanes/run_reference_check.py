"""Checks `reference.pns_reference` against pypulseq `Sequence.calculate_pns` (task 2,
step 2 of `docs/plans/pns-lanes-prototype.md`). Not library code.

For each of `spin_echo`, `gre`, `arbitrary`, `border`, `rep_12s`, `rep_60s`
(`build_seqs.build_seq`), runs `pns_reference(seq, ranges=((0, duration),))` (so the
one range covers the whole file) and pypulseq's own `seq.calculate_pns(safe_example_hw(),
do_plots=False)`, then:

- checks the sample times `t` are identical (`np.array_equal`);
- records the largest `|difference|` of the total and of each axis, divided by the
  pypulseq peak of the total (0 when the pypulseq peak is 0, i.e. no gradients);
- records both peaks and both peak times.

`calculate_pns` on `rep_60s` (about 300,085 samples) takes about 45 s and about
1.5 GB; that is expected and is why this script does not go past 60 s (see
`run_reference_timing.py` for longer files, which do not run `calculate_pns` at all).

Run from the repository root:

    nix develop --command uv run python prototypes/pns_lanes/run_reference_check.py

Writes `prototypes/pns_lanes/results/reference_check.json` and prints a table.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from pypulseq.utils.safe_pns_prediction import safe_example_hw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_seqs as bs  # noqa: E402
from reference import pns_reference  # noqa: E402

SEQUENCES = ["spin_echo", "gre", "arbitrary", "border", "rep_12s", "rep_60s"]
RESULTS_PATH = Path(__file__).resolve().parent / "results" / "reference_check.json"


def _check_one(name: str, hw) -> dict:
    seq = bs.build_seq(name)
    duration = seq.duration()[0]

    t0 = time.perf_counter()
    ref = pns_reference(seq, hw, ranges=((0.0, duration),))
    ref_s = time.perf_counter() - t0
    r = ref["ranges"][0]

    t0 = time.perf_counter()
    _, norm, comp, t = seq.calculate_pns(hw, do_plots=False)
    pypulseq_s = time.perf_counter() - t0

    times_equal = bool(np.array_equal(r["t"], t))
    pypulseq_peak = float(norm.max()) if norm.size else 0.0
    scale = pypulseq_peak if pypulseq_peak > 0 else 1.0

    def rel_max_abs_diff(a: np.ndarray, b: np.ndarray) -> float:
        if a.shape != b.shape:
            return float("nan")
        return float(np.max(np.abs(a - b))) / scale if a.size else 0.0

    first = np.flatnonzero(norm >= pypulseq_peak * (1 - 1e-6))[0] if norm.size else None
    pypulseq_peak_time = float(t[first]) if first is not None else None

    return {
        "name": name,
        "n_samples": int(r["t"].shape[0]),
        "times_equal": times_equal,
        "rel_max_abs_diff_total": rel_max_abs_diff(r["total"], norm),
        "rel_max_abs_diff_x": rel_max_abs_diff(r["x"], comp[:, 0]),
        "rel_max_abs_diff_y": rel_max_abs_diff(r["y"], comp[:, 1]),
        "rel_max_abs_diff_z": rel_max_abs_diff(r["z"], comp[:, 2]),
        "reference_peak": ref["peak"],
        "pypulseq_peak": pypulseq_peak,
        "reference_peak_time_s": ref["peak_time_s"],
        "pypulseq_peak_time_s": pypulseq_peak_time,
        "reference_s": ref_s,
        "pypulseq_s": pypulseq_s,
    }


def main() -> int:
    hw = safe_example_hw()
    rows = []
    for name in SEQUENCES:
        print(f"checking {name} ...", file=sys.stderr)
        row = _check_one(name, hw)
        rows.append(row)
        print(
            f"  n={row['n_samples']} times_equal={row['times_equal']} "
            f"rel_diff(total)={row['rel_max_abs_diff_total']:.3e} "
            f"peak(ref)={row['reference_peak']:.6f} peak(pypulseq)={row['pypulseq_peak']:.6f} "
            f"reference_s={row['reference_s']:.2f} pypulseq_s={row['pypulseq_s']:.2f}",
            file=sys.stderr,
        )

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    header = (
        f"{'name':<12}{'n_samples':>10}  {'t equal':>7}  {'rel diff total':>15}  "
        f"{'rel diff x':>11}  {'rel diff y':>11}  {'rel diff z':>11}  "
        f"{'peak ref':>10}  {'peak pypulseq':>13}  {'peak_time ref':>14}  {'peak_time pyp':>14}"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['name']:<12}{row['n_samples']:>10}  {str(row['times_equal']):>7}  "
            f"{row['rel_max_abs_diff_total']:>15.3e}  {row['rel_max_abs_diff_x']:>11.3e}  "
            f"{row['rel_max_abs_diff_y']:>11.3e}  {row['rel_max_abs_diff_z']:>11.3e}  "
            f"{row['reference_peak']:>10.6f}  {row['pypulseq_peak']:>13.6f}  "
            f"{str(row['reference_peak_time_s']):>14}  {str(row['pypulseq_peak_time_s']):>14}"
        )
    print(f"\nwrote {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
