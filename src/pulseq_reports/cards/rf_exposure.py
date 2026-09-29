"""RF exposure card: B1 energy and B1+rms of one sequence."""

import pypulseq as pp

from pulseq_reports.markup import html_table
from pulseq_reports.page import Card
from pulseq_reports.rf_exposure import WINDOW_S, RfExposure, rf_exposure


def rf_exposure_data(seq: pp.Sequence, periodic: bool = True, window_s: float = WINDOW_S) -> dict:
    """RF exposure (`rf_exposure.rf_exposure`) as JSON-ready data, in ms and µT."""
    return _to_dict(rf_exposure(seq, window_s=window_s, periodic=periodic), periodic)


def _to_dict(e: RfExposure, periodic: bool) -> dict:
    return {
        "duration_ms": round(e.duration_s * 1e3, 4),
        "num_pulses": e.num_pulses,
        "peak_b1_ut": round(e.peak_b1_ut, 4),
        "peak_block": e.peak_block,
        "energy_ut2_ms": round(e.energy_ut2_s * 1e3, 4),
        "b1rms_ut": round(e.b1rms_ut, 4),
        "window_s": e.window_s,
        "b1rms_window_ut": round(e.b1rms_window_ut, 4),
        "window_used_s": e.window_used_s,
        "periodic": periodic,
    }


def _rf_exposure_html(exposure: dict) -> str:
    """The body of the "RF exposure" card for one sequence: the table and its
    explanation, or a note that the sequence has no RF pulses."""
    if exposure["num_pulses"] == 0:
        return '<p class="muted">No RF pulses.</p>'
    periodic = exposure["periodic"]
    b1rms_label = "B1+rms, sequence repeated (µT)" if periodic else "B1+rms, one pass (µT)"
    table = html_table(
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
    if periodic:
        note = (
            '<p class="muted">B1 comes from the RF amplitudes in the sequence, for the flip '
            "angles as written; the scanner scales them with the transmitter calibration. "
            "B1+rms treats the sequence as one period that repeats, for example one TR, so a "
            "window can include the end of one repetition and the start of the next. SAR in "
            "W/kg depends on the patient and the transmit coil, and the scanner computes it: "
            "compare B1+rms with the value that the scanner predicts.</p>"
        )
    else:
        note = (
            '<p class="muted">B1 comes from the RF amplitudes in the sequence, for the flip '
            "angles as written; the scanner scales them with the transmitter calibration. The "
            "sequence plays once, so B1+rms is the energy divided by the duration, and the "
            "highest-window search does not wrap past the end of the sequence. SAR in W/kg "
            "depends on the patient and the transmit coil, and the scanner computes it: compare "
            "B1+rms with the value that the scanner predicts.</p>"
        )
    return table + note


def rf_exposure_card(
    seq: pp.Sequence,
    *,
    periodic: bool = True,
    window_s: float = WINDOW_S,
    card_id: str = "rf-exposure",
) -> Card:
    """The "RF exposure" card: the body is `_rf_exposure_html(rf_exposure_data(seq))`."""
    exposure = rf_exposure(seq, window_s=window_s, periodic=periodic)
    return Card(
        id=card_id,
        title="RF exposure",
        body_html=_rf_exposure_html(_to_dict(exposure, periodic)),
    )
