import numpy as np
import pypulseq as pp
import pytest
from synthetic import GAMMA_1H

from pulseq_reports import units
from pulseq_reports.targets import report_targets

_CONVERSIONS = [
    units.hz_per_m_to_mt_per_m,
    units.hz_per_m_per_s_to_t_per_m_per_s,
    units.hz_to_ut,
]


def test_the_proton_gamma_is_the_default_gamma_of_pypulseq():
    assert pp.Opts().gamma == GAMMA_1H


@pytest.mark.parametrize("convert", _CONVERSIONS)
def test_a_negative_gamma_gives_the_value_of_its_magnitude_for_a_number(convert):
    assert convert(1234.5, -GAMMA_1H) == convert(1234.5, GAMMA_1H)


@pytest.mark.parametrize("convert", _CONVERSIONS)
def test_a_negative_gamma_gives_the_value_of_its_magnitude_for_an_array(convert):
    values = np.array([0.0, 1234.5, 6.7e5])
    assert np.array_equal(convert(values, -GAMMA_1H), convert(values, GAMMA_1H))


def test_gamma_entries_with_signed_gammas_give_one_entry_for_each_sign(make_profile):
    profiles = [
        make_profile("a", f"gamma = {GAMMA_1H!r}"),
        make_profile("b", f"gamma = -{GAMMA_1H!r}"),
    ]
    targets = report_targets(profiles)
    seq = pp.Sequence()

    signed = units.gamma_entries(targets, seq, signed=True)
    magnitude = units.gamma_entries(targets, seq, signed=False)

    assert signed == (units.GammaEntry(GAMMA_1H, ("a",)), units.GammaEntry(-GAMMA_1H, ("b",)))
    assert magnitude == (units.GammaEntry(GAMMA_1H, ("a", "b")),)


def test_gamma_entries_share_an_entry_for_targets_with_one_gamma(make_profile):
    profiles = [
        make_profile("a", "gamma = 11.262e6"),
        make_profile("b"),
        make_profile("c", "gamma = 11.262e6"),
    ]

    entries = units.gamma_entries(report_targets(profiles), pp.Sequence(), signed=True)

    assert entries == (
        units.GammaEntry(11.262e6, ("a", "c")),
        units.GammaEntry(GAMMA_1H, ("b",)),
    )


def test_gamma_entries_without_targets_give_the_gamma_of_the_sequence():
    seq = pp.Sequence(pp.Opts(gamma=-11.777e6))

    assert units.gamma_entries((), seq, signed=True) == (units.GammaEntry(-11.777e6, ()),)
    assert units.gamma_entries((), seq, signed=False) == (units.GammaEntry(11.777e6, ()),)
