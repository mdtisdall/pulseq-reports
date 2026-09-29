"""Peripheral nerve stimulation (PNS) prediction for a Pulseq sequence with the SAFE model.

`pns_prediction` gives the PNS summary (the peak, the peak time and the axis peaks) of a
sequence: the reason, hardware and asc-file fields, and the summary fields of
`pns_levels.pns_levels`, cached one time for each (sequence object, asc path) by
`pns_levels_for`. `pns_levels_for` is the one place that runs the SAFE model
(`pns_levels.pns_levels`, which uses the pinned pypulseq fork's chunk function), so a
page that has both the PNS summary card and the diagram's PNS lane for one sequence
computes it once (`docs/plans/diagram-lanes.md`, section 4.6).

The model needs the scanner's gradient hardware parameters, which Siemens keeps in the
gradient system's .asc file (MP_GPA_*.asc, or MP_GradSys_*.asc on newer software). The
files are confidential, so this library does not include any. Without them, the
prediction uses pypulseq's example hardware, which is not a real scanner.
"""

import math
import re
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pypulseq as pp
from pypulseq.utils.siemens.readasc import readasc

from .seq_index import sequence_index

if TYPE_CHECKING:
    from .pns_levels import PnsLevels

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
    """The PNS summary of one sequence (`pns_prediction`). Summary-only: a caller that
    wants the samples of a short sequence can call `seq.calculate_pns` directly (the
    pinned fork's memory is near the size of its result), or use `pns_levels_for` for
    the stored level (`docs/plans/diagram-lanes.md`, section 7, question 1)."""

    reason: str | None  # why there is no prediction, or None
    hardware: str  # the hardware name in the .asc file, or EXAMPLE_HARDWARE
    asc_file: str | None  # the .asc file name, or None for the example hardware
    peak: float  # the largest total (root-sum-of-squares of the axes); 1 is the limit
    peak_time_s: float | None  # the first sample time within PEAK_TOLERANCE of the peak
    axis_peaks: dict[str, float] = field(default_factory=dict)  # "x", "y", "z"


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


# One `PnsLevels` for each sequence object, with the number of blocks, the last block id
# (the rule of `seq_index.sequence_index`) and the asc path it was built from.
_LEVELS_CACHE: "weakref.WeakKeyDictionary[pp.Sequence, tuple[int, int, str | None, PnsLevels]]" = (
    weakref.WeakKeyDictionary()
)


def pns_levels_for(seq: pp.Sequence, asc_path: str | Path | None = None) -> "PnsLevels":
    """The `PnsLevels` of `seq` with the hardware of the gradient .asc file `asc_path`
    (`pns_levels.pns_levels`), or pypulseq's example hardware when it is None.

    The result is kept for the sequence object, so that the PNS summary card
    (`cards.pns.pns_card`) and the diagram's PNS lane (`cards.diagram.diagram_card`)
    compute it one time for one sequence (`docs/plans/diagram-lanes.md`, section 4.6).
    It is built again when the number of blocks or the last block id changed, for
    example after `add_block` (the rule of `seq_index.sequence_index`), or when
    `asc_path` differs from the one the kept result was built with.
    """
    # Imported here, not at module level: `pns_levels` imports this module (`from . import
    # pns`) to reach `read_gradient_asc`, `hardware_name` and the constants above, so a
    # module-level import here in the other direction would be a circular import that
    # fails depending on which module is imported first.
    from .pns_levels import pns_levels

    block_events = seq.block_events
    num_blocks = len(block_events)
    last_id = int(next(reversed(block_events))) if num_blocks else 0
    key = None if asc_path is None else str(Path(asc_path))

    kept = _LEVELS_CACHE.get(seq)
    if kept is not None and kept[0] == num_blocks and kept[1] == last_id and kept[2] == key:
        return kept[3]
    levels = pns_levels(seq, asc_path)
    _LEVELS_CACHE[seq] = (num_blocks, last_id, key, levels)
    return levels


def pns_prediction(seq: pp.Sequence, asc_path: str | Path | None = None) -> PnsPrediction:
    """The SAFE PNS summary for `seq`, with the hardware in the .asc file `asc_path`, or
    pypulseq's example hardware when it is None. Built from `pns_levels_for`, so a page
    that also draws the PNS lane of the diagram for `seq` (`cards.diagram.diagram_card`)
    does not run the SAFE model twice."""
    levels = pns_levels_for(seq, asc_path)
    return PnsPrediction(
        reason=levels.reason,
        hardware=levels.hardware,
        asc_file=levels.asc_file,
        peak=levels.peak,
        peak_time_s=levels.peak_time_s,
        axis_peaks=dict(levels.axis_peaks),
    )


def peak_tr_window(seq: pp.Sequence, peak_time_s: float | None) -> tuple[float, float] | None:
    """Start and end, in seconds, of the TR that holds `peak_time_s`, counted from the
    sequence start in steps of the TR definition. None without a TR definition, or when
    the sequence is not longer than one TR.

    `peak_time_s` is in seconds, for example `PnsPrediction.peak_time_s`. A caller adds
    this window to the diagram card's windows for a "TR with the highest PNS" button
    (`docs/plans/diagram-lanes.md`, section 4.6), without a dependency on the PNS card."""
    tr = seq.definitions.get("TR")
    if tr is None or peak_time_s is None:
        return None
    tr = float(np.atleast_1d(tr)[0])
    duration = sequence_index(seq).end_s
    if tr <= 0 or duration <= tr * (1 + 1e-9):
        return None
    start = math.floor(peak_time_s / tr + 1e-9) * tr
    return start, min(start + tr, duration)
