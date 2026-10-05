"""The golden test of task 4.5 of `docs/plans/diagram-lanes.md`, for the PNS entries of the
targets (phase 7 of `docs/plans/pulseq-checks-implementation.md`): the browser module
`PnsLanes` (`src/pulseq_reports/assets/pns_lanes.js`) must give the same PNS total, at
the same sample times, as the Python pipeline of `pns_levels.pns_levels`, in percent of the
threshold of the target, to a relative 1e-12 of the peak (plan section 3.5, item 1); its
stored level must bound every JS exact sample of its own bin (plan section 4.2); and each
pyramid level of `PnsLanes.levels` must be the minimum/maximum of the 4 bins of the level
below it (plan section 4.5's "pyramid").

`_run_golden` runs the checks of one target on one sequence (`run_checks`, the analysis
`pns.safe.levels`), makes the diagram data of the real card (`diagram_card` with the
target and the matrix), and writes its tables and its first `pns` entry to a JSON file. It
runs `tests/js/golden_pns_lanes.js` with Node on it, and reads back the JSON result:
`PnsLanes.decode` (with `SeqLanes.GRAD_HZ_PER_VALUE`), one `exactView` call for the whole
file (forced to the "samples" kind by a bin count far larger than the sample count, so every
sample is returned, never a minimum/maximum reduction), those totals as percent
(`PnsLanes.percent` of the `threshold` of the entry), and the decoded pyramid
(`model.levels`).

The Python reference (`_python_reference_totals`) is the same pipeline
`pns_levels.pns_levels` itself runs (its own docstring, items 1 to 3), but built
independently in this file, in one call instead of `pns_levels`'s chunks:
`GradientSampler.block_samples` of gx, gy and gz for the whole file, in Hz/m (no gamma),
through pypulseq's `_safe_gwf_to_pns_chunk` (a single chunk, `state=None`) with the SAFE
parameters of the target, scaled by 0.01 and combined as `sqrt(x^2 + y^2 + z^2)`: totals in
Hz/T. The pinned fork's chunk function gives bit-identical results for any chunk size
(lean on pypulseq, decision 6: not tested here), so this file also asserts
`pns_levels(seq).peak_hz_per_t == totals.max()` exactly, as a check that this file's
one-call reference really is the same computation as `pns_levels`'s chunked one, not a
second, independent PNS implementation. The reference in percent is
`100 * total / threshold`, with `threshold = abs(gamma)` of the target, written here from the
gamma of the profile and not read from the entry.

The sequences (task 4.5, item 1): the three synthetic sequences of `tests/synthetic.py`
that have a gradient event (`pns_levels` has no bins to compare for the empty sequence);
a "border" sequence, whose gradient is not zero at the block junction
(`synthetic.border_sequence`); and a repeating sequence of
more than `3 * PnsLanes.GROUP_BLOCKS` (192) blocks, so the golden test crosses more than
3 of the JavaScript block map's checkpoint groups. Each runs for the proton target
(`tests/profiles/example_a.toml`), and two run for the target with a negative gamma
(`tests/profiles/example_c.toml`), whose threshold is the magnitude of its gamma. The case
with the gamma of the sequence (sodium) of version 4 is gone: the model runs on the samples
in Hz/m, so the gamma of the sequence does not enter, and the case would be the proton case.
"""

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pypulseq as pp
import pytest
from pulseq_analysis.pns_levels import pns_levels
from pulseq_analysis.sampling import GradientSampler
from pulseq_analysis.seq_index import sequence_index
from pulseq_checks import read_profile, run_checks
from pulseq_checks.safe_model import hw_from_dict
from pypulseq.utils.safe_pns_prediction import _safe_gwf_to_pns_chunk
from synthetic import (
    arbitrary_gradient_sequence,
    border_sequence,
    gre_sequence,
    spin_echo_sequence,
)

from pulseq_reports.cards.diagram import diagram_card
from pulseq_reports.targets import report_targets
from pulseq_reports.waveforms import full_window

_GOLDEN_SCRIPT = Path(__file__).parent / "js" / "golden_pns_lanes.js"
_PROFILES = Path(__file__).parent / "profiles"
PROTON = read_profile(_PROFILES / "example_a.toml")
NEGATIVE_GAMMA = read_profile(_PROFILES / "example_c.toml")

# `PnsLanes.GROUP_BLOCKS` (assets/pns_lanes.js): the block count between two
# checkpoints of the JavaScript block map. Not imported (this file has no Node
# dependency at collection time); the repeating sequence below is built to exceed
# `3 * GROUP_BLOCKS` blocks regardless.
GROUP_BLOCKS = 64


