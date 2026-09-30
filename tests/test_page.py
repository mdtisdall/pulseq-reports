import json
import re
from importlib import resources

import pytest

from pulseq_reports import page


def test_cards_appear_in_order_with_escaped_titles():
    cards = [
        page.Card(id="first", title="First <card>", body_html="<p>a</p>"),
        page.Card(id="second", title="Second & card", body_html="<p>b</p>"),
        page.Card(id="third", title="Third card", body_html="<p>c</p>"),
    ]
    result = page.render_page("Title", "Subtitle", cards)
    assert "<h2>First &lt;card&gt;</h2>" in result
    assert "<h2>Second &amp; card</h2>" in result
    assert "<h2>Third card</h2>" in result
    assert (
        result.index("<h2>First &lt;card&gt;</h2>")
        < result.index("<h2>Second &amp; card</h2>")
        < result.index("<h2>Third card</h2>")
    )


def test_duplicate_card_id_raises():
    cards = [
        page.Card(id="dup", title="One", body_html="<p>a</p>"),
        page.Card(id="dup", title="Two", body_html="<p>b</p>"),
    ]
    with pytest.raises(ValueError):
        page.render_page("Title", "Subtitle", cards)


@pytest.mark.parametrize("bad_id", ["Bad_id", "1x", ""])
def test_bad_card_id_raises(bad_id):
    cards = [page.Card(id=bad_id, title="Title", body_html="<p>a</p>")]
    with pytest.raises(ValueError):
        page.render_page("Title", "Subtitle", cards)


def test_bad_card_script_name_raises():
    cards = [page.Card(id="a", title="A", body_html="<p>a</p>", script="Bad_Script")]
    with pytest.raises(ValueError):
        page.render_page("Title", "Subtitle", cards)


def test_card_data_element_holds_json():
    data = {"values": [1, 2, 3], "label": "x"}
    cards = [page.Card(id="a", title="A", body_html="<p>a</p>", data=data)]
    result = page.render_page("Title", "Subtitle", cards)
    match = re.search(r'<script type="application/json" id="a-data">(.*?)</script>', result)
    assert match is not None
    payload = match.group(1).replace("<\\/", "</")
    assert json.loads(payload) == data


def test_card_data_element_escapes_close_script():
    data = {"note": "</script><script>alert(1)</script>"}
    cards = [page.Card(id="a", title="A", body_html="<p>a</p>", data=data)]
    result = page.render_page("Title", "Subtitle", cards)
    match = re.search(r'<script type="application/json" id="a-data">(.*?)</script>', result)
    assert match is not None
    payload = match.group(1)
    assert "</script>" not in payload
    assert json.loads(payload.replace("<\\/", "</")) == data


def test_card_without_data_has_no_data_element():
    cards = [page.Card(id="a", title="A", body_html="<p>a</p>", data=None)]
    result = page.render_page("Title", "Subtitle", cards)
    assert "a-data" not in result


def test_collapsed_card_uses_details():
    cards = [
        page.Card(id="a", title="A title", body_html="<p>body</p>", collapsed=True),
    ]
    result = page.render_page("Title", "Subtitle", cards)
    assert "<details>" in result
    assert "<summary>A title</summary>" in result
    assert "<h2>" not in result


def test_card_scripts_and_css_are_on_the_page_once_in_order_of_first_use():
    cards = [
        page.Card(
            id="a",
            title="A",
            body_html="<p>a</p>",
            scripts=("// SCRIPT_ONE", "// SCRIPT_TWO"),
            css=("/* CSS_ONE */",),
        ),
        page.Card(
            id="b",
            title="B",
            body_html="<p>b</p>",
            scripts=("// SCRIPT_THREE", "// SCRIPT_ONE"),
            css=("/* CSS_TWO */", "/* CSS_ONE */"),
        ),
    ]
    result = page.render_page(
        "Title",
        "Subtitle",
        cards,
        extra_scripts=["// EXTRA_SCRIPT"],
        extra_css=["/* EXTRA_CSS */"],
    )
    for marker in ("SCRIPT_ONE", "SCRIPT_TWO", "SCRIPT_THREE", "CSS_ONE", "CSS_TWO"):
        assert result.count(marker) == 1
    script_markers = ["SCRIPT_ONE", "SCRIPT_TWO", "SCRIPT_THREE", "EXTRA_SCRIPT"]
    script_indices = [result.index(m) for m in script_markers]
    assert script_indices == sorted(script_indices)
    assert result.index("const GLanes") < script_indices[0]
    assert script_indices[-1] < result.index("// Runs last on the page.")
    css_markers = ["CSS_ONE", "CSS_TWO", "EXTRA_CSS"]
    css_indices = [result.index(m) for m in css_markers]
    assert css_indices == sorted(css_indices)


