import json
import shutil
from pathlib import Path

import pypulseq as pp
import pytest
from plugin_card import SPEC
from pulseq_checks import (
    HardwareLimits,
    ResultMatrix,
    RunError,
    read_check_config,
    read_profile,
    run_checks,
)
from synthetic import gre_sequence, spin_echo_sequence

from pulseq_reports import __version__, cli, options, registry
from pulseq_reports.page import render_page
from pulseq_reports.registry import build_cards, discover

FAST = "gradient-limits,blocks,gradient-spectrum"
PROFILES = Path(__file__).parent / "profiles"
A_PATH = PROFILES / "example_a.toml"
B_PATH = PROFILES / "example_b.toml"
A_NAME = read_profile(A_PATH).name
B_NAME = read_profile(B_PATH).name


@pytest.fixture
def seq_file(tmp_path):
    """The path of a `.seq` file with a synthetic spin-echo sequence."""
    path = tmp_path / "se.seq"
    spin_echo_sequence().write(str(path))
    return path


def _read(path):
    seq = pp.Sequence()
    seq.read(str(path))
    return seq


def _page(path, cards=None, **values):
    """The page that `build_cards` gives for `path` read back, with the command line's
    title and subtitle."""
    built = build_cards(_read(path), cards=cards, **values)
    return render_page(path.name, f"pulseq-reports {__version__}", built)


def test_the_page_of_the_command_line_equals_the_page_of_build_cards(seq_file, tmp_path):
    out = tmp_path / "out.html"

    status = cli.main([str(seq_file), "-o", str(out), "--max-grad", "30", "--max-slew", "200"])

    assert status == 0
    expected = _page(seq_file, limits=HardwareLimits(30.0, 200.0, options.COMMAND_LINE_LABEL))
    assert out.read_text(encoding="utf-8") == expected


def test_the_default_output_is_the_stem_in_the_current_directory(seq_file, tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)

    assert cli.main([str(seq_file), "--cards", FAST]) == 0

    assert (work / "se.html").is_file()


def test_max_grad_and_max_slew_reach_the_gradient_limits_card(seq_file, tmp_path, capsys):
    out = tmp_path / "out.html"

    assert cli.main([str(seq_file), "-o", str(out), "--cards", "gradient-limits"]) == 0
    assert capsys.readouterr().err == ""
    assert out.read_text(encoding="utf-8") == _page(seq_file, ["gradient-limits"])

    args = ["--cards", "gradient-limits", "--max-grad", "33.25", "--max-slew", "211.5"]
    assert cli.main([str(seq_file), "-o", str(out), *args]) == 0
    assert capsys.readouterr().err == ""
    limits = HardwareLimits(33.25, 211.5, options.COMMAND_LINE_LABEL)
    assert out.read_text(encoding="utf-8") == _page(seq_file, ["gradient-limits"], limits=limits)
    assert out.read_text(encoding="utf-8") != _page(seq_file, ["gradient-limits"])


@pytest.mark.parametrize("flag", ["--max-grad", "--max-slew"])
def test_one_of_max_grad_and_max_slew_alone_exits_1(seq_file, tmp_path, capsys, flag):
    out = tmp_path / "out.html"

    assert cli.main([str(seq_file), "-o", str(out), flag, "30"]) == 1

    assert "--max-grad" in capsys.readouterr().err
    assert not out.exists()


def test_two_files_give_two_pages_in_the_output_directory(seq_file, tmp_path):
    other = tmp_path / "gre.seq"
    gre_sequence().write(str(other))
    out = tmp_path / "pages" / "deeper"

    assert cli.main([str(seq_file), str(other), "-o", str(out), "--cards", FAST]) == 0

    assert sorted(p.name for p in out.iterdir()) == ["gre.html", "se.html"]
    assert out.joinpath("gre.html").read_text(encoding="utf-8") != out.joinpath(
        "se.html"
    ).read_text(encoding="utf-8")


def test_two_files_with_one_stem_exit_1_and_write_no_page(tmp_path, capsys):
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
        spin_echo_sequence().write(str(tmp_path / name / "same.seq"))
    out = tmp_path / "pages"

    status = cli.main(
        [str(tmp_path / "a" / "same.seq"), str(tmp_path / "b" / "same.seq"), "-o", str(out)]
    )

    assert status == 1
    assert "same" in capsys.readouterr().err
    assert not out.exists()


