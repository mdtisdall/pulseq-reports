"""Times `reference.pns_reference` (task 2, step 3 of
`docs/plans/pns-lanes-prototype.md`). Not library code.

For `rep_12s`, `rep_60s`, `rep_120s`, `rep_370s_long` and `exvivo`
(`build_seqs.build_seq`), and `rep_1000000blocks` when its extrapolation from the
`rep_370s_long` row says it stays under the 5-minute/8-GB budget (see
`_should_run_1e6_blocks`), this measures in a FRESH process for each sequence
(`python run_reference_timing.py --worker <name>`, launched as a subprocess of this
same script):

- `build_s` (or the `.seq` read time for `exvivo`);
- `reference_s`: `pns_reference(seq, ranges=())` (no ranges, so the only memory this
  call itself adds is `chunk_samples` worth of arrays, per `reference.py`'s docstring);
- peak RSS before and after `pns_reference`, from `resource.getrusage(...).ru_maxrss`
  (a running maximum since the process started, in bytes on macOS -- this process
  only runs on macOS, so no Linux KiB conversion is needed here);
- `n_samples`, `peak`, `peak_time_s`.

This does NOT run pypulseq's own `calculate_pns` on anything here: it is too slow
above about 120 s (see `run_reference_check.py`, which already checked `pns_reference`
against it on shorter files). A worker also runs a watchdog thread that exits the
process if its own peak RSS passes 8 GB, and the parent applies a 5-minute
`subprocess.run(timeout=...)` to each worker, per the plan's "stop after 5 minutes or
8 GB" rule.

Run from the repository root:

    nix develop --command uv run python prototypes/pns_lanes/run_reference_timing.py

Writes `prototypes/pns_lanes/results/reference_timing.json` and prints a table.
"""

from __future__ import annotations

import argparse
import json
import resource
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

SEQUENCES = ["rep_12s", "rep_60s", "rep_120s", "rep_370s_long", "exvivo"]
RESULTS_PATH = Path(__file__).resolve().parent / "results" / "reference_timing.json"
TIME_BUDGET_S = 300.0
RSS_BUDGET_BYTES = 8 * 1024**3
# `docs/plans/pns-lanes-prototype.md`, section 4, item 5: a 10^7-block repeating
# sequence (built with `scripts/diagram_scale.build_repeating`) takes about 90 s and
# 3.8 GB to build. `rep_1000000blocks` uses the same builder at 1/10th the blocks;
# linear extrapolation gives about 9 s and 0.38 GB for the build alone.
KNOWN_1E7_BUILD_S = 90.0
KNOWN_1E7_BUILD_RSS_BYTES = 3.8 * 1024**3


