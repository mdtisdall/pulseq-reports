"""Sequence builders shared by the `pns_lanes` prototype scripts (task 2 of
`docs/plans/pns-lanes-prototype.md`). Not library code; not imported by `src/` or
`tests/`.

`build_seq(name)` returns a fresh `pp.Sequence` for one of:

- `"spin_echo"`, `"gre"`, `"arbitrary"`, `"empty"`: from `tests/synthetic.py`.
- `"border"`: a few blocks with extended trapezoids and an arbitrary gradient that
  are not zero at a block border (built here; pypulseq checks the continuity
  itself in `Sequence.add_block`).
- `"rep_<seconds>s"` (for example `"rep_12s"`, `"rep_60s"`): a repeating GRE-like
  sequence of about that duration, from `scripts/diagram_scale.build_repeating`
  (TR about 5.99 ms, 5 blocks).
- `"rep_370s_long"`: a repeating sequence of about 370 s with about 4e4 blocks
  (about 9.4 ms per block, about 47 ms TR). `build_repeating` has no TR argument,
  so this uses `_build_repeating_long`, a copy of it with a configurable delay
  block instead of `diagram_scale.TR_MARGIN_S`.
- `"rep_<N>blocks"` (`N` a multiple of 5, for example `"rep_1000000blocks"`):
  `build_repeating` with `N // 5` TRs.
- `"worst_<N>blocks"` (for example `"worst_100000blocks"`): `build_worst` with
  `N // 5` TRs.
- `"exvivo"`: reads `data/exvivo_gre_seg_0.seq` (git-ignored; never copied here).

Run any prototype script from the repository root with
`nix develop --command uv run python prototypes/pns_lanes/<script>.py`, which puts
the repository root on `sys.path` (as the working directory) so `import build_seqs`
works without a package.
"""

from __future__ import annotations

import importlib.util
import math
import re
import sys
from pathlib import Path

import numpy as np
import pypulseq as pp

REPO_ROOT = Path(__file__).resolve().parents[2]
EXVIVO_PATH = REPO_ROOT / "data" / "exvivo_gre_seg_0.seq"

# `tests/synthetic.py` is not a package (no `tests/__init__.py`), so it is loaded the
# way the plan text says: "sys.path.insert of the repo's tests dir".
sys.path.insert(0, str(REPO_ROOT / "tests"))
import synthetic  # noqa: E402  (after the sys.path insert)

# `scripts/diagram_scale.py` is loaded by path (the plan text's "import by path"),
# because `scripts/` is a directory of standalone scripts, not a package either.
_diagram_scale_spec = importlib.util.spec_from_file_location(
    "diagram_scale", REPO_ROOT / "scripts" / "diagram_scale.py"
)
diagram_scale = importlib.util.module_from_spec(_diagram_scale_spec)
_diagram_scale_spec.loader.exec_module(diagram_scale)

SIMPLE_BUILDERS = {
    "spin_echo": synthetic.spin_echo_sequence,
    "gre": synthetic.gre_sequence,
    "arbitrary": synthetic.arbitrary_gradient_sequence,
    "empty": synthetic.empty_sequence,
}

_REP_SECONDS_RE = re.compile(r"^rep_(\d+(?:\.\d+)?)s$")
_REP_BLOCKS_RE = re.compile(r"^rep_(\d+)blocks$")
_WORST_BLOCKS_RE = re.compile(r"^worst_(\d+)blocks$")


def _rep_used_s() -> float:
    """The duration of one TR's rf + phase-encode + readout + spoiler blocks
    (everything but the trailing delay block), the same way
    `diagram_scale.build_repeating` computes its `used`."""
    ds = diagram_scale
    rf = ds._block_pulse("excitation", math.radians(20))
    gx, adc = ds._readout()
    spoiler = pp.make_trapezoid(channel="z", area=4 / ds.WIDTH, system=ds.SYSTEM)
    pe = ds._pe_family([ds._pe_max_amplitude()])[0]
    return (
        pp.calc_duration(rf)
        + pp.calc_duration(pe)
        + pp.calc_duration(gx, adc)
        + pp.calc_duration(spoiler)
    )


def _build_repeating_long(n_trs: int, margin_s: float) -> pp.Sequence:
    """A copy of `diagram_scale.build_repeating` with `margin_s` (the trailing delay
    block) in place of its fixed `TR_MARGIN_S`, for a TR much longer than 5.99 ms.
    Reuses `diagram_scale`'s event builders so the TR is structurally identical
    (rf, phase-encode, readout, spoiler, delay), only the delay's duration differs."""
    ds = diagram_scale
    seq = pp.Sequence(ds.SYSTEM)
    rf = ds._block_pulse("excitation", math.radians(20))
    gx, adc = ds._readout()
    spoiler = pp.make_trapezoid(channel="z", area=4 / ds.WIDTH, system=ds.SYSTEM)
    pe_max = ds._pe_max_amplitude()
    pe_events = ds._pe_family(np.linspace(-pe_max, pe_max, min(ds.PE_STEPS, n_trs)))
    used = (
        pp.calc_duration(rf)
        + pp.calc_duration(pe_events[0])
        + pp.calc_duration(gx, adc)
        + pp.calc_duration(spoiler)
    )
    delay = pp.make_delay(margin_s)
    for i in range(n_trs):
        seq.add_block(rf)
        seq.add_block(pe_events[i % len(pe_events)])
        seq.add_block(gx, adc)
        seq.add_block(spoiler)
        seq.add_block(delay)
    seq.set_definition("TR", used + margin_s)
    return seq


