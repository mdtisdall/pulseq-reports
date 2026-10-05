"""The analyses use the rasters that a `.seq` file declares in `[DEFINITIONS]`.

`Sequence.read` sets `seq.grad_raster_time` and `seq.rf_raster_time` from the file but
does not change `seq.system`, which keeps the `Opts` given to `pp.Sequence` (the
pypulseq defaults when `pulseq-report` reads a file). Each test here writes a file with
rasters that are not the defaults, reads it back with `pp.Sequence()`, and compares with
what the file's own rasters give.
"""

import numpy as np
import pypulseq as pp
import pytest
from synthetic import GAMMA_1H

from pulseq_reports import rf_exposure
from pulseq_reports import rf_profiles as rp
from pulseq_reports.cards.rf_profile import _rf_table

# Not the pypulseq defaults (10 µs gradient, 1 µs RF). The RF block (100 µs dead time,
# 500 µs pulse, 24 µs ringdown) is a whole number of 4 µs block-duration rasters.
FILE_SYSTEM = pp.Opts(
    max_grad=30,
    grad_unit="mT/m",
    max_slew=150,
    slew_unit="T/m/s",
    grad_raster_time=4e-6,
    rf_raster_time=2e-6,
    block_duration_raster=4e-6,
    rf_dead_time=100e-6,
    rf_ringdown_time=24e-6,
)


@pytest.fixture(scope="module")
def seq_file(tmp_path_factory):
    """A block pulse (two shape points, so `hold_samples` samples it at the raster), a
    trapezoid and a delay, three times."""
    seq = pp.Sequence(FILE_SYSTEM)
    rf = pp.make_block_pulse(
        flip_angle=np.pi / 2,
        duration=0.5e-3,
        delay=FILE_SYSTEM.rf_dead_time,
        system=FILE_SYSTEM,
        use="excitation",
    )
    for _ in range(3):
        seq.add_block(rf)
        seq.add_block(pp.make_trapezoid("x", area=400, duration=1.2e-3, system=FILE_SYSTEM))
        seq.add_block(pp.make_delay(1.04e-3))
    path = tmp_path_factory.mktemp("rasters") / "rasters.seq"
    seq.write(str(path))
    return path


def _read(path, system=None) -> pp.Sequence:
    seq = pp.Sequence() if system is None else pp.Sequence(system)
    seq.read(str(path))
    return seq


def test_rf_samples_use_the_file_rf_raster(seq_file):
    """The RF profile card's RF table and `rf_profiles.block_pulse` sample the block pulse
    at the file's 2 µs RF raster (250 samples), not at `seq.system.rf_raster_time`."""
    seq = _read(seq_file)
    assert seq.system.rf_raster_time != FILE_SYSTEM.rf_raster_time  # the case under test

    table = _rf_table(seq)
    assert table["dt"][0] == pytest.approx(FILE_SYSTEM.rf_raster_time, abs=1e-12)
    assert table["shape_n"][0] == 250

    pulse = rp.block_pulse(seq, 0)
    assert pulse.dt_s == pytest.approx(FILE_SYSTEM.rf_raster_time, abs=1e-12)
    assert pulse.signal_hz.size == 250


def test_rf_exposure_does_not_depend_on_the_reader_opts(seq_file):
    """`rf_exposure` of the file read with `pp.Sequence()` equals that of the file read with
    its own `Opts`, exactly: both use the file's rasters."""
    default = _read(seq_file)
    own = _read(seq_file, FILE_SYSTEM)
    assert default.system.grad_raster_time != FILE_SYSTEM.grad_raster_time
    assert default.system.rf_raster_time != FILE_SYSTEM.rf_raster_time

    assert rf_exposure.rf_exposure(default, GAMMA_1H) == rf_exposure.rf_exposure(own, GAMMA_1H)
