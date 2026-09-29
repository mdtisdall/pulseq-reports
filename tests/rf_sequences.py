"""The sequence builders that `tests/test_rf_profiles.py` and
`tests/test_rf_profile_card.py` share: a system with a 5 µs RF raster, sinc and hard
pulses, a readout, trapezoids, an empty sequence with a `SliceThickness` definition,
turning gradients, and a gradient-echo sequence. `tests/test_rf_profiles_golden.py` reads
them as `test_rf_profiles._gre` and so on, so `tests/test_rf_profiles.py` imports each
name into its own namespace.
"""

import math

import numpy as np
import pypulseq as pp

SYSTEM = pp.Opts(
    max_grad=30,
    grad_unit="mT/m",
    max_slew=150,
    slew_unit="T/m/s",
    rf_dead_time=100e-6,
    rf_ringdown_time=30e-6,
    adc_dead_time=10e-6,
    rf_raster_time=5e-6,
)
W = 5e-3  # m, the SliceThickness definition
CRUSHER_AREA = 4 / W  # 1/m: four cycles across W


def _sinc(use, flip=math.pi / 2, thickness=W, system=SYSTEM, **kwargs):
    """A 1.5 ms sinc (300 samples at 5 µs) with its select gradient on z and rephaser."""
    return pp.make_sinc_pulse(
        flip_angle=flip,
        duration=1.5e-3,
        slice_thickness=thickness,
        system=system,
        return_gz=True,
        delay=system.rf_dead_time,
        use=use,
        **kwargs,
    )


def _hard(use, flip=math.pi / 2, duration=0.5e-3, system=SYSTEM, **kwargs):
    return pp.make_block_pulse(
        flip_angle=flip,
        duration=duration,
        delay=system.rf_dead_time,
        system=system,
        use=use,
        **kwargs,
    )


def _readout():
    """A readout trapezoid on x with its ADC on the flat top, and the area from the
    gradient start to the ADC centre."""
    gx = pp.make_trapezoid("x", flat_area=250, flat_time=0.64e-3, system=SYSTEM)
    adc = pp.make_adc(num_samples=32, duration=gx.flat_time, delay=gx.rise_time, system=SYSTEM)
    return gx, adc, gx.amplitude * (gx.rise_time + gx.flat_time) / 2


def _trap(axis, area):
    return pp.make_trapezoid(axis, area=area, system=SYSTEM)


def _new(thickness=W, system=SYSTEM):
    seq = pp.Sequence(system)
    if thickness is not None:
        seq.set_definition("SliceThickness", thickness)
    return seq


def _turning_gradients(duration=1e-3, amplitude=2e5):
    """Arbitrary gradients on x and y whose direction turns one time during `duration`."""
    n = round(duration / SYSTEM.grad_raster_time)
    t = (np.arange(n) + 0.5) * SYSTEM.grad_raster_time
    envelope = amplitude * np.sin(np.pi * t / duration)
    angle = 2 * np.pi * t / duration
    gx = pp.make_arbitrary_grad("x", envelope * np.cos(angle), first=0, last=0, system=SYSTEM)
    gy = pp.make_arbitrary_grad("y", envelope * np.sin(angle), first=0, last=0, system=SYSTEM)
    return gx, gy


def _gre(num_trs=3, *, rf_spoiling=False, slices=(0.0,), dummies=0):
    """A GRE: [RF + gz, rephaser + readout prephaser, readout + ADC, spoiler] for each
    slice of each TR. `dummies` TRs before them have no ADC."""
    rf, gz, gzr = _sinc("excitation")
    gx, adc, to_centre = _readout()
    prephaser = _trap("x", -to_centre)
    spoiler = _trap("z", CRUSHER_AREA)
    seq = _new()
    count = 0
    for tr in range(dummies + num_trs):
        for position in slices:
            rf.freq_offset = gz.amplitude * position
            rf.phase_offset = (
                math.radians((117 * count * (count + 1) / 2) % 360) if rf_spoiling else 0
            )
            count += 1
            seq.add_block(rf, gz)
            seq.add_block(gzr, prephaser)
            seq.add_block(gx, adc) if tr >= dummies else seq.add_block(gx)
            seq.add_block(spoiler)
    return seq
