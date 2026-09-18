"""Check that the library gives the same report data as vb-pulseq (parity).

The library's cards moved from vb-pulseq at commit 3a1c7dd. For the same sequence,
each moved card must give the same data as vb-pulseq, except the accepted
differences listed in ACCEPTED below. This script needs a vb-pulseq checkout, so it
is not part of scripts/check or CI. Run it in the devShell from the repository root:

    nix develop --command uv run --with-editable <vb-pulseq checkout> \
        python scripts/vb_parity.py

It builds the vb-pulseq sequences in SEQUENCES, computes the vb-pulseq report data
and the library data for each, and prints one line for each card: "ok", or the
first difference. Numbers must agree within a relative tolerance of 1e-9. It exits
1 when a card differs.
"""

import argparse
import math
import subprocess
import sys
from pathlib import Path

import vb_pulseq
from vb_pulseq import report as vb_report
from vb_pulseq.report import diagram as vb_diagram
from vb_pulseq.report import exposure_card as vb_exposure
from vb_pulseq.report import pns_card as vb_pns
from vb_pulseq.report import spectrum_card as vb_spectrum

from pulseq_reports import pns, waveforms
from pulseq_reports.cards import blocks, definitions, diagram, rf_exposure, spectrum, timing
from pulseq_reports.cards import pns as pns_cards
from pulseq_reports.seq_utils import NamedSequence

VB_COMMIT = "3a1c7dd"
SEQUENCES = ("vb-spin-echo-5mm-bw260", "vb-spin-echo-3mm-bw100")
RTOL = 1e-9
# The vb-pulseq files that the library copied. A later vb commit is also good when
# these files did not change.
VB_REPORT_PATHS = (
    "src/vb_pulseq/report",
    "src/vb_pulseq/seq_utils.py",
    "src/vb_pulseq/grad_spectrum.py",
    "src/vb_pulseq/rf_exposure.py",
    "src/vb_pulseq/pns.py",
)

# The accepted differences, by card. Each one was recorded in the PR of its phase.
ACCEPTED = {
    "diagram": [
        'The window buttons are data-window="i", not data-view="first-adc" and so on.',
        (
            "The peak-TR view is a caller-given window from pns.peak_tr_window, not a read of "
            "the PNS data (peak_tr_ms). This script checks that the window times are equal."
        ),
        "The ids start with the card id.",
    ],
    "gradient spectrum": [
        "The ids are gradient-spectrum-chart, -diagram and -tip, not spectrum-*.",
        (
            '"Prisma forbidden band" is "MAGNETOM Prisma (AS82) forbidden band" (table '
            'header and aria-label), and "the MAGNETOM Prisma gradient coil (AS82)" is '
            '"the MAGNETOM Prisma (AS82) gradient coil".'
        ),
    ],
    "rf exposure": ["The data has two new keys, window_used_s and periodic."],
    "pns": [
        (
            "The example-hardware note names the gradient_asc argument, not vb's "
            "seq-report --gradient-asc command."
        ),
    ],
}


class Difference(Exception):
    pass


def compare(vb, lib, path: str = "") -> None:
    """Raise Difference at the first place where `vb` and `lib` differ. Numbers agree
    within RTOL. A dict in `lib` must have the keys of `vb` (it can have more only when
    the caller removed them first)."""
    if isinstance(vb, bool) or isinstance(lib, bool):
        if vb is not lib:
            raise Difference(f"{path or '.'}: vb {vb!r}, library {lib!r}")
    elif isinstance(vb, (int, float)) and isinstance(lib, (int, float)):
        if not math.isclose(vb, lib, rel_tol=RTOL, abs_tol=0.0):
            raise Difference(f"{path or '.'}: vb {vb!r}, library {lib!r}")
    elif isinstance(vb, dict) and isinstance(lib, dict):
        if list(vb) != list(lib):
            raise Difference(f"{path or '.'}: keys vb {list(vb)}, library {list(lib)}")
        for key in vb:
            compare(vb[key], lib[key], f"{path}.{key}")
    elif isinstance(vb, (list, tuple)) and isinstance(lib, (list, tuple)):
        if len(vb) != len(lib):
            raise Difference(f"{path or '.'}: length vb {len(vb)}, library {len(lib)}")
        for i, (a, b) in enumerate(zip(vb, lib)):
            compare(a, b, f"{path}[{i}]")
    elif vb != lib:
        raise Difference(f"{path or '.'}: vb {vb!r:.200}, library {lib!r:.200}")


def compare_text(vb: str, lib: str) -> None:
    """Raise Difference at the first character where two HTML texts differ."""
    if vb == lib:
        return
    i = next((k for k, (a, b) in enumerate(zip(vb, lib)) if a != b), min(len(vb), len(lib)))
    raise Difference(
        f"HTML differs at character {i}: vb {vb[i - 40 : i + 80]!r}, "
        f"library {lib[i - 40 : i + 80]!r}"
    )


def vb_template_section(page: str, start: str, end: str) -> str:
    """The text of the vb page from `start` to `end`, both excluded."""
    begin = page.index(start) + len(start)
    return page[begin : page.index(end, begin)]


