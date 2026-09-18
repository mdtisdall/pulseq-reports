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
    assert markup._zoom_controls("diagram") == expected

    escaped_id = html.escape('a"b')
    assert markup._zoom_controls('a"b') == expected.replace(
        'data-zoom-for="diagram"', f'data-zoom-for="{escaped_id}"'
    )


def test_table_escapes_html():
    out = markup._table(
        ["<h1>&\"'"],
        [["<script>alert(1)</script>&\"'"]],
    )
    assert "<h1>" not in out
    assert "<script>" not in out
    assert html.escape("<h1>&\"'") in out
    assert html.escape("<script>alert(1)</script>&\"'") in out