def test_cards_and_skip_select_the_cards(seq_file, tmp_path):
    out = tmp_path / "out.html"

    assert cli.main([str(seq_file), "-o", str(out), "--cards", "timing,blocks"]) == 0
    assert out.read_text(encoding="utf-8") == _page(seq_file, ["timing", "blocks"])

    assert (
        cli.main([str(seq_file), "-o", str(out), "--cards", "timing,blocks", "--skip", "timing"])
        == 0
    )
    assert out.read_text(encoding="utf-8") == _page(seq_file, ["blocks"])


@pytest.mark.parametrize("flag", ["--cards", "--skip"])
def test_an_unknown_card_name_exits_1(seq_file, tmp_path, capsys, flag):
    out = tmp_path / "out.html"

    assert cli.main([str(seq_file), "-o", str(out), flag, "timing,no-such-card"]) == 1

    assert "no-such-card" in capsys.readouterr().err
    assert not out.exists()


def test_a_page_with_an_error_card_exits_1_and_the_page_is_written(seq_file, tmp_path, capsys):
    out = tmp_path / "out.html"

    status = cli.main(
        [
            str(seq_file),
            "-o",
            str(out),
            "--card-module",
            "plugin_card:BROKEN",
            "--cards",
            "timing,plugin-broken",
        ]
    )

    assert status == 1
    text = out.read_text(encoding="utf-8")
    assert 'id="timing"' in text and 'id="plugin-broken"' in text
    assert "NotImplementedError" in text


def test_a_file_with_no_error_card_exits_0(seq_file, tmp_path):
    assert cli.main([str(seq_file), "-o", str(tmp_path / "out.html"), "--cards", FAST]) == 0


def test_an_unreadable_file_exits_1_and_the_good_file_has_its_page(seq_file, tmp_path, capsys):
    bad = tmp_path / "bad.seq"
    bad.write_text("this is not a sequence file\n", encoding="utf-8")
    missing = tmp_path / "missing.seq"
    out = tmp_path / "pages"

    status = cli.main([str(bad), str(missing), str(seq_file), "-o", str(out), "--cards", "timing"])

    assert status == 1
    err = capsys.readouterr().err
    assert str(bad) in err and str(missing) in err
    assert [p.name for p in out.iterdir()] == ["se.html"]


def test_card_module_adds_the_card_and_its_option(seq_file, tmp_path):
    out = tmp_path / "out.html"

    status = cli.main(
        [
            str(seq_file),
            "-o",
            str(out),
            "--card-module",
            "plugin_card:SPEC",
            "--cards",
            "plugin-demo",
            "--max-rows",
            "7",
        ]
    )

    assert status == 0
    text = out.read_text(encoding="utf-8")
    assert 'data-max-rows="7"' in text and 'id="plugin-demo"' in text
    # The spec is not installed: the module is only added while the command runs.
    assert "plugin-demo" not in [spec.name for spec in discover()]


def test_card_module_with_a_bad_spec_exits_1_and_writes_no_page(seq_file, tmp_path, capsys):
    out = tmp_path / "out.html"

    # Given twice, the plugin's spec is two specs with one name.
    status = cli.main(
        [
            str(seq_file),
            "-o",
            str(out),
            "--card-module",
            "plugin_card:SPEC",
            "--card-module",
            "plugin_card:SPEC",
        ]
    )
    assert status == 1
    assert "plugin-demo" in capsys.readouterr().err

    for label in (
        "plugin_card:NO_SUCH",
        "no_such_module:SPEC",
        "plugin_card",
        "plugin_card:make_spec",
    ):
        assert cli.main([str(seq_file), "-o", str(out), "--card-module", label]) == 1
        assert label in capsys.readouterr().err
    assert not out.exists()


def test_each_option_of_the_discovered_specs_has_its_flag_in_the_parser(capsys, monkeypatch):
    monkeypatch.setattr(
        registry, "_load_entry_points", lambda f=registry._load_entry_points: [*f(), ("t", SPEC)]
    )
    specs = discover()

    assert cli.main(["--help"]) == 0
    help_text = capsys.readouterr().out
    flags = {flag.name for spec in specs for option in spec.options for flag in option.flags()}
    assert flags
    for spec in specs:
        for option in spec.options:
            for flag in option.flags():
                assert flag.name in help_text
                if flag.type is bool:
                    assert "--no-" + flag.name[2:] in help_text


