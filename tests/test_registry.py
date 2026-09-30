import dataclasses
import inspect
import logging
import math

import pypulseq as pp
import pytest
from plugin_card import CSS, SCRIPT, SPEC, make_spec
from synthetic import SYSTEM, spin_echo_sequence

from pulseq_reports import options, page, registry
from pulseq_reports.cards.blocks import blocks_card
from pulseq_reports.cards.definitions import definitions_card
from pulseq_reports.cards.diagram import diagram_card
from pulseq_reports.cards.gradient_limits import gradient_limits_card
from pulseq_reports.cards.pns import pns_card
from pulseq_reports.cards.rf_exposure import rf_exposure_card
from pulseq_reports.cards.rf_profile import rf_profile_card
from pulseq_reports.cards.spectrum import spectrum_card
from pulseq_reports.cards.timing import timing_card
from pulseq_reports.grad_limits import HardwareLimits
from pulseq_reports.page import Card
from pulseq_reports.registry import CardSpec, ReportContext, build_cards, discover
from pulseq_reports.waveforms import full_window

LIBRARY_CARDS = [
    "timing",
    "rf-exposure",
    "diagram",
    "rf-profile",
    "gradient-spectrum",
    "pns",
    "gradient-limits",
    "definitions",
    "blocks",
]

PLUGIN_LABEL = "plugin_card:SPEC"


@pytest.fixture
def add_specs(monkeypatch):
    """`add_specs((label, spec), ...)` adds specs to the ones that discovery finds. The
    label is the name of the entry point in an error message."""
    extra = []
    found = registry._load_entry_points
    monkeypatch.setattr(registry, "_load_entry_points", lambda: [*found(), *extra])

    def add(*labeled):
        extra.extend(labeled)

    return add


@pytest.fixture
def plugin(add_specs):
    add_specs((PLUGIN_LABEL, SPEC))


def _ids(cards):
    return [card.id for card in cards]


def test_plugin_card_is_in_the_report_in_its_order_with_its_assets_once(plugin, add_specs):
    add_specs(
        ("late:SPEC", make_spec("plugin-late", 99999)), ("early:SPEC", make_spec("plugin-early", 1))
    )
    seq = spin_echo_sequence()
    names = ["plugin-early", "plugin-demo", "plugin-late"]

    cards = build_cards(seq, cards=names, max_rows=7)

    assert _ids(cards) == names
    assert all('data-max-rows="7"' in card.body_html for card in cards)
    text = page.render_page("Title", "Subtitle", cards)
    assert text.count(SCRIPT) == 1
    assert text.count(CSS) == 1
    # The option has its default when the caller gives no value.
    default = build_cards(seq, cards=["plugin-demo"])[0]
    assert f'data-max-rows="{options.max_rows.default}"' in default.body_html


def test_two_specs_with_one_name_raise_and_no_card_is_built(plugin, add_specs):
    built = []

    def build(ctx):
        built.append(ctx)
        return Card(id="recorder", title="Recorder", body_html="")

    add_specs(
        ("clash:SPEC", make_spec("plugin-demo", 1)),
        ("recorder:SPEC", CardSpec("recorder", 2, build)),
    )

    with pytest.raises(ValueError) as error:
        build_cards(spin_echo_sequence())

    assert PLUGIN_LABEL in str(error.value)
    assert "clash:SPEC" in str(error.value)
    assert built == []


def test_two_options_with_one_name_raise(plugin, add_specs):
    other = dataclasses.replace(options.max_rows)
    assert other is not options.max_rows
    add_specs(("other:SPEC", make_spec("plugin-other", 56, read=(other,))))

    with pytest.raises(ValueError) as error:
        discover()

    message = str(error.value)
    assert "plugin-demo" in message
    assert "plugin-other" in message
    assert "max_rows" in message


def test_a_spec_reads_only_the_options_it_declares(plugin, add_specs):
    # `max_rows` is declared by the plugin, and not by this spec.
    reader = make_spec("plugin-reader", 1, read=())
    reader = dataclasses.replace(reader, build=lambda ctx: ctx.option(options.max_rows))
    add_specs(("reader:SPEC", reader))
    seq = spin_echo_sequence()

    with pytest.raises(ValueError, match="max_rows"):
        ReportContext(seq, [reader]).option(options.max_rows)
    # In a report, the error is the card's error: the card that declares the option
    # is built, and so is the card that does not.
    cards = build_cards(seq, cards=["plugin-reader", "plugin-demo"])
    assert _ids(cards) == ["plugin-reader", "plugin-demo"]
    assert [check.passed for check in cards[0].checks] == [False]
    assert "max_rows" in cards[0].body_html
    assert cards[1].checks == ()


