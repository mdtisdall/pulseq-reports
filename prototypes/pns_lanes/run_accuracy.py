"""Task 4 of docs/plans/pns-lanes-prototype.md, question 1 (accuracy): builds one test
sequence, exports its diagram tables (for `pns_lanes.js`), runs `reference.py`'s
`pns_reference` over one or more time ranges, and writes the reference samples plus a
manifest that `run_accuracy.js` reads to compare `PnsLanes.exactView` against them.
Prototype code only; not part of the library, never merged (see README.md).

Two modes:

- `run_accuracy.py <name>`: worker mode. Builds `name` (`build_seqs.build_seq`) ONE
  time, and from that one `pp.Sequence`:
  - exports the diagram tables (`pulseq_reports.diagram_data`) to
    `<scratch>/<name>_tables.json`, in the same JSON shape as `export_tables.py`
    writes, so `run_accuracy.js` (and `run_exact_selfcheck.js`'s own decode helper,
    which this file's JS counterpart duplicates) can decode it the same way;
  - runs `reference.py`'s `pns_reference` once, with a list of time ranges (the whole
    file for a short sequence, or a fixed set of random/edge ranges for a long one;
    see `_ranges_for`), and writes each range's `t`, `total`, `x`, `y`, `z` reference
    arrays as raw little-endian float64 `.bin` files under `<scratch>/<name>_bins/`;
  - writes `<scratch>/<name>_manifest.json`: the ranges (label, t0, t1, sample count,
    bin paths), the reference whole-file peak, peak time, axis peaks and sample count
    (all computed by `pns_reference` regardless of `ranges`, over the full chunked
    pass), and the tables JSON path and `dt`.
  Prints the manifest path (JSON on the last stdout line) and returns 0.

- `run_accuracy.py` (no name) or `run_accuracy.py --all`: driver mode. Runs worker mode
  for each of the nine sequences below in a FRESH `python` subprocess (plan section 4,
  "one fresh process for each measurement"), then runs `run_accuracy.js <manifest>
  <out.json>` in a fresh `node` subprocess for each manifest, collects the results, and
  writes `results/accuracy.json` plus a printed summary table (the largest
  |JS - reference| / reference peak, for total and each axis, per sequence).

Sequences (task 4, this task's own list): spin_echo, gre, arbitrary, border, rep_12s,
rep_60s, rep_370s_long, exvivo, worst_100000blocks (`build_seqs.build_seq` names).

Ranges (as instructed for task 4): for sequences up to ~12 s (spin_echo, gre,
arbitrary, border, rep_12s), the whole file. For longer ones (rep_60s, rep_370s_long,
exvivo, worst_100000blocks): 20 random 1 s ranges, 5 random 20 ms ranges, the first 1 s
and the last 1 s, with a fixed seed (so re-running this script picks the same ranges).

Scratch directory: the fixed path this task was given
(/private/tmp/claude-501/-Users-dylan-dev-pulseq-reports/
45cf8d58-d17a-495a-9bb4-3f5195b44223/scratchpad/pns_task4), not the worktree; override
with the PNS_TASK4_SCRATCH_DIR environment variable if needed.

Run from the repository root:

    nix develop --command uv run python prototypes/pns_lanes/run_accuracy.py --all
"""

from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT))

import build_seqs as bs  # noqa: E402
from pulseq_reports import diagram_data  # noqa: E402
from pypulseq.utils.safe_pns_prediction import safe_example_hw  # noqa: E402
from reference import pns_reference  # noqa: E402

SCRATCH_DIR = Path(
    os.environ.get(
        "PNS_TASK4_SCRATCH_DIR",
        "/private/tmp/claude-501/-Users-dylan-dev-pulseq-reports/"
        "45cf8d58-d17a-495a-9bb4-3f5195b44223/scratchpad/pns_task4",
    )
)
RESULTS_PATH = HERE / "results" / "accuracy.json"
RUN_ACCURACY_JS = HERE / "run_accuracy.js"

