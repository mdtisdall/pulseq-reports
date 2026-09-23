"""Measures the diagram card (`cards.diagram.diagram_card`) on large synthetic
pypulseq sequences, against the scale budgets of section 2.6 of
`docs/plans/diagram-event-table.md`.

Not part of `scripts/check` or CI: a large run can take minutes and writes a large
HTML page. Run it in the devShell from the repository root:

    nix develop --command uv run python scripts/diagram_scale.py \
        --blocks N --case repeating|worst --out DIR [--timing-probe]

`--case repeating`: a GRE-like TR of 5 blocks (as `tests/synthetic.gre_sequence`: a
hard excitation pulse, a phase-encode trapezoid on y, a readout trapezoid on x with
an ADC, a spoiler on z, and a delay to fill the TR), repeated, with a phase-encode
table of 256 amplitudes (TR `i` uses entry `i mod 256`). The distinct event objects
are made once, before the loop, so the RF, gradient and ADC libraries stay small.

`--case worst`: the same TR, but with a shaped RF pulse (a 2 ms sinc) whose copy's
phase offset is new in every TR (the golden angle, so no two TRs repeat one), and a
phase-encode amplitude that is new in every TR (linearly spaced over all TRs, same
ramps and flat time as the `repeating` case's table, so only the amplitude differs).
The RF and gradient event libraries then grow with the number of TRs.

The script does not import `tests/synthetic.py`; it copies the pieces of `gre_sequence`
that it needs, so it has no dependency on the test suite.

It builds the sequence with exactly `--blocks` blocks, or the largest multiple of the
TR's block count (5) that is not more than `--blocks`, and says so on stdout when the
two differ. It writes `DIR/diagram-scale-<case>-<N>.html` (a one-card report page: the
diagram card only, for the "First ADC" and "Full sequence" windows) and
`DIR/diagram-scale-<case>-<N>.json` (the measurements below, pretty-printed; `N` is the
requested `--blocks`), and prints the JSON to stdout. It does not write a `.seq` file:
`diagram_card` takes the `pp.Sequence` directly, and at 10^7 blocks a `.seq` file is
about 390 MB (section 2.5 of the plan) for no purpose here.

Measurements (`time.perf_counter` for time; `resource.getrusage(...).ru_maxrss`,
converted to bytes by platform, for peak RSS, which is a running maximum since the
process started, not a delta):

- `build_s`, `build_peak_rss_bytes`: building the `pp.Sequence`.
- `card_s`, `card_peak_rss_bytes`: `diagram_card(...)` for the one file, with windows
  `[first_adc_window, full_window]`. This is the number that counts against the
  "Python time to make the card data" budget.
- `breakdown`: `diagram_tables`, `lane_meta` and `encode_tables` timed separately, by
  calling them once more after `card_s` is measured (so this adds extra work of its
  own; it does not change what `card_s` measures).
- `render_s`, `page_bytes`: `render_page(...)` for the one card, and the UTF-8 length
  of the result. This is the "page size added by the diagram card" (the page has no
  other card).
- `tables`: for each table, `dtype`, `length` and the byte length of its base64 `data`
  string, plus `tables_bytes_total`.
- `num_blocks`, `num_unique_rf`, `num_unique_grad`, `num_unique_adc`, `duration_s`: from
  the card data (the lengths of the `rf_delay`, `grad_delay` and `adc_delay` table
  entries are the number of unique RF, gradient and ADC events).
- `python_version`, `numpy_version`, `pypulseq_version`.

`--timing-probe` adds an extra script to the page (through `render_page`'s
`extra_scripts`) for a browser check of the "time from page open to first chart" and
"JavaScript memory after load" budgets: at the start of the script,
`window.__diagramProbe = {scriptStart: performance.now()}`, and a `MutationObserver` on
the `diagram-mode` element records `window.__diagramProbe.firstRender` the first time
its text stops being "Loading…", and `usedJSHeapSize` from `performance.memory` when it
exists. Extra scripts run before `page.js` (`render_page`'s docstring), so the observer
is in place before the card starts. The page subtitle says the probe is included.

If a "must be" value of section 2.6 fails, stop and tell the user; this script only
measures and reports, it does not judge.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import platform
import resource
import sys
import time
from pathlib import Path

import numpy as np
import pypulseq as pp

from pulseq_reports import diagram_data
from pulseq_reports.cards.diagram import diagram_card
from pulseq_reports.page import render_page
from pulseq_reports.seq_utils import NamedSequence
from pulseq_reports.waveforms import first_adc_window, full_window

# ---- Copied from tests/synthetic.py (this script must not import tests/) ----

SYSTEM = pp.Opts(
    max_grad=28,
    grad_unit="mT/m",
    max_slew=150,
    slew_unit="T/m/s",
    rf_ringdown_time=20e-6,
    rf_dead_time=100e-6,
    adc_dead_time=10e-6,
)
NUM_SAMPLES = 64
CENTER = NUM_SAMPLES // 2
DWELL = 20e-6  # s
WIDTH = 5e-3  # m, for the phase-encode areas in cycles across the width


def _block_pulse(use: str, flip: float):
    return pp.make_block_pulse(
        flip_angle=flip, duration=1e-3, delay=SYSTEM.rf_dead_time, system=SYSTEM, use=use
    )


def _readout():
    """Readout gradient on x and its ADC, as `tests/synthetic.readout` (the readout
    area is not needed here: this script does not use a prephaser)."""
    gx = pp.make_trapezoid(channel="x", flat_time=1.4e-3, flat_area=1000, system=SYSTEM)
    echo_offset = (CENTER + 0.5) * DWELL
    adc = pp.make_adc(
        num_samples=NUM_SAMPLES,
        dwell=DWELL,
        delay=round((gx.rise_time + gx.flat_time / 2 - echo_offset) * 1e6) * 1e-6,
        system=SYSTEM,
    )
    return gx, adc


# ---- The TR ----

TR_BLOCKS = 5  # rf, phase-encode, readout (gx + adc), spoiler, delay
PE_STEPS = 256  # the repeating case's phase-encode table
GOLDEN_ANGLE = 2.399963229728653  # rad; the worst case's RF phase step
RF_DURATION = 2e-3  # s; the worst case's shaped pulse
TR_MARGIN_S = 2e-3  # padding added to the busiest part of the TR, to fill it out


def _pe_family(amplitudes: np.ndarray) -> list:
    """Trapezoids on y with the ramps and the flat time of one area-based trapezoid,
    each with one of `amplitudes` (Hz/m) instead of that trapezoid's own amplitude: all
    have the same duration, and each amplitude is a distinct gradient event."""
    base = pp.make_trapezoid(channel="y", area=1 / WIDTH, system=SYSTEM)
    return [
        pp.make_trapezoid(
            channel="y",
            amplitude=float(amp),
            rise_time=base.rise_time,
            flat_time=base.flat_time,
            fall_time=base.fall_time,
            system=SYSTEM,
        )
        for amp in amplitudes
    ]


def _pe_max_amplitude() -> float:
    return float(pp.make_trapezoid(channel="y", area=1 / WIDTH, system=SYSTEM).amplitude)


def _progress(case: str, done: int, total: int, step: int) -> None:
    if done == total or done % step == 0:
        print(f"  {case}: {done}/{total} TRs ({100 * done / total:.0f}%)", file=sys.stderr)


def build_repeating(n_trs: int) -> pp.Sequence:
    """A GRE-like TR of 5 blocks, repeated `n_trs` times, with a phase-encode table of
    `PE_STEPS` amplitudes (TR `i` uses entry `i mod PE_STEPS`). The RF, readout, spoiler
    and delay events are each made once and reused, so their libraries stay at 1 entry;
    the phase-encode library stays at `min(PE_STEPS, n_trs)` entries."""
    seq = pp.Sequence(SYSTEM)
    rf = _block_pulse("excitation", math.radians(20))
    gx, adc = _readout()
    spoiler = pp.make_trapezoid(channel="z", area=4 / WIDTH, system=SYSTEM)
    pe_max = _pe_max_amplitude()
    pe_events = _pe_family(np.linspace(-pe_max, pe_max, min(PE_STEPS, n_trs)))
    used = (
        pp.calc_duration(rf)
        + pp.calc_duration(pe_events[0])
        + pp.calc_duration(gx, adc)
        + pp.calc_duration(spoiler)
    )
    delay = pp.make_delay(TR_MARGIN_S)
    step = max(1, n_trs // 10)
    for i in range(n_trs):
        seq.add_block(rf)
        seq.add_block(pe_events[i % len(pe_events)])
        seq.add_block(gx, adc)
        seq.add_block(spoiler)
        seq.add_block(delay)
        _progress("repeating", i + 1, n_trs, step)
    seq.set_definition("TR", used + TR_MARGIN_S)
    return seq


def build_worst(n_trs: int) -> pp.Sequence:
    """The same TR as `build_repeating`, but with a shaped RF pulse (a 2 ms sinc, made
    once; each TR uses a shallow copy with a new `phase_offset`, the golden angle times
    the TR index, so no two TRs repeat one) and a phase-encode amplitude that is new in
    every TR (linearly spaced over all `n_trs` TRs, so the RF and gradient libraries
    grow with the number of TRs). The readout, spoiler and delay are made once and
    reused, as in `build_repeating`."""
    seq = pp.Sequence(SYSTEM)
    rf_base = pp.make_sinc_pulse(
        flip_angle=math.radians(20),
        duration=RF_DURATION,
        delay=SYSTEM.rf_dead_time,
        system=SYSTEM,
        use="excitation",
    )
    gx, adc = _readout()
    spoiler = pp.make_trapezoid(channel="z", area=4 / WIDTH, system=SYSTEM)
    pe_max = _pe_max_amplitude()
    pe_amplitudes = np.linspace(-pe_max, pe_max, n_trs)
    pe_events = _pe_family(pe_amplitudes)
    used = (
        pp.calc_duration(rf_base)
        + pp.calc_duration(pe_events[0])
        + pp.calc_duration(gx, adc)
        + pp.calc_duration(spoiler)
    )
    delay = pp.make_delay(TR_MARGIN_S)
    step = max(1, n_trs // 10)
    for i in range(n_trs):
        rf = copy.copy(rf_base)
        rf.phase_offset = (i * GOLDEN_ANGLE) % (2 * math.pi)
        seq.add_block(rf)
        seq.add_block(pe_events[i])
        seq.add_block(gx, adc)
        seq.add_block(spoiler)
        seq.add_block(delay)
        _progress("worst", i + 1, n_trs, step)
    seq.set_definition("TR", used + TR_MARGIN_S)
    return seq


BUILDERS = {"repeating": build_repeating, "worst": build_worst}


# ---- Measurement ----


def _peak_rss_bytes() -> int:
    """The peak resident set size of this process so far (a running maximum, not a
    delta), in bytes: `ru_maxrss` is bytes on macOS and KiB on Linux."""
    ru_maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return ru_maxrss if sys.platform == "darwin" else ru_maxrss * 1024


def _table_stats(encoded_tables: dict[str, dict]) -> dict:
    tables = {
        name: {
            "dtype": entry["dtype"],
            "length": entry["length"],
            "data_bytes": len(entry["data"]),
        }
        for name, entry in encoded_tables.items()
    }
    total = sum(t["data_bytes"] for t in tables.values())
    return {"tables": tables, "tables_bytes_total": total}


def _timing_probe_script(card_id: str) -> str:
    return f"""
