"""Writes the diagram block/event tables of one sequence to a JSON file, for
`run_slew_g.js` (task 6 of `docs/plans/pns-lanes-prototype.md`, section 3.6):
the exact minimum and maximum of the gradient slew rate (per axis) and of
|G| in each time bin of the sequence diagram's compact tables.

Prototype-only, not library code (`docs/plans/pns-lanes-prototype.md`,
section 4). Reads `pulseq_reports.diagram_data` (`diagram_tables`,
`encode_tables`, `lane_meta`) and `scripts/diagram_scale` (`build_repeating`,
`build_worst`), both read-only, as `export_grad_tables.py` writes only to
`prototypes/pns_lanes/`.

Usage:
    uv run python export_grad_tables.py NAME OUT.json

NAME is one of:
    spin_echo, gre, arbitrary            -- tests/synthetic.py
    rep_<N>trs                           -- scripts/diagram_scale.build_repeating(N)
    worst_<N>trs                         -- scripts/diagram_scale.build_worst(N)
    exvivo                               -- data/exvivo_gre_seg_0.seq (git-ignored,
                                             never copied into this directory)

OUT.json: {"format": 1, "tables": encode_tables(diagram_tables(seq)),
           "lanes": lane_meta(seq, tables)}
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(_REPO_ROOT / "tests"))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import pypulseq as pp  # noqa: E402

from pulseq_reports import diagram_data  # noqa: E402

_EXVIVO_PATH = _REPO_ROOT / "data" / "exvivo_gre_seg_0.seq"

_REP_RE = re.compile(r"^rep_(\d+)trs$")
_WORST_RE = re.compile(r"^worst_(\d+)trs$")


def _build(name: str) -> pp.Sequence:
    if name == "spin_echo":
        from synthetic import spin_echo_sequence

        return spin_echo_sequence()
    if name == "gre":
        from synthetic import gre_sequence

        return gre_sequence()
    if name == "arbitrary":
        from synthetic import arbitrary_gradient_sequence

        return arbitrary_gradient_sequence()
    if name == "exvivo":
        seq = pp.Sequence()
        seq.read(str(_EXVIVO_PATH))
        return seq

    m = _REP_RE.match(name)
    if m:
        from diagram_scale import build_repeating

        return build_repeating(int(m.group(1)))

    m = _WORST_RE.match(name)
    if m:
        from diagram_scale import build_worst

        return build_worst(int(m.group(1)))

    raise ValueError(
        f"unknown sequence name {name!r}: expected spin_echo, gre, arbitrary, "
        "exvivo, rep_<N>trs or worst_<N>trs"
    )


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} NAME OUT.json", file=sys.stderr)
        return 2
    name, out_path = argv[1], Path(argv[2])

    t0 = time.perf_counter()
    seq = _build(name)
    build_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    tables = diagram_data.diagram_tables(seq)
    tables_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    lanes = diagram_data.lane_meta(seq, tables)
    lanes_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    encoded = diagram_data.encode_tables(tables)
    encode_s = time.perf_counter() - t0

    payload = {"format": 1, "tables": encoded, "lanes": lanes}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload), encoding="utf-8")

    print(
        f"{name}: {tables['duration_index'].size} blocks, "
        f"{tables['grad_delay'].size} unique gradient events, "
        f"build {build_s:.2f}s tables {tables_s:.2f}s lane_meta {lanes_s:.2f}s "
        f"encode {encode_s:.2f}s -> {out_path}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
