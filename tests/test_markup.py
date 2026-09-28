import html

from pulseq_reports import markup


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
