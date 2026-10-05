"""The targets of a report: the target profiles of pulseq-checks that the caller gives, each
with its color on the page and its gamma.

A report has at most `MAX_TARGETS` targets, with distinct names. Target `k` (from 1) has the
color token `target-k` of `assets/report.css`, in the order that the caller gives. The gamma
of a target is the gamma of its `Opts` (`units.target_gamma`). It can be negative, and a
gamma that is 0 or not finite is an error.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from pulseq_checks import TargetProfile

from .units import check_gamma, target_gamma

MAX_TARGETS = 6


@dataclass(frozen=True)
class ReportTarget:
    """One target of a report. `profile` is the caller's `TargetProfile`. `color` is its
    color token, `"target-1"` to `"target-6"`. `gamma` is its gamma in Hz/T (signed)."""

    profile: TargetProfile
    color: str
    gamma: float


def report_targets(profiles: Sequence[TargetProfile]) -> tuple[ReportTarget, ...]:
    """The `ReportTarget` of each of `profiles`, in their order.

    Raises `ValueError` for more than `MAX_TARGETS` profiles, for two profiles with one name,
    and for a profile whose gamma is 0 or not finite. Raises `TypeError` for an item that is
    not a `TargetProfile`."""
    profiles = tuple(profiles)
    for profile in profiles:
        if not isinstance(profile, TargetProfile):
            raise TypeError(f"a target must be a TargetProfile, not {type(profile).__name__}")
    if len(profiles) > MAX_TARGETS:
        raise ValueError(
            f"a report has at most {MAX_TARGETS} targets, and {len(profiles)} were given"
        )
    names = [profile.name for profile in profiles]
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        raise ValueError(f"two targets have the name {repeated[0]!r}: each name must be unique")
    targets = []
    for k, profile in enumerate(profiles, start=1):
        gamma = target_gamma(profile)
        check_gamma(gamma, f"the target {profile.name!r}")
        targets.append(ReportTarget(profile, f"target-{k}", gamma))
    return tuple(targets)