def test_card_css_with_close_tag_raises():
    cards = [page.Card(id="a", title="A", body_html="<p>a</p>", css=("p {} </style> x",))]
    with pytest.raises(ValueError):
        page.render_page("Title", "Subtitle", cards)


def test_script_order():
    cards = [page.Card(id="a", title="A", body_html="<p>a</p>", scripts=("// CARD_SCRIPT_MARKER",))]
    extra_scripts = [
        "// EXTRA_ONE_MARKER",
        "// EXTRA_TWO_MARKER",
    ]
    result = page.render_page("Title", "Subtitle", cards, extra_scripts=extra_scripts)
    indices = [
        result.index("const ChartMath"),
        result.index("const PulseqReport"),
        result.index("PulseqReport.mapChart = mapChart;"),
        result.index("const RfProfiles"),
        result.index("const SeqLanes"),
        result.index("const PnsLanes"),
        result.index("const GLanes"),
        result.index("CARD_SCRIPT_MARKER"),
        result.index("EXTRA_ONE_MARKER"),
        result.index("EXTRA_TWO_MARKER"),
        result.index("// Runs last on the page."),
    ]
    assert indices == sorted(indices)


def _topic_cards(**topics):
    """Two cards; `topics` maps a card id to (publishes, subscribes)."""
    return [
        page.Card(id=card_id, title=card_id, body_html="", publishes=pub, subscribes=sub)
        for card_id, (pub, sub) in topics.items()
    ]


def test_two_publishers_of_a_state_topic_raise():
    cards = _topic_cards(one=(("sequence",), ()), two=(("sequence",), ()))
    with pytest.raises(ValueError, match=r"(?s)(?=.*sequence)(?=.*one)(?=.*two)"):
        page.render_page("Title", "Subtitle", cards)


def test_two_subscribers_of_a_request_topic_raise():
    cards = _topic_cards(one=((), ("goto",)), two=((), ("goto",)))
    with pytest.raises(ValueError, match=r"(?s)(?=.*goto)(?=.*one)(?=.*two)"):
        page.render_page("Title", "Subtitle", cards)


def test_topics_that_pass_the_check():
    """One publisher of a state topic and one subscriber of a request topic pass; so do
    many subscribers of a state topic, many publishers of a request topic, and any number
    of cards on a topic that is not in `TOPIC_KINDS`."""
    cards = _topic_cards(
        one=(("sequence", "goto", "plugin-topic"), ("goto",)),
        two=(("goto", "plugin-topic"), ("sequence", "plugin-topic")),
        three=(("plugin-topic",), ("sequence", "plugin-topic")),
    )
    page.render_page("Title", "Subtitle", cards)


def test_checks_are_not_on_the_page():
    check = page.Check(name="CHECK_NAME_MARKER", passed=False, message="CHECK_MESSAGE_MARKER")
    with_checks = page.Card(id="a", title="A", body_html="<p>a</p>", checks=(check,))
    without_checks = page.Card(id="a", title="A", body_html="<p>a</p>")
    result = page.render_page("Title", "Subtitle", [with_checks])
    assert "CHECK_NAME_MARKER" not in result
    assert "CHECK_MESSAGE_MARKER" not in result
    assert result == page.render_page("Title", "Subtitle", [without_checks])


def test_each_script_is_its_own_script_element():
    cards = [page.Card(id="a", title="A", body_html="<p>a</p>")]
    result = page.render_page("Title", "Subtitle", cards, extra_scripts=["// only extra"])
    # chart_math.js, lane_chart.js, map_chart.js, rf_profiles.js, seq_lanes.js,
    # pns_lanes.js, g_lanes.js, the extra script, page.js: no card scripts here.
    assert result.count("<script>\n") == 9


@pytest.mark.parametrize("closer", ["</script>", "</SCRIPT>", "</ScRiPt "])
def test_extra_script_with_close_tag_raises(closer):
    cards = [page.Card(id="a", title="A", body_html="<p>a</p>")]
    with pytest.raises(ValueError):
        page.render_page("Title", "Subtitle", cards, extra_scripts=[f"bad {closer} here"])


