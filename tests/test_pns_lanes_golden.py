"""The golden test of task 4.5 of `docs/plans/diagram-lanes.md`: the browser module
`PnsLanes` (`src/pulseq_reports/assets/pns_lanes.js`) must give the same PNS total, at
the same sample times, as the Python pipeline of `pns_levels.pns_levels`, to a
relative 1e-12 of the peak (plan section 3.5, item 1); its stored level must bound
every JS exact sample of its own bin (plan section 4.2); and each pyramid level of
`PnsLanes.levels` must be the minimum/maximum of the 4 bins of the level below it
(plan section 4.5's "pyramid").

`_run_golden` writes one sequence's diagram tables and its `pns` object (plan section
4.4, including `gradScale`, decision 14; made by `cards.diagram._pns_entry`, as for the
page) to a JSON file, runs `tests/js/golden_pns_lanes.js` with Node on it, and reads
back the JSON result: `PnsLanes.decode`, one `exactView` call for the whole file (forced
to the "samples" kind by a bin count far larger than the sample count, so every sample
is returned, never a minimum/maximum reduction), and the decoded pyramid
(`model.levels`).

The Python reference (`_python_reference_totals`) is the same pipeline
`pns_levels.pns_levels` itself runs (its own docstring, items 1 to 3), but built
independently in this file, in one call instead of `pns_levels`'s chunks:
`GradientSampler.block_samples` of gx, gy and gz for the whole file, divided by
`seq.system.gamma` (T/m, as `calc_pns` divides), through pypulseq's
`_safe_gwf_to_pns_chunk` (a single chunk, `state=None`), scaled by 0.01 and combined
as `sqrt(x^2 + y^2 + z^2)`. The pinned fork's chunk function gives bit-identical
results for any chunk size (lean on pypulseq, decision 6: not tested here), so this
file also asserts `pns_levels(seq).peak == totals.max()` exactly, as a check that this
file's one-call reference really is the same computation as `pns_levels`'s chunked one,
not a second, independent PNS implementation.

The sequences (task 4.5, item 1): the three synthetic sequences of `tests/synthetic.py`
that have a gradient event (`pns_levels` has no bins to compare for the empty sequence);
a "border" sequence, whose gradient is not zero at the block junction
(`synthetic.border_sequence`); a repeating sequence of
more than `3 * PnsLanes.GROUP_BLOCKS` (192) blocks, so the golden test crosses more than
3 of the JavaScript block map's checkpoint groups; and a sequence built with
`pp.Opts(gamma=11.262e6)` (sodium), with a gradient on every axis so a wrong `gradScale`
would show on all three, not just one.

The gamma case needs `PnsLanes.decode` to read `pns.gradScale`: the diagram tables
always hold gradients in mT/m under the fixed proton gamma (`GAMMA_1H` of `synthetic.py`)
(`diagram_data.diagram_tables`), so a sequence of another nucleus needs
`gradScale = GAMMA_1H / seq.system.gamma` to recover T/m (plan section 4.4, decision 14).
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
from pulseq_analysis.series import encode_array
from pypulseq.utils.safe_pns_prediction import _safe_gwf_to_pns_chunk, safe_example_hw
from synthetic import (
    arbitrary_gradient_sequence,
    border_sequence,
    gre_sequence,
    spin_echo_sequence,
)

from pulseq_reports import diagram_data
from pulseq_reports.cards.diagram import _pns_entry

_GOLDEN_SCRIPT = Path(__file__).parent / "js" / "golden_pns_lanes.js"

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


_SODIUM_SYSTEM = pp.Opts(
    max_grad=28,
    grad_unit="mT/m",
    max_slew=150,
    slew_unit="T/m/s",
    rf_ringdown_time=20e-6,
    rf_dead_time=100e-6,
    adc_dead_time=10e-6,
    gamma=11.262e6,  # sodium (23Na), decision 14 of docs/plans/diagram-lanes.md
)


def _sodium_sequence() -> pp.Sequence:
    """A sequence built with sodium's gyromagnetic ratio (`pp.Opts(gamma=11.262e6)`,
    decision 14): one trapezoid on each of x, y and z (areas scaled down from the
    proton synthetic sequences', since sodium's smaller gamma means a smaller
    max-gradient area in 1/m for the same mT/m hardware limit), so a wrong
    `gradScale` would show on every axis."""
    seq = pp.Sequence(_SODIUM_SYSTEM)
    seq.add_block(
        pp.make_trapezoid(channel="x", flat_time=1.4e-3, flat_area=200, system=_SODIUM_SYSTEM)
    )
    seq.add_block(pp.make_trapezoid(channel="y", area=150, system=_SODIUM_SYSTEM))
    seq.add_block(pp.make_trapezoid(channel="z", area=-90, system=_SODIUM_SYSTEM))
    return seq


_SEQUENCES = {
    "spin_echo": spin_echo_sequence,
    "gre_default": gre_sequence,
    "arbitrary_gradient": arbitrary_gradient_sequence,
    "border": border_sequence,
    "repeating_more_than_3_checkpoint_groups": _repeating_sequence,
    "sodium_gamma": _sodium_sequence,
}


# ---- The Python reference (independent of pns_levels's own chunking) ---------------


def _python_reference_totals(seq: pp.Sequence) -> np.ndarray:
    """The whole file's per-sample PNS total (float64), the same pipeline
    `pns_levels.pns_levels` runs, but in a single call instead of `pns_levels`'s
    chunks: `GradientSampler.block_samples` of gx, gy and gz for every block, divided
    by `seq.system.gamma` (T/m, as `calc_pns` divides), through
    `_safe_gwf_to_pns_chunk` (`state=None`, the whole file as one chunk, example
    hardware, as `pns_levels` uses by default), scaled by 0.01 and combined as
    `sqrt(x^2 + y^2 + z^2)`, with the same numpy operations `calc_pns` uses."""
    dt = seq.grad_raster_time
    index = sequence_index(seq)
    sampler = GradientSampler(seq, index)
    n = index.num_blocks
    gx = sampler.block_samples("gx", 0, n, dt)
    gy = sampler.block_samples("gy", 0, n, dt)
    gz = sampler.block_samples("gz", 0, n, dt)
    gwf = np.stack([gx, gy, gz], axis=1) / seq.system.gamma
    percent, _ = _safe_gwf_to_pns_chunk(gwf, dt, safe_example_hw(), None)
    axis_frac = 0.01 * percent
    return np.sqrt((axis_frac**2).sum(axis=1))


# ---- Running the Node half -----------------------------------------------------


def _run_golden(seq: pp.Sequence, tmp_path: Path):
    """Writes `seq`'s diagram tables and `pns` object (plan section 4.4, made by
    `cards.diagram._pns_entry`) to a JSON file in `tmp_path`, runs `golden_pns_lanes.js`
    on it with Node, and returns `(json.loads(OUT.json), pns_levels(seq))`.

    Fails the test, with a clear message, when `node` is not on `PATH`: the plan
    requires this (both devShells have Node), not a silent skip.
    """
    if shutil.which("node") is None:
        pytest.fail(
            "node is required to run tests/js/golden_pns_lanes.js (the golden test "
            "of PnsLanes against the Python pns_levels pipeline), but it was not "
            "found on PATH"
        )
    tables = diagram_data.diagram_tables(seq)
    levels = pns_levels(seq)
    pns_payload = _pns_entry(seq, levels)
    payload = {
        "tables": {name: encode_array(a) for name, a in tables.items()},
        "pns": pns_payload,
        "numSamples": levels.num_samples,
    }
    in_path = tmp_path / "in.json"
    out_path = tmp_path / "out.json"
    in_path.write_text(json.dumps(payload))
    subprocess.run(["node", str(_GOLDEN_SCRIPT), str(in_path), str(out_path)], check=True)
    return json.loads(out_path.read_text()), levels


# ---- The test ------------------------------------------------------------------


@pytest.mark.parametrize("builder", _SEQUENCES.values(), ids=_SEQUENCES.keys())
def test_pns_lanes_exact_view_and_levels_match_the_python_pipeline(builder, tmp_path):
    """`PnsLanes.decode` and `exactView`, run through Node on one sequence's real
    diagram tables and `pns` object, give the same whole-file PNS total, at the same
    sample times, as the Python `pns_levels` pipeline (`_python_reference_totals`),
    within a relative 1e-12 of the peak (plan section 3.5, item 1); the stored level
    (`pns_levels`'s `level_min_hz_per_t`/`level_max_hz_per_t`, divided by |gamma|) bounds
    every one of those JS exact samples in its own bin; and each level of the decoded
    pyramid (`PnsLanes.levels`) is exactly the minimum/maximum of the 4 bins of the level
    below it.
    """
    seq = builder()
    ref_totals = _python_reference_totals(seq)

    output, levels = _run_golden(seq, tmp_path)

    # pulseq-analysis gives Hz/T: the fraction times |gamma|. Divided by |gamma| it is the fraction
    # of the reference. The reference divides the gradient by gamma BEFORE the SAFE model, and
    # pulseq-analysis divides AFTER it, so the two peaks can differ by a few float64 roundings:
    # they are equal to a relative 1e-14 (measured: 1e-15 holds), not exactly.
    g = abs(seq.system.gamma)
    peak_fraction = levels.peak_hz_per_t / g
    level_min = levels.level_min_hz_per_t / g
    level_max = levels.level_max_hz_per_t / g
    assert peak_fraction == pytest.approx(ref_totals.max(), rel=1e-14, abs=0), (
        "pns_levels's chunked peak does not equal the one-call reference's max to a relative "
        "1e-14: the fork's chunk function should not depend on the chunk size"
    )
    assert output["onRaster"] is True, "sequence is not on the gradient raster"
    assert output["numSamples"] == levels.num_samples == ref_totals.shape[0]

    dt = levels.dt_s
    num_samples = levels.num_samples
    peak = peak_fraction or 1.0  # an all-zero file's tolerance would else be zero itself

    t = np.asarray(output["t"], dtype=np.float64)
    total = np.asarray(output["total"], dtype=np.float64)
    assert t.shape == (num_samples,)
    assert total.shape == (num_samples,)

    expected_t = (np.arange(num_samples, dtype=np.float64) + 0.5) * dt
    np.testing.assert_array_equal(
        t, expected_t, err_msg="JS sample times do not exactly equal (k + 0.5) * dt"
    )

    diff = np.abs(total - ref_totals)
    max_diff = float(diff.max()) if diff.size else 0.0
    tol = 1e-12 * peak
    assert max_diff <= tol, (
        f"JS exact total differs from the Python reference by {max_diff!r}, "
        f"tolerance {tol!r} (1e-12 of the peak {peak!r})"
    )

    # The stored level bounds every JS exact sample of its own bin (plan section
    # 4.2): level_min[i] <= min of the JS samples of bin i, level_max[i] >= their
    # max, allowing the same relative 1e-12 slack as the total-values check above
    # (the two totals arrays come from different code paths -- Python's chunked SAFE
    # filter versus the JavaScript block maps -- so they can differ by that much).
    bin_samples = levels.bin_samples
    slack = 1e-12 * peak
    for i in range(len(level_min)):
        s0 = i * bin_samples
        s1 = min(s0 + bin_samples, num_samples)
        segment = total[s0:s1]
        js_min = float(segment.min())
        js_max = float(segment.max())
        # `level_min_hz_per_t` is float32 and bounds its bin in Hz/T. Divided by |gamma|
        # (float32 / float, rounded to the nearest float32) it can pass the bound by half a
        # float32 spacing, so each comparison also allows one float32 spacing of the stored
        # value.
        assert float(level_min[i]) <= js_min + slack + float(np.spacing(level_min[i])), (
            f"bin {i}: stored level_min {level_min[i]!r} > JS min {js_min!r} + slack"
        )
        assert float(level_max[i]) >= js_max - slack - float(np.spacing(level_max[i])), (
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