@pytest.mark.parametrize("failing", ["build", "when"])
def test_a_card_that_raises_is_an_error_card_and_the_others_are_built(
    plugin, add_specs, caplog, failing
):
    error = NotImplementedError("<b>no rotations")

    def raise_error(ctx):
        raise error

    fields = {"build": make_spec("plugin-broken", 1, read=()).build, "when": None}
    fields[failing] = raise_error
    broken = CardSpec("plugin-broken", 1, **fields)
    add_specs(("broken:SPEC", broken))

    with caplog.at_level(logging.ERROR, logger="pulseq_reports"):
        cards = build_cards(spin_echo_sequence(), cards=["plugin-broken", "plugin-demo"])

    assert _ids(cards) == ["plugin-broken", "plugin-demo"]
    broken_card, good_card = cards
    assert broken_card.title == "plugin-broken: error"
    assert len(broken_card.checks) == 1
    assert broken_card.checks[0].passed is False
    assert "NotImplementedError" in broken_card.checks[0].message
    assert "&lt;b&gt;no rotations" in broken_card.body_html
    assert "<b>" not in broken_card.body_html
    assert good_card.checks == ()
    assert 'data-max-rows="' in good_card.body_html
    records = [r for r in caplog.records if r.name == "pulseq_reports"]
    assert len(records) == 1
    assert records[0].exc_info[1] is error
    # The error card is a valid card of a page.
    page.render_page("Title", "Subtitle", cards)


def test_cards_and_skip_select_cards(plugin, add_specs):
    add_specs(
        ("a:SPEC", make_spec("plugin-a", 1)),
        ("c:SPEC", make_spec("plugin-c", 99999)),
    )
    seq = spin_echo_sequence()
    names = ["plugin-a", "plugin-demo", "plugin-c"]

    assert _ids(build_cards(seq, cards=names)) == names
    assert _ids(build_cards(seq, cards=["plugin-c", "plugin-a"])) == ["plugin-a", "plugin-c"]
    assert _ids(build_cards(seq, cards=names, skip=["plugin-demo"])) == ["plugin-a", "plugin-c"]
    assert "plugin-demo" not in _ids(build_cards(seq, skip=["plugin-demo"]))
    assert "plugin-demo" in _ids(build_cards(seq))


@pytest.mark.parametrize("argument", ["cards", "skip"])
def test_an_unknown_card_name_raises(plugin, argument):
    with pytest.raises(ValueError, match="plugin-nope"):
        build_cards(spin_echo_sequence(), **{argument: ["plugin-demo", "plugin-nope"]})


def test_an_option_of_no_selected_card_raises(plugin, add_specs):
    add_specs(("periodic:SPEC", make_spec("plugin-periodic", 56, read=(options.periodic,))))
    seq = spin_echo_sequence()

    with pytest.raises(TypeError, match="periodic"):
        build_cards(seq, cards=["plugin-demo"], periodic=False)
    with pytest.raises(TypeError, match="periodic"):
        build_cards(seq, cards=["plugin-demo"], skip=["plugin-periodic"], periodic=False)
    cards = build_cards(seq, cards=["plugin-demo", "plugin-periodic"], periodic=False)
    assert 'data-periodic="False"' in cards[1].body_html


@pytest.mark.parametrize(
    ("declaration", "topic"),
    [("publishes", "anchor"), ("subscribes", "goto")],
)
def test_when_can_depend_on_the_topics_of_the_selected_cards(plugin, add_specs, declaration, topic):
    def when(ctx):
        return getattr(ctx, declaration)(topic)

    add_specs(
        ("needs:SPEC", make_spec("plugin-needs", 1, read=(), when=when)),
        ("declares:SPEC", make_spec("plugin-declares", 2, read=(), **{declaration: (topic,)})),
    )
    seq = spin_echo_sequence()

    both = build_cards(seq, cards=["plugin-needs", "plugin-declares"])
    assert _ids(both) == ["plugin-needs", "plugin-declares"]
    assert _ids(build_cards(seq, cards=["plugin-needs", "plugin-demo"])) == ["plugin-demo"]


def test_discovery_finds_the_nine_library_cards_in_their_order():
    specs = discover()

    assert [spec.name for spec in specs] == LIBRARY_CARDS
    assert [spec.order for spec in specs] == sorted(spec.order for spec in specs)


def _only_check(seq, name, **option_values):
    """The one check of the one card `name` that `build_cards` makes for `seq`."""
    (card,) = build_cards(seq, cards=[name], **option_values)
    assert card.id == name
    (check,) = card.checks
    return check


def _timing_error_sequence():
    """One RF block whose delay is below the RF dead time, so pypulseq's timing check fails."""
    seq = pp.Sequence(SYSTEM)
    rf = pp.make_block_pulse(flip_angle=math.pi / 2, duration=1e-3, system=SYSTEM)
    rf.delay = 0
    seq.add_block(rf)
    return seq


