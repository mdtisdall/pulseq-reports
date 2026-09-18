"""RF exposure card: B1 energy and B1+rms over one or more sequences."""

import html
import math
from collections.abc import Sequence

import numpy as np
import pypulseq as pp

from pulseq_reports import rf_exposure as _rf_exposure
from pulseq_reports.markup import _table
from pulseq_reports.page import Card
from pulseq_reports.rf_exposure import WINDOW_S, RfExposure
from pulseq_reports.seq_utils import NamedSequence


def rf_exposure_data(seq: pp.Sequence, periodic: bool = True, window_s: float = WINDOW_S) -> dict:
    """RF exposure (`rf_exposure.rf_exposure`) as JSON-ready data, in ms and µT."""
    return _to_dict(_rf_exposure.rf_exposure(seq, window_s=window_s, periodic=periodic), periodic)


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
    table = _table(
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


def _all_files_html(data: dict) -> str:
    """The body of the "All files" section for more than one sequence."""
    if data["num_pulses"] == 0:
        return '<p class="muted">No RF pulses in any file.</p>'
    periodic = data["periodic"]
    b1rms_label = "B1+rms, files repeated (µT)" if periodic else "B1+rms, files played once (µT)"
    table = _table(
        ["Quantity", "Value"],
        [
            ["RF pulses (all files)", data["num_pulses"]],
            ["Peak B1 (µT)", f"{data['peak_b1_ut']:.2f}"],
            ["∫B1² dt over all files (µT²·ms)", f"{data['energy_ut2_ms']:.1f}"],
            ["Total duration (ms)", f"{data['duration_ms']:g}"],
            [b1rms_label, f"{data['b1rms_ut']:.3f}"],
            [
                f"B1+rms, highest {data['window_used_s']:g} s window (µT)",
                f"{data['b1rms_window_ut']:.3f}",
            ],
        ],
    )
    repeat_clause = " then that sequence repeated," if periodic else ""
    note = (
        '<p class="muted">"All files" assumes the files play one after another with no gap '
        f"between them,{repeat_clause} for B1+rms and the highest-window value; peak B1 is the "
        "maximum peak B1 of the individual files. B1 comes from the RF amplitudes in the "
        "sequence, for the flip angles as written; the scanner scales them with the transmitter "
        "calibration. SAR in W/kg depends on the patient and the transmit coil, and the scanner "
        "computes it: compare B1+rms with the value that the scanner predicts.</p>"
    )
    return table + note


def _combined_data(
    seqs: Sequence[NamedSequence], exposures: list[RfExposure], periodic: bool, window_s: float
) -> dict:
    """The "All files" data: the files played one after another with no gap, and, when
    `periodic` is True, that concatenation repeated."""
    total_duration = sum(e.duration_s for e in exposures)
    total_pulses = sum(e.num_pulses for e in exposures)
    peak_b1 = max((e.peak_b1_ut for e in exposures), default=0.0)
    total_energy = sum(e.energy_ut2_s for e in exposures)

    times_parts: list[np.ndarray] = []
    energy_parts: list[np.ndarray] = []
    offset = 0.0
    for named, exposure in zip(seqs, exposures):
        raster = named.seq.system.rf_raster_time
        times, energies, _duration, _peak_b1, _peak_block, _num_pulses = _rf_exposure._rf_samples(
            named.seq, raster
        )
        if times:
            times_parts.append(np.concatenate(times) + offset)
            energy_parts.append(np.concatenate(energies))
        offset += exposure.duration_s

    if total_pulses == 0 or total_duration <= 0:
        window_used = window_s if periodic else total_duration
        window_energy = 0.0
    else:
        combined_times = np.concatenate(times_parts)
        combined_energy = np.concatenate(energy_parts)
        window_used, window_energy = _rf_exposure._windowed_energy(
            combined_times, combined_energy, total_duration, window_s, periodic
        )
    b1rms = math.sqrt(total_energy / total_duration) if total_duration > 0 else 0.0
    b1rms_window = math.sqrt(window_energy / window_used) if window_used > 0 else 0.0

    return {
        "duration_ms": round(total_duration * 1e3, 4),
        "num_pulses": total_pulses,
        "peak_b1_ut": round(peak_b1, 4),
        "peak_block": None,
        "energy_ut2_ms": round(total_energy * 1e3, 4),
        "b1rms_ut": round(b1rms, 4),
        "window_s": window_s,
        "b1rms_window_ut": round(b1rms_window, 4),
        "window_used_s": window_used,
        "periodic": periodic,
    }


def rf_exposure_card(
    seqs: Sequence[NamedSequence],
    periodic: bool = True,
    window_s: float = WINDOW_S,
    card_id: str = "rf-exposure",
) -> Card:
    """The "RF exposure" card. For one sequence, the body is the same table and note as
    `_rf_exposure_html(rf_exposure_data(seq))`. For more than one sequence, the body has one
    table for each file, named by its file name, and then an "All files" table: peak B1 is
    the maximum over the files, and B1+rms and the highest-window value treat the files as
    played one after another with no gap (see `_combined_data`)."""
    if not seqs:
        raise ValueError("rf_exposure_card needs at least one sequence")

    if len(seqs) == 1:
        data = rf_exposure_data(seqs[0].seq, periodic=periodic, window_s=window_s)
        return Card(id=card_id, title="RF exposure", body_html=_rf_exposure_html(data))

    exposures = [
        _rf_exposure.rf_exposure(named.seq, window_s=window_s, periodic=periodic) for named in seqs
    ]
    sections = [
        f"<h3>{html.escape(named.name)}</h3>" + _rf_exposure_html(_to_dict(exposure, periodic))
        for named, exposure in zip(seqs, exposures)
    ]
    all_files = _combined_data(seqs, exposures, periodic, window_s)
    body = "\n".join(sections) + "<h3>All files</h3>" + _all_files_html(all_files)
    return Card(id=card_id, title="RF exposure", body_html=body)
