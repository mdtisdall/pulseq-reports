"""Writes the external reference fixtures of `tests/test_rf_references.py` (phase 2b of
`docs/plans/rf-profiles.md`): the RF pulse profiles that MATLAB Pulseq's `mr.simRf` and
sigpy compute for the cases of task 2b.2, one JSON file for each case in
`tests/fixtures/rf_references/`.

Not part of `scripts/check` or CI: it needs GNU Octave, MATLAB Pulseq and sigpy, which
are not dependencies of this project. The `rf-references` shell of `flake.nix` has
Octave and MATLAB Pulseq (one commit, pinned by its hash, in `MATLAB_PULSEQ`); sigpy runs
in its own locked environment (`scripts/rf_references_sigpy.py` and its `.lock` file).
From the repository root:

    nix develop .#rf-references --command uv run python scripts/rf_references.py [--only NAME ...]

For each case, pypulseq builds a sequence with one block (the RF pulse and the gradients
of its block) and writes it to a `.seq` file. Then:

- MATLAB Pulseq reads the `.seq` file and runs `mr.simRf` on the RF pulse
  (`scripts/rf_references_simrf.m`): the frequency axis, Mz, |Mxy| and the refocusing
  efficiency, and the RF that `mr.simRf` simulates after its own resampling.
- sigpy's `abrm_nd` runs on the pulse as the reference of this project plays it
  (`rf_profiles.block_pulse` of the same `.seq` file: the hold samples with their
  offsets, and the mean gradient of each hold interval), at the points of a grid.
- For the SLR case, sigpy designs the pulse first (`dzrf`). pypulseq stores RF shapes
  with about 7 significant digits in a `.seq` file, so `abrm` (sigpy's 1D simulator of
  SLR design) gives the profile of the design as the `.seq` file stores it: one sample of
  each held group of the pulse that `block_pulse` reads.

Each fixture records its provenance (the tools, their versions or commit, the commands),
the inputs (the `.seq` file, gzip and base64, and the system values that a `.seq` file
does not store), a fingerprint of the pulse as `block_pulse` reads it, and the outputs.
"""

import argparse
import base64
import dataclasses
import gzip
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pypulseq as pp

from pulseq_reports import rf_profiles as rp
from pulseq_reports.rf_profiles import ProfileAxis, ProfileSpec

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "rf_references"
SIMRF_SCRIPT = ROOT / "scripts" / "rf_references_simrf.m"
SIGPY_SCRIPT = ROOT / "scripts" / "rf_references_sigpy.py"

# B0 is not the pypulseq default (1.5 T), so a ppm offset depends on reading it right.
SYSTEM = pp.Opts(
    max_grad=30,
    grad_unit="mT/m",
    max_slew=150,
    slew_unit="T/m/s",
    rf_dead_time=100e-6,
    rf_ringdown_time=30e-6,
    B0=2.89,
)
THICKNESS = 5e-3  # m
MATLAB_POINTS = 601  # at most this many points of the mr.simRf frequency axis are kept
SLR_DWELL = 10e-6  # s: the time of one sample of the SLR design
SLR_DESIGN = {"n": 256, "tb": 4, "ptype": "ex", "ftype": "ls", "d1": 0.01, "d2": 0.01}

SIMRF_COMMAND = "octave --no-gui --quiet --norc scripts/rf_references_simrf.m"
SIGPY_COMMAND = "uv run --locked --script scripts/rf_references_sigpy.py IN.json OUT.json"


# ---- The cases (task 2b.2 of the plan) ----


def _new() -> pp.Sequence:
    seq = pp.Sequence(SYSTEM)
    seq.set_definition("SliceThickness", THICKNESS)
    return seq


def _sinc(use: str, flip: float, **kwargs):
    return pp.make_sinc_pulse(
        flip_angle=flip,
        duration=3e-3,
        slice_thickness=THICKNESS,
        time_bw_product=4,
        system=SYSTEM,
        return_gz=True,
        delay=SYSTEM.rf_dead_time,
        use=use,
        **kwargs,
    )


def _sinc_excitation(_: dict) -> pp.Sequence:
    rf, gz, _ = _sinc("excitation", math.pi / 2)
    seq = _new()
    seq.add_block(rf, gz)
    return seq


def _sinc_refocusing(_: dict) -> pp.Sequence:
    rf, gz, _ = _sinc("refocusing", math.pi, phase_offset=math.pi / 2)
    seq = _new()
    seq.add_block(rf, gz)
    return seq


