import dataclasses
import inspect
import logging

import pypulseq as pp
import pytest
from plugin_card import CSS, SCRIPT, SPEC, make_spec
from synthetic import spin_echo_sequence

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
from pulseq_reports.page import Card
from pulseq_reports.registry import CardSpec, ReportContext, build_cards, discover
from pulseq_reports.targets import MAX_TARGETS, ReportTarget
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
    assert "max_rows" in cards[0].error
    assert "max_rows" in cards[0].body_html
    assert cards[1].error is None


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
    assert broken_card.error == "NotImplementedError: <b>no rotations"
    assert "&lt;b&gt;no rotations" in broken_card.body_html
    assert "<b>" not in broken_card.body_html
    assert good_card.error is None
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


def test_a_card_that_builds_has_no_error():
    cards = build_cards(spin_echo_sequence())

    assert cards
    assert [card.error for card in cards] == [None] * len(cards)


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


@pytest.fixture
def seen(add_specs):
    """The `ReportContext` objects that the build of a recording card has seen."""
    contexts = []

    def build(ctx):
        contexts.append(ctx)
        return Card(id="recorder", title="Recorder", body_html="")

    add_specs(("recorder:SPEC", CardSpec("recorder", 1, build)))
    return contexts


def _build_recorder(seen, seq=None, **keywords):
    build_cards(seq or spin_echo_sequence(), cards=["recorder"], **keywords)
    (ctx,) = seen
    return ctx


def test_a_report_without_targets_has_no_targets_and_no_check_results(seen):
    ctx = _build_recorder(seen)

    assert ctx.targets == ()
    assert ctx.check_results is None


def test_targets_do_not_change_the_cards_that_are_built(plugin, make_profile):
    seq = spin_echo_sequence()

    without = build_cards(seq)
    with_targets = build_cards(seq, targets=[make_profile("a"), make_profile("b")])

    assert build_cards(seq) == without
    assert with_targets == without


def test_the_context_has_the_report_targets_in_order_with_their_colors(seen, make_profile):
    profiles = [make_profile("b"), make_profile("a", "gamma = 11.262e6")]

    ctx = _build_recorder(seen, targets=profiles)

    assert isinstance(ctx.targets, tuple)
    assert all(isinstance(target, ReportTarget) for target in ctx.targets)
    assert [target.profile for target in ctx.targets] == profiles
    assert [target.color for target in ctx.targets] == ["target-1", "target-2"]
    assert [target.supported for target in ctx.targets] == [True, False]
    assert ctx.check_results is None


def test_the_context_has_the_result_matrix_that_the_caller_gave(seen, make_profile, make_matrix):
    matrix = make_matrix(["b", "a"])

    ctx = _build_recorder(
        seen, targets=[make_profile("b"), make_profile("a")], check_results=matrix
    )

    assert ctx.check_results is matrix


def test_a_sequence_with_another_gamma_raises(plugin):
    sodium = pp.Sequence(pp.Opts(gamma=11.262e6))

    with pytest.raises(ValueError, match="gamma"):
        build_cards(sodium, cards=["plugin-demo"])


def test_more_than_the_most_targets_raise(plugin, make_profile):
    profiles = [make_profile(f"t{k}") for k in range(MAX_TARGETS + 1)]

    with pytest.raises(ValueError, match=str(MAX_TARGETS)):
        build_cards(spin_echo_sequence(), cards=["plugin-demo"], targets=profiles)


def test_two_targets_with_one_name_raise(plugin, make_profile):
    profiles = [make_profile("a"), make_profile("a")]

    with pytest.raises(ValueError, match="'a'"):
        build_cards(spin_echo_sequence(), cards=["plugin-demo"], targets=profiles)


def test_a_target_that_is_not_a_target_profile_raises(plugin):
    with pytest.raises(TypeError, match="TargetProfile"):
        build_cards(spin_echo_sequence(), cards=["plugin-demo"], targets=["a.toml"])


@pytest.mark.parametrize(
    ("target_names", "matrix_names"),
    [
        (["a", "b"], ["a", "c"]),
        (["a", "b"], ["b", "a"]),
        (["a", "b"], ["a"]),
        (["a"], ["a", "b"]),
        ([], ["a"]),
        (["a"], []),
    ],
    ids=[
        "different-name",
        "different-order",
        "missing-target",
        "extra-target",
        "no-targets",
        "no-matrix-targets",
    ],
)
def test_check_results_with_other_target_names_raise(
    plugin, make_profile, make_matrix, target_names, matrix_names
):
    profiles = [make_profile(name) for name in target_names]

    with pytest.raises(ValueError, match="check_results"):
        build_cards(
            spin_echo_sequence(),
            cards=["plugin-demo"],
            targets=profiles,
            check_results=make_matrix(matrix_names),
        )


def test_check_results_that_are_not_a_result_matrix_raise(plugin, make_profile):
    with pytest.raises(TypeError, match="ResultMatrix"):
        build_cards(
            spin_echo_sequence(),
            cards=["plugin-demo"],
            targets=[make_profile("a")],
            check_results={"a": []},
        )


def test_no_card_is_built_when_the_inputs_raise(seen, make_profile, make_matrix):
    with pytest.raises(ValueError):
        build_cards(
            spin_echo_sequence(),
            cards=["recorder"],
            targets=[make_profile("a")],
            check_results=make_matrix(["b"]),
        )

    assert seen == []