# The nine sequences this task measures accuracy on.
WHOLE_FILE_NAMES = ["spin_echo", "gre", "arbitrary", "border", "rep_12s"]
SAMPLED_NAMES = ["rep_60s", "rep_370s_long", "exvivo", "worst_100000blocks"]
ALL_SEQUENCES = WHOLE_FILE_NAMES + SAMPLED_NAMES

TIME_BUDGET_S = 300.0
RSS_BUDGET_BYTES = 8 * 1024**3
RANDOM_SEED_BASE = 20260924  # fixed, so re-running picks the same ranges

FIELDS = ("t", "total", "x", "y", "z")


def _peak_rss_bytes() -> int:
    """The peak RSS of this process so far (macOS: bytes, a running maximum)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def _watchdog(stop_event: threading.Event, name: str) -> None:
    while not stop_event.wait(1.0):
        rss = _peak_rss_bytes()
        if rss >= RSS_BUDGET_BYTES:
            print(
                json.dumps({"name": name, "error": "peak RSS passed 8 GB", "peak_rss_bytes": rss}),
                flush=True,
            )
            os._exit(1)


def _hw_to_json(hw) -> dict:
    out = {}
    for axis in ("x", "y", "z"):
        a = getattr(hw, axis)
        out[axis] = {
            "tau1": a.tau1,
            "tau2": a.tau2,
            "tau3": a.tau3,
            "a1": a.a1,
            "a2": a.a2,
            "a3": a.a3,
            "stim_limit": a.stim_limit,
            "g_scale": a.g_scale,
        }
    return out


def _ranges_for(name: str, duration_s: float, dt: float) -> list[tuple[str, float, float]]:
    """The (label, t0, t1) ranges to check `name` over: the whole file for a name in
    WHOLE_FILE_NAMES, else 20 random 1 s ranges, 5 random 20 ms ranges, the first 1 s
    and the last 1 s, from a fixed per-name seed. `t1` of a range that reaches the file
    end is nudged a bit past the last sample time (as `run_exact_selfcheck.js`'s
    `rangesFor` does, "fileEnd = lastT + dt"), so the last real sample is included
    despite float rounding of `duration_s`."""
    # `duration_s` here is `reference_duration_s` (the caller's `n_samples * dt`,
    # reference.py's own sample domain, see build_manifest): its last real sample is
    # at `duration_s - 0.5 * dt`, and the next (non-existent, one past the reference
    # domain) sample would be at `duration_s + 0.5 * dt`. `file_end` must land
    # strictly between those two, or exactView's inclusive "t <= t1" rule (in
    # sampleRangeFor) picks up one sample beyond what the reference ever computed,
    # for no filter-accuracy reason (see run_accuracy.py's build_manifest comment). A
    # tiny epsilon above `duration_s` (not a full `dt`) keeps a margin for float
    # rounding of `duration_s` itself while staying well clear of that next sample.
    file_end = duration_s + dt * 1e-6
    if name in WHOLE_FILE_NAMES:
        return [("whole file", 0.0, file_end)]

    assert name in SAMPLED_NAMES, f"_ranges_for: {name!r} is in neither name list"
    # A fixed seed per sequence name (not a single shared seed), so the set of ranges
    # for one sequence does not shift if another sequence is added to/removed from
    # ALL_SEQUENCES; still fully deterministic across runs.
    seed = (RANDOM_SEED_BASE, int.from_bytes(name.encode(), "little") % (2**32))
    rng = np.random.default_rng(seed)

    ranges: list[tuple[str, float, float]] = []

    def _random_range(label: str, length: float) -> tuple[str, float, float] | None:
        span = duration_s - length
        if span <= 0:
            return None
        t0 = float(rng.uniform(0.0, span))
        return (label, t0, t0 + length)

    for i in range(20):
        r = _random_range(f"random_1s_{i:02d}", 1.0)
        if r is not None:
            ranges.append(r)
    for i in range(5):
        r = _random_range(f"random_20ms_{i:02d}", 0.02)
        if r is not None:
            ranges.append(r)

    ranges.append(("first_1s", 0.0, min(1.0, duration_s)))
    ranges.append(("last_1s", max(0.0, duration_s - 1.0), file_end))
    return ranges


def build_manifest(name: str) -> dict:
    """Builds `name` once, exports its tables JSON, runs `pns_reference` over this
    sequence's ranges, writes the .bin files, and returns the manifest dict (also
    written to `<scratch>/<name>_manifest.json` by the caller)."""
    scratch = SCRATCH_DIR
    scratch.mkdir(parents=True, exist_ok=True)
    bins_dir = scratch / f"{name}_bins"
    bins_dir.mkdir(parents=True, exist_ok=True)

    t_build0 = time.perf_counter()
    seq = bs.build_seq(name)
    build_s = time.perf_counter() - t_build0

    dt = float(seq.grad_raster_time)
    duration_s, num_blocks, _event_count = seq.duration()
    duration_s = float(duration_s)

    # The tables JSON (export_tables.py's own payload shape), from this one build.
    tables = diagram_data.diagram_tables(seq)
    encoded_tables = diagram_data.encode_tables(tables)
    hw = safe_example_hw()
    opts = {
        "gradRasterS": dt,
        "gamma": float(seq.system.gamma),
        "hw": _hw_to_json(hw),
        "groupBlocks": 64,
    }
    tables_path = scratch / f"{name}_tables.json"
    tables_path.write_text(
        json.dumps(
            {
                "format": 1,
                "tables": encoded_tables,
                "opts": opts,
                "durationS": duration_s,
                "numBlocks": int(num_blocks),
                "sequenceName": name,
            }
        )
    )

    # pns_reference's own sample count (n_samples, from calc_pns.py's "nt =
    # ceil((max_t - 1e-10) / dt)", max_t from the gradient PPolys' own last
    # breakpoint) is often SMALLER than `duration_s` (the block table's total
    # duration): a sequence with a trailing delay/spacer block after its last
    # gradient event has that many fewer PNS samples in pypulseq's own count than
    # blockLen would sum to (pypulseq's calc_pns simply never evaluates PNS past the
    # last gradient event; it is not that the model differs there). A range that
    # reaches "the end of the file" (whole file, first_1s, last_1s) must reach the
    # END OF THIS SHORTER, reference-defined domain, not `duration_s`, or the
    # reference and JS sides select different sample counts for no filter-accuracy
    # reason. A first pns_reference call (cheap: `ranges=()` adds no memory beyond
    # `chunk_samples`, per reference.py's docstring) gets n_samples; the real call
    # below uses ranges built from `reference_duration_s = n_samples * dt`.
    probe = pns_reference(seq, hw=hw, ranges=())
    reference_duration_s = probe["n_samples"] * dt

    ranges = _ranges_for(name, reference_duration_s, dt)
    t_ref0 = time.perf_counter()
    result = pns_reference(seq, hw=hw, ranges=tuple((t0, t1) for _label, t0, t1 in ranges))
    reference_s = time.perf_counter() - t_ref0

    range_entries = []
    for (label, t0, t1), range_result in zip(ranges, result["ranges"], strict=True):
        n = int(range_result["t"].shape[0])
        paths = {}
        for field in FIELDS:
            arr = np.ascontiguousarray(range_result[field], dtype="<f8")
            p = bins_dir / f"{label}_{field}.bin"
            arr.tofile(p)
            paths[f"{field}Path"] = str(p)
        range_entries.append(
            {
                "label": label,
                "t0": t0,
                "t1": t1,
                "n": n,
                "isWholeFile": label == "whole file",
                **paths,
            }
        )

    manifest = {
        "name": name,
        "tablesPath": str(tables_path),
        "dt": dt,
        "durationS": duration_s,
        "referenceDurationS": reference_duration_s,
        "numBlocks": int(num_blocks),
        "buildS": build_s,
        "referenceS": reference_s,
        "referencePeak": result["peak"],
        "referencePeakTimeS": result["peak_time_s"],
        "referenceAxisPeaks": result["axis_peaks"],
        "referenceNSamples": result["n_samples"],
        "ranges": range_entries,
    }
    manifest_path = scratch / f"{name}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    manifest["manifestPath"] = str(manifest_path)
    return manifest


def _run_worker(name: str) -> None:
    stop_event = threading.Event()
    watchdog = threading.Thread(target=_watchdog, args=(stop_event, name), daemon=True)
    watchdog.start()
    manifest = build_manifest(name)
    stop_event.set()
    print(json.dumps({"name": name, "manifestPath": manifest["manifestPath"]}))


def _run_worker_subprocess(name: str) -> dict:
    print(f"building + reference: {name} (fresh process) ...", file=sys.stderr)
    try:
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), name],
            capture_output=True,
            text=True,
            timeout=TIME_BUDGET_S,
        )
    except subprocess.TimeoutExpired:
        return {"name": name, "error": f"python worker timed out after {TIME_BUDGET_S:.0f}s"}
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    last_line = next((line for line in reversed(proc.stdout.splitlines()) if line.strip()), None)
    if proc.returncode != 0 or last_line is None:
        return {
            "name": name,
            "error": f"python worker exited {proc.returncode}",
            "stdout_tail": proc.stdout[-2000:],
        }
    return json.loads(last_line)


def _run_js_subprocess(name: str, manifest_path: str) -> dict:
    out_path = SCRATCH_DIR / f"{name}_js_result.json"
    print(f"exactView vs reference: {name} (fresh node process) ...", file=sys.stderr)
    try:
        proc = subprocess.run(
            ["node", str(RUN_ACCURACY_JS), manifest_path, str(out_path)],
            capture_output=True,
            text=True,
            timeout=TIME_BUDGET_S,
        )
    except subprocess.TimeoutExpired:
        return {"name": name, "error": f"node worker timed out after {TIME_BUDGET_S:.0f}s"}
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        return {
            "name": name,
            "error": f"node worker exited {proc.returncode}",
            "stdout_tail": proc.stdout[-2000:],
        }
    return json.loads(out_path.read_text())


def _print_summary(rows: list[dict]) -> None:
    header = f"{'name':<20}{'maxDiff/peak total':>20}{'x':>14}{'y':>14}{'z':>14}  notes"
    print(header)
    print("-" * len(header))
    for row in rows:
        if "error" in row:
            print(f"{row['name']:<20}  ERROR: {row['error']}")
            continue
        w = row["worstRelDiff"]
        notes = "" if not row.get("sampleMismatches") else f"{len(row['sampleMismatches'])} range(s) with a sample-count mismatch"
        print(
            f"{row['name']:<20}{w['total']:>20.3e}{w['x']:>14.3e}{w['y']:>14.3e}{w['z']:>14.3e}  {notes}"
        )


def _run_all() -> int:
    rows = []
    for name in ALL_SEQUENCES:
        worker_row = _run_worker_subprocess(name)
        if "error" in worker_row:
            rows.append(worker_row)
            continue
        js_row = _run_js_subprocess(name, worker_row["manifestPath"])
        rows.append(js_row)

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(rows, indent=2))
    _print_summary(rows)
    print(f"\nwrote {RESULTS_PATH}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] == "--all":
        return _run_all()
    name = argv[0]
    if name not in ALL_SEQUENCES:
        print(f"unknown sequence {name!r}; known: {ALL_SEQUENCES}", file=sys.stderr)
        return 2
    _run_worker(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
