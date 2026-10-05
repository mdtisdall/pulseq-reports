import dataclasses
from pathlib import Path

import pypulseq as pp
import pytest
from pulseq_checks import read_profile

from pulseq_reports.targets import MAX_TARGETS, ReportTarget, report_targets


def test_colors_are_target_1_to_target_k_in_order(make_profile):
    profiles = [make_profile(name) for name in ("c", "a", "b")]

    targets = report_targets(profiles)

    assert [target.profile for target in targets] == profiles
    assert [target.color for target in targets] == ["target-1", "target-2", "target-3"]
    assert all(isinstance(target, ReportTarget) for target in targets)


def test_no_profiles_give_no_targets():
    assert report_targets([]) == ()


def test_the_most_targets_are_accepted_and_one_more_raises(make_profile):
    profiles = [make_profile(f"t{k}") for k in range(MAX_TARGETS + 1)]

    targets = report_targets(profiles[:MAX_TARGETS])

    assert [target.color for target in targets] == [f"target-{k}" for k in range(1, 7)]
    with pytest.raises(ValueError, match=str(MAX_TARGETS)):
        report_targets(profiles)


def test_two_profiles_with_one_name_raise(make_profile):
    profile = make_profile("scanner")
    other = dataclasses.replace(make_profile("other"), name="scanner")

    with pytest.raises(ValueError, match="scanner"):
        report_targets([profile, make_profile("third"), other])


def test_an_item_that_is_not_a_target_profile_raises(make_profile):
    with pytest.raises(TypeError, match="TargetProfile"):
        report_targets([make_profile("a"), "b.toml"])


def test_a_negative_gamma_is_valid_and_kept_signed(make_profile):
    (target,) = report_targets([make_profile("xenon", "gamma = -11.777e6")])

    assert target.gamma == -11.777e6


def test_a_profile_with_no_gamma_gets_the_default_gamma_of_pypulseq(make_profile):
    no_gamma = make_profile("no-gamma", "max_grad = 30")
    no_opts = make_profile("no-opts")

    targets = report_targets([no_gamma, no_opts])

    assert [target.gamma for target in targets] == [pp.Opts().gamma] * 2


@pytest.mark.parametrize("gamma", ["0", "inf", "nan"])
def test_a_gamma_that_is_0_or_not_finite_raises(make_profile, gamma):
    profile = make_profile("bad", f"gamma = {gamma}")

    with pytest.raises(ValueError, match="bad"):
        report_targets([make_profile("ok"), profile])


def test_the_example_profile_with_a_negative_gamma_is_read():
    (target,) = report_targets(
        [read_profile(Path(__file__).parent / "profiles" / "example_c.toml")]
    )

    assert target.gamma == -11.777e6
    assert target.profile.opts["B0"] == 3.0
