"""The gamma of the cards, and the conversions from the units of a `.seq` file.

pulseq-analysis gives its values in the units of the `.seq` file, with no gamma: Hz/m,
Hz/m/s, Hz and Hz/T (its `docs/usage.md`, section 8). A card changes them into tesla
units with a gamma, in Hz/T. Each value that this module converts is a magnitude, so each
conversion uses the magnitude of the gamma (a gamma can be negative). This module is the
one place that takes that magnitude (decision D17 of `docs/plans/pulseq-checks-implementation.md`).

The gamma of a target is the gamma of its `Opts` (`target_gamma`), as in pulseq-checks: the
`opts.gamma` of the profile, or the default of pypulseq when the profile does not give it.
Without targets, a card uses `seq.system.gamma`. A gamma that is 0 or not finite is an error
(`check_gamma`). `gamma_entries` gives the entries of the control that selects the gamma of
a card (decision P36 of `docs/plans/pulseq-checks.md`).

`PROTON_GAMMA` is the proton gamma of the cards that do not use the gamma of the targets yet
(phases 5 and 7b of the plan remove its last uses).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pypulseq as pp
from pulseq_checks import TargetProfile

if TYPE_CHECKING:
    from .targets import ReportTarget

PROTON_GAMMA = 42.576e6  # Hz/T, the default gamma of pypulseq (`pp.Opts`)


@dataclass(frozen=True)
class GammaEntry:
    """One entry of the control of a card: `gamma` (Hz/T; its magnitude for an entry of
    magnitudes), and the names of the targets that have it, in their order (empty for the
    gamma of the sequence)."""

    gamma: float
    names: tuple[str, ...]


def target_gamma(profile: TargetProfile) -> float:
    """The gamma (Hz/T, signed) of `profile`: the gamma of its `Opts`, as in pulseq-checks."""
    return profile.make_opts().gamma


def check_gamma(gamma: float, where: str) -> None:
    """Raises `ValueError`, naming `where`, when `gamma` is 0 or not finite."""
    if not math.isfinite(gamma) or gamma == 0:
        raise ValueError(f"{where} has the gamma {gamma!r} Hz/T: a gamma must be finite and not 0")


def gamma_entries(
    targets: "Sequence[ReportTarget]", seq: pp.Sequence, *, signed: bool
) -> tuple[GammaEntry, ...]:
    """The entries of the control of a card: one for each distinct gamma of `targets`
    (`signed=True`) or for each distinct magnitude (`signed=False`), in the order of the first
    target of each entry. Without targets, one entry with `seq.system.gamma`."""
    if not targets:
        gamma = seq.system.gamma
        return (GammaEntry(gamma if signed else gamma_magnitude(gamma), ()),)
    names: dict[float, list[str]] = {}
    for target in targets:
        gamma = target.gamma if signed else gamma_magnitude(target.gamma)
        names.setdefault(gamma, []).append(target.profile.name)
    return tuple(GammaEntry(gamma, tuple(n)) for gamma, n in names.items())


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