def _oblique_sequence():
    """One block with Gx and Gy at 0.8 of `max_grad` and a slew well below `max_slew`: each
    axis is below its limit, and the peak of |G| is 1.13 times the limit."""
    seq = pp.Sequence(SYSTEM)
    axes = [
        pp.make_trapezoid(
            channel=channel,
            amplitude=0.8 * SYSTEM.max_grad,
            rise_time=300e-6,
            flat_time=1e-3,
            system=SYSTEM,
        )
        for channel in ("x", "y")
    ]
    seq.add_block(*axes)
    return seq


@pytest.mark.parametrize("name", ["timing", "gradient-limits", "pns"])
def test_a_check_passes_for_a_sequence_inside_its_limits(name):
    check = _only_check(spin_echo_sequence(), name)

    assert check.passed is True


def test_the_timing_check_fails_for_a_timing_error():
    check = _only_check(_timing_error_sequence(), "timing")

    assert check.passed is False


@pytest.mark.parametrize(
    ("limits", "quantity"),
    [
        (HardwareLimits(max_grad_mt_per_m=5.0, max_slew_t_per_m_per_s=1e6, label="tight"), "peak"),
        (HardwareLimits(max_grad_mt_per_m=1e6, max_slew_t_per_m_per_s=10.0, label="tight"), "slew"),
    ],
)
def test_the_gradient_limits_check_fails_for_limits_below_the_peak(limits, quantity):
    check = _only_check(spin_echo_sequence(), "gradient-limits", limits=limits)

    assert check.passed is False
    # The readout is on x, so the message names that axis, the quantity and the table.
    assert f"Gx {quantity}" in check.message
    assert "whole file" in check.message


@pytest.mark.parametrize(("check_norms", "passed"), [(True, False), (False, True)])
def test_the_gradient_limits_check_of_the_norm_needs_check_norms(check_norms, passed):
    seq = _oblique_sequence()
    # Each axis is below its limit, so the axes do not fail the check.
    assert _only_check(seq, "gradient-limits").passed is True

    check = _only_check(seq, "gradient-limits", check_norms=check_norms)

    assert check.passed is passed
    if not passed:
        assert "|G|" in check.message


def test_the_pns_check_fails_for_a_peak_of_100_percent_or_more(write_gradient_asc):
    seq = spin_echo_sequence()
    low_threshold = write_gradient_asc(limit_scale=0.1)

    check = _only_check(seq, "pns", gradient_asc=low_threshold)

    assert check.passed is False


def test_without_the_diagram_the_rf_profile_card_is_not_built():
    seq = spin_echo_sequence()

    assert _ids(build_cards(seq, cards=["rf-profile"])) == []
    assert _ids(build_cards(seq, skip=["diagram"])).count("rf-profile") == 0
    assert _ids(build_cards(seq, cards=["diagram", "rf-profile"])) == ["diagram", "rf-profile"]


def test_render_page_raises_for_two_diagram_cards():
    seq = spin_echo_sequence()
    windows = [full_window(seq)]
    cards = [diagram_card(seq, windows, card_id=name) for name in ("diagram-a", "diagram-b")]

    with pytest.raises(ValueError, match="sequence"):
        page.render_page("Title", "Subtitle", cards)


def test_render_page_raises_for_two_cards_that_subscribe_to_goto():
    seq = spin_echo_sequence()
    diagram = diagram_card(seq, [full_window(seq)])
    other = Card(id="other", title="Other", body_html="", subscribes=("goto",))

    with pytest.raises(ValueError, match="goto"):
        page.render_page("Title", "Subtitle", [diagram, other])


def test_render_page_does_not_check_a_plugin_topic():
    cards = [
        Card(
            id=name,
            title=name,
            body_html="",
            publishes=("plugin-topic",),
            subscribes=("plugin-topic",),
        )
        for name in ("plugin-a", "plugin-b")
    ]

    page.render_page("Title", "Subtitle", cards)


_BUILDERS = {
    "timing": timing_card,
    "rf-exposure": rf_exposure_card,
    "diagram": diagram_card,
    "rf-profile": rf_profile_card,
    "gradient-spectrum": spectrum_card,
    "pns": pns_card,
    "gradient-limits": gradient_limits_card,
    "definitions": definitions_card,
    "blocks": blocks_card,
}
# The keywords that the command line does not set (section 4.4, item 3 of the plan).
_NOT_OPTIONS = {"card_id", "windows"}


def test_the_options_of_each_spec_are_the_keywords_of_its_builder():
    specs = {spec.name: spec for spec in discover()}
    assert set(specs) == set(_BUILDERS)

    for name, builder in _BUILDERS.items():
        spec = specs[name]
        parameters = {
            parameter.name: parameter
            for parameter in inspect.signature(builder).parameters.values()
            if parameter.kind is inspect.Parameter.KEYWORD_ONLY
        }
        declared = {option.name: option for option in spec.options}
        assert set(parameters) - _NOT_OPTIONS == set(declared), name
        for option_name, option in declared.items():
            assert parameters[option_name].default == option.default, (name, option_name)
        assert parameters["card_id"].default == name