def _block_pulse(_: dict) -> pp.Sequence:
    rf = pp.make_block_pulse(
        flip_angle=math.radians(20),
        duration=100e-6,
        delay=SYSTEM.rf_dead_time,
        system=SYSTEM,
        use="excitation",
    )
    seq = _new()
    seq.add_block(rf)
    return seq


def _sinc_offsets(_: dict) -> pp.Sequence:
    rf, gz, _ = _sinc("excitation", math.pi / 2, freq_offset=500.0, phase_offset=0.7)
    seq = _new()
    seq.add_block(rf, gz)
    return seq


def _fat_saturation(_: dict) -> pp.Sequence:
    ppm = -3.45
    rf = pp.make_gauss_pulse(
        flip_angle=math.radians(110),
        duration=8e-3,
        bandwidth=abs(ppm * 1e-6 * SYSTEM.gamma * SYSTEM.B0),
        freq_ppm=ppm,
        delay=SYSTEM.rf_dead_time,
        system=SYSTEM,
        use="saturation",
    )
    seq = _new()
    seq.add_block(rf)
    return seq


def _hyperbolic_secant(_: dict) -> pp.Sequence:
    # pypulseq's defaults: beta 800 rad/s, mu 4.9, 10 ms, adiabaticity 4.
    rf = pp.make_adiabatic_pulse(
        "hypsec", delay=SYSTEM.rf_dead_time, system=SYSTEM, use="inversion"
    )
    seq = _new()
    seq.add_block(rf)
    return seq


def _slr_excitation(design: dict) -> pp.Sequence:
    """The sigpy SLR design, each sample held for SLR_DWELL on the RF raster, so that the
    pulse as played is the design. (With a dwell of SLR_DWELL instead, the RF event would
    have a time shape, and pypulseq and MATLAB Pulseq both read its shape duration as the
    time of its last sample.)"""
    rf = np.asarray(design["rf_re"]) + 1j * np.asarray(design["rf_im"])
    repeat = round(SLR_DWELL / SYSTEM.rf_raster_time)
    signal = np.repeat(rf / (2 * np.pi * SLR_DWELL), repeat)
    pulse = pp.make_arbitrary_rf(
        signal,
        flip_angle=math.pi / 2,
        no_signal_scaling=True,
        delay=SYSTEM.rf_dead_time,
        system=SYSTEM,
        use="excitation",
    )
    seq = _new()
    seq.add_block(pulse)
    return seq


def _sinc_on_ramps(_: dict) -> pp.Sequence:
    """A 3 ms sinc that plays across both ramps of its slice-select gradient."""
    rf, _, _ = _sinc("excitation", math.pi / 2)
    amplitude = (4 / 3e-3) / THICKNESS  # Hz/m: the bandwidth over the thickness
    gz = pp.make_trapezoid(
        "z",
        amplitude=amplitude,
        rise_time=0.6e-3,
        flat_time=1.8e-3,
        fall_time=0.6e-3,
        system=SYSTEM,
    )
    seq = _new()
    seq.add_block(rf, gz)
    return seq


def _sinc_oblique(_: dict) -> pp.Sequence:
    """The sinc of the first case, with its slice-select gradient on x and y at 30°."""
    rf, gz, _ = _sinc("excitation", math.pi / 2)
    gx = pp.scale_grad(gz, math.cos(math.radians(30)))
    gx.channel = "x"
    gy = pp.scale_grad(gz, math.sin(math.radians(30)))
    gy.channel = "y"
    seq = _new()
    seq.add_block(rf, gx, gy)
    return seq


def _turning_gradient(_: dict) -> pp.Sequence:
    """A 1 ms sinc with a gradient on x and y whose direction turns twice (a short
    spiral in and out): a pulse of kind "changing"."""
    rf, _, _ = pp.make_sinc_pulse(
        flip_angle=math.radians(30),
        duration=1e-3,
        slice_thickness=THICKNESS,
        time_bw_product=4,
        system=SYSTEM,
        return_gz=True,
        delay=SYSTEM.rf_dead_time,
        use="excitation",
    )
    duration = 1.2e-3
    n = round(duration / SYSTEM.grad_raster_time)
    t = (np.arange(n) + 0.5) * SYSTEM.grad_raster_time
    envelope = 2e5 * np.sin(np.pi * t / duration)  # Hz/m
    angle = 2 * 2 * np.pi * t / duration
    gx = pp.make_arbitrary_grad("x", envelope * np.cos(angle), first=0, last=0, system=SYSTEM)
    gy = pp.make_arbitrary_grad("y", envelope * np.sin(angle), first=0, last=0, system=SYSTEM)
    seq = _new()
    seq.add_block(rf, gx, gy)
    return seq


