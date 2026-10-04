"""The card interface: how a card declares itself, and how a report finds and builds cards.

A card is a `CardSpec`: its name, its place in the report, a function that builds it from
a `ReportContext`, the `Option` objects that the function reads, and the topics of its
messages. The library's own cards and a plugin's cards are found the same way: each is an
entry point of the group `pulseq_reports.cards` that names a `CardSpec` (`discover`).
`build_cards` builds the cards of one sequence.

The interface can change in 0.3.0.
"""

import html
import importlib.metadata
import logging
import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pypulseq as pp
from pulseq_analysis.seq_utils import GAMMA
from pulseq_checks import ResultMatrix, TargetProfile

from .page import Card
from .targets import ReportTarget, report_targets
from .waveforms import TimeWindow, first_adc_window, full_window

ENTRY_POINT_GROUP = "pulseq_reports.cards"

_NAME_RE = re.compile(r"[a-z][a-z0-9-]*")
_OPTION_NAME_RE = re.compile(r"[a-z][a-z0-9_]*")

_logger = logging.getLogger("pulseq_reports")


@dataclass(frozen=True)
class Flag:
    """One command-line flag of an option.

    `name` is the flag with its dashes, for example `"--max-grad"`. `type` is the type of
    its value: `bool` gives the pair `--name` and `--no-name`, and `int`, `float`, `str`
    and `Path` give one value. The default of a flag is "not given": the command line
    gives `Option.from_flags` only the flags that the caller gave. `choices`, when it is
    not None, are the values that the flag accepts.
    """

    name: str
    type: type
    help: str
    metavar: str | None = None
    choices: tuple[str, ...] | None = None

    @property
    def dest(self) -> str:
        """The name of the flag as a Python name, for example `"max_grad"`."""
        return self.name.lstrip("-").replace("-", "_")


@dataclass(frozen=True)
class OptionCli:
    """The command-line and config-file form of an option whose value is not one flag.

    `flags` are the flags that the option adds. `from_flags(values)` makes the option's
    value from the flags that the caller gave (a dict from `Flag.dest` to value; at least
    one flag is in it). `from_config(value, base_dir)` makes the option's value from its
    value in a config file (JSON or TOML data); `base_dir` is the directory of the config
    file, which a relative path is relative to. Each function raises `ValueError` (or `TypeError`
    for a value of the wrong type), with a message for the caller, when the input is not
    valid.
    """

    flags: tuple[Flag, ...]
    from_flags: Callable[[Mapping[str, object]], object]
    from_config: Callable[[object, Path], object]


_COMMA_TUPLE = tuple[str, ...]
_SIMPLE_TYPES = (bool, int, float, str, Path, _COMMA_TUPLE)