CONFIG_FLAGS = [
    "--max-grad", "30", "--max-slew", "200", "--max-rows", "5",
]  # fmt: skip
CONFIG_VALUES = {
    "limits": {
        "max_grad_mt_per_m": 30,
        "max_slew_t_per_m_per_s": 200,
        "label": options.COMMAND_LINE_LABEL,
    },
    "max_rows": 5,
    "cards": ["gradient-limits", "blocks", "gradient-spectrum"],
}
CONFIG_TOML = """
cards = ["gradient-limits", "blocks", "gradient-spectrum"]
max_rows = 5

[limits]
max_grad_mt_per_m = 30
max_slew_t_per_m_per_s = 200
label = "command line"
"""


def _config(tmp_path, suffix, text=None, name="site"):
    path = tmp_path / f"{name}{suffix}"
    path.write_text(text if text is not None else CONFIG_TOML if suffix == ".toml"
                    else json.dumps(CONFIG_VALUES), encoding="utf-8")  # fmt: skip
    return path


def test_a_toml_and_a_json_config_file_give_the_page_of_the_same_flags(seq_file, tmp_path):
    flags_out = tmp_path / "flags.html"
    assert cli.main([str(seq_file), "-o", str(flags_out), "--cards", FAST, *CONFIG_FLAGS]) == 0
    expected = flags_out.read_text(encoding="utf-8")

    for suffix in (".toml", ".json"):
        out = tmp_path / f"config{suffix}.html"
        config = _config(tmp_path, suffix)
        assert cli.main([str(seq_file), "-o", str(out), "--config", str(config)]) == 0
        assert out.read_text(encoding="utf-8") == expected


def test_a_flag_overrides_the_config_file(seq_file, tmp_path):
    config = _config(tmp_path, ".toml")
    out = tmp_path / "out.html"

    assert (
        cli.main([str(seq_file), "-o", str(out), "--config", str(config), "--max-rows", "3"]) == 0
    )
    assert cli.main([str(seq_file), "-o", str(tmp_path / "f.html"), "--cards", FAST,
                     *CONFIG_FLAGS[:-2], "--max-rows", "3"]) == 0  # fmt: skip

    assert out.read_text(encoding="utf-8") == (tmp_path / "f.html").read_text(encoding="utf-8")


def test_a_config_file_with_an_unknown_key_exits_1(seq_file, tmp_path, capsys):
    config = _config(tmp_path, ".toml", "max_rowz = 5\n")
    out = tmp_path / "out.html"

    assert cli.main([str(seq_file), "-o", str(out), "--config", str(config)]) == 1

    assert "max_rowz" in capsys.readouterr().err
    assert not out.exists()


def test_a_config_file_with_another_suffix_or_a_bad_value_exits_1(seq_file, tmp_path, capsys):
    out = tmp_path / "out.html"
    other = _config(tmp_path, ".yaml", "max_rows: 5\n")
    bad = _config(tmp_path, ".json", '{"max_rows": "many"}', name="bad")

    for config in (other, bad, tmp_path / "missing.toml"):
        assert cli.main([str(seq_file), "-o", str(out), "--config", str(config)]) == 1
        assert str(config) in capsys.readouterr().err
    assert not out.exists()


def test_a_config_key_of_a_skipped_card_is_ignored(seq_file, tmp_path):
    config = _config(tmp_path, ".toml", "max_rows = 5\n")
    out = tmp_path / "out.html"

    assert (
        cli.main([str(seq_file), "-o", str(out), "--config", str(config), "--cards", "timing"]) == 0
    )

    assert out.read_text(encoding="utf-8") == _page(seq_file, ["timing"])


def test_a_flag_of_a_skipped_card_exits_1_and_names_the_flag_and_the_card(
    seq_file, tmp_path, capsys
):
    out = tmp_path / "out.html"

    assert cli.main([str(seq_file), "-o", str(out), "--cards", "timing", "--max-rows", "5"]) == 1

    err = capsys.readouterr().err
    assert "--max-rows" in err and "blocks" in err
    assert not out.exists()


def test_a_relative_gradient_asc_is_read_from_the_config_file_directory(
    seq_file, tmp_path, write_gradient_asc, monkeypatch
):
    asc = write_gradient_asc()
    site = tmp_path / "site"
    site.mkdir()
    (site / "scanner.asc").write_bytes(asc.read_bytes())
    config = _config(site, ".toml", 'gradient_asc = "scanner.asc"\n')
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    out = tmp_path / "out.html"
    flags_out = tmp_path / "flags.html"

    args = ["--cards", "pns"]
    assert cli.main([str(seq_file), "-o", str(out), "--config", str(config), *args]) == 0
    assert cli.main([str(seq_file), "-o", str(flags_out), "--gradient-asc",
                     str(site / "scanner.asc"), *args]) == 0  # fmt: skip

    assert out.read_text(encoding="utf-8") == flags_out.read_text(encoding="utf-8")


