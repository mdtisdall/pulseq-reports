"""Writes the encoded diagram tables and the PNS options of one sequence to JSON, for
`pns_lanes.js` (prototype for docs/plans/pns-lanes-prototype.md, task 3). Prototype
code only: not part of the library, never merged (see README.md in this directory).

Usage (from the repository root, in the devShell):

    uv run python prototypes/pns_lanes/export_tables.py <name> <out.json>

`<name>` selects the sequence:

  - A zero-argument function that `build_seqs.py` (this directory) exports, when that
    file exists: another agent is writing it, with (at least) "spin_echo", "gre",
    "arbitrary", "border", "rep_12s", "rep_60s", "rep_370s_long", "rep_1000000blocks",
    "rep_10000000blocks", "worst_100000blocks", "exvivo".
  - Else, as a fallback:
    - "spin_echo", "gre", "arbitrary": `tests/synthetic.py`
      (`spin_echo_sequence`, `gre_sequence`, `arbitrary_gradient_sequence`).
    - "rep_<N>trs" (for example "rep_2000trs"): `scripts/diagram_scale.py`
      `build_repeating(N)`.
    - "exvivo": `data/exvivo_gre_seg_0.seq` (git-ignored; `pp.Sequence().read`).

Output JSON: {"format": 1, "tables": encode_tables(diagram_tables(seq)),
"opts": {"gradRasterS", "gamma", "hw": safe_example_hw() as plain JSON,
"groupBlocks": 64}, "durationS": seq.duration()[0]}.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]

# tests/synthetic.py and scripts/diagram_scale.py are read-only imports (plan section
# 4.4: "Import pulseq_reports.diagram_data ... and scripts/diagram_scale.py. Do not
# edit src/, tests/, TESTS.md or scripts/").
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import pypulseq as pp  # noqa: E402
from pypulseq.utils.safe_pns_prediction import safe_example_hw  # noqa: E402

from pulseq_reports import diagram_data  # noqa: E402

EXVIVO_PATH = REPO_ROOT / "data" / "exvivo_gre_seg_0.seq"
REP_TRS_RE = re.compile(r"^rep_(\d+)trs$")


def _load_build_seqs():
    """The `build_seqs` module in this directory, or None when it does not exist yet
    (another agent writes it at the same time as this file, per the task)."""
    path = HERE / "build_seqs.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location("pns_lanes_build_seqs", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _hw_to_json(hw) -> dict:
    """`safe_example_hw()` (a nested `SimpleNamespace`) as a plain JSON-able dict:
    {"x": {"tau1", "tau2", "tau3", "a1", "a2", "a3", "stim_limit", "g_scale"}, "y":
    {...}, "z": {...}}."""
    out = {}
    for axis in ("x", "y", "z"):
        a = getattr(hw, axis)
        out[axis] = {
            "tau1": a.tau1,
            "tau2": a.tau2,
            "tau3": a.tau3,
            "a1": a.a1,
            "a2": a.a2,
            "a3": a.a3,
            "stim_limit": a.stim_limit,
            "g_scale": a.g_scale,
        }
    return out


def build_sequence(name: str) -> pp.Sequence:
    build_seqs = _load_build_seqs()
    if build_seqs is not None and hasattr(build_seqs, "build_seq"):
        # `build_seqs.build_seq(name)` is task 2's builder (this directory's
        # `build_seqs.py`, owned by another agent, not edited here). Its "exvivo"
        # branch returns `pp.Sequence().read(...)`, whose return value is `None`
        # (`Sequence.read` mutates in place); guard against that (and against any
        # other name it does not actually recognize returning something that is not
        # a `pp.Sequence`) by falling through to this script's own fallback below
        # instead of handing `diagram_tables` a bad object.
        try:
            seq = build_seqs.build_seq(name)
        except Exception:
            seq = None
        if isinstance(seq, pp.Sequence):
            return seq

    if name == "spin_echo":
        from tests.synthetic import spin_echo_sequence

        return spin_echo_sequence()
    if name == "gre":
        from tests.synthetic import gre_sequence

        return gre_sequence()
    if name == "arbitrary":
        from tests.synthetic import arbitrary_gradient_sequence

        return arbitrary_gradient_sequence()

    m = REP_TRS_RE.match(name)
    if m:
        from diagram_scale import build_repeating

        return build_repeating(int(m.group(1)))

    if name == "exvivo":
        if not EXVIVO_PATH.exists():
            raise FileNotFoundError(
                f"{EXVIVO_PATH} is missing. It is git-ignored; see "
                "prototypes/pns_lanes/README.md and docs/plans/pns-lanes-prototype.md "
                "section 7, decision 1."
            )
        seq = pp.Sequence()
        seq.read(str(EXVIVO_PATH))
        return seq

    known = "build_seqs.py names (if present), or spin_echo, gre, arbitrary, rep_<N>trs, exvivo"
    raise ValueError(f"unknown sequence name {name!r} (known: {known})")


def export(name: str, out_path: Path) -> None:
    seq = build_sequence(name)
    tables = diagram_data.diagram_tables(seq)
    encoded_tables = diagram_data.encode_tables(tables)
    hw = safe_example_hw()
    duration_s, num_blocks, _event_count = seq.duration()

    payload = {
        "format": 1,
        "tables": encoded_tables,
        "opts": {
            "gradRasterS": float(seq.grad_raster_time),
            "gamma": float(seq.system.gamma),
            "hw": _hw_to_json(hw),
            "groupBlocks": 64,
        },
        "durationS": float(duration_s),
        "numBlocks": int(num_blocks),
        "sequenceName": name,
    }
    out_path.write_text(json.dumps(payload))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__)
        return 2
    name, out_path = argv
    export(name, Path(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