@dataclass(frozen=True, eq=False)
class Option:
    """One option of one or more cards.

    `name` is the keyword of the card builder that the option stands for, in lowercase
    (`[a-z][a-z0-9_]*`). One name has one meaning on a page, and one `Option` object
    (`discover` checks it); a plugin that uses a shared option imports its object from
    `pulseq_reports.options`. `default` is the value when the caller gives none: the
    default of the builder keyword. `help` is the text of the option's flag.

    `type` says how the command line and a config file give the value. `bool`, `int`,
    `float`, `str` and `Path` give one flag (`bool` gives `--name` and `--no-name`), and
    `tuple[str, ...]` gives one flag with a comma list, and a list in a config file. Any
    other type needs `cli`, the `OptionCli` that makes its value.

    Two options are equal only when they are the same object.
    """

    name: str
    type: object
    default: object
    help: str
    cli: OptionCli | None = None

    def __post_init__(self) -> None:
        if not _OPTION_NAME_RE.fullmatch(self.name):
            raise ValueError(f"option name {self.name!r} does not match [a-z][a-z0-9_]*")
        if self.cli is None and self.type not in _SIMPLE_TYPES:
            raise ValueError(f"option {self.name!r} has the type {self.type!r} and needs cli")

    def flags(self) -> tuple[Flag, ...]:
        """The flags that the option adds to the command line."""
        if self.cli is not None:
            return self.cli.flags
        flag_name = "--" + self.name.replace("_", "-")
        if self.type == _COMMA_TUPLE:
            return (Flag(flag_name, str, self.help, metavar="NAME,..."),)
        return (Flag(flag_name, self.type, self.help),)

    def from_flags(self, values: Mapping[str, object]) -> object:
        """The option's value from the flags that the caller gave (`Flag.dest` to value;
        the caller gave at least one). Raises `ValueError` or `TypeError` for a value that is
        not valid."""
        if self.cli is not None:
            return self.cli.from_flags(values)
        value = values[self.flags()[0].dest]
        if self.type == _COMMA_TUPLE:
            return tuple(part.strip() for part in str(value).split(",") if part.strip())
        return value

    def from_config(self, value: object, base_dir: Path) -> object:
        """The option's value from its value in a config file (see `OptionCli`). Raises
        `ValueError` or `TypeError` for a value that is not valid."""
        if self.cli is not None:
            return self.cli.from_config(value, base_dir)
        if self.type is bool:
            ok = isinstance(value, bool)
        elif self.type is int:
            ok = isinstance(value, int) and not isinstance(value, bool)
        elif self.type is float:
            ok = isinstance(value, int | float) and not isinstance(value, bool)
        elif self.type in (str, Path):
            ok = isinstance(value, str)
        else:
            ok = isinstance(value, list | tuple) and all(isinstance(item, str) for item in value)
        if not ok:
            raise ValueError(f"the value of {self.name!r} is not valid: {value!r}")
        if self.type is float:
            return float(value)
        if self.type is Path:
            return Path(value)
        if self.type == _COMMA_TUPLE:
            return tuple(value)
        return value


@dataclass(frozen=True)
class CardSpec:
    """The declaration of one card.

    `name` is the card's name (`[a-z][a-z0-9-]*`); it is also the card's `card_id` in the
    standard report. `order` is a number: the cards of a report are in the order of their
    `order`. `build(ctx)` makes the `Card` from a `ReportContext`. `options` are the
    `Option` objects that `build` reads, and no others. `publishes` and `subscribes` are
    the topics of the card's messages; the card that `build` makes has the same topics.
    `when(ctx)` says if the card applies to the report; with None, it always applies.
    """

    name: str
    order: float
    build: Callable[["ReportContext"], Card]
    options: tuple[Option, ...] = ()
    publishes: tuple[str, ...] = ()
    subscribes: tuple[str, ...] = ()
    when: Callable[["ReportContext"], bool] | None = None


class ReportContext:
    """What a card's `build` and `when` know about the report: the sequence, the values
    of the options, the standard windows, the topics of the selected cards, the targets
    and the result matrix.

    `build_cards` makes one context for a report. `option` and the topics read the
    selected cards' specs, so a card never asks for another card by name. `targets` is a
    tuple of `targets.ReportTarget`, in the order of the targets (empty for a report
    without targets). `check_results` is the `pulseq_checks.ResultMatrix` of the run, or
    None when the caller gave none; `build_cards` never runs checks.
    """

    def __init__(
        self,
        seq: pp.Sequence,
        specs: Sequence[CardSpec],
        values: Mapping[str, object] | None = None,
        *,
        targets: Sequence[ReportTarget] = (),
        check_results: ResultMatrix | None = None,
    ) -> None:
        self.seq = seq
        self.targets = tuple(targets)
        self.check_results = check_results
        self._specs = tuple(specs)
        self._values = dict(values or {})
        self._windows: tuple[TimeWindow, ...] | None = None
        self._current: CardSpec | None = None

    def option(self, option: Option) -> object:
        """The value of `option`: the caller's value, or the option's default. Raises
        `ValueError` when the spec that is being built does not declare `option` (outside
        a card, when no selected spec declares it), so the declarations stay complete."""
        specs = self._specs if self._current is None else (self._current,)
        if not any(option is declared for spec in specs for declared in spec.options):
            owner = "any selected card" if self._current is None else self._current.name
            raise ValueError(
                f"the card {owner!r} reads the option {option.name!r}, and does not declare it"
            )
        return self._values.get(option.name, option.default)

    def windows(self) -> tuple[TimeWindow, ...]:
        """The standard windows of the sequence: the first ADC, and the whole file."""
        if self._windows is None:
            self._windows = (first_adc_window(self.seq), full_window(self.seq))
        return self._windows

    def publishes(self, topic: str) -> bool:
        """True when a selected card declares that it publishes `topic`."""
        return any(topic in spec.publishes for spec in self._specs)

    def subscribes(self, topic: str) -> bool:
        """True when a selected card declares that it subscribes to `topic`."""
        return any(topic in spec.subscribes for spec in self._specs)