class Spy:
    """What the command passed to `build_cards` (`built`, the keyword arguments of each call)
    and to `run_checks` (`runs`, a pair of the arguments and the keywords of each call)."""

    def __init__(self):
        self.built = []
        self.runs = []


@pytest.fixture
def spy(monkeypatch):
    """Record the calls of the command to `build_cards` and `run_checks`, and call the real
    functions."""
    spy = Spy()

    def build(*args, **kwargs):
        spy.built.append(kwargs)
        return build_cards(*args, **kwargs)

    def run(*args, **kwargs):
        spy.runs.append((args, kwargs))
        return run_checks(*args, **kwargs)

    monkeypatch.setattr(cli, "build_cards", build)
    monkeypatch.setattr(cli, "run_checks", run)
    return spy


@pytest.fixture
def fake_checks(monkeypatch, spy, make_matrix):
    """Like `spy`, but `run_checks` gives a matrix with no results and the names of the
    targets, without running a check. `fake_checks.raises` is the set of file names for which
    it raises `RunError`."""
    spy.raises = set()

    def run(sequence, targets, **kwargs):
        spy.runs.append(((sequence, targets), kwargs))
        if Path(sequence).name in spy.raises:
            raise RunError("a test error")
        return make_matrix([target.name for target in targets])

    monkeypatch.setattr(cli, "run_checks", run)
    return spy


@pytest.fixture
def no_checks(monkeypatch):
    """`run_checks` of the command fails the test when it is called."""

    def run(*args, **kwargs):
        raise AssertionError("run_checks was called")

    monkeypatch.setattr(cli, "run_checks", run)


def _names(profiles):
    return [profile.name for profile in profiles]


def _fails(argv, out, capsys):
    """The command exits 1, writes no page at `out` and reports with its prefix. Returns the
    text of stderr."""
    assert cli.main([*argv, "-o", str(out)]) == 1
    err = capsys.readouterr().err
    assert "pulseq-report:" in err
    assert not out.exists()
    return err


def test_targets_reach_build_cards_with_their_matrix_and_the_checks_run_once(
    seq_file, tmp_path, spy
):
    out = tmp_path / "out.html"

    status = cli.main(
        [str(seq_file), "-o", str(out), "--cards", "timing", "--target", str(A_PATH)]
        + ["--target", str(B_PATH)]
    )

    assert status == 0
    assert out.is_file()
    (kwargs,) = spy.built
    assert _names(kwargs["targets"]) == [A_NAME, B_NAME]
    assert [target.name for target in kwargs["check_results"].targets] == [A_NAME, B_NAME]
    ((args, run_kwargs),) = spy.runs
    assert args[0] == str(seq_file)
    assert _names(args[1]) == [A_NAME, B_NAME]
    assert run_kwargs["select"] is None
    assert run_kwargs["required"] is None
    assert run_kwargs["fast_only"] is False


def test_two_files_run_the_checks_once_for_each_file(seq_file, tmp_path, fake_checks):
    other = tmp_path / "gre.seq"
    gre_sequence().write(str(other))

    status = cli.main(
        [str(seq_file), str(other), "-o", str(tmp_path / "pages"), "--cards", "timing"]
        + ["--target", str(A_PATH)]
    )

    assert status == 0
    assert [args[0] for args, _ in fake_checks.runs] == [str(seq_file), str(other)]
    assert [len(kwargs["check_results"].targets) for kwargs in fake_checks.built] == [1, 1]


@pytest.mark.parametrize(
    ("flags", "analyses"),
    [
        (["--cards", "pns,timing"], ("pns.safe.levels",)),
        (["--cards", "diagram", "--pns-lane"], ("pns.safe.levels",)),
        (["--cards", "timing"], ()),
        (["--cards", "diagram"], ()),
    ],
    ids=["pns-card", "diagram-with-pns-lane", "timing-only", "diagram-without-pns-lane"],
)
def test_the_analyses_of_the_run_follow_the_selected_cards(
    seq_file, tmp_path, fake_checks, flags, analyses
):
    out = tmp_path / "out.html"

    assert cli.main([str(seq_file), "-o", str(out), *flags, "--target", str(A_PATH)]) == 0

    ((_, run_kwargs),) = fake_checks.runs
    assert tuple(run_kwargs["analyses"]) == analyses


