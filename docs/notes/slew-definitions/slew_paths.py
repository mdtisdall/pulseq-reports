"""The four slew paths of docs/notes/slew-definitions.md, computed on the same examples.

- pypulseq limit checks: the slope of each segment of each gradient event, and the step
  at each block junction divided by grad_raster_time (what make_* and add_block check).
- pypulseq PNS: the SAFE input dgdt of pypulseq's calc_pns.
- MATLAB Pulseq limit checks and MATLAB PNS (calcPNS with the SAFE MATLAB toolbox): run
  in GNU Octave by matlab_paths.m and matlab_limit_cases.m.

Each example is built with pypulseq, written to a .seq file, and read back by pypulseq
and by MATLAB Pulseq, so all the paths see the same file. make_figures.py plots the
results. It is a script for the report.
"""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pypulseq as pp
import scipy.io
from pypulseq.utils.safe_pns_prediction import safe_gwf_to_pns
from pypulseq.utils.siemens.asc_to_hw import asc_to_hw
from pypulseq.utils.siemens.readasc import readasc

HERE = Path(__file__).resolve().parent
AXES = ("x", "y", "z")

# Round numbers make the plots easy to read: a step of max_slew * grad_raster_time is
# 1 mT/m, and a ramp of one raster at the limit is 1 mT/m high.
SYS = pp.Opts(max_grad=40, grad_unit="mT/m", max_slew=100, slew_unit="T/m/s")
GAMMA = SYS.gamma
DT = SYS.grad_raster_time
S_MAX = SYS.max_slew  # Hz/m/s


def mt(value):
    """mT/m to Hz/m."""
    return np.asarray(value, dtype=float) * 1e-3 * GAMMA if np.ndim(value) else value * 1e-3 * GAMMA


def _delay(t=50e-6):
    return pp.make_delay(t)


def _trap(amp_mt, rise, flat, fall, channel="x"):
    return pp.make_trapezoid(
        channel,
        amplitude=mt(amp_mt),
        rise_time=rise,
        flat_time=flat,
        fall_time=fall,
        system=SYS,
    )


def _ext(times_us, amps_mt, channel="x"):
    return pp.make_extended_trapezoid(
        channel,
        times=np.asarray(times_us, dtype=float) * 1e-6,
        amplitudes=mt(np.asarray(amps_mt, dtype=float)),
        system=SYS,
        skip_check=True,
    )


def _arb(samples_mt, first_mt, last_mt, channel="x"):
    return pp.make_arbitrary_grad(
        channel,
        mt(np.asarray(samples_mt, dtype=float)),
        first=mt(first_mt),
        last=mt(last_mt),
        system=SYS,
    )


def _seq(*blocks):
    seq = pp.Sequence(SYS)
    for block in blocks:
        seq.add_block(*block) if isinstance(block, tuple) else seq.add_block(block)
    return seq


# --- The examples ----------------------------------------------------------------


def ex_trap():
    """A trapezoid with ramps of three raster intervals at the slew limit."""
    return _seq(_delay(), _trap(3, 30e-6, 30e-6, 30e-6), _delay())


def ex_blips():
    """Triangles with ramps of one and of two raster intervals, both at the slew limit."""
    return _seq(_delay(), _trap(1, 10e-6, 0, 10e-6), _delay(), _trap(2, 20e-6, 0, 20e-6), _delay())


def ex_arb():
    """An arbitrary gradient: a sine lobe of 20 samples, first = last = 0."""
    n = 20
    samples = 6 * np.sin(np.pi * (np.arange(n) + 0.5) / n)
    return _seq(_delay(), _arb(samples, 0, 0), _delay())


def ex_junction_arb():
    """Arbitrary -> arbitrary with a step of 1 mT/m (the add_block tolerance) at the
    junction. Both ramp at 100 T/m/s."""
    ramp = (np.arange(10) + 0.5) * 1e-2 * 100  # mT/m at the half-raster samples
    a = _arb(ramp, 0, 10)
    b = _arb(11 + ramp, 11, 21)
    down = _ext([0, 210], [21, 0])
    return _seq(_delay(), a, b, down, _delay())


def ex_junction_ext_long():
    """Extended trapezoid -> extended trapezoid with a step of 1 mT/m. The first segment
    of the second event is 100 us long."""
    a = _ext([0, 100], [0, 10])
    b = _ext([0, 100, 310], [11, 21, 0])
    return _seq(_delay(), a, b, _delay())