def _axis(kind: str, half: float, n: int) -> ProfileAxis:
    return ProfileAxis(kind, -half, half, n)


@dataclasses.dataclass(frozen=True)
class Case:
    name: str
    description: str
    build: Callable[[dict], pp.Sequence]
    matlab: bool
    sigpy_spec: ProfileSpec | None = None  # the grid of abrm_nd, if sigpy checks this case
    slr: bool = False


CASES = (
    Case(
        "sinc_excitation",
        "pypulseq sinc excitation, 90°, time-bandwidth product 4, 3 ms, with its "
        "slice-select gradient on z",
        _sinc_excitation,
        matlab=True,
        sigpy_spec=ProfileSpec((_axis("z", 10e-3, 201),)),
    ),
    Case(
        "sinc_refocusing",
        "pypulseq sinc refocusing pulse, 180°, time-bandwidth product 4, 3 ms, phase "
        "offset π/2, with its slice-select gradient on z",
        _sinc_refocusing,
        matlab=True,
    ),
    Case("block_pulse", "pypulseq block pulse, 20°, 100 µs", _block_pulse, matlab=True),
    Case(
        "sinc_offsets",
        "pypulseq sinc excitation, 90°, time-bandwidth product 4, 3 ms, with a frequency "
        "offset of 500 Hz and a phase offset of 0.7 rad, with its slice-select gradient",
        _sinc_offsets,
        matlab=True,
    ),
    Case(
        "fat_saturation",
        "pypulseq Gaussian fat saturation pulse, 110°, 8 ms, at −3.45 ppm (B0 2.89 T)",
        _fat_saturation,
        matlab=True,
    ),
    Case(
        "hyperbolic_secant",
        "pypulseq hyperbolic secant adiabatic inversion (make_adiabatic_pulse 'hypsec', "
        "its defaults: beta 800 rad/s, mu 4.9, 10 ms, adiabaticity 4)",
        _hyperbolic_secant,
        matlab=True,
    ),
    Case(
        "slr_excitation",
        "sigpy SLR 90° excitation (dzrf: 256 samples, time-bandwidth product 4, ptype "
        "'ex', ftype 'ls', d1 = d2 = 0.01), each sample held 10 µs on the RF raster",
        _slr_excitation,
        matlab=True,
        slr=True,
    ),
    Case(
        "sinc_on_ramps",
        "pypulseq sinc excitation, 90°, 3 ms, that plays across both ramps of its "
        "slice-select trapezoid on z (0.6 ms ramps, 1.8 ms flat top)",
        _sinc_on_ramps,
        matlab=False,
        sigpy_spec=ProfileSpec((_axis("z", 10e-3, 201),)),
    ),
    Case(
        "sinc_oblique",
        "the sinc excitation of 'sinc_excitation', with its slice-select gradient on x "
        "and y at 30° from x, on an x-y grid",
        _sinc_oblique,
        matlab=False,
        sigpy_spec=ProfileSpec((_axis("x", 10e-3, 31), _axis("y", 10e-3, 31))),
    ),
    Case(
        "turning_gradient",
        "a 30° sinc, 1 ms, with gradients on x and y whose direction turns twice during "
        "the RF (1.2 ms, peak 2e5 Hz/m), on an x-y grid",
        _turning_gradient,
        matlab=False,
        sigpy_spec=ProfileSpec((_axis("x", 0.1, 31), _axis("y", 0.1, 31))),
    ),
)


# ---- The tools ----


def _run(command: list[str], env: dict | None = None) -> None:
    result = subprocess.run(command, env=env, capture_output=True, text=True, cwd=ROOT, check=False)
    if result.returncode != 0:
        sys.exit(f"rf_references: {' '.join(command)} failed:\n{result.stdout}\n{result.stderr}")


def _simrf(seq_path: Path, work: Path) -> dict:
    out = work / "simrf.json"
    env = dict(
        os.environ,
        SEQ=str(seq_path),
        OUT=str(out),
        GAMMA=repr(float(SYSTEM.gamma)),
        B0=repr(float(SYSTEM.B0)),
    )
    _run(["octave", "--no-gui", "--quiet", "--norc", str(SIMRF_SCRIPT)], env)
    return json.loads(out.read_text())