def _load_entry_points() -> list[tuple[str, object]]:
    """The label and the object of each entry point of the group `pulseq_reports.cards`,
    in the order of their names. A test replaces this function to add specs."""
    found = sorted(
        importlib.metadata.entry_points(group=ENTRY_POINT_GROUP), key=lambda point: point.name
    )
    loaded = []
    for point in found:
        label = f"{point.name} = {point.value}"
        try:
            loaded.append((label, point.load()))
        except Exception as error:
            raise RuntimeError(f"could not load the entry point {label!r}: {error}") from error
    return loaded


def _check_spec(label: str, spec: object) -> CardSpec:
    if not isinstance(spec, CardSpec):
        raise TypeError(f"the entry point {label!r} is not a CardSpec: {spec!r}")
    if not isinstance(spec.name, str) or not _NAME_RE.fullmatch(spec.name):
        raise ValueError(
            f"the card name {spec.name!r} of the entry point {label!r} does not match "
            "[a-z][a-z0-9-]*"
        )
    if (
        isinstance(spec.order, bool)
        or not isinstance(spec.order, int | float)
        or not math.isfinite(spec.order)
    ):
        raise ValueError(f"the order {spec.order!r} of the card {spec.name!r} is not a number")
    if not callable(spec.build):
        raise TypeError(f"the build of the card {spec.name!r} ({label!r}) is not callable")
    if spec.when is not None and not callable(spec.when):
        raise TypeError(f"the when of the card {spec.name!r} ({label!r}) is not callable")
    for option in spec.options:
        if not isinstance(option, Option):
            raise TypeError(
                f"the card {spec.name!r} ({label!r}) has an option that is not an Option"
            )
    return spec


def discover() -> list[CardSpec]:
    """The `CardSpec` of each entry point of the group `pulseq_reports.cards`, in the
    order of their `order` (then their name).

    Before any card is built, it raises `TypeError` for an entry point
    that is not a `CardSpec`, for a `build` or `when` that is not callable, and for an
    option that is not an `Option`. It raises `ValueError` for a name or an order that is
    not valid; for two specs with one name (the message names both entry points); and for
    two options with one name that are not the same `Option` object (the message names both
    cards and the option).
    """
    labeled = [(label, _check_spec(label, spec)) for label, spec in _load_entry_points()]
    labels: dict[str, str] = {}
    for label, spec in labeled:
        if spec.name in labels:
            raise ValueError(
                f"two cards have the name {spec.name!r}: the entry points "
                f"{labels[spec.name]!r} and {label!r}"
            )
        labels[spec.name] = label
    specs = sorted((spec for _, spec in labeled), key=lambda spec: (spec.order, spec.name))
    owners: dict[str, tuple[str, Option]] = {}
    for spec in specs:
        for option in spec.options:
            if option.name not in owners:
                owners[option.name] = (spec.name, option)
            elif owners[option.name][1] is not option:
                raise ValueError(
                    f"the cards {owners[option.name][0]!r} and {spec.name!r} declare different "
                    f"options with the name {option.name!r}: one name has one meaning, and one "
                    "Option object"
                )
    return specs


def _error_card(spec: CardSpec, error: Exception) -> Card:
    message = f"{type(error).__name__}: {error}"
    return Card(
        id=spec.name,
        title=f"{spec.name}: error",
        body_html=f'<p class="muted">{html.escape(message)}</p>',
        error=message,
    )


