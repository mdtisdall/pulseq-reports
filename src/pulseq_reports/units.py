"""The gamma of the cards, and the conversions from the units of a `.seq` file.

pulseq-analysis gives its values in the units of the `.seq` file, with no gamma: Hz/m,
Hz/m/s, Hz and Hz/T (its `docs/usage.md`, section 8). A card changes them into tesla
units with a gamma, in Hz/T. Each value that this module converts is a magnitude, so each
conversion uses the magnitude of the gamma (a gamma can be negative). This module is the
one place that takes that magnitude (decision D17 of `docs/plans/pulseq-checks-implementation.md`).

`PROTON_GAMMA` is the proton gamma of the cards until each card uses the gamma of its
targets (phases 2c to 7b of that plan).
"""

PROTON_GAMMA = 42.576e6  # Hz/T, the default gamma of pypulseq (`pp.Opts`)


def gamma_magnitude(gamma: float) -> float:
    """The magnitude of `gamma` (Hz/T)."""
    return abs(gamma)


def hz_per_m_to_mt_per_m(value, gamma: float):
    """A gradient amplitude in Hz/m (a number or an array) in mT/m, for `gamma` (Hz/T)."""
    return value / gamma_magnitude(gamma) * 1e3


def hz_per_m_per_s_to_t_per_m_per_s(value, gamma: float):
    """A slew rate in Hz/m/s (a number or an array) in T/m/s, for `gamma` (Hz/T)."""
    return value / gamma_magnitude(gamma)


def hz_to_ut(value, gamma: float):
    """An RF amplitude in Hz (a number or an array) in µT, for `gamma` (Hz/T)."""
    return value / gamma_magnitude(gamma) * 1e6
