"""Measures the time and the memory of one report card, on large synthetic pypulseq
sequences, against the budgets of section 2.6 of `docs/plans/cards-at-scale.md`.

Not part of `scripts/check` or CI: a large run can take minutes and use several GB of
memory. Run it in the devShell from the repository root:

    nix develop --command uv run python scripts/cards_scale.py \
        --card pns|rf|limits|spectrum|diagram|rf-profile|all --blocks N \
        --case repeating|worst \
        [--tr-s T] [--pns-lanes] --out DIR

`--card`: which card to measure. `pns` is `cards.pns.pns_card` (with the target and the
result matrix below), `rf` is
`cards.rf_exposure.rf_exposure_card`, `limits` is `cards.gradient_limits.gradient_limits_card`
(no window, and no targets, the default), `spectrum` is `cards.spectrum.spectrum_card` (with the
matrix of `run_checks(seq, [example A], select=[], analyses=["gradient.spectrum"])`, whose time is
`run_checks_s`; the card reads the result and calculates no spectrum), `diagram` is
`cards.diagram.diagram_card` with the "First ADC" and "Full sequence" windows
(`waveforms.first_adc_window`, `waveforms.full_window`), as `diagram_scale.py` uses,
`rf-profile` is `cards.rf_profile.rf_profile_card` (`docs/plans/rf-profiles.md`; the
builders label their RF pulses, as the card needs). Each card is called with its own
defaults and one file, except that the PNS card and the PNS lane of the diagram get the
PNS of one target from a result matrix: the script calls `pulseq_checks.run_checks` on the
sequence object with the target `tests/profiles/example_a.toml` (it gives SAFE parameters),
`select=[]` and `analyses=["pns.safe.levels"]`, and gives the card the target
(`targets.report_targets`) and the matrix. The time of `run_checks` and the time of the card
are recorded separately. `--card all` runs each of the six cards in its own fresh process
(a subprocess of this script with the same arguments and one `--card`), one after
another, so that the peak RSS of one card does not hide another; it collects their JSON
into one combined file too.

`--blocks N`: the target number of blocks, turned into a number of TRs the same way as
`diagram_scale.py`: `n_trs = blocks // TR_BLOCKS` (`TR_BLOCKS` is 5, from
`diagram_scale.py`), at least one TR, and a note on stderr when `n_trs * TR_BLOCKS` is
not `blocks`.

`--case repeating|worst`: `diagram_scale.build_repeating` or `diagram_scale.build_worst`
(imported from `scripts/diagram_scale.py`, next to this script, by path with
`importlib.util.spec_from_file_location`; this script does not copy them).

`--tr-s T`: an optional longer TR (s), for a file like a 370 s protocol with about
4e4 blocks, whose TR is much longer than the builders' default. The builders read the
module constant `diagram_scale.TR_MARGIN_S` (the delay that fills the rest of each TR)
at call time; the TR is `used + TR_MARGIN_S`, where `used` is the fixed, busy part of
the TR (`build_repeating` and `build_worst`). This script learns `used` by building one
TR with the module's own default `TR_MARGIN_S`, then sets `diagram_scale.TR_MARGIN_S` so
that the built TR equals `T`, rounded to the nearest multiple of 10 us (the default
`grad_raster_time`). It exits with an error, before building the full sequence, when `T`
is shorter than the TR that the default margin gives: `used` is fixed, so no smaller
margin can reach a shorter TR. Without `--tr-s`, the builders' own default TR is used.

For each card run, it records (as JSON, and prints a one-line summary):

- `card`, `case`, `requested_blocks` (the `--blocks` value), `num_blocks` (the built
  number of blocks, `n_trs * TR_BLOCKS`), `num_trs`.
- `duration_s`: the built sequence's `seq.duration()[0]`.
- `tr_s`: the built sequence's `seq.get_definition("TR")` (`used + TR_MARGIN_S`, the
  same value that `--tr-s` targets when it is given). `requested_tr_s`: the `--tr-s`
  value, or `null` when it was not given.
- `build_s`: the time to build the `pp.Sequence` (`time.perf_counter`).
- `build_rss_bytes`: the current RSS right after the build, from `ps -o rss= -p <pid>`
  (KiB, converted to bytes).
- `peak_rss_before_card_bytes`, `peak_rss_after_card_bytes`: the peak RSS of this
  process so far (a running maximum, not a delta), measured right before and right
  after the card call (`resource.getrusage(resource.RUSAGE_SELF).ru_maxrss`, converted
  to bytes by platform, as `diagram_scale._peak_rss_bytes` does: `ru_maxrss` is bytes on
  macOS and KiB on Linux).
- `run_checks_s`: the time of `run_checks` (`time.perf_counter`) for `--card spectrum` (it
  calculates the spectrum, before the peak RSS before the card is read), and for the `pns`
  card and the diagram card with `--pns-lanes` (it runs the SAFE model, after that reading);
  `null` for the other cards.
- `card_s`: the time of the card call alone (`time.perf_counter`), after `run_checks`.
- `raised_peak`: whether the card call raised the peak RSS
  (`peak_rss_after_card_bytes > peak_rss_before_card_bytes`). For the `pns` card and the
  diagram card with `--pns-lanes`, the peak RSS is measured before `run_checks` and after the
  card, so it covers both.
- `added_rss_bytes`: the "added RSS" of section 2.6 of the plan: the peak RSS during
  the card, minus the RSS after the sequence is built
  (`peak_rss_after_card_bytes - build_rss_bytes`). `null` when `raised_peak` is false:
  then the card did not grow the process's peak, and the added RSS is not measured.
- `card_bytes`: the size of the card in the page: its body HTML plus its data as JSON
  (UTF-8 bytes; the data holds the base64 of the compressed tables and levels).
- `pns_lanes`: whether `--pns-lanes` was given.
- `python_version`, `numpy_version`, `pypulseq_version`.

`--pns-lanes`: the diagram card is called with `pns_lane=True`, the target and the result
matrix, so it adds the PNS lane (`docs/plans/diagram-lanes.md`). Its time and `card_bytes`
minus those of a run without `--pns-lanes` are what the PNS lane adds (section 2.4 of that
plan), and `run_checks_s` is the time of the SAFE model. No other card reads it, so
`--pns-lanes` with a `--card` other than `diagram` or `all` is an error, and `--card all
--pns-lanes` gives it only to the diagram subprocess.

It writes one JSON file for each card run to `--out`, named
`cards-scale-<card>-<case>-<blocks>.json` (pretty-printed; `blocks` is the requested
`--blocks`), or `cards-scale-diagram-pns-lanes-<case>-<blocks>.json` for the diagram
card with `--pns-lanes`. With `--card all`, it also writes the six results, keyed by
card name, to `cards-scale-all-<case>-<blocks>.json` in the same directory
(`cards-scale-all-pns-lanes-<case>-<blocks>.json` with `--pns-lanes`).

Example, for a 370 s protocol of about 4e4 blocks:

    nix develop --command uv run python scripts/cards_scale.py \
        --card all --blocks 40000 --case repeating --tr-s 0.04707 --out <dir>

The script only measures. It does not compare the results with the budgets.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import subprocess
import sys
import time
import types
from pathlib import Path

import numpy as np
import pypulseq as pp
from pulseq_checks import ResultMatrix, read_profile, run_checks

from pulseq_reports.cards.diagram import diagram_card
from pulseq_reports.cards.gradient_limits import gradient_limits_card
from pulseq_reports.cards.pns import pns_card
from pulseq_reports.cards.rf_exposure import rf_exposure_card
from pulseq_reports.cards.rf_profile import rf_profile_card
from pulseq_reports.cards.spectrum import spectrum_card
from pulseq_reports.page import Card
from pulseq_reports.targets import ReportTarget, report_targets
from pulseq_reports.waveforms import first_adc_window, full_window

_THIS_FILE = Path(__file__).resolve()
_DIAGRAM_SCALE_PATH = _THIS_FILE.parent / "diagram_scale.py"
# The example target of the cards that need a result matrix (spectrum, PNS, PNS lane).
_TARGET_PATH = _THIS_FILE.parent.parent / "tests" / "profiles" / "example_a.toml"

_RASTER_S = 10e-6  # --tr-s is rounded to the nearest multiple of this (grad_raster_time)


def _load_diagram_scale() -> types.ModuleType:
    """Loads `diagram_scale.py`, next to this script, as a module by path (not by
    package import), so this script can use its builders and helpers without copying
    them and without `scripts/` being an importable package."""
    spec = importlib.util.spec_from_file_location("cards_scale_diagram_scale", _DIAGRAM_SCALE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _current_rss_bytes() -> int:
    """The current resident set size of this process, in bytes, from `ps -o rss=`
    (kibibytes on both macOS and Linux)."""
    out = subprocess.run(
        ["ps", "-o", "rss=", "-p", str(os.getpid())],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(out.stdout.strip()) * 1024


def _round_to_raster(t_s: float) -> float:
    return round(t_s / _RASTER_S) * _RASTER_S


def resolve_tr_margin(diagram_scale: types.ModuleType, case: str, tr_s: float) -> float:
    """The `TR_MARGIN_S` that makes one TR of `case` equal `tr_s`, rounded to the
    nearest multiple of 10 us.

    Builds one TR with the module's own default `TR_MARGIN_S`, to learn the fixed,
    busy part of the TR ("used"): `default_tr - default_margin`. The returned margin
    is the rounded target TR minus that fixed part, so a later build with this margin
    gives `used + margin == round(tr_s to 10 us)`.

    Raises `ValueError` when `tr_s` is shorter than the TR that the default margin
    gives: `used` does not depend on the margin, so no smaller margin reaches a
    shorter TR.
    """
    default_margin = diagram_scale.TR_MARGIN_S
    probe = diagram_scale.BUILDERS[case](1)
    default_tr = probe.get_definition("TR")
    if tr_s < default_tr:
        raise ValueError(
            f"--tr-s {tr_s:g} is shorter than the TR with the default margin ({default_tr:g} s)"
        )
    used = default_tr - default_margin
    return _round_to_raster(_round_to_raster(tr_s) - used)


def pns_inputs(seq: pp.Sequence) -> tuple[tuple[ReportTarget, ...], ResultMatrix]:
    """The target of `_TARGET_PATH` as `ReportTarget`s, and the result matrix of
    `run_checks(seq, [target], select=[], analyses=["pns.safe.levels"])`: no check runs, and the
    analysis `pns.safe.levels` runs the SAFE model."""
    profile = read_profile(_TARGET_PATH)
    return report_targets([profile]), run_checks(
        seq, [profile], select=[], analyses=["pns.safe.levels"]
    )


def _run_pns(seq: pp.Sequence, targets: tuple[ReportTarget, ...], matrix: ResultMatrix) -> Card:
    return pns_card(seq, targets=targets, check_results=matrix)


def _run_rf(seq: pp.Sequence) -> Card:
    return rf_exposure_card(seq)


def _run_limits(seq: pp.Sequence) -> Card:
    return gradient_limits_card(seq)


def _spectrum_matrix(seq: pp.Sequence) -> ResultMatrix:
    """The matrix of the analysis `gradient.spectrum` of `seq` for the example target A, with no
    check: the spectrum is calculated here, not in the card."""
    return run_checks(seq, [read_profile(_TARGET_PATH)], select=[], analyses=["gradient.spectrum"])


def _run_spectrum(seq: pp.Sequence, matrix: ResultMatrix) -> Card:
    return spectrum_card(
        seq, targets=report_targets([read_profile(_TARGET_PATH)]), check_results=matrix
    )


def _run_diagram(
    seq: pp.Sequence,
    pns_lanes: bool,
    targets: tuple[ReportTarget, ...] = (),
    matrix: ResultMatrix | None = None,
) -> Card:
    windows = [first_adc_window(seq), full_window(seq)]
    return diagram_card(seq, windows, pns_lane=pns_lanes, targets=targets, check_results=matrix)


def _run_rf_profile(seq: pp.Sequence) -> Card:
    return rf_profile_card(seq)


def _card_bytes(card: Card) -> int:
    """The size of `card` in the page: its body HTML and its data as JSON (UTF-8)."""
    data = b"" if card.data is None else json.dumps(card.data).encode("utf-8")
    return len(card.body_html.encode("utf-8")) + len(data)


CARD_RUNNERS = {
    "pns": _run_pns,
    "rf": _run_rf,
    "limits": _run_limits,
    "spectrum": _run_spectrum,
    "diagram": _run_diagram,
    "rf-profile": _run_rf_profile,
}
CARD_NAMES = tuple(CARD_RUNNERS)


def run(
    card: str,
    blocks: int,
    case: str,
    tr_s: float | None,
    out_dir: Path,
    pns_lanes: bool = False,
) -> dict:
    diagram_scale = _load_diagram_scale()
    n_trs = blocks // diagram_scale.TR_BLOCKS
    if n_trs < 1:
        raise ValueError(f"--blocks {blocks} is below one TR ({diagram_scale.TR_BLOCKS} blocks)")
    effective_blocks = n_trs * diagram_scale.TR_BLOCKS
    if effective_blocks != blocks:
        print(
            f"note: {blocks} blocks is not a multiple of {diagram_scale.TR_BLOCKS}; "
            f"building {effective_blocks} blocks ({n_trs} TRs) instead",
            file=sys.stderr,
        )

    if tr_s is not None:
        diagram_scale.TR_MARGIN_S = resolve_tr_margin(diagram_scale, case, tr_s)

    build_start = time.perf_counter()
    seq = diagram_scale.BUILDERS[case](n_trs)
    build_s = time.perf_counter() - build_start
    build_rss_bytes = _current_rss_bytes()
    run_checks_s = None
    targets: tuple[ReportTarget, ...] = ()
    matrix = None
    if card == "spectrum":
        checks_start = time.perf_counter()
        matrix = _spectrum_matrix(seq)
        run_checks_s = time.perf_counter() - checks_start
    peak_rss_before_card_bytes = diagram_scale._peak_rss_bytes()

    if card == "pns" or (card == "diagram" and pns_lanes):
        checks_start = time.perf_counter()
        targets, matrix = pns_inputs(seq)
        run_checks_s = time.perf_counter() - checks_start

    card_start = time.perf_counter()
    if card == "diagram":
        built = _run_diagram(seq, pns_lanes, targets, matrix)
    elif card == "pns":
        built = _run_pns(seq, targets, matrix)
    elif card == "spectrum":
        built = _run_spectrum(seq, matrix)
    else:
        built = CARD_RUNNERS[card](seq)
    card_s = time.perf_counter() - card_start
    peak_rss_after_card_bytes = diagram_scale._peak_rss_bytes()

    raised_peak = peak_rss_after_card_bytes > peak_rss_before_card_bytes
    added_rss_bytes = peak_rss_after_card_bytes - build_rss_bytes if raised_peak else None

    result = {
        "card": card,
        "case": case,
        "requested_blocks": blocks,
        "num_blocks": effective_blocks,
        "num_trs": n_trs,
        "duration_s": seq.duration()[0],
        "tr_s": seq.get_definition("TR"),
        "requested_tr_s": tr_s,
        "build_s": build_s,
        "build_rss_bytes": build_rss_bytes,
        "peak_rss_before_card_bytes": peak_rss_before_card_bytes,
        "run_checks_s": run_checks_s,
        "card_s": card_s,
        "peak_rss_after_card_bytes": peak_rss_after_card_bytes,
        "raised_peak": raised_peak,
        "added_rss_bytes": added_rss_bytes,
        "card_bytes": _card_bytes(built),
        "pns_lanes": pns_lanes,
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "pypulseq_version": pp.__version__,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / _json_name(card, case, blocks, pns_lanes)
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    result["json_path"] = str(json_path)

    checks_str = "" if run_checks_s is None else f" run_checks_s={run_checks_s:.2f}"
    added_rss_str = "n/a" if added_rss_bytes is None else f"{added_rss_bytes / 1e6:.1f} MB"
    print(
        f"{card}: case={case} blocks={effective_blocks} tr_s={result['tr_s']:.6g} "
        f"duration_s={result['duration_s']:.6g} build_s={build_s:.2f}{checks_str} "
        f"card_s={card_s:.2f} "
        f"build_rss={build_rss_bytes / 1e6:.1f} MB raised_peak={raised_peak} "
        f"added_rss={added_rss_str}"
    )
    return result


def _json_name(card: str, case: str, blocks: int, pns_lanes: bool) -> str:
    lanes = "-pns-lanes" if pns_lanes else ""
    return f"cards-scale-{card}{lanes}-{case}-{blocks}.json"


def _run_all(
    blocks: int,
    case: str,
    tr_s: float | None,
    out_dir: Path,
    pns_lanes: bool,
) -> dict:
    """Runs each of `CARD_NAMES` as a fresh subprocess of this script, with the same
    `--blocks`, `--case`, `--tr-s` and `--out`, and one `--card`, so that the peak RSS
    of one card does not hide another. `pns_lanes` gives `--pns-lanes` to the diagram
    subprocess only. Reads back each subprocess's own
    JSON file and combines them into one file, keyed by card name."""
    combined: dict[str, dict] = {}
    for card in CARD_NAMES:
        cmd = [
            sys.executable,
            str(_THIS_FILE),
            "--card",
            card,
            "--blocks",
            str(blocks),
            "--case",
            case,
            "--out",
            str(out_dir),
        ]
        if tr_s is not None:
            cmd += ["--tr-s", str(tr_s)]
        card_pns_lanes = pns_lanes and card == "diagram"
        if card_pns_lanes:
            cmd.append("--pns-lanes")
        print(f"---- {card}: running in a fresh process ----", file=sys.stderr)
        subprocess.run(cmd, check=True)
        json_path = out_dir / _json_name(card, case, blocks, card_pns_lanes)
        combined[card] = json.loads(json_path.read_text(encoding="utf-8"))

    out_dir.mkdir(parents=True, exist_ok=True)
    combined_path = out_dir / _json_name("all", case, blocks, pns_lanes)
    combined_path.write_text(json.dumps(combined, indent=2), encoding="utf-8")
    print(f"all: wrote {combined_path}")
    return combined


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--card", choices=(*CARD_NAMES, "all"), required=True)
    parser.add_argument("--blocks", type=int, required=True, help="target number of blocks")
    parser.add_argument("--case", choices=("repeating", "worst"), required=True)
    parser.add_argument(
        "--tr-s", type=float, default=None, help="a longer TR (s), rounded to 10 us"
    )
    parser.add_argument(
        "--pns-lanes",
        action="store_true",
        help="the diagram card with pns_lane=True (the PNS lane)",
    )
    parser.add_argument("--out", type=Path, required=True, help="output directory")
    args = parser.parse_args(argv)
    if args.pns_lanes and args.card not in ("diagram", "all"):
        parser.error("--pns-lanes needs --card diagram or --card all")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.card == "all":
        _run_all(args.blocks, args.case, args.tr_s, args.out, args.pns_lanes)
        return 0
    result = run(args.card, args.blocks, args.case, args.tr_s, args.out, args.pns_lanes)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
