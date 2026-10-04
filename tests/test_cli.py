import json

import pypulseq as pp
import pytest
from plugin_card import SPEC
from synthetic import gre_sequence, spin_echo_sequence

from pulseq_reports import __version__, cli, options, registry
from pulseq_reports.grad_limits import HardwareLimits
from pulseq_reports.page import render_page
from pulseq_reports.registry import build_cards, discover

FAST = "gradient-limits,blocks,gradient-spectrum"


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
