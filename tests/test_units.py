import numpy as np
import pypulseq as pp
import pytest
from synthetic import GAMMA_1H

from pulseq_reports import units

_CONVERSIONS = [
    units.hz_per_m_to_mt_per_m,
    units.hz_per_m_per_s_to_t_per_m_per_s,
    units.hz_to_ut,
]


def test_the_proton_gamma_is_the_default_gamma_of_pypulseq():
    assert pp.Opts().gamma == GAMMA_1H
    assert units.PROTON_GAMMA == GAMMA_1H


@pytest.mark.parametrize("convert", _CONVERSIONS)
def test_a_negative_gamma_gives_the_value_of_its_magnitude_for_a_number(convert):
    assert convert(1234.5, -GAMMA_1H) == convert(1234.5, GAMMA_1H)


@pytest.mark.parametrize("convert", _CONVERSIONS)
def test_a_negative_gamma_gives_the_value_of_its_magnitude_for_an_array(convert):
    values = np.array([0.0, 1234.5, 6.7e5])
    assert np.array_equal(convert(values, -GAMMA_1H), convert(values, GAMMA_1H))
