import dataclasses

import pytest
from synthetic import GAMMA_1H

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


def test_a_gamma_that_is_not_the_proton_gamma_is_not_supported(make_profile):
    sodium = make_profile("sodium", "gamma = 11.262e6")

    (target,) = report_targets([sodium])

    assert target.supported is False
    assert target.reason is not None
    assert target.color == "target-1"


def test_the_proton_gamma_and_no_gamma_are_supported(make_profile):
    proton = make_profile("proton", f"gamma = {GAMMA_1H!r}")
    no_gamma = make_profile("no-gamma", "max_grad = 30")
    no_opts = make_profile("no-opts")
    assert no_opts.opts is None or "gamma" not in no_opts.opts

    targets = report_targets([proton, no_gamma, no_opts])

    assert [target.supported for target in targets] == [True, True, True]
    assert [target.reason for target in targets] == [None, None, None]


def test_an_unsupported_target_does_not_change_the_colors_of_the_others(make_profile):
    profiles = [
        make_profile("a"),
        make_profile("b", "gamma = 11.262e6"),
        make_profile("c"),
    ]

    targets = report_targets(profiles)

    assert [target.color for target in targets] == ["target-1", "target-2", "target-3"]
    assert [target.supported for target in targets] == [True, False, True]