def ex_junction_ext_short():
    """The same step, but the first segment of the second event is one raster long."""
    a = _ext([0, 100], [0, 10])
    b = _ext([0, 10, 130], [11, 12, 0])
    return _seq(_delay(), a, b, _delay())


def ex_junction_empty():
    """An event that ends at 0.9 mT/m (inside the tolerance) at the block end, then a
    block with no gradient on that axis, then a trapezoid."""
    a = _ext([0, 100, 200], [0, 10, 0.9])
    return _seq(_delay(), a, _delay(200e-6), _trap(3, 30e-6, 30e-6, 30e-6), _delay())


def ex_epi():
    """A short EPI-like train for the PNS comparison: readout trapezoids of +-20 mT/m
    with 200 us ramps on x, and blips with one-raster ramps on y."""
    blocks = [_delay(100e-6)]
    for i in range(8):
        blocks.append(_trap(20 if i % 2 == 0 else -20, 200e-6, 400e-6, 200e-6))
        blocks.append(_trap(1, 10e-6, 0, 10e-6, channel="y"))
    blocks.append(_delay(100e-6))
    return _seq(*blocks)


def ex_arb_oversampled():
    """An oversampled arbitrary gradient (a sample every half raster): a trapezoid with
    40 us ramps to 8 mT/m, so its ramps are at 200 % of max_slew. pypulseq accepts it."""
    t = np.arange(1, 22) * DT / 2  # 21 samples; shape_dur is 22 half rasters = 110 us
    w = np.interp(t, [0, 40e-6, 70e-6, 110e-6], [0, 8, 8, 0])
    g = pp.make_arbitrary_grad("x", mt(w), first=0, last=0, oversampling=True, system=SYS)
    return _seq(_delay(), g, _delay())


# pypulseq 1.5.0.post1 cannot round-trip an oversampled arbitrary gradient through a
# .seq file: write() and read() fail in remove_duplicates (KeyError: -1, the time
# shape ID that flags half-raster sampling), and read(remove_duplicates=False) gives the
# gradient twice its shape_dur. So these examples are written without remove_duplicates
# (MATLAB Pulseq reads them correctly), and the pypulseq paths use the sequence in memory.
IN_MEMORY = {"arb_oversampled"}

EXAMPLES = {
    "trap": ex_trap,
    "blips": ex_blips,
    "arb": ex_arb,
    "junction_arb": ex_junction_arb,
    "junction_ext_long": ex_junction_ext_long,
    "junction_ext_short": ex_junction_ext_short,
    "junction_empty": ex_junction_empty,
    "epi": ex_epi,
    "arb_oversampled": ex_arb_oversampled,
}


# --- Construction checks: what each implementation accepts -----------------------


def _oversampled_350():
    step = 3.5 * S_MAX * DT / 2  # 350 % of max_slew over half a raster
    w = np.concatenate([np.arange(1, 9) * step, [9 * step], np.arange(8, 0, -1) * step])
    return pp.make_arbitrary_grad("x", w, system=SYS, oversampling=True, first=0, last=0)