def _sigpy(jobs: list[dict], work: Path) -> dict:
    source, target = work / "sigpy_in.json", work / "sigpy_out.json"
    source.write_text(json.dumps({"jobs": jobs}))
    _run(["uv", "run", "--locked", "--script", str(SIGPY_SCRIPT), str(source), str(target)])
    return json.loads(target.read_text())


def _spec_json(spec: ProfileSpec) -> dict:
    return {
        "axes": [dataclasses.asdict(axis) for axis in spec.axes],
        "at": dict(spec.at),
    }


def _positions(pulse: rp.BlockPulse, spec: ProfileSpec) -> np.ndarray:
    """The (m, 3) points of `spec`, as `rf_profiles.simulate` builds them (C order)."""
    _, _, count, values = rp._grid_values(spec)
    return rp._positions(pulse, values, count)


def _fingerprint(pulse: rp.BlockPulse) -> dict:
    """A few numbers of the pulse as `block_pulse` reads it: a test compares them, to
    tell a change of the input (the reader, the hold rule, the interval gradients) from a
    change of the simulator."""
    return {
        "num_samples": int(pulse.signal_hz.size),
        "dt_s": pulse.dt_s,
        "signal_sum_re": float(pulse.signal_hz.real.sum()),
        "signal_sum_im": float(pulse.signal_hz.imag.sum()),
        "signal_abs_max": float(np.abs(pulse.signal_hz).max()),
        "grad_sum": [float(v) for v in pulse.grad_hz_per_m.sum(axis=0)],
        "grad_abs_max": [float(v) for v in np.abs(pulse.grad_hz_per_m).max(axis=0)],
        "gradient_kind": pulse.gradient_kind,
    }


def _matlab_entry(result: dict) -> dict:
    f = np.asarray(result["f_hz"])
    stride = max(1, math.ceil(f.size / MATLAB_POINTS))
    keep = slice(None, None, stride)
    mxy = np.asarray(result["mxy_re"]) + 1j * np.asarray(result["mxy_im"])
    ref_eff = np.asarray(result["ref_eff_re"]) + 1j * np.asarray(result["ref_eff_im"])
    return {
        "tool": "MATLAB Pulseq mr.simRf, in GNU Octave",
        "matlab_pulseq": "github.com/pulseq/pulseq",
        "matlab_pulseq_commit": os.environ["MATLAB_PULSEQ_REV"],
        "octave": result["octave"],
        "command": SIMRF_COMMAND,
        "num_f": int(f.size),
        "stride": stride,
        "dt_s": result["dt"],
        "f_hz": f[keep].tolist(),
        "mz": np.asarray(result["mz"])[keep].tolist(),
        "mxy_abs": np.abs(mxy)[keep].tolist(),
        "ref_eff_abs": np.abs(ref_eff)[keep].tolist(),
        "resampled_re": result["resampled_re"],
        "resampled_im": result["resampled_im"],
    }


def _abrm_job(pulse: rp.BlockPulse, spec: ProfileSpec) -> dict:
    two_pi_dt = 2 * np.pi * pulse.dt_s
    rf = two_pi_dt * pulse.signal_hz
    return {
        "kind": "abrm_nd",
        "rf_re": rf.real.tolist(),
        "rf_im": rf.imag.tolist(),
        "g": (two_pi_dt * pulse.grad_hz_per_m).tolist(),
        "x": _positions(pulse, spec).tolist(),
    }


def _ab(result: dict) -> dict:
    return {key: result[key] for key in ("a_re", "a_im", "b_re", "b_im")}


def _slr_spec() -> ProfileSpec:
    return ProfileSpec((ProfileAxis("df", -3000.0, 3000.0, 601),))


def _slr_design(work: Path) -> tuple[dict, dict]:
    """The SLR design and its ripples and band edges, from sigpy."""
    out = _sigpy([{"kind": "slr", **SLR_DESIGN}], work)
    return out["results"][0], out["versions"]


