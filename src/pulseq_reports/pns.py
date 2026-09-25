"""Peripheral nerve stimulation (PNS) prediction for a Pulseq sequence with the SAFE model.

`pns_prediction` runs pypulseq's `Sequence.calculate_pns`, a port of the
safe_pns_prediction code by Szczepankiewicz and Witzel for the SAFE model of
Hebrank and Gebhardt. The model needs the scanner's gradient hardware
parameters, which Siemens keeps in the gradient system's .asc file
(MP_GPA_*.asc, or MP_GradSys_*.asc on newer software). The files are
confidential, so this library does not include any. Without them,
the prediction uses pypulseq's example hardware, which is not a real scanner.
"""

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pypulseq as pp
from pypulseq.utils.safe_pns_prediction import safe_example_hw
from pypulseq.utils.siemens.asc_to_hw import asc_to_hw
from pypulseq.utils.siemens.readasc import readasc

EXAMPLE_HARDWARE = "pypulseq example hardware (not a real scanner)"
NO_GRADIENTS = "no gradients"
# Samples within this fraction of the peak count as the peak. Identical TRs differ only by
# rounding, so the peak time is in the first of them.
PEAK_TOLERANCE = 1e-6
# A line that includes another .asc file, for example the _GSWD_SAFETY.asc file with the
# SAFE PNS parameters.
INCLUDE_LINE = re.compile(r'^\s*\$INCLUDE\s+"?([^"\s]+)"?\s*$')


@dataclass(frozen=True)
class PnsPrediction:
    reason: str | None  # why there is no prediction, or None
    hardware: str  # the hardware name in the .asc file, or EXAMPLE_HARDWARE
    asc_file: str | None  # the .asc file name, or None for the example hardware
    t_s: np.ndarray  # sample times
    norm: np.ndarray  # root-sum-of-squares of the axes; 1 is the stimulation limit
    axes: dict[str, np.ndarray] = field(default_factory=dict)  # "x", "y", "z"

    @property
    def peak(self) -> float:
        return float(self.norm.max()) if self.norm.size else 0.0

    @property
    def peak_time_s(self) -> float | None:
        """The first sample time within PEAK_TOLERANCE of the peak."""
        if not self.norm.size:
            return None
        first = np.flatnonzero(self.norm >= self.peak * (1 - PEAK_TOLERANCE))[0]
        return float(self.t_s[first])

    @property
    def axis_peaks(self) -> dict[str, float]:
        return {axis: float(values.max()) for axis, values in self.axes.items()}


def read_gradient_asc(path: str | Path) -> dict:
    """The fields of the .asc file `path`, as pypulseq's `readasc` gives them, and the fields
    of each file that a `$INCLUDE` line names. `readasc` ignores `$INCLUDE`. An included
    file is in the same directory as the file that includes it, and its fields replace
    fields with the same name."""
    path = Path(path)
    asc, _ = readasc(str(path))
    for line in path.read_text().splitlines():
        match = INCLUDE_LINE.match(line)
        if match:
            included = path.parent / match[1]
            if not included.is_file():
                raise FileNotFoundError(
                    f"{path.name} includes {match[1]}, which is not in {path.parent}"
                )
            _merge(asc, read_gradient_asc(included))
    return asc


def _merge(into: dict, fields: dict) -> None:
    for key, value in fields.items():
        if isinstance(value, dict) and isinstance(into.get(key), dict):
            _merge(into[key], value)
        else:
            into[key] = value


def hardware_name(asc: dict) -> str:
    """The component name in `asc`: `asCOMP[0].tName` in a scanner file, or `asCOMP.tName`.
    pypulseq's `asc_to_hw` reads only `asCOMP.tName` and gives "unknown" for a scanner
    file."""
    comp = asc.get("asCOMP", {})
    comp = comp.get(0, comp)
    return comp.get("tName", "unknown")


def pns_prediction(seq: pp.Sequence, asc_path: str | Path | None = None) -> PnsPrediction:
    """The SAFE PNS prediction for `seq`, with the hardware in the .asc file `asc_path`,
    or pypulseq's example hardware when it is None."""
    if asc_path is None:
        hw, hardware, asc_file = safe_example_hw(), EXAMPLE_HARDWARE, None
    else:
        asc = read_gradient_asc(asc_path)
        hw = asc_to_hw(asc)
        hardware, asc_file = hardware_name(asc), Path(asc_path).name

    if not _has_gradients(seq):
        empty = np.zeros(0)
        return PnsPrediction(NO_GRADIENTS, hardware, asc_file, empty, empty)

    # calculate_pns reads every block with get_block. With the block cache on, pypulseq
    # keeps each of them in seq.block_cache, and nothing removes them.
    use_block_cache = seq.use_block_cache
    seq.use_block_cache = False
    try:
        _, norm, components, t = seq.calculate_pns(hw, do_plots=False)
    finally:
        seq.use_block_cache = use_block_cache
    axes = {axis: components[:, i] for i, axis in enumerate("xyz")}
    return PnsPrediction(None, hardware, asc_file, t, norm, axes)


def _has_gradients(seq: pp.Sequence) -> bool:
    """Whether a block of `seq` has a gradient event, from the gradient columns (2, 3 and 4)
    of `seq.block_events`. `seq.get_gradients()` gives the same answer, but it builds the
    gradients of the whole file."""
    return any(ev[2] or ev[3] or ev[4] for ev in seq.block_events.values())


def peak_tr_window(seq: pp.Sequence, peak_time_s: float | None) -> tuple[float, float] | None:
    """Start and end, in seconds, of the TR that holds `peak_time_s`, counted from the
    sequence start in steps of the TR definition. None without a TR definition, or when
    the sequence is not longer than one TR.

    `peak_time_s` is in seconds, for example `PnsPrediction.peak_time_s`. Callers give
    this a diagram window without a dependency on the PNS card (see the PNS card's
    `peak_tr_ms`, which is this window in milliseconds)."""
    tr = seq.definitions.get("TR")
    if tr is None or peak_time_s is None:
        return None
    tr = float(np.atleast_1d(tr)[0])
    duration = seq.duration()[0]
    if tr <= 0 or duration <= tr * (1 + 1e-9):
        return None
    start = math.floor(peak_time_s / tr + 1e-9) * tr
    return start, min(start + tr, duration)
