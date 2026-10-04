"""The command line: `pulseq-report FILE.seq [FILE.seq ...]` writes one report page for each file.

The flags come from the cards that are installed (`registry.discover`): one flag, or one
flag pair, for each distinct option. A config file (`--config`) gives the same options.
The exit status is 0 when each page is written and no card is an error card, and 1 for an
error in the arguments, in the config file or in a card spec, for a file that cannot be
read or written, and for a page with an error card (the page is written).
"""

import argparse
import contextlib
import importlib
import json
import sys
import tomllib
from collections.abc import Iterator, Sequence
from pathlib import Path

import pypulseq as pp

from . import __version__, registry
from .page import write_page
from .registry import CardSpec, Option, build_cards


class _CliError(Exception):
    """An error in the arguments, in the config file or in a card spec: the status is 1."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):
        raise _CliError(message)


def _report(message: str) -> None:
    print(f"pulseq-report: {message}", file=sys.stderr)


def _load_card_modules(labels: Sequence[str]) -> list[tuple[str, object]]:
    loaded = []
    here = str(Path.cwd())  # a project's own file, next to where the command runs
    sys.path.append(here)
    try:
        for label in labels:
            module_name, separator, attribute = label.partition(":")
            if not separator or not module_name or not attribute:
                raise _CliError(f"--card-module {label!r} is not MODULE:ATTRIBUTE")
            try:
                loaded.append((label, getattr(importlib.import_module(module_name), attribute)))
            except (ImportError, AttributeError) as error:
                raise _CliError(f"--card-module {label!r} could not be loaded: {error}") from error
    finally:
        # The copy that was added (the last one): the path can be in sys.path already.
        del sys.path[len(sys.path) - 1 - sys.path[::-1].index(here)]
    return loaded


@contextlib.contextmanager
def _extra_specs(extra: list[tuple[str, object]]) -> Iterator[None]:
    """Add `extra` (label, object) pairs to the entry points that `discover` reads, so
    `discover` and `build_cards` check them and use them like a plugin's."""
    found = registry._load_entry_points
    registry._load_entry_points = lambda: [*found(), *extra]
    try:
        yield
    finally:
        registry._load_entry_points = found


def _distinct_options(specs: Sequence[CardSpec]) -> list[Option]:
    found: list[Option] = []
    for spec in specs:
        for option in spec.options:
            if not any(option is seen for seen in found):
                found.append(option)
    return found


def _build_parser(specs: Sequence[CardSpec]) -> argparse.ArgumentParser:
    parser = _Parser(
        prog="pulseq-report",
        description="Write a review report page for each Pulseq .seq file.",
        allow_abbrev=False,
    )
    parser.add_argument("files", nargs="+", type=Path, metavar="FILE.seq", help="A .seq file.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        metavar="OUT",
        help="The page, for one file (default: <stem>.html in the current directory); the "
        "directory of the pages, for several files (default: the current directory).",
    )
    parser.add_argument(
        "--cards", metavar="NAME,...", help="Only these cards (a comma list of card names)."
    )
    parser.add_argument(
        "--skip", metavar="NAME,...", help="Leave out these cards (a comma list of card names)."
    )
    parser.add_argument(
        "--card-module",
        action="append",
        default=[],
        metavar="MODULE:ATTRIBUTE",
        help="A CardSpec from a module that is not installed as a plugin. It can be given "
        "more than one time.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        metavar="FILE",
        help="A .toml or .json file of option values, by option name, and cards and skip. "
        "A flag overrides the same key.",
    )
    group = parser.add_argument_group("card options")
    for option in _distinct_options(specs):
        for flag in option.flags():
            kwargs: dict[str, object] = {
                "dest": flag.dest,
                "default": argparse.SUPPRESS,
                "help": flag.help.replace("%", "%%"),
            }
            if flag.type is bool:
                kwargs["action"] = argparse.BooleanOptionalAction
            else:
                kwargs["type"] = flag.type
                kwargs["metavar"] = flag.metavar
                kwargs["choices"] = flag.choices
            try:
                group.add_argument(flag.name, **kwargs)
            except argparse.ArgumentError as error:
                raise _CliError(f"the flag {flag.name} of the option {option.name!r}: {error}")
    return parser


def _read_config(path: Path) -> dict:
    readers = {".toml": ("rb", tomllib.load), ".json": ("r", json.load)}
    if path.suffix not in readers:
        raise _CliError(f"--config {str(path)!r} must end in .toml or .json")
    mode, load = readers[path.suffix]
    try:
        with open(path, mode, **({} if mode == "rb" else {"encoding": "utf-8"})) as f:
            data = load(f)
    except (OSError, ValueError) as error:  # tomllib and json errors are ValueErrors
        raise _CliError(f"--config {str(path)!r} could not be read: {error}") from error
    if not isinstance(data, dict):
        raise _CliError(f"--config {str(path)!r} must hold a table of keys")
    return data


