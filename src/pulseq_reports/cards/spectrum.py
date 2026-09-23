"""Gradient spectrum card: the axis and RSS spectra against a gradient coil's acoustic
resonances."""

import html
from collections.abc import Sequence

import pypulseq as pp

from pulseq_reports.extensions import refuse_rotations
from pulseq_reports.grad_spectrum import (
    MAX_FREQUENCY_HZ,
    PRISMA_AS82_RESONANCES,
    WINDOW_S,
    AcousticResonance,
    GradientSpectrum,
    combine,
    gradient_spectrum,
)
from pulseq_reports.markup import (
    _AXIS_COLOR,
    Lane,
    _fmt,
    _lanes_json,
    _sig,
    _table,
    _zoom_controls,
)
from pulseq_reports.page import Card
from pulseq_reports.seq_utils import NamedSequence

_SPECTRUM_UNIT = "mT/m/√Hz"
_SPECTRUM_DB_FLOOR = -80  # the lowest value drawn on the spectrum's dB scale


def _spectrum_data(s: GradientSpectrum) -> dict:
    """`GradientSpectrum` as JSON-ready data, in Hz and mT/m/√Hz. All lanes share the RSS
    lane's value range."""
    out = {
        "reason": s.reason,
        "max_frequency_hz": MAX_FREQUENCY_HZ,
        "db_floor": _SPECTRUM_DB_FLOOR,
        "resonances": [
            {"frequency_hz": r.frequency_hz, "bandwidth_hz": r.bandwidth_hz} for r in s.resonances
        ],
        "lanes": [],
        "bands": [],
    }
    if s.reason is not None:
        return out

    peak = float(s.rss.max())
    if peak > 0:
        domain, ticks, labels = [0.0, 1.1 * peak], [0.0, peak], ["0", _fmt(peak)]
    else:
        domain, ticks, labels = [0.0, 1.0], [0.0], ["0"]
    series = [(f"g{a}", f"G{a}", _AXIS_COLOR[a], s.axes[a]) for a in "xyz"]
    series.append(("rss", "RSS", "ink-2", s.rss))
    out["lanes"] = _lanes_json(
        [
            Lane(
                id=lane_id,
                title=title,
                unit=_SPECTRUM_UNIT,
                color=color,
                segments=[
                    [[round(float(f), 3), _sig(float(v))] for f, v in zip(s.frequency_hz, values)]
                ],
                domain=domain,
                ticks=ticks,
                tick_labels=labels,
            )
            for lane_id, title, color, values in series
        ]
    )
    out["bands"] = [
        {
            "low_hz": b.resonance.low_hz,
            "high_hz": b.resonance.high_hz,
            "peak": _sig(b.peak),
            "peak_frequency_hz": round(b.frequency_hz, 3),
            "relative": round(b.relative, 4),
        }
        for b in s.band_peaks
    ]
    return out


def spectrum_data(
    seq: pp.Sequence, resonances: tuple[AcousticResonance, ...] = PRISMA_AS82_RESONANCES
) -> dict:
    """Gradient spectrum (`grad_spectrum.gradient_spectrum`) of one sequence, as
    JSON-ready data, in Hz and mT/m/√Hz (`_spectrum_data` of the result). With the
    default `resonances`, this is exactly the vb-pulseq `spectrum_data(seq)` data."""
    return _spectrum_data(gradient_spectrum(seq, resonances=resonances))