def _slr_entry(design: dict, versions: dict, pulse: rp.BlockPulse, work: Path) -> dict:
    """The design, and sigpy's `abrm` of the design as the `.seq` file stores it, at
    x = f * duration (cycles per pulse) for the frequencies f of `_slr_spec`."""
    duration = SLR_DESIGN["n"] * SLR_DWELL
    repeat = round(SLR_DWELL / pulse.dt_s)
    stored = 2 * np.pi * SLR_DWELL * pulse.signal_hz[::repeat]  # rad for each design sample
    designed = np.asarray(design["rf_re"]) + 1j * np.asarray(design["rf_im"])
    axis = _slr_spec().axes[0]
    x = np.linspace(axis.lo, axis.hi, axis.n) * duration
    job = {"kind": "abrm", "rf_re": stored.real.tolist(), "rf_im": stored.imag.tolist()}
    result = _sigpy([{**job, "x": x.tolist()}], work)["results"][0]
    return {
        "tool": "sigpy.mri.rf.slr.dzrf (the design) and sigpy.mri.rf.sim.abrm (the profile "
        "of the design as the .seq file stores it, at x = f * duration, cycles per pulse)",
        "versions": versions,
        "command": SIGPY_COMMAND,
        "design": {**SLR_DESIGN, "dwell_s": SLR_DWELL, "duration_s": duration},
        "beta_d1": design["beta_d1"],
        "beta_d2": design["beta_d2"],
        "w": design["w"],
        "pass_edge_hz": design["pass_edge_cycles"] / duration,
        "stop_edge_hz": design["stop_edge_cycles"] / duration,
        "rf_re": design["rf_re"],
        "rf_im": design["rf_im"],
        "stored_rf_re": stored.real.tolist(),
        "stored_rf_im": stored.imag.tolist(),
        "stored_max_difference": float(np.abs(stored - designed).max() / np.abs(designed).max()),
        "spec": _spec_json(_slr_spec()),
        **_ab(result),
    }


def _write_case(case: Case, work: Path) -> Path:
    design, slr_versions = _slr_design(work) if case.slr else ({}, {})
    seq = case.build(design)
    seq_path = work / f"{case.name}.seq"
    seq.write(str(seq_path))

    # The pulse as the reference of this project reads the same file.
    read = pp.Sequence(SYSTEM)
    read.read(str(seq_path))
    pulse = rp.block_pulse(read, 0, float(SYSTEM.B0), float(SYSTEM.gamma))

    fixture: dict = {
        "case": case.name,
        "description": case.description,
        "generated_by": "scripts/rf_references.py",
        "pypulseq": pp.__version__,
        "numpy": np.__version__,
        "system": {
            "B0": float(SYSTEM.B0),
            "gamma": float(SYSTEM.gamma),
            "rf_raster_time": float(SYSTEM.rf_raster_time),
            "grad_raster_time": float(SYSTEM.grad_raster_time),
            "adc_raster_time": float(SYSTEM.adc_raster_time),
            "block_duration_raster": float(SYSTEM.block_duration_raster),
        },
        "seq_gzip_base64": base64.b64encode(
            gzip.compress(seq_path.read_bytes(), compresslevel=9, mtime=0)
        ).decode("ascii"),
        "block": 0,
        "pulse": _fingerprint(pulse),
    }
    if case.matlab:
        fixture["matlab"] = _matlab_entry(_simrf(seq_path, work))
    if case.sigpy_spec is not None:
        out = _sigpy([_abrm_job(pulse, case.sigpy_spec)], work)
        fixture["sigpy"] = {
            "tool": "sigpy.mri.rf.sim.abrm_nd",
            "versions": out["versions"],
            "command": SIGPY_COMMAND,
            "inputs": "the hold samples and interval gradients of rf_profiles.block_pulse, "
            "times 2 pi dt; the points of 'spec' as rf_profiles.simulate builds them",
            "spec": _spec_json(case.sigpy_spec),
            **_ab(out["results"][0]),
        }
    if case.slr:
        fixture["slr"] = _slr_entry(design, slr_versions, pulse, work)
    target = FIXTURES / f"{case.name}.json"
    target.write_text(json.dumps(fixture, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="+", metavar="NAME", help="write only these cases")
    args = parser.parse_args()
    names = [case.name for case in CASES]
    for name in args.only or ():
        if name not in names:
            parser.error(f"unknown case {name!r}: one of {names}")
    if shutil.which("octave") is None or "MATLAB_PULSEQ" not in os.environ:
        sys.exit(
            "rf_references: run it in the rf-references shell: "
            "nix develop .#rf-references --command uv run python scripts/rf_references.py"
        )
    FIXTURES.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        for case in CASES:
            if args.only and case.name not in args.only:
                continue
            path = _write_case(case, Path(folder))
            print(f"{case.name}: {path.relative_to(ROOT)} ({path.stat().st_size / 1e3:.0f} KB)")


if __name__ == "__main__":
    main()