def _names(name: str, value: Iterable[str] | None, known: set[str]) -> list[str]:
    if isinstance(value, str):
        raise TypeError(f"{name} must be a list of card names, not a str")
    names = [] if value is None else list(value)
    unknown = sorted(set(names) - known)
    if unknown:
        raise ValueError(
            f"{name} has the unknown card names {unknown}; the cards are {sorted(known)}"
        )
    return names


def _check_inputs(
    seq: pp.Sequence, profiles: Sequence[TargetProfile], check_results: ResultMatrix | None
) -> tuple[ReportTarget, ...]:
    """The `ReportTarget` of each of `profiles`, after the checks of `build_cards`."""
    if seq.system.gamma != GAMMA:
        raise ValueError(
            f"the sequence has the gamma {seq.system.gamma:g} Hz/T, and pulseq-reports "
            f"supports only the proton gamma ({GAMMA:g} Hz/T)"
        )
    targets = report_targets(profiles)
    if check_results is not None:
        if not isinstance(check_results, ResultMatrix):
            raise TypeError(
                f"check_results must be a ResultMatrix, not {type(check_results).__name__}"
            )
        given = [target.profile.name for target in targets]
        matrix = [target.name for target in check_results.targets]
        if matrix != given:
            raise ValueError(
                f"the targets of check_results are {matrix}, and the targets of the report are "
                f"{given}: they must be the same names, in the same order"
            )
    return targets


def build_cards(
    seq: pp.Sequence,
    *,
    cards: Iterable[str] | None = None,
    skip: Iterable[str] = (),
    targets: Sequence[TargetProfile] = (),
    check_results: ResultMatrix | None = None,
    **options: object,
) -> list[Card]:
    """The cards of the report of `seq`, in the order of their specs (`discover`).

    `cards` are the names of the cards to build (all of them when None), and `skip` the
    names to leave out. `targets` are the target profiles of the report (`TargetProfile`
    of pulseq-checks, at most `targets.MAX_TARGETS`, with distinct names), and
    `check_results` is the `ResultMatrix` of a run of pulseq-checks for those targets, or
    None. `build_cards` never runs checks: the caller runs `pulseq_checks.run_checks` and
    gives the matrix. `options` are the values of the options, by option name; an option
    that the caller does not give has its default. A card whose `when` is false is not
    built.

    Raises `ValueError` when `seq.system.gamma` is not the proton gamma (`GAMMA`), for
    more than `targets.MAX_TARGETS` targets or two targets with one name, when the target
    names of `check_results` are not the names of `targets` in the same order, for a name
    in `cards` or `skip` that no spec has, and for the errors of `discover`. Raises
    `TypeError` for a target that is not a `TargetProfile`, for `check_results` that is
    not a `ResultMatrix`, and for an option that no selected card declares.
    When the `when` or the `build` of a card raises an exception (for example
    `NotImplementedError`, for a sequence that the card refuses), the card is an error card:
    its `id` is the spec's name, its title is "<name>: error", its body has the message, and
    its `error` is the message. The exception, with its traceback, goes to the logger
    `pulseq_reports`, and the other cards are built.
    """
    report = _check_inputs(seq, targets, check_results)
    all_specs = discover()
    known = {spec.name for spec in all_specs}
    wanted = set(_names("cards", cards, known)) if cards is not None else known
    left_out = set(_names("skip", skip, known))
    selected = [spec for spec in all_specs if spec.name in wanted and spec.name not in left_out]
    declared = {option.name for spec in selected for option in spec.options}
    unexpected = sorted(set(options) - declared)
    if unexpected:
        raise TypeError(
            f"no selected card declares the options {unexpected}; the selected cards declare "
            f"{sorted(declared)}"
        )
    ctx = ReportContext(seq, selected, options, targets=report, check_results=check_results)
    built = []
    for spec in selected:
        ctx._current = spec
        try:
            if spec.when is not None and not spec.when(ctx):
                continue
            card = spec.build(ctx)
            if not isinstance(card, Card):
                raise TypeError(f"build returned {type(card).__name__}, not a Card")
        except Exception as error:
            _logger.exception("the card %r did not build", spec.name)
            card = _error_card(spec, error)
        finally:
            ctx._current = None
        built.append(card)
    return built