def check_sequence(name: str) -> bool:
    seq = vb_report.SEQUENCES[name]()
    named = [NamedSequence(name, seq)]
    vb_data = vb_diagram.sequence_data(seq)
    vb_pns_data = vb_pns.pns_data(seq)
    vb_page, _ = vb_report.render_report(seq, title=name)

    def diagram_check():
        compare(vb_data["lanes"], waveforms.file_lanes(seq))
        first, full = waveforms.first_adc_window(named), waveforms.full_window(named)
        compare(vb_data["first_adc_window_ms"], round(first.end_s * 1e3, 4))
        compare(vb_data["duration_ms"], round(full.end_s * 1e3, 4))
        peak_time = pns_cards.pns_data(seq)["peak_time_ms"]
        window = None if peak_time is None else pns.peak_tr_window(seq, peak_time / 1e3)
        lib_peak_tr = None if window is None else [round(t * 1e3, 4) for t in window]
        compare(vb_pns_data["peak_tr_ms"], lib_peak_tr)
        # vb sends every point of the file. The library does that for a file within the
        # point budget, so the card is checked with a budget of the file's points.
        count = waveforms.point_count(seq)
        card = diagram.diagram_card(named, [first, full], point_budget=count)
        compare(vb_data["lanes"], card.data["lane_sets"][0]["lanes"])
        if count > waveforms.DIAGRAM_POINT_BUDGET:
            notes.append(
                f"diagram: the file has {count} points, more than the default budget "
                f"({waveforms.DIAGRAM_POINT_BUDGET}). With the default, the card sends an "
                "envelope for the full-file view; pass point_budget to keep the vb page."
            )

    def blocks_check():
        rows, total = waveforms.block_rows(seq)
        compare(vb_data["blocks"], rows)
        compare(len(vb_data["blocks"]), total)
        vb_html = vb_template_section(
            vb_page, "<summary>Blocks (table view)</summary>\n", "\n</details>"
        )
        compare_text(vb_html, blocks.blocks_card(named).body_html)

    def timing_check():
        vb_html = vb_diagram._timing_html(vb_diagram.timing_errors(seq))
        compare_text(vb_html, timing.timing_card(named).body_html)

    def definitions_check():
        vb_html = vb_template_section(vb_page, "<h2>Definitions</h2>\n", "\n</section>")
        compare_text(vb_html, definitions.definitions_card(named).body_html)

    def rf_exposure_check():
        lib = rf_exposure.rf_exposure_data(seq)
        extra = {k: lib.pop(k) for k in ("window_used_s", "periodic")}  # accepted
        compare(vb_exposure.rf_exposure_data(seq), lib)
        if extra["periodic"] is not True:
            raise Difference("periodic is not True by default")
        compare_text(
            vb_exposure._rf_exposure_html(vb_exposure.rf_exposure_data(seq)),
            rf_exposure.rf_exposure_card(named).body_html,
        )

    def spectrum_check():
        vb = vb_spectrum.spectrum_data(seq)
        compare(vb, spectrum.spectrum_data(seq))
        lib_html = spectrum.spectrum_card(named).body_html
        # Undo the accepted differences, then the rest must be equal.
        lib_html = lib_html.replace("gradient-spectrum-", "spectrum-")
        lib_html = lib_html.replace(
            "MAGNETOM Prisma (AS82) forbidden band", "Prisma forbidden band"
        )
        lib_html = lib_html.replace(
            "the MAGNETOM Prisma (AS82) gradient coil", "the MAGNETOM Prisma gradient coil (AS82)"
        )
        compare_text(vb_spectrum._spectrum_html(vb), lib_html)

    def pns_check():
        compare(vb_pns_data, pns_cards.pns_data(seq))
        lib_html = pns_cards.pns_card(named[0]).body_html
        lib_html = lib_html.replace(
            "Give the gradient .asc file of your scanner (<code>gradient_asc</code>) for a "
            "real prediction.",
            "Run <code>seq-report</code> with <code>--gradient-asc PATH</code> and the "
            "gradient .asc file of your scanner for a real prediction.",
        )
        compare_text(vb_pns._pns_html(vb_pns_data), lib_html)

    checks = {
        "timing": timing_check,
        "rf exposure": rf_exposure_check,
        "diagram": diagram_check,
        "gradient spectrum": spectrum_check,
        "pns": pns_check,
        "definitions": definitions_check,
        "blocks": blocks_check,
    }
    ok = True
    notes: list[str] = []
    print(name)
    for card, check in checks.items():
        try:
            check()
            accepted = f" ({len(ACCEPTED[card])} accepted differences)" if card in ACCEPTED else ""
            print(f"  ok    {card}{accepted}")
        except Difference as difference:
            ok = False
            print(f"  FAIL  {card}: {difference}")
    for note in notes:
        print(f"  note  {note}")
    return ok


def vb_version() -> str:
    """The vb-pulseq commit, and whether its report code is the same as at VB_COMMIT."""
    root = Path(vb_pulseq.__file__).resolve().parents[2]

    def run(*args):
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
        )

    head = run("rev-parse", "--short", "HEAD")
    if head.returncode != 0:
        return f"{root} is not a git checkout: its commit is unknown"
    same = run("diff", "--quiet", VB_COMMIT, "--", *VB_REPORT_PATHS).returncode == 0
    note = "the same as" if same else "DIFFERENT from"
    return f"{root} at {head.stdout.strip()}: the report code is {note} {VB_COMMIT}"


def main() -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    print(f"vb-pulseq: {vb_version()}")
    results = [check_sequence(name) for name in SEQUENCES]  # check every sequence
    ok = all(results)
    print()
    print("Accepted differences:")
    for card, items in ACCEPTED.items():
        for item in items:
            print(f"  {card}: {item}")
    print("ok: every card has parity" if ok else "FAIL: a card differs")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