def test_extra_css_follows_the_library_css():
    cards = [page.Card(id="a", title="A", body_html="<p>a</p>")]
    extra_css = ["/* EXTRA_CSS_ONE */", "/* EXTRA_CSS_TWO */"]
    result = page.render_page("Title", "Subtitle", cards, extra_css=extra_css)
    assert result.count("<style>") == 1
    style = result[result.index("<style>") : result.index("</style>")]
    css_path = resources.files("pulseq_reports").joinpath("assets", "report.css")
    library_css = css_path.read_text(encoding="utf-8")
    indices = [
        style.index(library_css),
        style.index("EXTRA_CSS_ONE"),
        style.index("EXTRA_CSS_TWO"),
    ]
    assert indices == sorted(indices)
    assert indices[0] + len(library_css) < indices[1]


@pytest.mark.parametrize("closer", ["</style>", "</STYLE>", "</StYlE "])
def test_extra_css_with_close_tag_raises(closer):
    cards = [page.Card(id="a", title="A", body_html="<p>a</p>")]
    with pytest.raises(ValueError):
        page.render_page("Title", "Subtitle", cards, extra_css=[f"p {{}} {closer} here"])


@pytest.mark.parametrize("argument", ["extra_scripts", "extra_css"])
def test_str_in_place_of_a_list_raises(argument):
    """A `str` is a sequence of one-character texts, so without the check each character
    would become its own script element or CSS text."""
    cards = [page.Card(id="a", title="A", body_html="<p>a</p>")]
    with pytest.raises(TypeError, match=argument):
        page.render_page("Title", "Subtitle", cards, **{argument: "p { color: red; }"})


def test_library_css_selects_no_element_id():
    """The caller gives each card its id (`card_id`), so a `#id` selector in the library's
    CSS either styles nothing or styles one project's own card."""
    css_path = resources.files("pulseq_reports").joinpath("assets", "report.css")
    css = re.sub(r"/\*.*?\*/", "", css_path.read_text(encoding="utf-8"), flags=re.DOTALL)
    selectors = re.findall(r"([^{}]*)\{", css)
    assert selectors
    assert [s.strip() for s in selectors if "#" in s] == []


def test_substitute_replaces_every_placeholder():
    result = page._substitute("__A__-__B__", {"__A__": "1", "__B__": "2"})
    assert result == "1-2"


def test_substitute_raises_on_unresolved_placeholder():
    with pytest.raises(ValueError, match="__MISSING__"):
        page._substitute("before __MISSING__ after", {"__A__": "1"})


def test_substitute_keeps_placeholder_shaped_value_as_is():
    result = page._substitute("__A__", {"__A__": "__MISSING__"})
    assert result == "__MISSING__"


def test_render_page_with_placeholder_shaped_card_body_does_not_raise():
    cards = [page.Card(id="a", title="A", body_html="<p>__FOO__</p>")]
    result = page.render_page("Title", "Subtitle", cards)
    assert "__FOO__" in result


def test_write_page_matches_render_page(tmp_path):
    cards = [page.Card(id="a", title="A", body_html="<p>a</p>")]
    extra_scripts = ["// EXTRA_SCRIPT_MARKER"]
    extra_css = ["/* EXTRA_CSS_MARKER */"]
    expected = page.render_page(
        "Title", "Subtitle", cards, extra_scripts=extra_scripts, extra_css=extra_css
    )
    out_path = tmp_path / "report.html"
    page.write_page(
        out_path, "Title", "Subtitle", cards, extra_scripts=extra_scripts, extra_css=extra_css
    )
    assert out_path.read_text(encoding="utf-8") == expected
    assert "EXTRA_SCRIPT_MARKER" in expected
    assert "EXTRA_CSS_MARKER" in expected


def test_card_asset_bad_name_raises():
    with pytest.raises(ValueError):
        page.card_asset("../x")


def test_card_asset_missing_name_raises():
    with pytest.raises((FileNotFoundError, OSError)):
        page.card_asset("does-not-exist")


def test_rendered_page_has_no_leftover_placeholder():
    cards = [page.Card(id="a", title="A", body_html="<p>a</p>")]
    result = page.render_page("Title", "Subtitle", cards)
    assert re.search(r"__[A-Z_]+__", result) is None