window.__diagramProbe = {{scriptStart: performance.now()}};
(function () {{
  var el = document.getElementById("{card_id}-mode");
  if (!el) return;
  var obs = new MutationObserver(function () {{
    if (el.textContent !== "Loading…" && !window.__diagramProbe.firstRender) {{
      window.__diagramProbe.firstRender = performance.now();
      if (window.performance && performance.memory) {{
        window.__diagramProbe.usedJSHeapSize = performance.memory.usedJSHeapSize;
      }}
      obs.disconnect();
    }}
  }});
  obs.observe(el, {{childList: true, characterData: true, subtree: true}});
}})();
""".strip()


def run(blocks: int, case: str, out_dir: Path, timing_probe: bool) -> dict:
    n_trs = blocks // TR_BLOCKS
    if n_trs < 1:
        raise ValueError(f"--blocks {blocks} is below one TR ({TR_BLOCKS} blocks)")
    effective_blocks = n_trs * TR_BLOCKS
    if effective_blocks != blocks:
        print(
            f"note: {blocks} blocks is not a multiple of {TR_BLOCKS}; "
            f"building {effective_blocks} blocks ({n_trs} TRs) instead",
            file=sys.stderr,
        )

    build_start = time.perf_counter()
    seq = BUILDERS[case](n_trs)
    build_s = time.perf_counter() - build_start
    build_peak_rss_bytes = _peak_rss_bytes()

    named = [NamedSequence(f"diagram-scale-{case}-{blocks}", seq)]
    windows = [first_adc_window(named), full_window(named)]

    card_start = time.perf_counter()
    card = diagram_card(named, windows, card_id="diagram")
    card_s = time.perf_counter() - card_start
    card_peak_rss_bytes = _peak_rss_bytes()

    # The breakdown: build the tables, the lane metadata and the encoded tables once
    # more, timed separately. This is extra work of its own; it does not change card_s.
    breakdown_start = time.perf_counter()
    tables_again = diagram_data.diagram_tables(seq)
    diagram_tables_s = time.perf_counter() - breakdown_start
    lane_meta_start = time.perf_counter()
    diagram_data.lane_meta(seq, tables_again)
    lane_meta_s = time.perf_counter() - lane_meta_start
    encode_start = time.perf_counter()
    diagram_data.encode_tables(tables_again)
    encode_tables_s = time.perf_counter() - encode_start

    file_entry = card.data["files"][0]
    num_unique_rf = file_entry["tables"]["rf_delay"]["length"]
    num_unique_grad = file_entry["tables"]["grad_delay"]["length"]
    num_unique_adc = file_entry["tables"]["adc_delay"]["length"]
    print(
        f"  {case}: {file_entry['num_blocks']} blocks, "
        f"{num_unique_rf} unique RF, {num_unique_grad} unique gradient, "
        f"{num_unique_adc} unique ADC events",
        file=sys.stderr,
    )

    subtitle = f"Scale check: case={case}, blocks={effective_blocks}."
    extra_scripts = []
    if timing_probe:
        subtitle += " Includes a browser timing probe (window.__diagramProbe)."
        extra_scripts.append(_timing_probe_script(card.id))

    render_start = time.perf_counter()
    page = render_page(f"Diagram scale check: {case}", subtitle, [card], extra_scripts)
    render_s = time.perf_counter() - render_start
    page_bytes = len(page.encode("utf-8"))

    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"diagram-scale-{case}-{blocks}.html"
    html_path.write_text(page, encoding="utf-8")

    result = {
        "case": case,
        "requested_blocks": blocks,
        "num_blocks": file_entry["num_blocks"],
        "num_trs": n_trs,
        "num_unique_rf": num_unique_rf,
        "num_unique_grad": num_unique_grad,
        "num_unique_adc": num_unique_adc,
        "duration_s": file_entry["duration_s"],
        "build_s": build_s,
        "build_peak_rss_bytes": build_peak_rss_bytes,
        "card_s": card_s,
        "card_peak_rss_bytes": card_peak_rss_bytes,
        "breakdown": {
            "diagram_tables_s": diagram_tables_s,
            "lane_meta_s": lane_meta_s,
            "encode_tables_s": encode_tables_s,
        },
        "render_s": render_s,
        "page_bytes": page_bytes,
        "timing_probe": timing_probe,
        "html_path": str(html_path),
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "pypulseq_version": pp.__version__,
        **_table_stats(file_entry["tables"]),
    }

    json_path = out_dir / f"diagram-scale-{case}-{blocks}.json"
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    result["json_path"] = str(json_path)
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--blocks", type=int, required=True, help="target number of blocks")
    parser.add_argument("--case", choices=sorted(BUILDERS), required=True)
    parser.add_argument("--out", type=Path, required=True, help="output directory")
    parser.add_argument(
        "--timing-probe",
        action="store_true",
        help="add the browser timing probe script to the page",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run(args.blocks, args.case, args.out, args.timing_probe)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