def _peak_rss_bytes() -> int:
    """The peak RSS of this process so far (a running maximum, not a delta); bytes on
    macOS, which is the only platform this prototype runs on."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def _watchdog(stop_event: threading.Event, name: str) -> None:
    """Exits the process immediately if peak RSS passes RSS_BUDGET_BYTES, so a worker
    that is heading for the 8 GB limit stops instead of being left to the parent's
    5-minute timeout (which does not look at memory)."""
    while not stop_event.wait(1.0):
        rss = _peak_rss_bytes()
        if rss >= RSS_BUDGET_BYTES:
            print(
                json.dumps({"name": name, "error": "peak RSS passed 8 GB", "peak_rss_bytes": rss}),
                flush=True,
            )
            # os._exit: skip cleanup, so nothing tries to free the oversized arrays.
            import os

            os._exit(1)


def _run_worker(name: str, chunk_samples: int) -> None:
    import build_seqs as bs
    from reference import pns_reference

    stop_event = threading.Event()
    watchdog = threading.Thread(target=_watchdog, args=(stop_event, name), daemon=True)
    watchdog.start()

    t0 = time.perf_counter()
    seq = bs.build_seq(name)
    build_s = time.perf_counter() - t0
    peak_rss_before_bytes = _peak_rss_bytes()

    t0 = time.perf_counter()
    result = pns_reference(seq, chunk_samples=chunk_samples, ranges=())
    reference_s = time.perf_counter() - t0
    peak_rss_after_bytes = _peak_rss_bytes()

    stop_event.set()
    print(
        json.dumps(
            {
                "name": name,
                "build_s": build_s,
                "reference_s": reference_s,
                "peak_rss_before_bytes": peak_rss_before_bytes,
                "peak_rss_after_bytes": peak_rss_after_bytes,
                "n_samples": result["n_samples"],
                "peak": result["peak"],
                "peak_time_s": result["peak_time_s"],
            }
        )
    )


def _run_in_subprocess(name: str, chunk_samples: int) -> dict:
    print(f"timing {name} (fresh process) ...", file=sys.stderr)
    try:
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--worker", name,
             "--chunk-samples", str(chunk_samples)],
            capture_output=True,
            text=True,
            timeout=TIME_BUDGET_S,
        )
    except subprocess.TimeoutExpired:
        print(f"  {name}: timed out after {TIME_BUDGET_S:.0f}s", file=sys.stderr)
        return {"name": name, "error": f"timed out after {TIME_BUDGET_S:.0f}s"}

    if proc.stderr:
        sys.stderr.write(proc.stderr)
    last_line = next((line for line in reversed(proc.stdout.splitlines()) if line.strip()), None)
    if proc.returncode != 0 or last_line is None:
        return {
            "name": name,
            "error": f"worker exited {proc.returncode}",
            "stdout_tail": proc.stdout[-2000:],
        }
    row = json.loads(last_line)
    if "error" not in row:
        print(
            f"  {name}: build_s={row['build_s']:.2f} reference_s={row['reference_s']:.2f} "
            f"peak_rss_after={row['peak_rss_after_bytes'] / 1024**3:.2f}GB "
            f"n_samples={row['n_samples']} peak={row['peak']:.4f}",
            file=sys.stderr,
        )
    return row


def _should_run_1e6_blocks(rep_370s_row: dict) -> tuple[bool, dict]:
    """Extrapolates from the measured `rep_370s_long` row (40,000 blocks) to
    `rep_1000000blocks` (1,000,000 blocks, a factor of 25), using its own measured
    `reference_s` (the reference computation is chunk-bounded, so its time scales
    with sample count, and its memory does not grow with file length) and the known
    10^7-block build figures (linearly scaled to 10^6 blocks) for the build.
    Returns `(should_run, estimate)`."""
    if "error" in rep_370s_row:
        return False, {"reason": "rep_370s_long did not complete"}
    scale = 1_000_000 / 40_000  # 25
    estimated_reference_s = rep_370s_row["reference_s"] * scale
    estimated_build_s = KNOWN_1E7_BUILD_S / 10  # 10^6 is 1/10th of 10^7
    estimated_total_s = estimated_build_s + estimated_reference_s
    estimated_build_rss_bytes = KNOWN_1E7_BUILD_RSS_BYTES / 10
    # The reference call's own peak RSS is chunk-bounded, so use rep_370s_long's
    # measured figure as-is (it does not scale with file length).
    estimated_peak_rss_bytes = max(estimated_build_rss_bytes, rep_370s_row["peak_rss_after_bytes"])
    estimate = {
        "estimated_total_s": estimated_total_s,
        "estimated_peak_rss_bytes": estimated_peak_rss_bytes,
    }
    should_run = estimated_total_s < TIME_BUDGET_S and estimated_peak_rss_bytes < RSS_BUDGET_BYTES
    return should_run, estimate


def _print_table(rows: list[dict]) -> None:
    header = (
        f"{'name':<20}{'n_samples':>12}  {'build_s':>8}  {'reference_s':>11}  "
        f"{'peak_rss_after':>15}  {'peak':>10}  {'peak_time_s':>14}"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        if "error" in row:
            print(f"{row['name']:<20}  ERROR: {row['error']}")
            continue
        print(
            f"{row['name']:<20}{row['n_samples']:>12}  {row['build_s']:>8.2f}  "
            f"{row['reference_s']:>11.2f}  {row['peak_rss_after_bytes'] / 1024**3:>13.2f}GB  "
            f"{row['peak']:>10.4f}  {str(row['peak_time_s']):>14}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    parser.add_argument("--chunk-samples", type=int, default=2**20, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.worker:
        _run_worker(args.worker, args.chunk_samples)
        return 0

    rows = [_run_in_subprocess(name, args.chunk_samples) for name in SEQUENCES]

    rep_370s_row = next(r for r in rows if r["name"] == "rep_370s_long")
    should_run, estimate = _should_run_1e6_blocks(rep_370s_row)
    print(
        f"rep_1000000blocks extrapolation from rep_370s_long: "
        f"estimated_total_s={estimate.get('estimated_total_s')} "
        f"estimated_peak_rss_bytes={estimate.get('estimated_peak_rss_bytes')} "
        f"run={should_run}",
        file=sys.stderr,
    )
    if should_run:
        row = _run_in_subprocess("rep_1000000blocks", args.chunk_samples)
        row["extrapolated_before_running"] = estimate
        rows.append(row)
    else:
        rows.append(
            {"name": "rep_1000000blocks", "skipped": True, "extrapolated_before_running": estimate}
        )

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    _print_table(rows)
    print(f"\nwrote {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
