"""The targets of a report: the target profiles of pulseq-checks that the caller gives, each
with its color on the page and whether the cards can use it.

A report has at most `MAX_TARGETS` targets, with distinct names. Target `k` (from 1) has the
color token `target-k` of `assets/report.css`, in the order that the caller gives. A target
is supported when its gamma is the proton gamma (`GAMMA`), or when it gives no gamma:
pulseq-reports changes Hz into T only with the proton gamma. A card leaves out a target that
is not supported, with its `reason` in a note. The check summary still shows its results.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from pulseq_analysis.seq_utils import GAMMA
from pulseq_checks import TargetProfile

MAX_TARGETS = 6


@dataclass(frozen=True)
class ReportTarget:
    """One target of a report. `profile` is the caller's `TargetProfile`. `color` is its
    color token, `"target-1"` to `"target-6"`. `supported` is False when the cards cannot
    use the target, and `reason` then says why; `reason` is None for a supported target."""

    profile: TargetProfile
    color: str
    supported: bool
    reason: str | None


def report_targets(profiles: Sequence[TargetProfile]) -> tuple[ReportTarget, ...]:
    """The `ReportTarget` of each of `profiles`, in their order.

    Raises `ValueError` for more than `MAX_TARGETS` profiles and for two profiles with one
    name. Raises `TypeError` for an item that is not a `TargetProfile`."""
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
    return tuple(
        _report_target(profile, f"target-{k}") for k, profile in enumerate(profiles, start=1)
    )


def _report_target(profile: TargetProfile, color: str) -> ReportTarget:
    gamma = (profile.opts or {}).get("gamma")
    if gamma is not None and gamma != GAMMA:
        reason = (
            f"the target gives the gamma {gamma:g} Hz/T, and pulseq-reports supports only the "
            f"proton gamma ({GAMMA:g} Hz/T)"
        )
        return ReportTarget(profile, color, supported=False, reason=reason)
    return ReportTarget(profile, color, supported=True, reason=None)