LIMIT_CASES = {
    # name: (description, function that builds and adds the blocks). The events that a
    # case does not test are at 90 % of max_slew.
    "segment_at_100pct": (
        "Extended trapezoid, one segment at exactly 100 % (10 mT/m in 100 us)",
        lambda: _seq(_ext([0, 100], [0, 10]), _ext([0, 100], [10, 0])),
    ),
    "segment_at_120pct": (
        "Extended trapezoid, one segment at 120 %",
        lambda: _seq(_ext([0, 100], [0, 12]), _ext([0, 120], [12, 0])),
    ),
    "trap_explicit_rise_200pct": (
        "Trapezoid, 20 mT/m with an explicit 100 us rise time (200 %)",
        lambda: _seq(_trap(20, 100e-6, 100e-6, 100e-6)),
    ),
    "arb_oversampled_350pct": (
        "Oversampled arbitrary gradient, segments at 350 %",
        lambda: _seq(_oversampled_350()),
    ),
    "junction_step_110pct": (
        "Junction step of 1.1 mT/m (110 %): 9 -> 10.1 mT/m",
        lambda: _seq(_ext([0, 100], [0, 9]), _ext([0, 120], [10.1, 0])),
    ),
    "junction_step_opposite_signs": (
        "Junction step of 1.8 mT/m (180 %): -0.9 -> +0.9 mT/m",
        lambda: _seq(_ext([0, 10], [0, -0.9]), _ext([0, 10], [0.9, 0])),
    ),
    "end_nonzero_then_no_gradient": (
        "Event ends at 9 mT/m, the next block has no gradient on that axis",
        lambda: _seq(_ext([0, 100], [0, 9]), _delay()),
    ),
    "unaligned_end_negative": (
        "Event ends at -18 mT/m, 100 us before its block ends",
        lambda: _seq((_ext([0, 200], [0, -18]), _delay(300e-6))),
    ),
    "unaligned_end_positive": (
        "Event ends at +18 mT/m, 100 us before its block ends",
        lambda: _seq((_ext([0, 200], [0, 18]), _delay(300e-6))),
    ),
    "zero_duration_block_in_joint": (
        "A label-only block (duration 0) between two joined events",
        lambda: _seq(
            _ext([0, 100], [0, 9]),
            pp.make_label(type="SET", label="LIN", value=0),
            _ext([0, 100], [9, 0]),
        ),
    ),
}


def python_limit_cases():
    """{name: [accepted, message]} for pypulseq."""
    out = {}
    for name, (_, build) in LIMIT_CASES.items():
        try:
            build()
            out[name] = [True, ""]
        except (ValueError, RuntimeError, AssertionError) as err:
            out[name] = [False, str(err).splitlines()[0]]
    return out


# --- The synthetic .asc file ------------------------------------------------------

# The parameters of the SAFE example hardware (safe_example_hw(), not a real scanner),
# in the newer .asc layout. MATLAB calcPNS takes only an .asc file name (a struct fails
# with "unknown .asc file format"), so both PNS paths read this file.
ASC_HW = {
    "X": ((0.20, 0.03, 3.00), (0.40, 0.10, 0.50), 30.0, 24.0, 0.35),
    "Y": ((1.50, 2.50, 0.15), (0.55, 0.15, 0.30), 15.0, 12.0, 0.31),
    "Z": ((2.00, 0.12, 1.00), (0.42, 0.40, 0.18), 25.0, 20.0, 0.25),
}


def write_asc(path: Path, old_layout: bool = False) -> None:
    """Write the example hardware as an .asc file. With old_layout, the gradient scale
    factors are the top-level flGCGScaleFactor* of older files (no asGPAParameters)."""
    lines = []
    for ax, (tau, a, limit, thresh, g_scale) in ASC_HW.items():
        lines += [f"flGSWDTau{ax}[{i}] = {v}" for i, v in enumerate(tau)]
        lines += [f"flGSWDA{ax}[{i}] = {v}" for i, v in enumerate(a)]
        lines += [f"flGSWDStimulationLimit{ax} = {limit}"]
        lines += [f"flGSWDStimulationThreshold{ax} = {thresh}"]
        if old_layout:
            lines += [f"flGCGScaleFactor{ax} = {g_scale}"]
        else:
            lines += [f"asGPAParameters[0].sGCParameters.flGScaleFactor{ax} = {g_scale}"]
    path.write_text("\n".join(lines) + "\n")


# --- The pypulseq paths -----------------------------------------------------------


def event_points(g) -> tuple[np.ndarray, np.ndarray]:
    """The corner or sample points (s from the block start, Hz/m) of one gradient event:
    the polyline whose segments make_trapezoid, make_extended_trapezoid and
    make_arbitrary_grad check. An arbitrary gradient runs from `first` at 0 through its
    samples to `last` at shape_dur. An extended trapezoid repeats its first and last
    points; the zero-length segments are dropped.

    For an oversampled gradient, the end is tt[-1] + grad_raster_time / 2, as
    make_arbitrary_grad sets shape_dur. Sequence.get_block of pypulseq 1.5.0.post1 gives
    such a gradient twice that shape_dur (block.py:428 has no factor 0.5)."""
    if g.type == "trap":
        t = np.cumsum([0.0, g.rise_time, g.flat_time, g.fall_time])
        amp = np.array([0.0, g.amplitude, g.amplitude, 0.0])
    else:
        end = g.tt[-1] + DT / 2 if is_oversampled(g) else g.shape_dur
        t = np.concatenate([[0.0], np.asarray(g.tt, dtype=float), [end]])
        amp = np.concatenate([[g.first], np.asarray(g.waveform, dtype=float), [g.last]])
    return g.delay + t, amp