# ---- The sequences -----------------------------------------------------------------


def _repeating_sequence() -> pp.Sequence:
    """A gradient-echo sequence with more than `3 * GROUP_BLOCKS` (192) blocks (task
    4.5, item 1): 45 TRs of `gre_sequence`'s 5 blocks each (RF, phase encode, readout
    with ADC, spoiler, TR-padding delay) is 225 blocks."""
    return gre_sequence(num_trs=45)


_CASES = {
    "spin_echo": (spin_echo_sequence, PROTON),
    "gre_default": (gre_sequence, PROTON),
    "arbitrary_gradient": (arbitrary_gradient_sequence, PROTON),
    "border": (border_sequence, PROTON),
    "repeating_more_than_3_checkpoint_groups": (_repeating_sequence, PROTON),
    "spin_echo_negative_gamma": (spin_echo_sequence, NEGATIVE_GAMMA),
    "gre_default_negative_gamma": (gre_sequence, NEGATIVE_GAMMA),
}


# ---- The Python reference (independent of pns_levels's own chunking) ---------------


def _python_reference_totals(seq: pp.Sequence, hw) -> np.ndarray:
    """The whole file's per-sample PNS total (float64, Hz/T), the same pipeline
    `pns_levels.pns_levels` runs, but in a single call instead of `pns_levels`'s chunks:
    `GradientSampler.block_samples` of gx, gy and gz for every block, in Hz/m (not divided
    by a gamma), through `_safe_gwf_to_pns_chunk` (`state=None`, the whole file as one chunk,
    the SAFE hardware `hw`), scaled by 0.01 and combined as `sqrt(x^2 + y^2 + z^2)`, with
    the same numpy operations `calc_pns` uses."""
    dt = seq.grad_raster_time
    index = sequence_index(seq)
    sampler = GradientSampler(seq, index)
    n = index.num_blocks
    gx = sampler.block_samples("gx", 0, n, dt)
    gy = sampler.block_samples("gy", 0, n, dt)
    gz = sampler.block_samples("gz", 0, n, dt)
    gwf = np.stack([gx, gy, gz], axis=1)
    percent, _ = _safe_gwf_to_pns_chunk(gwf, dt, hw, None)
    axis_frac = 0.01 * percent
    return np.sqrt((axis_frac**2).sum(axis=1))


# ---- Running the Node half -----------------------------------------------------


def _run_golden(seq: pp.Sequence, profile, tmp_path: Path):
    """Runs the checks of `profile` on `seq` (the analysis `pns.safe.levels`), writes the
    tables and the first `pns` entry of the data of the real diagram card (made with the
    target and the matrix) to a JSON file in `tmp_path`, runs `golden_pns_lanes.js` on it with
    Node, and returns `(json.loads(OUT.json), the entry)`.

    Fails the test, with a clear message, when `node` is not on `PATH`: the plan
    requires this (both devShells have Node), not a silent skip.
    """
    if shutil.which("node") is None:
        pytest.fail(
            "node is required to run tests/js/golden_pns_lanes.js (the golden test "
            "of PnsLanes against the Python pns_levels pipeline), but it was not "
            "found on PATH"
        )
    matrix = run_checks(seq, [profile], select=[], analyses=["pns.safe.levels"])
    card = diagram_card(
        seq,
        [full_window(seq)],
        pns_lane=True,
        targets=report_targets([profile]),
        check_results=matrix,
    )
    file = card.data["file"]
    (entry,) = file["pns"]
    payload = {"tables": file["tables"], "pns": entry}
    in_path = tmp_path / "in.json"
    out_path = tmp_path / "out.json"
    in_path.write_text(json.dumps(payload))
    subprocess.run(["node", str(_GOLDEN_SCRIPT), str(in_path), str(out_path)], check=True)
    return json.loads(out_path.read_text()), entry


# ---- The test ------------------------------------------------------------------


