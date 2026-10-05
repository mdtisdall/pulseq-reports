"""RF exposure card: B1 energy and B1+rms of one sequence."""

from collections.abc import Sequence

import pypulseq as pp

from pulseq_reports import options
from pulseq_reports.markup import gamma_select_html, html_table
from pulseq_reports.page import Card, card_asset
from pulseq_reports.registry import CardSpec, ReportContext
from pulseq_reports.rf_exposure import B1RMS_WINDOW_S, RfExposure, rf_exposure
from pulseq_reports.targets import ReportTarget
from pulseq_reports.units import gamma_entries


def _rf_exposure_data(
    seq: pp.Sequence,
    gamma: float,
    *,
    periodic: bool = True,
    b1rms_window_s: float = B1RMS_WINDOW_S,
) -> dict:
    """RF exposure (`rf_exposure.rf_exposure`, B1 for `gamma`, Hz/T) as JSON-ready data, in ms
    and µT."""
    return _to_dict(
        rf_exposure(seq, gamma, periodic=periodic, b1rms_window_s=b1rms_window_s), periodic
    )


def _to_dict(e: RfExposure, periodic: bool) -> dict:
    return {
        "duration_ms": round(e.duration_s * 1e3, 4),
        "num_pulses": e.num_pulses,
        "peak_b1_ut": round(e.peak_b1_ut, 4),
        "peak_block": e.peak_block,
        "energy_ut2_ms": round(e.energy_ut2_s * 1e3, 4),
        "b1rms_ut": round(e.b1rms_ut, 4),
        "window_s": e.b1rms_window_s,
        "b1rms_window_ut": round(e.b1rms_window_ut, 4),
        "window_used_s": e.b1rms_window_used_s,
        "periodic": periodic,
    }


def _table_html(exposure: dict) -> str:
    """The table of the "RF exposure" card for one gamma."""
    periodic = exposure["periodic"]
    b1rms_label = "B1+rms, sequence repeated (µT)" if periodic else "B1+rms, one pass (µT)"
    return html_table(
        ["Quantity", "Value"],
        [
            ["RF pulses", exposure["num_pulses"]],
            ["Peak B1 (µT)", f"{exposure['peak_b1_ut']:.2f} (block {exposure['peak_block']})"],
            ["∫B1² dt over the sequence (µT²·ms)", f"{exposure['energy_ut2_ms']:.1f}"],
            ["Sequence duration (ms)", f"{exposure['duration_ms']:g}"],
            [b1rms_label, f"{exposure['b1rms_ut']:.3f}"],
            [
                f"B1+rms, highest {exposure['window_used_s']:g} s window (µT)",
                f"{exposure['b1rms_window_ut']:.3f}",
            ],
        ],
    )


def _note_html(periodic: bool) -> str:
    """The explanation under the table (or the tables) of the card."""
    if periodic:
        return (
            '<p class="muted">B1 comes from the RF amplitudes in the sequence, for the flip '
            "angles as written; the scanner scales them with the transmitter calibration. "
            "B1+rms treats the sequence as one period that repeats, for example one TR, so a "
            "window can include the end of one repetition and the start of the next. SAR in "
            "W/kg depends on the patient and the transmit coil, and the scanner computes it: "
            "compare B1+rms with the value that the scanner predicts.</p>"
        )
    return (
        '<p class="muted">B1 comes from the RF amplitudes in the sequence, for the flip '
        "angles as written; the scanner scales them with the transmitter calibration. The "
        "sequence plays once, so B1+rms is the energy divided by the duration, and the "
        "highest-window search does not wrap past the end of the sequence. SAR in W/kg "
        "depends on the patient and the transmit coil, and the scanner computes it: compare "
        "B1+rms with the value that the scanner predicts.</p>"
    )


def rf_exposure_card(
    seq: pp.Sequence,
    *,
    periodic: bool = True,
    b1rms_window_s: float = B1RMS_WINDOW_S,
    targets: Sequence[ReportTarget] = (),
    card_id: str = "rf-exposure",
) -> Card:
    """The "RF exposure" card: the table of `_table_html` (or a note that the sequence has no
    RF pulses) and its explanation.

    B1 and the energy use |gamma| of one entry of `units.gamma_entries(targets, seq,
    signed=False)`. With one entry, the card has one table. With more than one (targets with
    different |gamma|), it has one table for each entry, each in an element with
    `data-gamma-entry` (the index of the entry; all but the first `hidden`), and, before the
    tables, the control of `markup.gamma_select_html` with the card script `gamma-select`.
    Without `targets`, the entry is `seq.system.gamma`. A sequence with no RF pulse has no
    table for a gamma, and no control."""
    entries = gamma_entries(targets, seq, signed=False)
    exposures = [
        _to_dict(
            rf_exposure(seq, entry.gamma, periodic=periodic, b1rms_window_s=b1rms_window_s),
            periodic,
        )
        for entry in entries
    ]
    if exposures[0]["num_pulses"] == 0:
        return Card(
            id=card_id,
            title="RF exposure",
            body_html='<p class="muted">No RF pulses.</p>',
        )
    control = gamma_select_html(entries, card_id)
    if control:
        tables = "\n".join(
            f'<div data-gamma-entry="{k}"{"" if k == 0 else " hidden"}>{_table_html(e)}</div>'
            for k, e in enumerate(exposures)
        )
        body = control + "\n" + tables + _note_html(periodic)
    else:
        body = _table_html(exposures[0]) + _note_html(periodic)
    return Card(
        id=card_id,
        title="RF exposure",
        body_html=body,
        script="gamma-select" if control else None,
        scripts=(card_asset("gamma-select"),) if control else (),
    )


def _build(ctx: ReportContext) -> Card:
    return rf_exposure_card(
        ctx.seq,
        periodic=ctx.option(options.periodic),
        b1rms_window_s=ctx.option(options.b1rms_window_s),
        targets=ctx.targets,
        card_id=SPEC.name,
    )


SPEC = CardSpec("rf-exposure", 20, _build, (options.periodic, options.b1rms_window_s))