def is_oversampled(g) -> bool:
    """An arbitrary gradient with a sample every half raster (oversampling=True)."""
    tt = np.asarray(getattr(g, "tt", []), dtype=float)
    return (
        g.type == "grad"
        and tt.size > 1
        and abs(tt[0] - DT / 2) < 1e-9
        and abs(tt[1] - tt[0] - DT / 2) < 1e-9
    )


def limit_check_slew(seq: pp.Sequence) -> dict:
    """The slew as pypulseq's limit checks define it, for each axis (T/m/s):

    - "segments": rows (t0, t1, slope, pypulseq value, MATLAB value) for each segment
      of each gradient event (event_points). The slope is the true slope. The last two
      are the values that the make_* checks of each library compare with max_slew:
      pypulseq's is slope / 4 for an oversampled arbitrary gradient (it divides by
      2 * grad_raster_time, make_arbitrary_grad.py:96); MATLAB's is NaN for a
      trapezoid (mr.makeTrapezoid has no slope check).
    - "events": (t, amplitude in T/m) of each event, for the plots.
    - "junctions": rows (t, step / grad_raster_time) at each block junction, where the
      step is (first value after - last value before), with 0 for a block that has no
      event on the axis, and 0 before the first block. add_block checks |step|.
    """
    out = {ax: {"segments": [], "junctions": [], "events": []} for ax in AXES}
    prev_last = dict.fromkeys(AXES, 0.0)
    start = 0.0
    for block_id in seq.block_events:
        duration = seq.block_durations[block_id]
        block = seq.get_block(block_id)
        for ax in AXES:
            g = getattr(block, f"g{ax}", None)
            first = last = 0.0
            if g is not None:
                t, amp = event_points(g)
                t = start + t
                out[ax]["events"].append((t, amp / GAMMA))
                dt = np.diff(t)
                keep = dt > 1e-12
                slope = np.diff(amp)[keep] / dt[keep] / GAMMA
                py_value = slope / 4 if is_oversampled(g) else slope
                mat_value = np.full_like(slope, np.nan) if g.type == "trap" else slope
                rows = zip(t[:-1][keep], t[1:][keep], slope, py_value, mat_value, strict=True)
                out[ax]["segments"] += list(rows)
                if abs(t[0] - start) < 1e-9:
                    first = amp[0] / GAMMA
                if abs(t[-1] - (start + duration)) < 1e-9:
                    last = amp[-1] / GAMMA
            out[ax]["junctions"].append((start, (first - prev_last[ax]) / DT))
            prev_last[ax] = last
        start += duration
    for d in out.values():
        d["segments"] = np.array(d["segments"]).reshape(-1, 5)
        d["junctions"] = np.array(d["junctions"]).reshape(-1, 2)
    return out


def pypulseq_waveform(seq: pp.Sequence) -> dict:
    """The merged waveform of Sequence.waveforms() (points, T/m), which get_gradients,
    calc_pns and the test report use."""
    wave = seq.waveforms()
    return {ax: np.vstack([w[0], w[1] / GAMMA]) for ax, w in zip(AXES, wave, strict=True)}


def pypulseq_dgdt(seq: pp.Sequence, hw: SimpleNamespace) -> dict:
    """The SAFE input of pypulseq calc_pns: the same lines as Sequence/calc_pns.py, but
    keeping res.dgdt. Returns the report times t, the samples g (T/m), dgdt (T/m/s) and
    the PNS (fraction of the limit) for each kept sample."""
    dt = seq.grad_raster_time
    gw_pp = seq.get_gradients()
    max_t = max(g.x[-1] for g in gw_pp if g is not None) - 1e-10
    nt = int(np.ceil(max_t / dt))
    t = (np.arange(nt) + 0.5) * dt
    gw = np.zeros((t.shape[0], len(gw_pp)))
    for i, g in enumerate(gw_pp):
        if g is not None:
            gw[:, i] = g(t)
    pns, res = safe_gwf_to_pns(gw / seq.system.gamma, np.nan * np.ones(nt), dt, hw)
    keep = ~np.isfinite(res.rf[1:])
    return {"t": t, "g": gw / seq.system.gamma, "dgdt": res.dgdt[keep], "pns": 0.01 * pns[keep]}