@pytest.mark.parametrize(("builder", "profile"), _CASES.values(), ids=_CASES.keys())
def test_pns_lanes_exact_view_and_levels_match_the_python_pipeline(builder, profile, tmp_path):
    """`PnsLanes.decode` and `exactView`, run through Node on one sequence's real
    diagram tables and `pns` entry, give the same whole-file PNS total in percent
    (`100 * total / threshold`, `threshold = abs(gamma)` of the target), at the same
    sample times, as the Python `pns_levels` pipeline (`_python_reference_totals`), within a
    relative 1e-12 of the peak (plan section 3.5, item 1); the stored level (the float32
    `level_min_hz_per_t`/`level_max_hz_per_t` of the matrix, as percent) bounds every one of
    those JS exact samples in its own bin; and each level of the decoded pyramid
    (`PnsLanes.levels`) is exactly the minimum/maximum of the 4 bins of the level below it.
    """
    seq = builder()
    safe = profile.models["pns.safe"]
    hw = hw_from_dict(safe)
    threshold = abs(profile.make_opts().gamma)
    ref_totals = _python_reference_totals(seq, hw)
    levels = pns_levels(seq, hardware=(hw, safe["name"]))

    output, entry = _run_golden(seq, profile, tmp_path)

    assert entry["threshold"] == threshold
    # Both pipelines run on the samples in Hz/m with no division by a gamma, so the chunked
    # peak of pns_levels is the maximum of the one-call reference exactly.
    assert levels.peak_hz_per_t == ref_totals.max(), (
        "pns_levels's chunked peak does not equal the one-call reference's max: the fork's "
        "chunk function should not depend on the chunk size"
    )
    assert entry["summary"]["peak"] == levels.peak_hz_per_t
    assert output["onRaster"] is True, "sequence is not on the gradient raster"
    assert output["numSamples"] == levels.num_samples == ref_totals.shape[0]

    dt = levels.dt_s
    num_samples = levels.num_samples
    ref_percent = 100 * ref_totals / threshold
    peak = ref_percent.max() or 1.0  # an all-zero file's tolerance would else be zero itself

    t = np.asarray(output["t"], dtype=np.float64)
    percent = np.asarray(output["percent"], dtype=np.float64)
    assert t.shape == (num_samples,)
    assert percent.shape == (num_samples,)

    expected_t = (np.arange(num_samples, dtype=np.float64) + 0.5) * dt
    np.testing.assert_array_equal(
        t, expected_t, err_msg="JS sample times do not exactly equal (k + 0.5) * dt"
    )

    diff = np.abs(percent - ref_percent)
    max_diff = float(diff.max()) if diff.size else 0.0
    tol = 1e-12 * peak
    assert max_diff <= tol, (
        f"JS exact percent differs from the Python reference by {max_diff!r}, "
        f"tolerance {tol!r} (1e-12 of the peak {peak!r})"
    )

    # The stored level bounds every JS exact sample of its own bin (plan section 4.2):
    # level_min[i] <= min of the JS samples of bin i, level_max[i] >= their max, allowing the
    # same relative 1e-12 slack as the values check above (the two come from different code
    # paths -- Python's chunked SAFE filter versus the JavaScript block maps -- so they can
    # differ by that much). The level reaches the browser unchanged (float32, Hz/T) and
    # `lanesFor` divides it in float64, so the bound needs no float32 spacing.
    stored = output["levels"][0]
    np.testing.assert_array_equal(stored["min"], levels.level_min_hz_per_t)
    np.testing.assert_array_equal(stored["max"], levels.level_max_hz_per_t)
    level_min = 100 * np.asarray(stored["min"], dtype=np.float64) / threshold
    level_max = 100 * np.asarray(stored["max"], dtype=np.float64) / threshold
    bin_samples = levels.bin_samples
    assert stored["binSamples"] == bin_samples == entry["binSamples"]
    slack = 1e-12 * peak
    for i in range(len(level_min)):
        s0 = i * bin_samples
        s1 = min(s0 + bin_samples, num_samples)
        segment = percent[s0:s1]
        js_min = float(segment.min())
        js_max = float(segment.max())
        assert float(level_min[i]) <= js_min + slack, (
            f"bin {i}: stored level_min {level_min[i]!r} > JS min {js_min!r} + slack"
        )
        assert float(level_max[i]) >= js_max - slack, (
            f"bin {i}: stored level_max {level_max[i]!r} < JS max {js_max!r} - slack"
        )

    # The pyramid: level L + 1 is exactly the minimum/maximum of up to 4 bins of
    # level L (no rounding: a min/max reduction of already-float32 values).
    js_levels = output["levels"]
    for lvl in range(1, len(js_levels)):
        prev_min, prev_max = js_levels[lvl - 1]["min"], js_levels[lvl - 1]["max"]
        cur_min, cur_max = js_levels[lvl]["min"], js_levels[lvl]["max"]
        assert len(cur_min) == -(-len(prev_min) // 4)  # ceil division
        for j in range(len(cur_min)):
            lo, hi = j * 4, min(len(prev_min), j * 4 + 4)
            assert cur_min[j] == min(prev_min[lo:hi]), f"level {lvl} bin {j}: min"
            assert cur_max[j] == max(prev_max[lo:hi]), f"level {lvl} bin {j}: max"