def _rep_370s_long() -> pp.Sequence:
    """About 370 s, about 4e4 blocks (8000 TRs of 5 blocks, about 9.4 ms each, about
    47 ms TR): the margin is chosen so that 8000 TRs add up to exactly 370 s."""
    target_s = 370.0
    n_trs = 8000  # 40,000 blocks
    tr = target_s / n_trs
    margin_s = tr - _rep_used_s()
    if margin_s <= 0:
        raise ValueError(f"one TR of rep_370s_long needs {_rep_used_s()}s, more than {tr}s")
    return _build_repeating_long(n_trs, margin_s)


def _rep_seconds(seconds: float) -> pp.Sequence:
    tr = _rep_used_s() + diagram_scale.TR_MARGIN_S
    n_trs = max(1, round(seconds / tr))
    return diagram_scale.build_repeating(n_trs)


def _border_sequence() -> pp.Sequence:
    """Three blocks on the x axis, each ending or starting away from zero, so the
    gradient is not zero at either internal block border:

    1. An extended trapezoid (`make_extended_trapezoid`) that ramps up from 0 and
       holds at `amp`: ends the block at `amp`, not 0.
    2. An arbitrary gradient (`make_arbitrary_grad`) that starts at `amp` (matching
       block 1's end) and ends at `amp` too (a small wiggle in between).
    3. An extended trapezoid that starts at `amp` (matching block 2's end) and ramps
       back down to 0, so the sequence itself ends cleanly.

    `Sequence.add_block` checks the connection between consecutive gradients on the
    same channel itself (`pypulseq/Sequence/block.py`, the "PERFORM GRADIENT CHECKS"
    section): it raises if a block's first gradient sample does not match the
    previous block's last sample within the achievable slew. Passing `first=`/`last=`
    explicitly on the arbitrary gradient, and matching amplitudes at each end of the
    extended trapezoids, satisfies that check.
    """
    system = synthetic.SYSTEM
    dt = system.grad_raster_time
    amp = 0.3 * system.max_grad  # Hz/m; well inside system.max_grad
    # A comfortable (80% of the limit) slew-rate-achievable ramp, rounded up to
    # a whole number of raster steps.
    rise_time = math.ceil(amp / (0.8 * system.max_slew) / dt) * dt

    seq = pp.Sequence(system)

    g1 = pp.make_extended_trapezoid(
        channel="x",
        times=np.array([0.0, rise_time, rise_time + 5 * dt]),
        amplitudes=np.array([0.0, amp, amp]),
        system=system,
    )
    seq.add_block(g1)

    n2 = 20
    t2 = (np.arange(n2) + 0.5) * dt
    waveform2 = amp + 0.05 * amp * np.sin(2 * np.pi * t2 / (n2 * dt))
    g2 = pp.make_arbitrary_grad(
        channel="x", waveform=waveform2, first=amp, last=amp, system=system
    )
    seq.add_block(g2)

    g3 = pp.make_extended_trapezoid(
        channel="x",
        times=np.array([0.0, 5 * dt, 5 * dt + rise_time]),
        amplitudes=np.array([amp, amp, 0.0]),
        system=system,
    )
    seq.add_block(g3)

    return seq


def build_seq(name: str) -> pp.Sequence:
    """Return a fresh `pp.Sequence` for `name`. See the module docstring for the
    recognized names."""
    if name in SIMPLE_BUILDERS:
        return SIMPLE_BUILDERS[name]()
    if name == "border":
        return _border_sequence()
    if name == "exvivo":
        if not EXVIVO_PATH.is_file():
            raise FileNotFoundError(f"{EXVIVO_PATH} is missing (git-ignored data file)")
        seq = pp.Sequence()
        seq.read(str(EXVIVO_PATH))  # mutates seq in place; returns None
        return seq
    if name == "rep_370s_long":
        return _rep_370s_long()

    match = _REP_SECONDS_RE.match(name)
    if match:
        return _rep_seconds(float(match[1]))

    match = _REP_BLOCKS_RE.match(name)
    if match:
        blocks = int(match[1])
        if blocks % diagram_scale.TR_BLOCKS != 0:
            raise ValueError(f"{name}: blocks must be a multiple of {diagram_scale.TR_BLOCKS}")
        return diagram_scale.build_repeating(blocks // diagram_scale.TR_BLOCKS)

    match = _WORST_BLOCKS_RE.match(name)
    if match:
        blocks = int(match[1])
        if blocks % diagram_scale.TR_BLOCKS != 0:
            raise ValueError(f"{name}: blocks must be a multiple of {diagram_scale.TR_BLOCKS}")
        return diagram_scale.build_worst(blocks // diagram_scale.TR_BLOCKS)

    raise ValueError(f"unknown sequence name: {name!r}")