def _spectrum_html(spectrum: dict, scanner_label: str, card_id: str) -> str:
    """The body of the "Gradient spectrum" card: the band table, the chart and its
    explanation, or a note that there is no spectrum. `card_id` is used to build the
    chart element ids (`{card_id}-chart`, `{card_id}-diagram`, `{card_id}-tip`)."""
    if spectrum["reason"] is not None:
        return f'<p class="muted">No gradient spectrum: {html.escape(spectrum["reason"])}.</p>'

    table = _table(
        [
            f"{scanner_label} forbidden band (Hz)",
            f"Largest RSS in band ({_SPECTRUM_UNIT})",
            "At (Hz)",
            "Relative to spectrum peak",
        ],
        [
            [
                f"{b['low_hz']:g}–{b['high_hz']:g}",
                _fmt(b["peak"]),
                f"{b['peak_frequency_hz']:.0f}",
                f"{b['relative']:.3f}",
            ]
            for b in spectrum["bands"]
        ],
    )
    bands = ", ".join(f"{b['low_hz']:g}–{b['high_hz']:g} Hz" for b in spectrum["bands"])
    controls = (
        '<div class="controls" role="group" aria-label="Spectrum scale">'
        '<button type="button" data-scale="linear" aria-pressed="true">Linear</button>'
        '<button type="button" data-scale="db" aria-pressed="false">dB</button>'
        "</div>"
    )
    diagram_id = f"{card_id}-diagram"
    chart = (
        f'<div class="chart" id="{card_id}-chart">'
        f'<svg id="{diagram_id}" tabindex="0" role="img" aria-label="'
        + html.escape(
            f"Gradient spectrum: Gx, Gy, Gz and RSS against frequency, 0 to "
            f"{spectrum['max_frequency_hz']:g} Hz, with the {scanner_label} forbidden bands "
            f"{bands} shaded"
        )
        + f'"></svg><div class="tip" id="{card_id}-tip" hidden></div></div>'
    )
    band_text = " and ".join(
        f"{r['frequency_hz']:g} ± {r['bandwidth_hz'] / 2:g} Hz" for r in spectrum["resonances"]
    )
    window_ms = WINDOW_S * 1e3
    note = (
        '<p class="muted">The spectra use the method of pypulseq '
        f"<code>calculate_gradient_spectrum</code> over the whole sequence: {window_ms:g} ms "
        "Hann windows with 50% overlap, the magnitude spectrum (amplitude spectral density) of "
        "each window, and the maximum over windows. The gradients are padded with half a window "
        "of zeros at each end. RSS is the root-sum-of-squares of the three axes in each window. "
        "A band's largest value can be at its edge, from the tail of lower-frequency content. The red "
        f"bands are the acoustic resonances of the {scanner_label} gradient coil: "
        f"{band_text}. These are published values, not read from a scanner; "
        "check them against the gradient .asc file of the scanner you use. On the dB scale, "
        "each value is 20 log10 of its ratio to the largest RSS value, and values below "
        f"{_fmt(_SPECTRUM_DB_FLOOR)} dB are drawn at {_fmt(_SPECTRUM_DB_FLOOR)} dB. "
        "Click the chart to mark the centre for the zoom buttons. "
        "Drag across the chart to zoom to that range. Hold Shift and drag, or scroll "
        "sideways, to pan.</p>"
    )
    return table + controls + _zoom_controls(diagram_id) + chart + note


def spectrum_card(
    seqs: Sequence[NamedSequence],
    resonances: tuple[AcousticResonance, ...] = PRISMA_AS82_RESONANCES,
    scanner_label: str = "MAGNETOM Prisma (AS82)",
    card_id: str = "gradient-spectrum",
) -> Card:
    """The "Gradient spectrum" card: for one sequence, the body is
    `_spectrum_html(spectrum_data(seq, resonances), scanner_label, card_id)`.

    For more than one sequence, the data is the combined spectrum
    (`grad_spectrum.combine`) of each file's own spectrum: the element-wise maximum,
    at each frequency, over the files, with the band peaks recomputed from that
    maximum. The body then has an extra note that the spectrum is this maximum over
    the files, and that windows that would cross from one file to the next are not
    included (`grad_spectrum.combine` does not compute them).

    `data` is always the JSON-ready spectrum dict and `script` is always `"spectrum"`,
    even when there are no gradients, so the card script can still read `data.reason`.

    Raises `NotImplementedError` for a sequence with the rotation extension
    (`extensions.refuse_rotations`).
    """
    if not seqs:
        raise ValueError("spectrum_card needs at least one sequence")
    for named in seqs:
        refuse_rotations(named.seq)

    if len(seqs) == 1:
        data = spectrum_data(seqs[0].seq, resonances=resonances)
    else:
        spectra = [gradient_spectrum(named.seq, resonances=resonances) for named in seqs]
        data = _spectrum_data(combine(spectra))

    body = _spectrum_html(data, scanner_label, card_id)
    if len(seqs) > 1 and data["reason"] is None:
        body += (
            '<p class="muted">This chart is the maximum, at each frequency, over the files: '
            "windows that would cross from one file to the next are not included.</p>"
        )
    return Card(id=card_id, title="Gradient spectrum", body_html=body, data=data, script="spectrum")