def _names(what: str, value: object) -> list[str]:
    """A list of card names from a flag (a comma list) or from a config file (a list)."""
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    raise _CliError(f"{what} must be a list of card names: {value!r}")


def _output_paths(files: Sequence[Path], output: Path | None) -> list[Path]:
    if len(files) == 1:
        return [output if output is not None else Path(f"{files[0].stem}.html")]
    stems = [file.stem for file in files]
    repeated = sorted({stem for stem in stems if stems.count(stem) > 1})
    if repeated:
        raise _CliError(f"several files have the stem {repeated}: their pages would be one file")
    directory = output if output is not None else Path()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise _CliError(f"the output directory {str(directory)!r} could not be made: {error}")
    return [directory / f"{stem}.html" for stem in stems]


def _run(argv: Sequence[str]) -> int:
    pre = _Parser(add_help=False, allow_abbrev=False)
    pre.add_argument("--card-module", action="append", default=[])
    labels = pre.parse_known_args(list(argv))[0].card_module
    with _extra_specs(_load_card_modules(labels)):
        try:
            specs = registry.discover()
        except Exception as error:  # a failed start check: no page is written
            raise _CliError(str(error)) from error
        parser = _build_parser(specs)
        args = parser.parse_args(list(argv))
        given = vars(args)
        known = {spec.name for spec in specs}
        all_options = _distinct_options(specs)

        config: dict = {}
        base_dir = Path()
        if args.config is not None:
            config = _read_config(args.config)
            base_dir = args.config.resolve().parent
            unknown = sorted(set(config) - {"cards", "skip"} - {o.name for o in all_options})
            if unknown:
                raise _CliError(f"--config {str(args.config)!r} has the unknown keys {unknown}")

        cards_value = args.cards if args.cards is not None else config.get("cards")
        cards = None if cards_value is None else _names("cards", cards_value)
        skip = _names("skip", args.skip if args.skip is not None else config.get("skip", []))
        for what, names in (("cards", cards or []), ("skip", skip)):
            unknown = sorted(set(names) - known)
            if unknown:
                raise _CliError(
                    f"{what} has the unknown card names {unknown}; the cards are {sorted(known)}"
                )
        selected = [s for s in specs if (cards is None or s.name in cards) and s.name not in skip]
        declared = _distinct_options(selected)

        values: dict[str, object] = {}
        for option in all_options:
            flags = {f.dest: given[f.dest] for f in option.flags() if f.dest in given}
            in_selected = any(option is d for d in declared)
            if flags and not in_selected:
                skipped = [s.name for s in specs if any(option is o for o in s.options)]
                names = ", ".join(f.name for f in option.flags() if f.dest in given)
                raise _CliError(
                    f"{names} is an option of the cards {skipped}, and none of them is selected"
                )
            if not in_selected:
                continue
            try:
                if flags:
                    values[option.name] = option.from_flags(flags)
                elif option.name in config:
                    values[option.name] = option.from_config(config[option.name], base_dir)
            except (ValueError, TypeError) as error:
                where = "the flags" if flags else f"--config {str(args.config)!r}"
                raise _CliError(f"{where}: {error}") from error

        outputs = _output_paths(args.files, args.output)
        return _write_pages(args.files, outputs, cards, skip, values)


def _write_pages(
    files: Sequence[Path],
    outputs: Sequence[Path],
    cards: Sequence[str] | None,
    skip: Sequence[str],
    values: dict[str, object],
) -> int:
    status = 0
    for file, output in zip(files, outputs):
        try:
            seq = pp.Sequence()
            seq.read(str(file))
        except Exception as error:  # noqa: BLE001 - pypulseq raises many types for a bad file
            _report(f"{file}: could not be read: {type(error).__name__}: {error}")
            status = 1
            continue
        try:
            built = build_cards(seq, cards=cards, skip=skip, **values)
            write_page(output, file.name, f"pulseq-reports {__version__}", built)
        except (ValueError, TypeError, OSError) as error:
            _report(f"{file}: no page was written: {error}")
            status = 1
            continue
        for card in built:
            if card.error is not None:
                _report(f"{file}: {card.id}: {card.error}")
                status = 1
    return status


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line with `argv` (default: `sys.argv[1:]`). Returns the exit status:
    0 (each page is written and no card is an error card) or 1 (an error)."""
    try:
        return _run(sys.argv[1:] if argv is None else argv)
    except _CliError as error:
        _report(f"error: {error}")
        return 1
    except SystemExit as exit_:  # --help
        return exit_.code if isinstance(exit_.code, int) else 1


if __name__ == "__main__":
    sys.exit(main())
