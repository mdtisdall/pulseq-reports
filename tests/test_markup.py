import dataclasses
import html

import pytest
from pulseq_analysis.seq_index import sequence_index
from synthetic import spin_echo_sequence

from pulseq_reports import markup
from pulseq_reports.targets import report_targets


def test_zoom_controls_markup():
    expected = (
        '<div class="controls" role="group" aria-label="Zoom" data-zoom-for="diagram">'
        '<button type="button" data-zoom="10" aria-label="Zoom in 10 times">×10</button>'
        '<button type="button" data-zoom="2" aria-label="Zoom in 2 times">×2</button>'
        '<button type="button" data-zoom="0.5" aria-label="Zoom out 2 times">×0.5</button>'
        '<button type="button" data-zoom="0.1" aria-label="Zoom out 10 times">×0.1</button>'
        '<button type="button" data-zoom="reset">Reset</button></div>'
    )
    assert markup.zoom_controls("diagram") == expected

    escaped_id = html.escape('a"b')
    assert markup.zoom_controls('a"b') == expected.replace(
        'data-zoom-for="diagram"', f'data-zoom-for="{escaped_id}"'
    )


def test_table_escapes_html():
    out = markup.html_table(
        ["<h1>&\"'"],
        [["<script>alert(1)</script>&\"'"]],
    )
    assert "<h1>" not in out
    assert "<script>" not in out
    assert html.escape("<h1>&\"'") in out
    assert html.escape("<script>alert(1)</script>&\"'") in out


def test_fmt_gives_three_significant_digits_and_a_minus_sign():
    assert markup.fmt(12.3456) == "12.3"
    assert markup.fmt(0.000123456) == "0.000123"
    assert markup.fmt(123456.0) == "1.23e+05"
    assert markup.fmt(-2.5) == "−2.5"
    assert "-" not in markup.fmt(-2.5)


def test_lanes_json_converts_lanes_in_field_order_and_keeps_dicts():
    lane = markup.Lane(
        id="gx",
        title="Gx",
        unit="mT/m",
        color="gx",
        segments=[[[0.0, 0.0], [1.0, 2.0]]],
        domain=[-2.2, 2.2],
        ticks=[-2.0, 0.0, 2.0],
        tick_labels=["−2", "0", "2"],
    )
    gate = {"id": "adc", "kind": "gate", "windows": [[0.0, 1.0]]}
    out = markup.lanes_json([lane, gate])
    assert list(out[0]) == [
        "id",
        "title",
        "unit",
        "color",
        "kind",
        "segments",
        "domain",
        "ticks",
        "tick_labels",
        "empty",
        "fill",
    ]
    assert out[0]["kind"] == "line"
    assert out[0]["segments"] == [[[0.0, 0.0], [1.0, 2.0]]]
    assert out[0]["empty"] is False
    assert out[0]["fill"] is None
    assert out[1] is gate


def test_show_button_has_the_play_index_of_the_block_hidden_and_an_escaped_label():
    index = sequence_index(spin_echo_sequence())
    # pypulseq numbers the blocks from 1, so a block id is its play index plus 1.
    assert list(index.block_id) == list(range(1, len(index.block_id) + 1))

    for play, block_id in enumerate(index.block_id):
        button = markup.show_button_html(index, int(block_id), "Show <b>")
        assert button.startswith("<button")
        assert f'data-block="{play}"' in button
        assert " hidden" in button
        assert button.endswith(f"{html.escape('Show <b>')}</button>")
        assert "<b>" not in button


def test_show_button_raises_for_a_block_that_the_sequence_does_not_have():
    index = sequence_index(spin_echo_sequence())

    for block_id in (0, int(index.block_id.max()) + 1):
        with pytest.raises(ValueError, match=str(block_id)):
            markup.show_button_html(index, block_id, "Show")


def test_target_legend_is_empty_for_no_targets():
    assert markup.target_legend_html([]) == ""
    assert markup.target_legend_html(()) == ""


def test_target_legend_lists_the_targets_in_order_with_their_colors(make_profile):
    targets = report_targets([make_profile(name) for name in ("zeta", "alpha", "mid")])

    legend = markup.target_legend_html(targets)

    assert legend.startswith("<ul")
    assert legend.endswith("</ul>")
    assert legend.count("<li>") == 3
    positions = [legend.index(name) for name in ("zeta", "alpha", "mid")]
    assert positions == sorted(positions)
    colors = [legend.index(f"var(--target-{k})") for k in (1, 2, 3)]
    assert colors == sorted(colors)
    assert "var(--target-4)" not in legend
    for item, name, k in zip(legend.split("<li>")[1:], ("zeta", "alpha", "mid"), (1, 2, 3)):
        assert name in item
        assert f"var(--target-{k})" in item


def test_target_legend_escapes_the_name(make_profile):
    name = "A <b>&\"' scanner"
    profile = dataclasses.replace(make_profile("x"), name=name)

    legend = markup.target_legend_html(report_targets([profile]))

    assert html.escape(name) in legend
    assert "<b>" not in legend


def test_target_legend_gives_an_unsupported_target_its_reason(make_profile):
    profiles = [make_profile("ok"), make_profile("sodium", "gamma = 11.262e6")]
    targets = report_targets(profiles)
    reason = '<&> "reason"'
    targets = (targets[0], dataclasses.replace(targets[1], reason=reason))

    legend = markup.target_legend_html(targets)

    first, second = legend.split("<li>")[1:]
    assert "sodium" in second
    assert html.escape(reason) in second
    assert reason not in legend
    assert "ok" in first
    assert "reason" not in first
