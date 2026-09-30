"""Build the example report: a simple 2D gradient echo (GRE) sequence, every library card.

The sequence follows pypulseq's own example `examples/scripts/write_gre.py` (MIT
license): a 64 x 64 Cartesian GRE with a sinc slice-selective excitation, RF spoiling
and gradient spoiling, TR 12 ms, TE 5 ms.

Run it from the repository root, in the devShell:

    nix develop --command uv run python examples/gre_report.py

It writes `docs/examples/gre.html`, which GitHub Pages serves from `main`. Give a path
as the first argument to write the page somewhere else.
"""

import sys
from pathlib import Path

import numpy as np
import pypulseq as pp

import pulseq_reports
from pulseq_reports import build_cards, write_page

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "examples" / "gre.html"

FOV = 256e-3  # m
N_X = 64  # readout samples
N_Y = 64  # phase encoding steps
FLIP_ANGLE_DEG = 10
SLICE_THICKNESS = 3e-3  # m
TR = 12e-3  # s
TE = 5e-3  # s
RF_SPOILING_INC = 117  # degrees


def gre_sequence() -> pp.Sequence:
    """A 2D GRE, as in pypulseq's `write_gre.py` example, with a TR definition."""
    system = pp.Opts(
        max_grad=28,
        grad_unit="mT/m",
        max_slew=150,
        slew_unit="T/m/s",
        rf_ringdown_time=20e-6,
        rf_dead_time=100e-6,
        adc_dead_time=10e-6,
    )
    seq = pp.Sequence(system)

    rf, gz, _ = pp.make_sinc_pulse(
        flip_angle=np.deg2rad(FLIP_ANGLE_DEG),
        duration=3e-3,
        slice_thickness=SLICE_THICKNESS,
        apodization=0.42,
        time_bw_product=4,
        system=system,
        return_gz=True,
        delay=system.rf_dead_time,
        use="excitation",
    )
    delta_k = 1 / FOV
    gx = pp.make_trapezoid(channel="x", flat_area=N_X * delta_k, flat_time=3.2e-3, system=system)
    adc = pp.make_adc(num_samples=N_X, duration=gx.flat_time, delay=gx.rise_time, system=system)
    gx_pre = pp.make_trapezoid(channel="x", area=-gx.area / 2, duration=1e-3, system=system)
    gz_reph = pp.make_trapezoid(channel="z", area=-gz.area / 2, duration=1e-3, system=system)
    phase_areas = (np.arange(N_Y) - N_Y / 2) * delta_k
    gx_spoil = pp.make_trapezoid(channel="x", area=2 * N_X * delta_k, system=system)
    gz_spoil = pp.make_trapezoid(channel="z", area=4 / SLICE_THICKNESS, system=system)

    te_delay = (
        TE
        - (pp.calc_duration(gz, rf) - pp.calc_rf_center(rf)[0] - rf.delay)
        - pp.calc_duration(gx_pre)
        - pp.calc_duration(gx) / 2
        - pp.eps
    )
    te_delay = np.ceil(te_delay / seq.grad_raster_time) * seq.grad_raster_time
    tr_delay = (
        TR - pp.calc_duration(gz, rf) - pp.calc_duration(gx_pre) - pp.calc_duration(gx) - te_delay
    )
    tr_delay = np.ceil(tr_delay / seq.grad_raster_time) * seq.grad_raster_time
    assert te_delay >= 0
    assert tr_delay >= pp.calc_duration(gx_spoil, gz_spoil)

    rf_phase = 0.0
    rf_inc = 0.0
    for area in phase_areas:
        rf.phase_offset = rf_phase / 180 * np.pi
        adc.phase_offset = rf_phase / 180 * np.pi
        rf_inc = (rf_inc + RF_SPOILING_INC) % 360.0
        rf_phase = (rf_phase + rf_inc) % 360.0

        seq.add_block(rf, gz)
        gy_pre = pp.make_trapezoid(
            channel="y", area=area, duration=pp.calc_duration(gx_pre), system=system
        )
        seq.add_block(gx_pre, gy_pre, gz_reph)
        seq.add_block(pp.make_delay(te_delay))
        seq.add_block(gx, adc)
        gy_pre.amplitude = -gy_pre.amplitude
        seq.add_block(pp.make_delay(tr_delay), gx_spoil, gy_pre, gz_spoil)

    seq.set_definition(key="FOV", value=[FOV, FOV, SLICE_THICKNESS])
    seq.set_definition(key="TR", value=TR)
    seq.set_definition(key="Name", value="gre")
    return seq


def main(output: Path) -> None:
    seq = gre_sequence()

    cards = build_cards(seq, pns_lane=True, views=("profile", "z_df"))

    output.parent.mkdir(parents=True, exist_ok=True)
    write_page(
        output,
        title="Example gradient echo (GRE)",
        subtitle=(
            f"A 64 × 64 2D GRE built with pypulseq, TR 12 ms, TE 5 ms. "
            f"Every library card, pulseq-reports {pulseq_reports.__version__}."
        ),
        cards=cards,
    )
    print(f"wrote {output}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT)