def test_a_check_config_gives_the_targets_in_its_order_and_the_checks(
    seq_file, tmp_path, fake_checks
):
    for path in (A_PATH, B_PATH):
        shutil.copy(path, tmp_path / path.name)
    sub = tmp_path / "sub"
    sub.mkdir()
    shutil.copy(A_PATH, sub / "a.toml")
    config = tmp_path / "checks.toml"
    config.write_text(
        "format = 1\n"
        f'targets = ["{B_PATH.name}", "sub/a.toml"]\n'
        'select = ["gradient.amplitude.axis"]\n'
        "fast_only = true\n"
        '[required]\n"gradient.amplitude.axis" = true\n'
    )
    expected = read_check_config(config)
    out = tmp_path / "out.html"

    status = cli.main(
        [str(seq_file), "-o", str(out), "--cards", "timing", "--check-config", str(config)]
    )

    assert status == 0
    ((args, run_kwargs),) = fake_checks.runs
    assert _names(args[1]) == [B_NAME, A_NAME]
    assert list(run_kwargs["select"]) == ["gradient.amplitude.axis"]
    assert run_kwargs["select"] == expected.select
    assert run_kwargs["required"] == expected.required
    assert run_kwargs["required"] is not None
    assert run_kwargs["fast_only"] is True
    (kwargs,) = fake_checks.built
    assert _names(kwargs["targets"]) == [B_NAME, A_NAME]


def test_check_results_give_build_cards_the_matrix_and_run_no_check(
    seq_file, tmp_path, spy, no_checks
):
    profiles = [read_profile(A_PATH), read_profile(B_PATH)]
    matrix = run_checks(str(seq_file), profiles, select=["gradient.amplitude.axis"])
    assert matrix.results
    results = tmp_path / "results.json"
    results.write_text(matrix.to_json(), encoding="utf-8")
    out = tmp_path / "out.html"

    status = cli.main(
        [str(seq_file), "-o", str(out), "--cards", "timing", "--target", str(A_PATH)]
        + ["--target", str(B_PATH), "--check-results", str(results)]
    )

    assert status == 0
    assert out.is_file()
    (kwargs,) = spy.built
    given = kwargs["check_results"]
    assert given.to_json() == ResultMatrix.from_json(results.read_text(encoding="utf-8")).to_json()
    assert len(given.results) == len(matrix.results)
    assert [target.name for target in given.targets] == [A_NAME, B_NAME]


def _seven_profiles(tmp_path):
    paths = []
    for k in range(7):
        text = A_PATH.read_text(encoding="utf-8").replace(
            f'name = "{A_NAME}"', f'name = "target {k}"'
        )
        path = tmp_path / f"t{k}.toml"
        path.write_text(text, encoding="utf-8")
        paths.append(str(path))
    return paths


def _target_flags(*paths):
    return [flag for path in paths for flag in ("--target", str(path))]


def test_a_target_and_a_check_config_together_exit_1(seq_file, tmp_path, capsys, no_checks):
    config = tmp_path / "checks.toml"
    config.write_text(f'format = 1\ntargets = ["{A_PATH}"]\n')
    argv = [str(seq_file), *_target_flags(A_PATH), "--check-config", str(config)]

    _fails(argv, tmp_path / "out.html", capsys)


def test_check_results_without_targets_exit_1(seq_file, tmp_path, capsys, make_matrix, no_checks):
    results = tmp_path / "results.json"
    results.write_text(make_matrix([A_NAME]).to_json(), encoding="utf-8")

    _fails([str(seq_file), "--check-results", str(results)], tmp_path / "out.html", capsys)


def test_check_results_with_two_files_exit_1(seq_file, tmp_path, capsys, make_matrix, no_checks):
    other = tmp_path / "gre.seq"
    gre_sequence().write(str(other))
    results = tmp_path / "results.json"
    results.write_text(make_matrix([A_NAME]).to_json(), encoding="utf-8")
    argv = [str(seq_file), str(other), *_target_flags(A_PATH), "--check-results", str(results)]

    assert cli.main([*argv, "-o", str(tmp_path / "pages")]) == 1

    assert "pulseq-report:" in capsys.readouterr().err
    assert not (tmp_path / "pages").exists()


def test_a_missing_result_file_exits_1_and_names_it(seq_file, tmp_path, capsys, no_checks):
    missing = tmp_path / "missing.json"
    argv = [str(seq_file), *_target_flags(A_PATH), "--check-results", str(missing)]

    assert "missing.json" in _fails(argv, tmp_path / "out.html", capsys)