def pypulseq_test_report_slew(wave: dict) -> list:
    """The per-axis "Max slew rate" of pypulseq's test report (T/m/s): the same lines as
    Sequence/ext_test_report.py (gws = diff(g) / diff(t) of the merged waveform).
    test_report() itself needs an RF pulse, which most examples do not have."""
    out = []
    for ax in AXES:
        t, g = wave[ax]
        out.append(float(np.max(np.abs(np.diff(g) / np.diff(t)))) if t.size > 1 else 0.0)
    return out


# --- Octave -----------------------------------------------------------------------


def octave_command() -> list:
    """octave-cli from PATH, or from the locked nixpkgs of the repository's flake."""
    if shutil.which("octave-cli"):
        return ["octave-cli"]
    repo = HERE.parents[2]
    return ["nix", "shell", "--inputs-from", str(repo), "nixpkgs#octave", "--command"] + [
        "octave-cli"
    ]


def run_octave(script: str, out_dir: Path, pulseq: Path, safe: Path) -> None:
    env = dict(os.environ, PULSEQ_MATLAB=str(pulseq), SAFE_MATLAB=str(safe), OUT_DIR=str(out_dir))
    subprocess.run(
        octave_command() + ["--no-gui", "--quiet", "--no-init-file", str(HERE / script)],
        check=True,
        env=env,
        cwd=out_dir,
    )


@dataclass
class ExampleResult:
    name: str
    doc: str
    limit: dict  # limit_check_slew
    py_wave: dict  # pypulseq_waveform
    py: dict  # pypulseq_dgdt
    py_calc_pns: tuple  # calc_pns (ok, pns_norm, pns_comp, t)
    py_report_slew: list
    py_pns_norm_old: np.ndarray | None  # calc_pns with the old-layout .asc ("epi" only)
    mat: dict  # the .mat file written by matlab_paths.m


def compute(
    out_dir: Path, pulseq: Path | None, safe: Path | None, run_matlab: bool = True
) -> tuple[dict, dict]:
    """Build and write every example, run both Octave drivers (unless run_matlab is
    False and out_dir already has their output), and compute the pypulseq paths on the
    sequences read back from the files (IN_MEMORY: on the built sequences).
    Returns ({name: ExampleResult}, the limit-case table)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    asc = out_dir / "example_hw.asc"
    write_asc(asc)
    old_asc = out_dir / "example_hw_old_layout.asc"
    write_asc(old_asc, old_layout=True)
    built = {}
    for name, build in EXAMPLES.items():
        built[name] = build()
        built[name].write(str(out_dir / f"{name}.seq"), remove_duplicates=name not in IN_MEMORY)
    (out_dir / "examples.txt").write_text("\n".join(EXAMPLES) + "\n")

    if run_matlab:
        run_octave("matlab_paths.m", out_dir, pulseq, safe)
        run_octave("matlab_limit_cases.m", out_dir, pulseq, safe)

    hw = asc_to_hw(readasc(str(asc))[0])
    results = {}
    for name, build in EXAMPLES.items():
        if name in IN_MEMORY:
            seq = built[name]
        else:
            seq = pp.Sequence(SYS)
            seq.read(str(out_dir / f"{name}.seq"))
        results[name] = ExampleResult(
            name=name,
            doc=build.__doc__,
            limit=limit_check_slew(seq),
            py_wave=pypulseq_waveform(seq),
            py=pypulseq_dgdt(seq, hw),
            py_calc_pns=pp.Sequence.calculate_pns(seq, str(asc), do_plots=False),
            py_report_slew=pypulseq_test_report_slew(pypulseq_waveform(seq)),
            py_pns_norm_old=(
                pp.Sequence.calculate_pns(seq, str(old_asc), do_plots=False)[1]
                if name == "epi"
                else None
            ),
            mat=scipy.io.loadmat(out_dir / f"{name}_matlab.mat", squeeze_me=True),
        )

    mat_cases = json.loads((out_dir / "limit_cases_matlab.json").read_text())
    py_cases = python_limit_cases()
    table = {
        name: {"doc": doc, "pypulseq": py_cases[name], "matlab": mat_cases[name]}
        for name, (doc, _) in LIMIT_CASES.items()
    }
    return results, table