def test_a_result_file_that_is_not_a_matrix_exits_1(seq_file, tmp_path, capsys, no_checks):
    results = tmp_path / "results.json"
    results.write_text('{"a": 1}', encoding="utf-8")
    argv = [str(seq_file), *_target_flags(A_PATH), "--check-results", str(results)]

    assert "results.json" in _fails(argv, tmp_path / "out.html", capsys)


def test_a_missing_profile_exits_1(seq_file, tmp_path, capsys, no_checks):
    missing = tmp_path / "missing.toml"

    err = _fails([str(seq_file), *_target_flags(missing)], tmp_path / "out.html", capsys)

    assert "missing.toml" in err


def test_a_missing_check_config_exits_1(seq_file, tmp_path, capsys, no_checks):
    argv = [str(seq_file), "--check-config", str(tmp_path / "missing.toml")]

    _fails(argv, tmp_path / "out.html", capsys)


def test_the_same_profile_twice_exits_1(seq_file, tmp_path, capsys, no_checks):
    _fails([str(seq_file), *_target_flags(A_PATH, A_PATH)], tmp_path / "out.html", capsys)


def test_seven_targets_exit_1(seq_file, tmp_path, capsys, no_checks):
    paths = _seven_profiles(tmp_path)

    _fails([str(seq_file), *_target_flags(*paths)], tmp_path / "out.html", capsys)


def test_check_results_for_other_targets_exit_1(seq_file, tmp_path, capsys, make_matrix, no_checks):
    results = tmp_path / "results.json"
    results.write_text(make_matrix([A_NAME]).to_json(), encoding="utf-8")
    argv = [
        str(seq_file),
        *_target_flags(A_PATH, B_PATH),
        "--check-results",
        str(results),
    ]

    _fails(argv, tmp_path / "out.html", capsys)


def _copy_profiles(tmp_path):
    for path in (A_PATH, B_PATH):
        shutil.copy(path, tmp_path / path.name)


def test_the_targets_key_of_a_config_file_gives_the_targets_of_the_flags(
    seq_file, tmp_path, fake_checks
):
    _copy_profiles(tmp_path)
    config = tmp_path / "report.toml"
    config.write_text(f'targets = ["{A_PATH.name}", "{B_PATH.name}"]\n')
    out = tmp_path / "out.html"

    assert (
        cli.main([str(seq_file), "-o", str(out), "--cards", "timing", "--config", str(config)]) == 0
    )
    assert (
        cli.main(
            [str(seq_file), "-o", str(out), "--cards", "timing", *_target_flags(A_PATH, B_PATH)]
        )
        == 0
    )

    (from_config, _), (from_flags, _) = fake_checks.runs
    assert _names(from_config[1]) == _names(from_flags[1]) == [A_NAME, B_NAME]
    assert [p.opts for p in from_config[1]] == [p.opts for p in from_flags[1]]


@pytest.mark.parametrize("line", ['targets = "x"', "check_config = 3", 'check_results = ["x"]'])
def test_a_config_key_of_the_wrong_type_exits_1(seq_file, tmp_path, capsys, no_checks, line):
    config = tmp_path / "report.toml"
    config.write_text(line + "\n")

    _fails([str(seq_file), "--config", str(config)], tmp_path / "out.html", capsys)


def test_a_target_flag_replaces_the_targets_key(seq_file, tmp_path, fake_checks):
    _copy_profiles(tmp_path)
    config = tmp_path / "report.toml"
    config.write_text(f'targets = ["{A_PATH.name}", "{B_PATH.name}"]\n')
    out = tmp_path / "out.html"

    argv = [str(seq_file), "-o", str(out), "--cards", "timing", "--config", str(config)]
    assert cli.main([*argv, "--target", str(B_PATH)]) == 0

    ((args, _),) = fake_checks.runs
    assert _names(args[1]) == [B_NAME]


def test_a_run_error_for_one_file_gives_no_page_for_it_and_the_other_page_is_written(
    seq_file, tmp_path, capsys, fake_checks
):
    other = tmp_path / "gre.seq"
    gre_sequence().write(str(other))
    fake_checks.raises.add(seq_file.name)
    out = tmp_path / "pages"

    status = cli.main(
        [str(seq_file), str(other), "-o", str(out), "--cards", "timing", *_target_flags(A_PATH)]
    )

    assert status == 1
    assert sorted(p.name for p in out.iterdir()) == ["gre.html"]
    assert seq_file.name in capsys.readouterr().err
